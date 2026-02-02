import asyncio
import logging
import json
import os
from datetime import datetime, timezone
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import POLYGON
from config import config

import aiofiles

logger = logging.getLogger(__name__)

class Executor:
    """Trade Execution Engine"""
    def __init__(self, positions_file="positions.json"):
        self.client = self._init_client()
        self.positions_file = positions_file
        self.positions = self._load_positions()
        self.paper_trade = config.get("paper_trade", True)
        
    def _init_client(self):
        key = config.get("PRIVATE_KEY")
        if not key or self.paper_trade:
            return None
        try:
            host = "https://clob.polymarket.com"
            chain_id = POLYGON
            client = ClobClient(host, key=key, chain_id=chain_id)
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
            async with aiofiles.open(self.positions_file, "w") as f:
                data = json.dumps({
                    "positions": self.positions, 
                    "updated": datetime.now(timezone.utc).isoformat()
                })
                await f.write(data)
        except Exception as e:
            logger.error(f"Save positions failed: {e}")
            
    async def place_order(self, market_slug, direction, token_id, price, size_usd):
        """Place order with tracking"""
        price = round(price, 2)
        shares = round(size_usd / price, 4)
        
        logger.info(f"🚀 Placing order: {direction} {shares} @ {price}")
        
        if self.paper_trade:
            # Simulate fill
            position = {
                "market_slug": market_slug,
                "direction": direction,
                "entry_price": price,
                "shares": shares,
                "status": "OPEN",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.positions.append(position)
            await self.save_positions()
            return True
            
        # Live Trading
        if not self.client: return False
        
        try:
            order_args = OrderArgs(
                price=price,
                size=shares,
                side="BUY",
                token_id=token_id
            )
            resp = self.client.create_and_post_order(order_args)
            
            if resp and resp.get("success") and resp.get("orderID"):
                order_id = resp["orderID"]
                position = {
                    "market_slug": market_slug,
                    "direction": direction,
                    "entry_price": price,
                    "shares": shares,
                    "status": "PENDING",
                    "order_id": order_id,
                    "token_id": token_id, # [Fix] Store Token ID for closing
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                self.positions.append(position)
                await self.save_positions()
                
                # Start tracking
                asyncio.create_task(self._track_order(order_id, position))
                return True
            else:
                logger.error(f"Order failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Order exception: {e}")
            return False
            
    async def close_position(self, position, price):
        """Close position (Sell)"""
        logger.info(f"📉 Closing position: {position['direction']} @ {price}")
        
        if self.paper_trade:
            # Simulate sell
            if position in self.positions:
                self.positions.remove(position)
                await self.save_positions()
                logger.info("✅ Position closed (Paper)")
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
            
            if resp and resp.get("success") and resp.get("orderID"):
                logger.info(f"✅ Close order placed: {resp['orderID']}")
                # We could track this exit order too, but for simplicity just assume
                # Or better: track it. For V4 MVP, let's remove position optimistically or mark 'CLOSING'
                # Best practice: Mark CLOSING, track order.
                if position in self.positions:
                    self.positions.remove(position) # Simple exit
                    await self.save_positions()
                return True
            else:
                logger.error(f"Close failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Close exception: {e}")
            return False
            
    async def _track_order(self, order_id, position):
        """Track order with P0 fixes"""
        max_wait = 5  # 5s timeout
        check_interval = 1
        
        for _ in range(0, max_wait, check_interval):
            try:
                order = self.client.get_order(order_id)
                if order and order.get("status") == "FILLED":
                    position["status"] = "OPEN"
                    position["entry_price"] = float(order.get("avg_price", position["entry_price"]))
                    position["shares"] = float(order.get("size", position["shares"]))
                    await self.save_positions()
                    logger.info(f"✅ Order filled: {order_id}")
                    return
            except Exception as e:
                logger.warning(f"Track error: {e}")
            await asyncio.sleep(check_interval)
            
        # Timeout handling
        try:
            final = self.client.get_order(order_id)
            if final and final.get("status") == "FILLED":
                position["status"] = "OPEN"
                await self.save_positions()
                return
        except: pass
        
        # Cancel and cleanup
        try:
            self.client.cancel(order_id)
            if position in self.positions:
                self.positions.remove(position)
                await self.save_positions()
            logger.info(f"🗑️ Order timed out and cancelled: {order_id}")
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
