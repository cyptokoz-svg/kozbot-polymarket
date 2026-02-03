import time
import logging
from api_client import request as http_request
import json
import asyncio
import websockets
import os
import shutil
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timezone
from config import config

logger = logging.getLogger(__name__)

class BinanceData:
    """Binance Data Source"""
    BASE_URL = "https://api.binance.com/api/v3"
    _last_price = None
    _last_ts = 0.0
    
    @staticmethod
    async def get_current_price(symbol: str = "BTCUSDT") -> Optional[float]:
        try:
            ttl = float(config.get("price_cache_sec", 0) or 0)
            now = time.time()
            if ttl > 0 and BinanceData._last_price is not None and (now - BinanceData._last_ts) < ttl:
                return BinanceData._last_price
            url = f"{BinanceData.BASE_URL}/ticker/price"
            params = {"symbol": symbol}
            resp = await http_request("GET", url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                price = float(data["price"])
                BinanceData._last_price = price
                BinanceData._last_ts = now
                return price
            if BinanceData._last_price is not None:
                return BinanceData._last_price
            return None
        except Exception as e:
            logger.error(f"Binance Error: {e}")
            return BinanceData._last_price if BinanceData._last_price is not None else None
    
    @staticmethod
    async def get_historical_price(timestamp_seconds: int) -> Optional[float]:
        """Get BTC price at specific timestamp using Binance kline data"""
        try:
            import httpx
            from datetime import datetime, timezone
            
            timestamp_ms = timestamp_seconds * 1000
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "startTime": timestamp_ms,
                "limit": 1
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        open_price = float(data[0][1])  # Open price
                        dt = datetime.fromtimestamp(timestamp_seconds, timezone.utc)
                        logger.info(f"📜 Binance historical at {dt.strftime('%H:%M:%S')} UTC: ${open_price:.2f}")
                        return open_price
            
            logger.warning(f"No historical data for timestamp {timestamp_seconds}")
            return None
        except Exception as e:
            logger.warning(f"Error getting historical Binance price: {e}")
            return None

class WebSocketManager:
    """Polymarket WebSocket Manager"""
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    
    def __init__(self, asset_ids: List[str]):
        self.asset_ids = asset_ids
        self.ws = None
        self.running = False
        self.data = {}
        self.callbacks = []
        self._backoff = 1
        
    async def connect(self):
        self.running = True
        while self.running:
            try:
                async with websockets.connect(
                    self.WS_URL,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5
                ) as ws:
                    self.ws = ws
                    logger.info("✅ WebSocket Connected")
                    self._backoff = 1
                    
                    # Subscribe
                    msg = {
                        "assets_ids": self.asset_ids,
                        "asset_ids": self.asset_ids,
                        "type": "market"
                    }
                    await ws.send(json.dumps(msg))
                    
                    async for message in ws:
                        await self._handle_message(message)
                        
            except Exception as e:
                logger.error(f"WebSocket Error: {e}")
                await asyncio.sleep(self._backoff) # Reconnect delay
                self._backoff = min(self._backoff * 2, 30)
                
    async def close(self):
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
                
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
        
    def _ensure_book(self, asset_id: str):
        if asset_id not in self.data:
            self.data[asset_id] = {
                "bids": {},
                "asks": {},
                "best_bid": None,
                "best_ask": None,
                "ts": 0.0
            }
        return self.data[asset_id]

    def _parse_side_price_size(self, entry):
        side = None
        price = None
        size = None
        try:
            if isinstance(entry, dict):
                side = entry.get("side") or entry.get("type") or entry.get("action")
                price = entry.get("price")
                size = entry.get("size") or entry.get("qty") or entry.get("quantity") or entry.get("amount")
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                if len(entry) >= 3:
                    side = entry[0]
                    price = entry[1]
                    size = entry[2]
                else:
                    price = entry[0]
                    size = entry[1]
        except Exception:
            return None, None, None
        if side is not None:
            side = str(side).upper()
            if side in ("BUY", "BID"):
                side = "BID"
            elif side in ("SELL", "ASK"):
                side = "ASK"
        try:
            price = float(price) if price is not None else None
            size = float(size) if size is not None else None
        except Exception:
            return side, None, None
        return side, price, size

    def _apply_snapshot(self, asset_id: str, bids, asks):
        book = self._ensure_book(asset_id)
        book["bids"] = {}
        book["asks"] = {}
        for entry in bids or []:
            _, price, size = self._parse_side_price_size(entry)
            if price is None or size is None:
                continue
            if size > 0:
                book["bids"][price] = size
        for entry in asks or []:
            _, price, size = self._parse_side_price_size(entry)
            if price is None or size is None:
                continue
            if size > 0:
                book["asks"][price] = size
        self._recalc_best(book)

    def _apply_delta(self, asset_id: str, side: str, price: float, size: float):
        book = self._ensure_book(asset_id)
        if side == "BID":
            if size <= 0:
                book["bids"].pop(price, None)
            else:
                book["bids"][price] = size
        elif side == "ASK":
            if size <= 0:
                book["asks"].pop(price, None)
            else:
                book["asks"][price] = size
        self._recalc_best(book)

    def _recalc_best(self, book: dict):
        best_bid = max(book["bids"].keys(), default=None)
        best_ask = min(book["asks"].keys(), default=None)
        book["best_bid"] = best_bid
        book["best_ask"] = best_ask
        book["ts"] = time.time()

    def _update_book(self, item):
        if not isinstance(item, dict):
            return
        payload = item.get("data") if isinstance(item.get("data"), dict) else item
        asset_id = payload.get("asset_id") or payload.get("assetId") or payload.get("token_id") or payload.get("tokenId")
        if not asset_id:
            return

        bids = payload.get("bids")
        asks = payload.get("asks")
        changes = payload.get("changes") or payload.get("deltas") or payload.get("updates")

        if isinstance(bids, list) or isinstance(asks, list):
            self._apply_snapshot(asset_id, bids or [], asks or [])
            return

        if isinstance(changes, list):
            for change in changes:
                side, price, size = self._parse_side_price_size(change)
                if side in ("BID", "ASK") and price is not None and size is not None:
                    self._apply_delta(asset_id, side, price, size)
            return

        # Fallback to best bid/ask fields
        best_bid = payload.get("best_bid") or payload.get("bestBid")
        best_ask = payload.get("best_ask") or payload.get("bestAsk")
        try:
            best_bid = float(best_bid) if best_bid is not None else None
            best_ask = float(best_ask) if best_ask is not None else None
        except Exception:
            best_bid = None
            best_ask = None
        book = self._ensure_book(asset_id)
        if best_bid is not None:
            book["best_bid"] = best_bid
        if best_ask is not None:
            book["best_ask"] = best_ask
        book["ts"] = time.time()
            
    def get_price(self, asset_id) -> Optional[float]:
        # Backward-compat: return best ask if available
        book = self.data.get(asset_id) or {}
        ask = book.get("best_ask")
        if self._is_stale(book):
            return None
        return ask

    def get_best_ask(self, asset_id) -> Optional[float]:
        book = self.data.get(asset_id) or {}
        if self._is_stale(book):
            return None
        return book.get("best_ask")

    def get_best_bid(self, asset_id) -> Optional[float]:
        book = self.data.get(asset_id) or {}
        if self._is_stale(book):
            return None
        return book.get("best_bid")

    def _is_stale(self, book: dict) -> bool:
        ttl = float(config.get("ws_stale_sec", 2) or 0)
        if ttl <= 0:
            return False
        ts = book.get("ts", 0)
        return (time.time() - ts) > ttl

class PolyMarketData:
    """Polymarket REST Data Source"""
    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"
    _orderbook_cache: Dict[str, Tuple[float, Dict]] = {}
    _market_cache: Dict[str, Tuple[float, Dict]] = {}
    _events_cache: Dict[str, Tuple[float, List[Dict]]] = {}

    @staticmethod
    def _cache_get(cache: Dict, key: str, ttl: float):
        if ttl <= 0:
            return None
        item = cache.get(key)
        if not item:
            return None
        ts, value = item
        if (time.time() - ts) <= ttl:
            return value
        return None

    @staticmethod
    def _cache_set(cache: Dict, key: str, value):
        cache[key] = (time.time(), value)
    
    @staticmethod
    async def get_orderbook(token_id: str) -> Optional[Dict]:
        """Get orderbook for a token"""
        try:
            ttl = float(config.get("orderbook_cache_sec", 0) or 0)
            cached = PolyMarketData._cache_get(PolyMarketData._orderbook_cache, token_id, ttl)
            if cached is not None:
                return cached
            url = f"{PolyMarketData.CLOB_API}/book"
            params = {"token_id": token_id}
            resp = await http_request("GET", url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                
                # Fix Orderbook Sorting
                # API returns strange order. We enforce: 
                # Bids: Best (High) -> Worst (Low)
                # Asks: Best (Low) -> Worst (High)
                if "bids" in data and isinstance(data["bids"], list):
                     data["bids"].sort(key=lambda x: float(x.get("price", 0)), reverse=True)
                if "asks" in data and isinstance(data["asks"], list):
                     data["asks"].sort(key=lambda x: float(x.get("price", 0)), reverse=False)

                PolyMarketData._cache_set(PolyMarketData._orderbook_cache, token_id, data)
                return data
            fallback = PolyMarketData._orderbook_cache.get(token_id)
            return fallback[1] if fallback else None
        except Exception as e:
            logger.error(f"Orderbook fetch error: {e}")
            fallback = PolyMarketData._orderbook_cache.get(token_id)
            return fallback[1] if fallback else None
    
    @staticmethod
    async def fetch_markets(params: Dict) -> List[Dict]:
        """Fetch active markets"""
        try:
            # Default params
            default_params = {
                "limit": 100,
                "active": True,
                "closed": False,
                "archived": False,
                "order": "startDate",
                "ascending": False
            }
            default_params.update(params)
            cache_ttl = float(config.get("market_cache_sec", 0) or 0)
            cache_key = json.dumps(default_params, sort_keys=True, default=str)
            cached = PolyMarketData._cache_get(PolyMarketData._events_cache, cache_key, cache_ttl)
            if cached is not None:
                return cached
            
            url = f"{PolyMarketData.GAMMA_API}/events"
            resp = await http_request("GET", url, params=default_params, timeout=10)
            if resp.status_code == 200:
                events = resp.json()
                markets = []
                for event in events:
                    if not isinstance(event, dict): continue
                    
                    # Find BTC markets inside events
                    event_markets = event.get("markets", [])
                    for m in event_markets:
                        # Basic filtering
                        question = m.get("question", "")
                        slug = m.get("slug", "")
                        
                        # Match logic: BTC 15m
                        if "Bitcoin" in event.get("title", "") or "BTC" in question:
                            # Return raw market data (normalization happens in get_market())
                            markets.append(m)
                            
                PolyMarketData._cache_set(PolyMarketData._events_cache, cache_key, markets)
                return markets
            fallback = PolyMarketData._events_cache.get(cache_key)
            return fallback[1] if fallback else []
        except Exception as e:
            logger.error(f"Market Fetch Error: {e}")
            fallback = PolyMarketData._events_cache.get(json.dumps(default_params, sort_keys=True, default=str))
            return fallback[1] if fallback else []
            
    @staticmethod
    async def get_market(slug: str) -> Optional[Dict]:
        try:
            cache_ttl = float(config.get("market_cache_sec", 0) or 0)
            cached = PolyMarketData._cache_get(PolyMarketData._market_cache, slug, cache_ttl)
            if cached is not None:
                return cached
            # Prefer direct market lookup
            url = f"{PolyMarketData.GAMMA_API}/markets"
            params = {"slug": slug}
            resp = await http_request("GET", url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    market = await PolyMarketData.normalize_market(data[0])
                    PolyMarketData._cache_set(PolyMarketData._market_cache, slug, market)
                    return market
                if isinstance(data, dict) and data:
                    market = await PolyMarketData.normalize_market(data)
                    PolyMarketData._cache_set(PolyMarketData._market_cache, slug, market)
                    return market
        except Exception:
            pass
        try:
            # Fallback: fetch events and search market list
            url = f"{PolyMarketData.GAMMA_API}/events"
            params = {"slug": slug}
            resp = await http_request("GET", url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    event = data[0]
                    markets = event.get("markets", [])
                    for m in markets:
                        if m.get("slug") == slug:
                            market = await PolyMarketData.normalize_market(m)
                            PolyMarketData._cache_set(PolyMarketData._market_cache, slug, market)
                            return market
                    market = await PolyMarketData.normalize_market(markets[0] if markets else event)
                    PolyMarketData._cache_set(PolyMarketData._market_cache, slug, market)
                    return market
                if isinstance(data, dict):
                    markets = data.get("markets", [])
                    for m in markets:
                        if m.get("slug") == slug:
                            market = await PolyMarketData.normalize_market(m)
                            PolyMarketData._cache_set(PolyMarketData._market_cache, slug, market)
                            return market
                    market = await PolyMarketData.normalize_market(data)
                    PolyMarketData._cache_set(PolyMarketData._market_cache, slug, market)
                    return market
            fallback = PolyMarketData._market_cache.get(slug)
            return fallback[1] if fallback else None
        except Exception:
            fallback = PolyMarketData._market_cache.get(slug)
            return fallback[1] if fallback else None

    @staticmethod
    def _parse_json_field(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    @staticmethod
    async def normalize_market(market: Dict) -> Dict:
        if not isinstance(market, dict):
            return market
        tokens = PolyMarketData._parse_json_field(market.get("clobTokenIds"))
        if isinstance(tokens, list):
            market["clobTokenIds"] = tokens
        outcomes = PolyMarketData._parse_json_field(market.get("outcomes"))
        if isinstance(outcomes, list):
            market["outcomes"] = outcomes
        # Get strike price - for BTC markets, cache Binance price at market start
        strike = market.get("strike")
        
        # Check if this is a BTC Up/Down market
        question = market.get("question", "").lower()
        slug = market.get("slug", "").lower()
        is_btc_market = ("bitcoin" in question or "btc" in question or "btc" in slug) and ("up" in question or "down" in question)
        
        if is_btc_market:
            # Use class-level cache to store strike per market slug (fixed for each market)
            if not hasattr(PolyMarketData, '_strike_cache'):
                PolyMarketData._strike_cache = {}
            
            market_slug = market.get("slug")
            if market_slug and market_slug not in PolyMarketData._strike_cache:
                # First time seeing this market - get Binance price at market START time
                try:
                    # Extract timestamp from slug (e.g., btc-updown-15m-1770120900)
                    slug_parts = market_slug.split('-')
                    if len(slug_parts) >= 4 and slug_parts[-1].isdigit():
                        strike_timestamp = int(slug_parts[-1])
                        
                        # Try to get historical price at market start
                        strike = await BinanceData.get_historical_price(strike_timestamp)
                        
                        if not strike:
                            # Fallback to current price if historical unavailable
                            logger.warning(f"⚠️ Historical price unavailable, using current price")
                            strike = await BinanceData.get_current_price()
                        
                        if strike:
                            PolyMarketData._strike_cache[market_slug] = strike
                    else:
                        # Can't parse timestamp, use current price
                        strike = await BinanceData.get_current_price()
                        if strike:
                            PolyMarketData._strike_cache[market_slug] = strike
                            
                except Exception as e:
                    logger.warning(f"Failed to get Binance price for strike: {e}")
            else:
                # Use cached strike for this market (fixed value)
                strike = PolyMarketData._strike_cache.get(market_slug, strike)
        
        
        
        
        if isinstance(strike, str):
            try:
                strike = float(strike)
            except Exception:
                pass
        if strike is not None:
            market["strike"] = strike
        expiry = market.get("expiry")
        if not expiry:
            for key in ("endDate", "end_date", "endTime", "end_time", "closeDate", "close_date", "resolutionDate", "resolution_date"):
                if market.get(key):
                    expiry = market.get(key)
                    break
        if expiry:
            market["expiry"] = expiry
        return market

    @staticmethod
    def resolve_token_ids(market: Dict) -> Tuple[Optional[str], Optional[str]]:
        if not isinstance(market, dict):
            return None, None
        tokens = market.get("clobTokenIds") or []
        if isinstance(tokens, str):
            tokens = PolyMarketData._parse_json_field(tokens)
        if not isinstance(tokens, list):
            return None, None
        if len(tokens) < 2:
            return tokens[0] if tokens else None, None
        outcomes = market.get("outcomes")
        if isinstance(outcomes, str):
            outcomes = PolyMarketData._parse_json_field(outcomes)
        if isinstance(outcomes, list) and len(outcomes) >= 2:
            labels = [str(o).lower() for o in outcomes]
            def idx_for(targets):
                for t in targets:
                    for i, label in enumerate(labels):
                        if t in label:
                            return i
                return None
            up_idx = idx_for(["up", "yes", "higher", "above", "increase", "bull"])
            down_idx = idx_for(["down", "no", "lower", "below", "decrease", "bear"])
            if up_idx is not None and down_idx is not None and up_idx != down_idx:
                return tokens[up_idx], tokens[down_idx]
        return tokens[0], tokens[1]

    @staticmethod
    async def get_market_by_condition(condition_id: str) -> Optional[Dict]:
        try:
            url = f"{PolyMarketData.GAMMA_API}/markets"
            params = {"conditionId": condition_id}
            resp = await http_request("GET", url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return await PolyMarketData.normalize_market(data[0])
                if isinstance(data, dict) and data:
                    return await PolyMarketData.normalize_market(data)
            return None
        except Exception:
            return None

class HyperliquidData:
    """Hyperliquid High-Speed Data Source (<50ms)"""
    SERVER_URL = "http://localhost:3000" # HL CLI Server
    _hl_path = None
    _last_price = None
    _last_ts = 0.0

    @staticmethod
    def _get_hl_path():
        if HyperliquidData._hl_path is not None:
            return HyperliquidData._hl_path
        HyperliquidData._hl_path = os.getenv("HL_CLI_PATH") or shutil.which("hl")
        return HyperliquidData._hl_path
    
    @staticmethod
    async def get_current_price(coin: str = "BTC") -> Optional[float]:
        """Get ultra-low latency price from Hyperliquid SDK"""
        try:
            ttl = float(config.get("hl_price_cache_sec", config.get("price_cache_sec", 0)) or 0)
            now = time.time()
            if ttl > 0 and HyperliquidData._last_price is not None and (now - HyperliquidData._last_ts) < ttl:
                return HyperliquidData._last_price

            # Use Hyperliquid SDK directly (faster than CLI subprocess)
            # Run in executor to avoid blocking the event loop
            try:
                import asyncio
                from hyperliquid.info import Info
                from hyperliquid.utils import constants
                
                def _fetch_price():
                    # Create Info object (cached for efficiency)
                    info = Info(constants.MAINNET_API_URL, skip_ws=True)
                    
                    # Get all mids (market prices)
                    all_mids = info.all_mids()
                    
                    # Find BTC price
                    # Common symbols: "BTC", "BTC-USD", "@1" (coin index 0 is usually BTC)
                    price = None
                    if coin in all_mids:
                        price = float(all_mids[coin])
                    elif f"{coin}-USD" in all_mids:
                        price = float(all_mids[f"{coin}-USD"])
                    elif "@1" in all_mids:  # BTC is typically index 0, displayed as @1
                        price = float(all_mids["@1"])
                    return price
                
                # Run blocking SDK call in thread pool
                loop = asyncio.get_event_loop()
                price = await loop.run_in_executor(None, _fetch_price)
                
                if price:
                    HyperliquidData._last_price = price
                    HyperliquidData._last_ts = now
                    return price
                    
                # If SDK fails, return cached value
                return HyperliquidData._last_price if HyperliquidData._last_price is not None else None
                
            except ImportError:
                # If SDK not installed, fall back to cached value
                logger.debug("Hyperliquid SDK not installed, using cache")
                return HyperliquidData._last_price if HyperliquidData._last_price is not None else None
                
        except Exception as e:
            logger.error(f"HL Price Error: {e}")
            return HyperliquidData._last_price if HyperliquidData._last_price is not None else None

    @staticmethod
    async def get_historical_price(timestamp_ms: int, coin: str = "BTC") -> Optional[float]:
        """Get historical price from Hyperliquid at specific timestamp
        
        Args:
            timestamp_ms: Unix timestamp in milliseconds
            coin: Coin symbol (default "BTC")
            
        Returns:
            Close price at that timestamp, or None if unavailable
        """
        try:
            import asyncio
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            
            def _fetch_historical():
                info = Info(constants.MAINNET_API_URL, skip_ws=True)
                
                # Get 1-minute candle at that timestamp
                # Request wider window: timestamp ± 5 minutes for better data availability
                start_time = timestamp_ms - 300000  # 5 min before
                end_time = timestamp_ms + 300000    # 5 min after
                
                candles = info.candles_snapshot(coin, '1m', start_time, end_time)
                
                if candles and len(candles) > 0:
                    # Return close price of closest candle
                    close_price = float(candles[0]['c'])
                    logger.debug(f"Historical {coin} price at {timestamp_ms}: ${close_price:.2f}")
                    return close_price
                
                logger.warning(f"No historical candles found for {coin} at {timestamp_ms}")
                return None
            
            # Run blocking SDK call in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _fetch_historical)
            
        except ImportError:
            logger.debug("Hyperliquid SDK not installed")
            return None
        except Exception as e:
            logger.error(f"HL historical price error: {e}")
            return None
