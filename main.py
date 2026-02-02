import asyncio
import logging
import signal
import sys
import os

# Fix import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone

from config import config
from data_source import BinanceData, PolyMarketData, WebSocketManager, HyperliquidData
from risk_manager import RiskManager
from executor import Executor
from strategy import Strategy
from notification import notifier

logger = logging.getLogger(__name__)

class PolymarketBotV4:
    def __init__(self):
        self.running = True
        self.risk_manager = RiskManager()
        self.executor = Executor()
        self.strategy = Strategy(
            min_edge=config.get("min_edge", 0.08),
            safety_margin_pct=config.get("safety_margin_pct", 0.0006)
        )
        self.ws_manager = None
        
        # Graceful Shutdown
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        
    def stop(self, signum=None, frame=None):
        logger.info("🛑 Stopping Bot...")
        self.running = False
        notifier.send("🛑 Bot stopping...")
        
    async def find_active_market(self):
        """Find the active 15m BTC market"""
        try:
            # Fetch events from Gamma API
            params = {
                "closed": False,
                "limit": 20,
                # "tag_id": "1"  # Removed potentially restrictive tag
            }
            # Simplified: In real usage we need strict filtering by slug pattern
            # For test, we look for 'btc-updown-'
            markets = PolyMarketData.fetch_markets(params)
            
            for m in markets:
                slug = m.get("slug", "")
                if "btc-updown-" in slug and "15m" in slug:
                    return slug
            
            logger.warning("No active BTC 15m market found")
            return None
        except Exception as e:
            logger.error(f"Find market error: {e}")
            return None
        
    async def run(self):
        logger.info("🚀 Polymarket Bot V4 Starting...")
        notifier.send("🚀 Bot V4 Starting...")
        
        # 1. Start WebSocket (Background)
        # self.ws_manager = WebSocketManager(["asset_id_1", "asset_id_2"])
        # asyncio.create_task(self.ws_manager.connect())
        
        while self.running:
            try:
                # 2. Check Daily Limits
                if not self.risk_manager.check_daily_limit():
                    await asyncio.sleep(60)
                    continue
                    
                # 3. Dynamic Market Selection
                market_slug = await self.find_active_market()
                if not market_slug:
                    await asyncio.sleep(5)
                    continue
                    
                market_data = PolyMarketData.get_market(market_slug)
                
                # [Optimization] Use Hyperliquid for <50ms latency (Primary)
                # Fallback to Binance if HL fails
                btc_price = HyperliquidData.get_current_price("BTC")
                if btc_price:
                    logger.debug(f"⚡ HL Price: {btc_price}")
                else:
                    btc_price = BinanceData.get_current_price()
                    logger.debug(f"🐢 Binance Price: {btc_price}")
                
                if not btc_price or not market_data:
                    await asyncio.sleep(1)
                    continue
                    
                # [WebSocket] Init/Update
                # Extract token IDs
                token_up = market_data.get("clobTokenIds", [])[0] if market_data.get("clobTokenIds") else None
                token_down = market_data.get("clobTokenIds", [])[1] if market_data.get("clobTokenIds") and len(market_data.get("clobTokenIds")) > 1 else None
                
                if token_up and token_down:
                    # Fetch orderbook data for exit price checking
                    ob_up = PolyMarketData.get_orderbook(token_up)
                    ob_down = PolyMarketData.get_orderbook(token_down)
                    
                    if ob_up and "asks" in ob_up and len(ob_up["asks"]) > 0:
                        market_data["ask_up"] = float(ob_up["asks"][0]["price"])
                    if ob_down and "asks" in ob_down and len(ob_down["asks"]) > 0:
                        market_data["ask_down"] = float(ob_down["asks"][0]["price"])
                    
                    # If WS not running or market changed, restart WS
                    current_tokens = getattr(self.ws_manager, "asset_ids", []) if self.ws_manager else []
                    new_tokens = [token_up, token_down]
                    
                    if not self.ws_manager or set(current_tokens) != set(new_tokens):
                        if self.ws_manager:
                            logger.info("🔌 Closing old WebSocket...")
                            await self.ws_manager.close()
                            
                        logger.info(f"🔌 Starting WebSocket for {market_slug}")
                        self.ws_manager = WebSocketManager(new_tokens)
                        asyncio.create_task(self.ws_manager.connect())
                    
                    # Update market data with WS price if available (faster updates)
                    if self.ws_manager:
                        ws_price_up = self.ws_manager.get_price(token_up)
                        ws_price_down = self.ws_manager.get_price(token_down)
                        
                        if ws_price_up: 
                            market_data["ask_up"] = ws_price_up
                            logger.debug(f"WS Price UP: {ws_price_up}")
                        if ws_price_down:
                            market_data["ask_down"] = ws_price_down
                            logger.debug(f"WS Price DOWN: {ws_price_down}")
                
                # 4. Position Management (Priority High)
                # If we have open positions, MONITOR them instead of opening new ones
                open_positions = [p for p in self.executor.positions if p.get("status") == "OPEN"]
                
                if open_positions:
                    for pos in open_positions:
                        direction = pos["direction"]
                        # Fetch fresh orderbook for exit price (use BID for selling)
                        pos_token = pos.get("token_id")
                        if pos_token:
                            ob = PolyMarketData.get_orderbook(pos_token)
                            if ob and "bids" in ob and len(ob["bids"]) > 0:
                                exit_price = float(ob["bids"][0]["price"])
                                
                                action = self.risk_manager.check_exit_signal(pos, exit_price)
                                if action != "HOLD":
                                    logger.info(f"🚨 Exit Signal: {action} @ {exit_price}")
                                    notifier.send(f"🚨 Exit Signal: {action}")
                                    await self.executor.close_position(pos, exit_price)
                    
                    # Skip new entry if we have positions (Single Trade Mode)
                    await asyncio.sleep(1)
                    continue

                # 5. Strategy & Execution (Only if no positions)
                # Ensure we have orderbook data for strategy (asks for entry)
                if "ask_up" not in market_data or "ask_down" not in market_data:
                    if token_up and token_down:
                        ob_up = PolyMarketData.get_orderbook(token_up)
                        ob_down = PolyMarketData.get_orderbook(token_down)
                        if ob_up and "asks" in ob_up and len(ob_up["asks"]) > 0:
                            market_data["ask_up"] = float(ob_up["asks"][0]["price"])
                        if ob_down and "asks" in ob_down and len(ob_down["asks"]) > 0:
                            market_data["ask_down"] = float(ob_down["asks"][0]["price"])
                
                signal = self.strategy.calculate_signal(market_data, btc_price)
                if signal:
                    target_token_id = token_up if signal['direction'] == "UP" else token_down
                    logger.info(f"🔥 Signal: {signal['direction']} {signal['edge']:.1%}")
                    notifier.send(f"🔥 Signal: {signal['direction']} Edge: {signal['edge']:.1%}")
                    
                    success = await self.executor.place_order(
                        market_slug,
                        signal['direction'],
                        target_token_id or "TOKEN_ID_MISSING", # Pass real token ID
                        signal['price'],
                        config.get("trade_amount_usd", 1.0)
                    )
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                await asyncio.sleep(1)
            
            await asyncio.sleep(0.5)
            
if __name__ == "__main__":
    bot = PolymarketBotV4()
    asyncio.run(bot.run())
