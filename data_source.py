import time
import logging
import requests
import json
import asyncio
import websockets
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class BinanceData:
    """Binance Data Source"""
    BASE_URL = "https://api.binance.com/api/v3"
    
    @staticmethod
    def get_current_price(symbol: str = "BTCUSDT") -> Optional[float]:
        try:
            url = f"{BinanceData.BASE_URL}/ticker/price"
            params = {"symbol": symbol}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return float(data["price"])
            return None
        except Exception as e:
            logger.error(f"Binance Error: {e}")
            return None

class WebSocketManager:
    """Polymarket WebSocket Manager (Ported from V3)"""
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    
    def __init__(self, asset_ids: List[str]):
        self.asset_ids = asset_ids
        self.ws = None
        self.running = False
        self.data = {}
        self.callbacks = []
        
    async def connect(self):
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.WS_URL) as ws:
                    self.ws = ws
                    logger.info("✅ WebSocket Connected")
                    
                    # Subscribe
                    msg = {
                        "assets_ids": self.asset_ids,
                        "type": "market"
                    }
                    await ws.send(json.dumps(msg))
                    
                    async for message in ws:
                        await self._handle_message(message)
                        
            except Exception as e:
                logger.error(f"WebSocket Error: {e}")
                await asyncio.sleep(5) # Reconnect delay
                
    async def _handle_message(self, message):
        try:
            data = json.loads(message)
            # Process updates (Simplified for V4)
            if isinstance(data, list):
                for item in data:
                    self._update_book(item)
            else:
                self._update_book(data)
        except: pass
        
    def _update_book(self, item):
        asset_id = item.get("asset_id")
        if asset_id:
            # Store latest snapshot
            self.data[asset_id] = item
            
    def get_price(self, asset_id) -> Optional[float]:
        # Extract best price from stored book
        book = self.data.get(asset_id)
        # Simplified logic - real implementation needs full orderbook reconstruction
        # For now return None to force REST API fallback (safe default)
        return None 

class PolyMarketData:
    """Polymarket REST Data Source"""
    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"
    
    @staticmethod
    def get_orderbook(token_id: str) -> Optional[Dict]:
        """Get orderbook for a token"""
        try:
            url = f"{PolyMarketData.CLOB_API}/book/{token_id}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"Orderbook fetch error: {e}")
            return None
    
    @staticmethod
    def fetch_markets(params: Dict) -> List[Dict]:
        """Fetch active markets (V3 Logic Ported)"""
        try:
            # Add V3 default params
            default_params = {
                "limit": 100,
                "active": True,
                "closed": False,
                "archived": False,
                "order": "startDate",
                "ascending": False
            }
            default_params.update(params)
            
            url = f"{PolyMarketData.GAMMA_API}/events"
            resp = requests.get(url, params=default_params, timeout=10)
            if resp.status_code == 200:
                events = resp.json()
                markets = []
                for event in events:
                    if not isinstance(event, dict): continue
                    
                    # V3 Logic: Find BTC markets inside events
                    event_markets = event.get("markets", [])
                    for m in event_markets:
                        # Basic filtering
                        question = m.get("question", "")
                        slug = m.get("slug", "")
                        
                        # Match logic: BTC 15m
                        if "Bitcoin" in event.get("title", "") or "BTC" in question:
                            # Verify if it's the right type
                            markets.append(m)
                            
                return markets
            return []
        except Exception as e:
            logger.error(f"Market Fetch Error: {e}")
            return []
            
    @staticmethod
    def get_market(slug: str) -> Optional[Dict]:
        try:
            url = f"{PolyMarketData.GAMMA_API}/events"
            params = {"slug": slug}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data[0] if isinstance(data, list) else data
            return None
        except Exception: return None

class HyperliquidData:
    """Hyperliquid High-Speed Data Source (<50ms)"""
    SERVER_URL = "http://localhost:3000" # HL CLI Server
    
    @staticmethod
    def get_current_price(coin: str = "BTC") -> Optional[float]:
        """Get ultra-low latency price from local HL server"""
        try:
            # Use 'asset price' endpoint from HL Server
            # The CLI tool exposes a REST interface when server is running
            # We use 'hl asset price BTC --json' logic via HTTP if available
            # Or use IPC if implemented. For now, assuming HL server exposes simple JSON.
            # Actually, chrisling-dev/hyperliquid-cli server might not expose HTTP port 3000 by default for pricing.
            # It uses IPC/WebSocket. Let's try to invoke 'hl' command which is fast when server runs.
            
            # Method A: Sub-process call (Fast enough? ~10-20ms overhead)
            # cmd = ["hl", "asset", "price", coin, "--json"]
            # result = subprocess.run(cmd, capture_output=True, text=True)
            # data = json.loads(result.stdout)
            # return float(data['price'])
            
            # Method B: Direct HTTP if server supports it (Fastest)
            # Let's assume standard port or use method A for now as it uses IPC to server
            
            # Using Method A for robustness first
            import subprocess
            cmd = ["/home/ubuntu/.npm-global/bin/hl", "asset", "price", coin, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data["price"])
            return None
        except Exception as e:
            logger.error(f"HL Price Error: {e}")
            return None
