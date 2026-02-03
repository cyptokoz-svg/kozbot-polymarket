import asyncio
import logging
import signal
import sys
import os
import argparse
import json

# Fix import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone

from config import config
from data_source import BinanceData, PolyMarketData
from websocket_client import MarketWebSocket
from risk_manager import RiskManager
from executor import Executor
try:
    from strategy import Strategy
except Exception:
    Strategy = None
from notification import notifier
from constants import MIN_LOOP_INTERVAL, MARKET_INTERVAL_SECONDS

# Import TUI
from tui import BotTUI
from rich.live import Live

# Configure logging to file only (to not mess up TUI)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='bot_v4.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

class PolymarketBotV4:
    def __init__(self, dry_run: bool = False):
        self.tui = BotTUI()
        self.tui.add_log("🔍 Validating configuration...")
        logger.info("🔍 Validating configuration...")
        
        try:
            config.validate_config()
        except ValueError as e:
            msg = f"❌ Configuration validation failed: {e}"
            self.tui.add_log(msg)
            logger.error(msg)
            raise
        
        self.running = True
        self.risk_manager = RiskManager()
        self.executor = Executor()
        self.dry_run = dry_run
        if Strategy is None:
            self.tui.add_log("⚠️ Strategy module missing")
            self.strategy = None
        else:
            self.strategy = Strategy(
                min_edge=config.get("min_edge", 0.08),
                safety_margin_pct=config.get("safety_margin_pct", 0.0006)
            )
        self.ws_manager = None
        
        
        # Graceful Shutdown
        # signal.signal(signal.SIGINT, self.stop) # Disable to allow asyncio to handle KeyboardInterrupt
        # signal.signal(signal.SIGTERM, self.stop)
        
    def stop(self, signum=None, frame=None):
        self.tui.add_log("🛑 Stopping Bot...")
        logger.info("🛑 Stopping Bot...")
        self.running = False
        notifier.send("🛑 Bot stopping...")
        
    async def find_active_market(self):
        """Find the active 15m BTC market that is still within trading window"""
        self.tui.update_state(status="Searching Market...")
        try:
            from datetime import datetime, timezone, timedelta
            
            # Fetch events from Gamma API
            params = {"active": False, "closed": False, "limit": 50}
            markets = await PolyMarketData.fetch_markets(params)
            
            now = datetime.now(timezone.utc)
            ts = int(now.timestamp())
            current_slot_ts = ts - (ts % 900)
            
            # STRATEGY A: Deterministic
            slots_to_check = [current_slot_ts, current_slot_ts - 900]
            for slot_ts in slots_to_check:
                target_slug = f"btc-updown-15m-{slot_ts}"
                m = await PolyMarketData.get_market(target_slug)
                if m and not m.get("closed"):
                    try:
                        market_start = datetime.fromtimestamp(slot_ts, timezone.utc)
                        market_end = market_start + timedelta(minutes=15)
                        time_since_start = (now - market_start).total_seconds() / 60
                        time_until_end = (market_end - now).total_seconds() / 60
                        
                        if time_since_start >= 0 and time_until_end > 0.5:
                            logger.info(f"✅ Found active market via calculation: {target_slug}")
                            return target_slug
                    except Exception:
                        pass

            # STRATEGY B: Fallback search
            for m in markets:
                slug = m.get("slug", "")
                if "btc-updown-" in slug and "15m" in slug:
                    start_date = m.get("startDate")
                    if start_date:
                        try:
                            market_start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                            market_end = market_start + timedelta(minutes=15)
                            time_since_start = (now - market_start).total_seconds() / 60
                            time_until_end = (market_end - now).total_seconds() / 60
                            
                            if time_since_start >= 0 and time_until_end > 0.5:
                                return slug
                        except Exception:
                            continue
            
            self.tui.add_log("⏳ No active market found, waiting...")
            return None
        except Exception as e:
            self.tui.add_log(f"Find market error: {e}")
            logger.error(f"Find market error: {e}")
            return None
        
    async def run(self):
        logger.info("🚀 Polymarket Bot V4 Starting...")
        self.tui.add_log("🚀 Polymarket Bot V4 Starting...")
        self.tui.update_state(status="Initializing...")
        
        notifier.send("🚀 Bot V4 Starting...")
        
        # 1. Initialize WebSocket
        self.ws_manager = None
        
        # Sync exchange state
        if config.get("sync_on_startup", True):
            self.tui.add_log("Syncing exchange state...")
            await self.executor.sync_exchange_state()
            if not self.dry_run:
                asyncio.create_task(self.executor.auto_redeem_positions())
        
        # Cache current market
        current_market_slug = None
        market_data = None
        
        # Use Rich Live Manager
        with Live(self.tui.render(), refresh_per_second=4, screen=True) as live:
            self.tui.update_state(status="Running")
            
            while self.running:
                live.update(self.tui.render()) # Refresh UI
                
                try:
                    # 2. Check Daily Limits
                    if not self.risk_manager.check_daily_limit():
                        self.tui.update_state(status="Limit Reached")
                        await asyncio.sleep(60)
                        continue
                    
                    # Refresh pending orders
                    await self.executor.refresh_pending_orders()
                
                    # 3. Dynamic Market Selection
                    if not current_market_slug:
                        current_market_slug = await self.find_active_market()
                        if not current_market_slug:
                            await asyncio.sleep(5)
                            continue
                        
                        market_data = await PolyMarketData.get_market(current_market_slug)
                        if not market_data:
                            current_market_slug = None
                            await asyncio.sleep(5)
                            continue
                        
                        self.tui.update_state(market_slug=current_market_slug)
                        self.tui.add_log(f"🎯 Locked: {current_market_slug}")
                        logger.info(f"🎯 Locked: {current_market_slug}")
                        
                        # Start WebSocket
                        token_up, token_down = PolyMarketData.resolve_token_ids(market_data)
                        if token_up and token_down:
                            if self.ws_manager:
                                await self.ws_manager.disconnect()
                            
                            self.tui.add_log(f"🔌 Starting WebSocket...")
                            self.ws_manager = MarketWebSocket()
                            await self.ws_manager.subscribe([token_up, token_down], replace=True, fetch_initial=False)
                            asyncio.create_task(self.ws_manager.run(auto_reconnect=True))
                            await asyncio.sleep(1)
                        else:
                            self.tui.add_log("⚠️ Could not resolve token IDs for WebSocket")
                            
                    else:
                        # Check expiry
                        from datetime import datetime, timezone, timedelta
                        slug_parts = current_market_slug.split('-')
                        if len(slug_parts) >= 4 and slug_parts[-1].isdigit():
                            market_end = datetime.fromtimestamp(int(slug_parts[-1]), timezone.utc) + timedelta(minutes=15)
                            if datetime.now(timezone.utc) >= market_end:
                                self.tui.add_log(f"⏰ Market expired: {current_market_slug}")
                                current_market_slug = None
                                market_data = None
                                asyncio.create_task(self.executor.auto_redeem_positions())
                                continue
                    
                    # Get BTC price
                    btc_price = await BinanceData.get_current_price()
                    
                    if not btc_price or not market_data:
                        await asyncio.sleep(1)
                        continue
                        
                    # Update TUI State
                    strike = market_data.get('strike', 0)
                    self.tui.update_state(
                        btc_price=btc_price,
                        strike=strike
                    )
                    
                    # [WebSocket] Update Data
                    token_up, token_down = PolyMarketData.resolve_token_ids(market_data)
                    source = "REST"
                    
                    if token_up and token_down:
                        if self.ws_manager:
                            ob_up = self.ws_manager.get_orderbook(token_up)
                            ob_down = self.ws_manager.get_orderbook(token_down)
                            
                            if ob_up and ob_down:
                                market_data["ask_up"] = ob_up.best_ask
                                market_data["ask_down"] = ob_down.best_ask
                                market_data["bid_up"] = ob_up.best_bid
                                market_data["bid_down"] = ob_down.best_bid
                                source = "WebSocket"

                        if "ask_up" not in market_data:
                            ob_up = await PolyMarketData.get_orderbook(token_up)
                            if ob_up and "asks" in ob_up and len(ob_up["asks"]) > 0:
                                market_data["ask_up"] = float(ob_up["asks"][0]["price"])
                        if "ask_down" not in market_data:
                            ob_down = await PolyMarketData.get_orderbook(token_down)
                            if ob_down and "asks" in ob_down and len(ob_down["asks"]) > 0:
                                market_data["ask_down"] = float(ob_down["asks"][0]["price"])
                    
                    # Update TUI Orderbook
                    self.tui.update_state(
                        ask_up=market_data.get("ask_up", 0),
                        bid_up=market_data.get("bid_up", 0),
                        ask_down=market_data.get("ask_down", 0),
                        bid_down=market_data.get("bid_down", 0),
                        source=source
                    )
                    
                    # Export to JSON for Web Dashboard
                    try:
                        export_state = self.tui.state.copy()
                        del export_state['logs'] # Keep file small
                        temp_file = "market_state.tmp"
                        final_file = "market_state.json"
                        with open(temp_file, "w") as f:
                            json.dump(export_state, f)
                        os.replace(temp_file, final_file)
                    except Exception:
                        pass
                    
                    # 4. Position Management
                    active_positions = [p for p in self.executor.positions if (p.get("status") or "").upper() in ("OPEN")]
                    if active_positions:
                        self.tui.update_state(positions=active_positions)
                        for pos in active_positions:
                            pos_token = pos.get("token_id")
                            if pos_token:
                                exit_price = None
                                if self.ws_manager:
                                    ob = self.ws_manager.get_orderbook(pos_token)
                                    if ob: exit_price = ob.best_bid
                                if exit_price is None:
                                    # Fallback
                                    pass

                                if exit_price is not None:
                                    action = self.risk_manager.check_exit_signal(pos, exit_price)
                                    if action != "HOLD":
                                        self.tui.add_log(f"🚨 EXIT: {action} @ {exit_price:.3f}")
                                        logger.info(f"Exit Signal: {action}")
                                        if not self.dry_run:
                                            await self.executor.close_position(pos, exit_price, reason=action)
                        await asyncio.sleep(1)
                        continue

                    # 5. Strategy
                    if not self.strategy:
                        await asyncio.sleep(1)
                        continue

                    signal = self.strategy.calculate_signal(market_data, btc_price)
                    if signal:
                        condition_id = market_data.get("conditionId") or market_data.get("condition_id")
                        target_token_id = token_up if signal['direction'] == "UP" else token_down
                        self.tui.add_log(f"🔥 Signal: {signal['direction']} Edge: {signal['edge']:.1%}")
                        logger.info(f"Signal: {signal['direction']} Edge: {signal['edge']:.1%}")
                        
                        if not self.dry_run:
                            await self.executor.place_order(
                                current_market_slug,
                                signal['direction'],
                                target_token_id or "TOKEN_ID_MISSING",
                                signal['price'],
                                config.get("trade_amount_usd", 1.0),
                                condition_id=condition_id
                            )
                        else:
                            self.tui.add_log("🧪 DRY_RUN: Order skipped")
                            
                except Exception as e:
                    self.tui.add_log(f"Error: {str(e)[:50]}")
                    logger.error(f"Loop Error: {e}")
                    await asyncio.sleep(1)
                
                await asyncio.sleep(0.033)
            
        # Cleanup
        self.tui.update_state(status="Stopping...")
        try:
            if self.ws_manager:
                await self.ws_manager.disconnect()
        except Exception:
            pass
            
        try:
            from api_client import close_client
            await close_client()
        except:
            pass
        self.tui.add_log("👋 Bye!")
            
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket Bot V4")
    parser.add_argument("--dry-run", action="store_true", help="Run without placing or closing orders")
    args = parser.parse_args()
    if args.dry_run:
        config.update("dry_run", True)
    
    bot = PolymarketBotV4(dry_run=args.dry_run)
    
    try:
        # Use a new event loop policy (optional debugging)
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        # This catches Ctrl+C immediately
        print("\n\n🛑 Forecefully Stopping... (KeyboardInterrupt)")
        # Clean exit is handled in finally block of run() usually, 
        # but if we are stuck in a blocking call, we force exit.
        sys.exit(0)
