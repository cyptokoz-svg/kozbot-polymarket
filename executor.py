import asyncio
import logging
import json
import os
import time
from datetime import datetime, timezone
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import POLYGON
from config import config
from api_client import request as http_request
from py_builder_signing_sdk.config import BuilderConfig
from validators import validate_price, validate_size, validate_token_id, ValidationError

try:
    import aiofiles
    _AIOFILES_AVAILABLE = True
except Exception:
    aiofiles = None
    _AIOFILES_AVAILABLE = False

logger = logging.getLogger(__name__)
TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.jsonl")

class Executor:
    """Trade Execution Engine"""
    def __init__(self, positions_file="positions.json"):
        self.client = self._init_client()
        self.positions_file = positions_file
        self.positions = self._load_positions()
        self.paper_trade = config.get("paper_trade", True)
        self.execution_enabled = bool(config.get("execution_enabled", False) or config.get("live_trading_enabled", False))
        self._synced = False
        self._funder = config.get("FUNDER_ADDRESS")
        self._last_order_refresh = 0.0
        
    def _init_client(self):
        key = config.get("PRIVATE_KEY")
        if not key or self.paper_trade:
            return None
        try:
            host = "https://clob.polymarket.com"
            chain_id = POLYGON
            funder = config.get("FUNDER_ADDRESS")
            
            # Init Builder Config
            builder_config = None
            b_key = config.get("POLY_BUILDER_API_KEY")
            b_secret = config.get("POLY_BUILDER_API_SECRET")
            b_pass = config.get("POLY_BUILDER_API_PASSPHRASE")
            
            if b_key and b_secret and b_pass:
                try:
                    builder_config = BuilderConfig(
                        api_key=b_key,
                        api_secret=b_secret,
                        api_passphrase=b_pass
                    )
                    logger.info("✅ Builder API enabled")
                except Exception as be:
                    logger.warning(f"Builder Config failed: {be}")

            if funder:
                client = ClobClient(
                    host, 
                    key=key, 
                    chain_id=chain_id, 
                    signature_type=2, 
                    funder=funder,
                    builder_config=builder_config
                )
                client.set_api_creds(client.create_or_derive_api_creds())
            else:
                client = ClobClient(
                    host, 
                    key=key, 
                    chain_id=chain_id,
                    builder_config=builder_config
                )
                client.set_api_creds(client.derive_api_key())
            return client
        except Exception as e:
            logger.error(f"Failed to init CLOB client: {e}")
            return None
            
    def _load_positions(self):
        if os.path.exists(self.positions_file):
            try:
                with open(self.positions_file, "r") as f:
                    data = json.load(f)
                    return data.get("positions", [])
            except: pass
        return []
        
    async def save_positions(self):
        """Save positions asynchronously"""
        try:
            data = json.dumps({
                "positions": self.positions,
                "updated": datetime.now(timezone.utc).isoformat()
            })
            if _AIOFILES_AVAILABLE:
                async with aiofiles.open(self.positions_file, "w") as f:
                    await f.write(data)
            else:
                await asyncio.to_thread(self._write_file, self.positions_file, data, "w")
        except Exception as e:
            logger.error(f"Save positions failed: {e}")

    async def _append_trade_log(self, record: dict):
        try:
            line = json.dumps(record) + "\n"
            if _AIOFILES_AVAILABLE:
                async with aiofiles.open(TRADES_FILE, "a") as f:
                    await f.write(line)
            else:
                await asyncio.to_thread(self._write_file, TRADES_FILE, line, "a")
        except Exception as e:
            logger.error(f"Trade log failed: {e}")

    def _write_file(self, path: str, data: str, mode: str):
        with open(path, mode) as f:
            f.write(data)

    def _extract_float(self, data: dict, keys, default=0.0):
        for key in keys:
            if key in data and data[key] is not None:
                try:
                    return float(data[key])
                except Exception:
                    continue
        return default

    def _extract_filled_size(self, order: dict) -> float:
        return self._extract_float(
            order,
            [
                "filled_size",
                "filledSize",
                "filled_amount",
                "filledAmount",
                "maker_amount",
                "makerAmount",
                "filled_size_base",
                "filledSizeBase",
            ],
            default=0.0,
        )

    def _extract_avg_price(self, order: dict, fallback: float) -> float:
        return self._extract_float(
            order,
            ["avg_price", "avgPrice", "average_price", "averagePrice"],
            default=fallback,
        )

    def _extract_order_id(self, resp: dict):
        if not isinstance(resp, dict):
            return None
        return (
            resp.get("orderID")
            or resp.get("orderId")
            or resp.get("order_id")
            or resp.get("id")
        )

    def _parse_timestamp(self, value):
        if not value:
            return None
        try:
            if isinstance(value, (int, float)):
                ts = float(value)
                if ts > 1e12:
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts, timezone.utc)
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
        return None

    def _match_recent_order(self, orders, token_id, side, price, shares):
        candidates = []
        for order in orders or []:
            order_id = self._extract_order_id(order)
            if not order_id:
                continue
            if token_id:
                order_token = order.get("token_id") or order.get("tokenId") or order.get("asset_id")
                if order_token and str(order_token) != str(token_id):
                    continue
            if side:
                order_side = str(order.get("side", "")).upper()
                if order_side and order_side != str(side).upper():
                    continue
            order_price = self._extract_float(order, ["price"], None)
            if order_price is not None and abs(order_price - price) > 0.02:
                continue
            order_size = self._extract_float(order, ["size", "amount", "qty", "quantity"], None)
            if order_size is not None and abs(order_size - shares) > max(0.0001, shares * 0.02):
                continue
            created_at = self._parse_timestamp(order.get("created_at") or order.get("timestamp"))
            candidates.append((created_at, order_id))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return candidates[0][1]

    async def _recover_order_id(self, token_id, side, price, shares):
        if self.paper_trade or not self.client:
            return None
        max_wait = float(config.get("order_id_recovery_sec", 3))
        interval = 0.5
        deadline = asyncio.get_running_loop().time() + max_wait
        statuses = ["PENDING", "OPEN", "PARTIALLY_FILLED"]
        while asyncio.get_running_loop().time() < deadline:
            for status in statuses:
                try:
                    orders = self.client.get_orders(status=status) or []
                except Exception:
                    orders = []
                order_id = self._match_recent_order(orders, token_id, side, price, shares)
                if order_id:
                    return order_id
            try:
                orders = self.client.get_orders() or []
                order_id = self._match_recent_order(orders, token_id, side, price, shares)
                if order_id:
                    return order_id
            except Exception:
                pass
            await asyncio.sleep(interval)
        return None

    def _position_key(self, pos: dict) -> str:
        if not isinstance(pos, dict):
            return ""
        order_id = pos.get("order_id")
        if order_id:
            return f"order:{order_id}"
        token_id = pos.get("token_id")
        if token_id:
            return f"token:{token_id}"
        condition_id = pos.get("condition_id")
        direction = pos.get("direction")
        if condition_id and direction:
            return f"cond:{condition_id}:{direction}"
        return ""

    def _map_outcome_to_direction(self, outcome: str) -> str:
        if not outcome:
            return "UNKNOWN"
        label = str(outcome).lower()
        if any(k in label for k in ["up", "yes", "higher", "above", "increase", "bull"]):
            return "UP"
        if any(k in label for k in ["down", "no", "lower", "below", "decrease", "bear"]):
            return "DOWN"
        return str(outcome).upper()

    async def sync_exchange_state(self):
        """Sync open orders and positions from exchange on startup"""
        if self._synced or self.paper_trade or not self.client:
            return
        existing = {self._position_key(p) for p in self.positions if self._position_key(p)}
        updated = False

        # 1) Sync open orders
        orders = []
        try:
            orders = self.client.get_orders(status="OPEN") or []
        except Exception:
            try:
                orders = self.client.get_orders() or []
            except Exception as e:
                logger.warning(f"Order sync failed: {e}")
        for order in orders:
            status = str(order.get("status", "")).upper()
            if status not in ("OPEN", "PARTIALLY_FILLED", "PENDING"):
                continue
            order_id = self._extract_order_id(order)
            if not order_id:
                continue
            key = f"order:{order_id}"
            if key in existing:
                continue
            token_id = order.get("token_id") or order.get("tokenId") or order.get("asset_id")
            filled_size = self._extract_filled_size(order)
            avg_price = self._extract_avg_price(order, self._extract_float(order, ["price"], 0.0))
            size = self._extract_float(order, ["size", "amount", "qty", "quantity"], 0.0)
            position = {
                "market_slug": order.get("market") or order.get("market_slug") or "",
                "direction": order.get("side", ""),
                "entry_price": avg_price,
                "shares": filled_size if filled_size > 0 else size,
                "status": "PARTIALLY_FILLED" if filled_size > 0 else "OPEN_ORDER",
                "order_id": order_id,
                "token_id": token_id,
                "timestamp": order.get("created_at") or order.get("timestamp") or ""
            }
            self.positions.append(position)
            existing.add(key)
            updated = True

        # 2) Sync open positions (Data API)
        if self._funder:
            try:
                resp = await http_request(
                    "GET",
                    "https://data-api.polymarket.com/positions",
                    params={"user": self._funder.lower()},
                    timeout=15
                )
                if resp.status_code == 200:
                    positions = resp.json()
                else:
                    positions = []
            except Exception as e:
                logger.warning(f"Position sync failed: {e}")
                positions = []
            for pos in positions or []:
                size = float(pos.get("size", 0) or 0)
                if size <= 0:
                    continue
                condition_id = pos.get("conditionId") or pos.get("condition_id")
                outcome = pos.get("outcome", "")
                direction = self._map_outcome_to_direction(outcome)
                token_id = pos.get("tokenId") or pos.get("token_id")
                entry_price = self._extract_float(pos, ["avgPrice", "avg_price", "averagePrice", "average_price", "price"], 0.0)
                market_obj = pos.get("market") or {}
                market_slug = market_obj.get("slug") if isinstance(market_obj, dict) else pos.get("market_slug", "")

                # If token_id missing, resolve from Gamma market
                if condition_id and not token_id:
                    try:
                        from data_source import PolyMarketData
                        market = await PolyMarketData.get_market_by_condition(condition_id)
                        if market:
                            token_up, token_down = PolyMarketData.resolve_token_ids(market)
                            token_id = token_up if direction == "UP" else token_down
                            market_slug = market_slug or market.get("slug", "")
                    except Exception:
                        pass

                key = f"cond:{condition_id}:{direction}" if condition_id and direction else ""
                if key and key in existing:
                    continue
                position = {
                    "market_slug": market_slug or "",
                    "direction": direction,
                    "entry_price": entry_price,
                    "shares": size,
                    "status": "OPEN",
                    "token_id": token_id,
                    "condition_id": condition_id,
                    "timestamp": pos.get("timestamp") or ""
                }
                self.positions.append(position)
                if key:
                    existing.add(key)
                updated = True

        if updated:
            await self.save_positions()
        self._synced = True

    async def refresh_pending_orders(self):
        """Refresh pending/open orders from exchange"""
        if self.paper_trade or not self.client:
            return
        refresh_sec = float(config.get("order_refresh_sec", 0) or 0)
        now = time.time()
        if refresh_sec > 0 and (now - self._last_order_refresh) < refresh_sec:
            return
        self._last_order_refresh = now
        updated = False
        to_remove = []
        for pos in list(self.positions):
            status = (pos.get("status") or "").upper()
            if status not in ("PENDING", "OPEN_ORDER", "PARTIALLY_FILLED"):
                continue
            order_id = pos.get("order_id")
            if not order_id:
                continue
            try:
                order = self.client.get_order(order_id)
                if not order:
                    continue
                order_status = str(order.get("status", "")).upper()
                filled_size = self._extract_filled_size(order)
                avg_price = self._extract_avg_price(order, pos.get("entry_price", 0) or 0)
                if order_status in ("FILLED", "MATCHED"):
                    pos["status"] = "OPEN"
                    pos["entry_price"] = avg_price
                    pos["shares"] = float(order.get("size", pos.get("shares", 0)) or 0)
                    updated = True
                    logger.info(f"✅ Order filled: {order_id}")
                elif order_status in ("CANCELED", "CANCELLED", "REJECTED", "EXPIRED"):
                    if filled_size > 0:
                        pos["status"] = "OPEN"
                        pos["entry_price"] = avg_price
                        pos["shares"] = filled_size
                        updated = True
                        logger.info(f"✅ Order partially filled: {order_id} ({filled_size})")
                    else:
                        to_remove.append(pos)
                        updated = True
                elif order_status in ("OPEN", "PARTIALLY_FILLED", "PENDING"):
                    pos["status"] = "PARTIALLY_FILLED" if order_status == "PARTIALLY_FILLED" else "OPEN_ORDER"
                    if filled_size > 0:
                        pos["shares"] = max(pos.get("shares", 0) or 0, filled_size)
                        pos["entry_price"] = avg_price
                    updated = True
            except Exception as e:
                logger.warning(f"Refresh order failed: {e}")
        if to_remove:
            for pos in to_remove:
                if pos in self.positions:
                    self.positions.remove(pos)
        if updated:
            await self.save_positions()
            
    async def place_order(self, market_slug, direction, token_id, price, size_usd, condition_id=None):
        """Place order with tracking and validation"""
        # Validate inputs
        try:
            price = validate_price(price, "order_price")
            token_id = validate_token_id(token_id)
            if size_usd <= 0:
                raise ValidationError(f"size_usd must be > 0, got {size_usd}")
        except ValidationError as e:
            logger.error(f"❌ Order validation failed: {e}")
            return False
        
        shares = round(size_usd / price, 4)
        
        try:
            shares = validate_size(shares)
        except ValidationError as e:
            logger.error(f"❌ Share validation failed: {e}")
            return False
        
        logger.info(f"🚀 Placing order: {direction} {shares} @ {price}")
        
        if self.paper_trade:
            # Simulate fill
            position = {
                "market_slug": market_slug,
                "direction": direction,
                "entry_price": price,
                "shares": shares,
                "status": "OPEN",
                "token_id": token_id,
                "condition_id": condition_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.positions.append(position)
            await self.save_positions()
            return True
            
        # Live Trading
        if not self.execution_enabled:
            logger.warning("⚠️ Live trading is disabled (set execution_enabled or live_trading_enabled to true)")
            return False
        if not self.client: return False
        
        try:
            order_args = OrderArgs(
                price=price,
                size=shares,
                side="BUY",
                token_id=token_id
            )
            resp = self.client.create_and_post_order(order_args)
            order_id = self._extract_order_id(resp or {})

            if not order_id:
                logger.warning(f"Order response missing order_id: {resp}")
                order_id = await self._recover_order_id(token_id, "BUY", price, shares)
            
            if order_id:
                position = {
                    "market_slug": market_slug,
                    "direction": direction,
                    "entry_price": price,
                    "shares": shares,
                    "status": "PENDING",
                    "order_id": order_id,
                    "token_id": token_id, # [Fix] Store Token ID for closing
                    "condition_id": condition_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                self.positions.append(position)
                await self.save_positions()
                
                # Start tracking
                asyncio.create_task(self._track_order(order_id, position))
                return True
            else:
                if isinstance(resp, dict) and resp.get("success"):
                    logger.error(f"Order placed but no order_id in response: {resp}")
                else:
                    logger.error(f"Order failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Order exception: {e}")
            return False
            
    async def close_position(self, position, price, reason=None):
        """Close position (Sell) with validation"""
        # Validate price
        try:
            price = validate_price(price, "exit_price")
        except ValidationError as e:
            logger.error(f"❌ Close price validation failed: {e}")
            return False
        
        logger.info(f"📉 Closing position: {position['direction']} @ {price}")
        entry_price = position.get("entry_price") or 0
        pnl_pct = (price - entry_price) / entry_price if entry_price else 0.0
        trade_type = reason or "CLOSE"
        if self.paper_trade:
            trade_type = f"{trade_type}_PAPER"
        
        if self.paper_trade:
            # Simulate sell
            if position in self.positions:
                self.positions.remove(position)
                await self.save_positions()
                logger.info("✅ Position closed (Paper)")
            await self._append_trade_log({
                "time": datetime.now(timezone.utc).isoformat(),
                "market": position.get("market_slug", ""),
                "direction": position.get("direction", ""),
                "condition_id": position.get("condition_id"),
                "entry_price": entry_price,
                "exit_price": price,
                "pnl": pnl_pct,
                "type": trade_type
            })
            return True
            
        # Live Trading
        if not self.client: return False
        
        try:
            # Determine Token ID from position or lookup
            # Position should store token_id, but if not we need to pass it
            # For now assuming we can get it from market data in main loop or stored in pos
            token_id = position.get("token_id")
            if not token_id:
                logger.error("❌ Cannot close: Missing token_id in position")
                return False

            order_args = OrderArgs(
                price=price,
                size=position["shares"],
                side="SELL",
                token_id=token_id
            )
            resp = self.client.create_and_post_order(order_args)
            order_id = self._extract_order_id(resp or {})

            if not order_id:
                logger.warning(f"Close response missing order_id: {resp}")
                order_id = await self._recover_order_id(token_id, "SELL", price, position["shares"])

            if order_id:
                logger.info(f"✅ Close order placed: {order_id}")
                position["status"] = "CLOSING"
                position["close_order_id"] = order_id
                if position in self.positions:
                    await self.save_positions()
                asyncio.create_task(self._track_close_order(order_id, position))
                await self._append_trade_log({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "market": position.get("market_slug", ""),
                    "direction": position.get("direction", ""),
                    "condition_id": position.get("condition_id"),
                    "entry_price": entry_price,
                    "exit_price": price,
                    "pnl": pnl_pct,
                    "type": trade_type
                })
                return True
            else:
                logger.error(f"Close failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Close exception: {e}")
            return False
            
    async def _track_order(self, order_id, position):
        """Track order with P0 fixes"""
        max_wait = int(config.get("order_timeout_sec", 5))
        check_interval = 1
        
        for _ in range(0, max_wait, check_interval):
            try:
                order = self.client.get_order(order_id)
                if order:
                    status = str(order.get("status", "")).upper()
                    if status in ("FILLED", "MATCHED"):
                        position["status"] = "OPEN"
                        position["entry_price"] = self._extract_avg_price(order, position.get("entry_price", 0) or 0)
                        filled_size = self._extract_filled_size(order)
                        position["shares"] = filled_size if filled_size > 0 else float(order.get("size", position["shares"]) or 0)
                        await self.save_positions()
                        logger.info(f"✅ Order filled: {order_id}")
                        return
                    if status in ("CANCELED", "CANCELLED", "REJECTED", "EXPIRED"):
                        if position in self.positions:
                            self.positions.remove(position)
                            await self.save_positions()
                        logger.info(f"🗑️ Order closed: {order_id} ({status})")
                        return
            except Exception as e:
                logger.warning(f"Track error: {e}")
            await asyncio.sleep(check_interval)
            
        # Timeout handling
        try:
            final = self.client.get_order(order_id)
            if final:
                final_status = str(final.get("status", "")).upper()
                if final_status in ("FILLED", "MATCHED"):
                    position["status"] = "OPEN"
                    position["entry_price"] = self._extract_avg_price(final, position.get("entry_price", 0) or 0)
                    filled_size = self._extract_filled_size(final)
                    position["shares"] = filled_size if filled_size > 0 else float(final.get("size", position["shares"]) or 0)
                    await self.save_positions()
                    return
                if final_status in ("CANCELED", "CANCELLED", "REJECTED", "EXPIRED"):
                    if position in self.positions:
                        self.positions.remove(position)
                        await self.save_positions()
                    return
        except: pass
        
        # Mark as open order after timeout
        if position in self.positions:
            position["status"] = "OPEN_ORDER"
            await self.save_positions()

        if config.get("cancel_unfilled_orders", False):
            # Cancel and cleanup (preserve partial fills)
            try:
                order = self.client.get_order(order_id)
                filled_size = self._extract_filled_size(order or {})
                avg_price = self._extract_avg_price(order or {}, position.get("entry_price", 0) or 0)
                self.client.cancel(order_id)
                if filled_size > 0:
                    position["status"] = "OPEN"
                    position["shares"] = filled_size
                    position["entry_price"] = avg_price
                    await self.save_positions()
                    logger.info(f"🗑️ Order cancelled, kept partial fill: {order_id}")
                else:
                    if position in self.positions:
                        self.positions.remove(position)
                        await self.save_positions()
                    logger.info(f"🗑️ Order timed out and cancelled: {order_id}")
            except Exception as e:
                logger.error(f"Cancel failed: {e}")

    async def _track_close_order(self, order_id, position):
        """Track close (SELL) order and remove position on fill"""
        max_wait = int(config.get("order_timeout_sec", 5))
        check_interval = 1

        for _ in range(0, max_wait, check_interval):
            try:
                order = self.client.get_order(order_id)
                if order:
                    status = str(order.get("status", "")).upper()
                    if status in ("FILLED", "MATCHED"):
                        if position in self.positions:
                            self.positions.remove(position)
                            await self.save_positions()
                        logger.info(f"✅ Close order filled: {order_id}")
                        return
                    if status in ("CANCELED", "CANCELLED", "REJECTED", "EXPIRED"):
                        position["status"] = "OPEN"
                        position.pop("close_order_id", None)
                        await self.save_positions()
                        logger.info(f"🗑️ Close order failed: {order_id} ({status})")
                        return
            except Exception as e:
                logger.warning(f"Track close error: {e}")
            await asyncio.sleep(check_interval)

        # On timeout, mark as open again
        # On timeout, mark as open again
        position["status"] = "OPEN"
        position.pop("close_order_id", None)
        await self.save_positions()

    async def redeem_market(self, condition_id):
        """Redeem winnings for a condition (Gasless)"""
        if self.paper_trade or not self.client:
            return False
        
        try:
            logger.info(f"💰 Attempting to redeem unused positions for {condition_id}...")
            # Using py_clob_client's exchange wrapper
            resp = await asyncio.to_thread(self.client.exchange.redeem_positions, condition_id=condition_id)
            logger.info(f"✅ Redeem Transaction Sent! TX: {resp}")
            return True
        except Exception as e:
            if "no tokens" in str(e).lower() or "nothing to redeem" in str(e).lower():
                logger.info(f"ℹ️ Nothing to redeem for {condition_id}")
            else:
                logger.error(f"❌ Redeem failed for {condition_id}: {e}")
            return False

    async def auto_redeem_positions(self):
        """Periodically check and redeem winning positions"""
        if self.paper_trade: return
        
        # Group by condition_id
        conditions = set()
        for pos in self.positions:
            if pos.get("condition_id"):
                conditions.add(pos["condition_id"])
        
        from data_source import PolyMarketData
        
        for cond_id in conditions:
            # Check if market is resolved/closed
            # This is a bit expensive so we only do it if we have positions?
            # Actually, just try to redeem occasionally is safer/easier than checking status perfectly
            # But rate limits?
            # Let's assume this is called infrequently (e.g. every hour or on startup)
            await self.redeem_market(cond_id)

