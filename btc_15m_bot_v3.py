#!/usr/bin/env python3
"""
Polymarket BTC 15-minute Trading Bot v3 (Smart Probability)
- Retrieves 'Strike Price' (Open price of the 15m candle) from Binance.
- Calculates theoretical probability based on distance to strike and time remaining.
- Trades only when market price deviates significantly from fair value.
"""

import os
import sys
import json
import time
import math
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
import statistics

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import websockets
# [ML Upgrade]
import pandas as pd
import pandas_ta as ta
import joblib

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
# [Builder API]
from py_builder_signing_sdk.config import BuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds

# [Auto-Healing] Crash recovery and self-healing system
class AutoHealer:
    """Monitors bot health and automatically applies fixes"""
    def __init__(self):
        self.crash_count = 0
        self.crash_history = []
        self.healing_actions = []
        self.last_restart = time.time()
        
    def analyze_crash(self, error_msg: str, stack_trace: str) -> dict:
        """Analyze crash type and determine healing action"""
        error_lower = (error_msg + stack_trace).lower()
        
        # Pattern matching for known issues
        if "websocket" in error_lower or "connection" in error_lower:
            return {
                "type": "websocket_failure",
                "action": "disable_websocket",
                "severity": "high"
            }
        elif "memory" in error_lower or "oom" in error_lower:
            return {
                "type": "memory_issue",
                "action": "reduce_memory_usage",
                "severity": "critical"
            }
        elif "timeout" in error_lower or "api" in error_lower:
            return {
                "type": "api_timeout",
                "action": "increase_timeouts",
                "severity": "medium"
            }
        elif "json" in error_lower or "parse" in error_lower:
            return {
                "type": "data_corruption",
                "action": "clear_caches",
                "severity": "medium"
            }
        else:
            return {
                "type": "unknown",
                "action": "full_restart",
                "severity": "unknown"
            }
    
    def apply_fix(self, diagnosis: dict) -> bool:
        """Apply automatic healing action"""
        action = diagnosis.get("action")
        
        try:
            if action == "disable_websocket":
                # Create a flag file to indicate WebSocket should not be used
                flag_file = "/tmp/bot_disable_websocket"
                with open(flag_file, "w") as f:
                    f.write(f"Disabled at {datetime.now(timezone.utc).isoformat()}")
                self.healing_actions.append(f"Created {flag_file}")
                return True
                
            elif action == "clear_caches":
                # Clear potential corrupted cache files
                cache_files = [
                    "/tmp/*.cache",
                    "/home/ubuntu/clawd/bots/polymarket/*.pyc",
                    "/home/ubuntu/clawd/bots/polymarket/__pycache__/*"
                ]
                import glob
                for pattern in cache_files:
                    for f in glob.glob(pattern):
                        try:
                            os.remove(f)
                        except:
                            pass
                self.healing_actions.append("Cleared cache files")
                return True
                
            elif action == "reduce_memory_usage":
                # Force garbage collection
                import gc
                gc.collect()
                self.healing_actions.append("Forced garbage collection")
                return True
                
            elif action == "increase_timeouts":
                # Will be applied on restart via config
                config_patch = {"timeout_multiplier": 2.0}
                with open("/tmp/bot_timeout_patch.json", "w") as f:
                    json.dump(config_patch, f)
                self.healing_actions.append("Created timeout patch")
                return True
                
            elif action == "full_restart":
                self.healing_actions.append("Standard full restart")
                return True
                
        except Exception as e:
            logger.error(f"Auto-healing failed: {e}")
            return False
        
        return True
    
    def record_crash(self, error_msg: str, stack_trace: str):
        """Record crash for analysis"""
        self.crash_count += 1
        self.crash_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error_msg,
            "count": self.crash_count
        })
        
        # Analyze and heal
        diagnosis = self.analyze_crash(error_msg, stack_trace)
        success = self.apply_fix(diagnosis)
        
        return diagnosis, success
    
    def get_health_report(self) -> str:
        """Generate health report"""
        uptime = time.time() - self.last_restart
        return f"""
🩺 Auto-Healer Report:
- Crashes: {self.crash_count}
- Uptime: {uptime/60:.1f} minutes
- Healing actions: {len(self.healing_actions)}
- Last actions: {self.healing_actions[-3:] if self.healing_actions else 'None'}
"""
from py_clob_client.order_builder.constants import BUY

# [Added for Auto-Redeem]
from web3 import Web3
from eth_account import Account
from eth_abi import encode
import subprocess # Added for notifications

# Load environment
load_dotenv()

# --- Auto-Redeem Config ---
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS")

# [OPTIMIZATION] Reusable HTTP Session with Connection Pooling
def create_optimized_session():
    """Create optimized requests session with connection pooling and retries"""
    session = requests.Session()
    
    # Connection pool settings
    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=Retry(
            total=3,
            backoff_factor=0.1,
            status_forcelist=[500, 502, 503, 504]
        )
    )
    
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

# Global session for Binance API calls
BINANCE_SESSION = create_optimized_session()

from logging.handlers import RotatingFileHandler

# Setup logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler('bot.log', maxBytes=5*1024*1024, backupCount=3) # 5MB limit, keep 3 backups
    ]
)
logger = logging.getLogger(__name__)

from eip712_signer import sign_safe_tx

# Constants
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RELAYER_URL = "https://tx-relay.polymarket.com/relay"
CHAIN_ID = 137

@dataclass
class OrderBook:
    """
    Real-time order book with depth support and price caching.
    [OPTIMIZED] Added price caching during brief disconnections.
    """
    asset_id: str
    best_bid: float = 0.0
    best_bid_size: float = 0.0
    best_ask: float = 1.0
    best_ask_size: float = 0.0
    last_update: float = 0.0  # [新增] 最后更新时间戳
    update_count: int = 0     # [新增] 更新次数，用于判断数据新鲜度
    
    # [OPTIMIZED] Price caching for brief disconnections
    _cache_max_age: float = 5.0  # Use cached price for up to 5 seconds during disconnect
    _cached_bid: float = 0.0
    _cached_ask: float = 1.0
    _cache_timestamp: float = 0.0
    _disconnected_at: Optional[float] = None
    _consecutive_errors: int = 0
    
    def update(self, data: dict):
        """Update order book with validation and cache management"""
        now = time.time()
        
        if data.get("event_type") == "price_change":
            for change in data.get("price_changes", []):
                if change.get("asset_id") == self.asset_id:
                    # [CRITICAL-Fix] 验证价格合理性后再更新
                    new_bid = change.get("best_bid")
                    if new_bid is not None:
                        new_bid_float = float(new_bid)
                        # [Data-Quality] 严格过滤异常值 (0.01/0.99 是常见错误值)
                        if 0.02 <= new_bid_float <= 0.98:
                            self.best_bid = new_bid_float
                            # Update cache on valid update
                            self._cached_bid = new_bid_float
                        else:
                            logger.warning(f"[OrderBook] 忽略异常 best_bid: {new_bid_float} (超出有效范围 0.02~0.98)")
                    
                    new_bid_size = change.get("best_bid_size")
                    if new_bid_size is not None:
                        self.best_bid_size = float(new_bid_size)
                    
                    new_ask = change.get("best_ask")
                    if new_ask is not None:
                        new_ask_float = float(new_ask)
                        # [Data-Quality] 严格过滤异常值
                        if 0.02 <= new_ask_float <= 0.98:
                            self.best_ask = new_ask_float
                            # Update cache on valid update
                            self._cached_ask = new_ask_float
                        else:
                            logger.warning(f"[OrderBook] 忽略异常 best_ask: {new_ask_float} (超出有效范围 0.02~0.98)")
                    
                    new_ask_size = change.get("best_ask_size")
                    if new_ask_size is not None:
                        self.best_ask_size = float(new_ask_size)
                    
                    # [新增] 记录更新时间和次数
                    self.last_update = now
                    self._cache_timestamp = now
                    self.update_count += 1
                    
                    # Reset error counter on successful update
                    self._consecutive_errors = 0
                    self._disconnected_at = None

        elif data.get("event_type") == "book":
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            # [新增] 验证并更新 best_bid
            if bids:
                bid_price = float(bids[0]["price"])
                if 0.01 <= bid_price <= 0.99:
                    self.best_bid = bid_price
                    self.best_bid_size = float(bids[0]["size"])
                    self._cached_bid = bid_price
                else:
                    logger.warning(f"[OrderBook] Book更新忽略异常 bid: {bid_price}")
            
            # [新增] 验证并更新 best_ask
            if asks:
                ask_price = float(asks[0]["price"])
                if 0.01 <= ask_price <= 0.99:
                    self.best_ask = ask_price
                    self.best_ask_size = float(asks[0]["size"])
                    self._cached_ask = ask_price
                else:
                    logger.warning(f"[OrderBook] Book更新忽略异常 ask: {ask_price}")
            
            self.last_update = now
            self._cache_timestamp = now
            self.update_count += 1
            self._consecutive_errors = 0
            self._disconnected_at = None
    
    def is_fresh(self, max_age_sec: float = 30.0, allow_cached: bool = True) -> bool:
        """
        [OPTIMIZED] Check if data is fresh with caching support.
        
        Args:
            max_age_sec: Maximum age for fresh data
            allow_cached: If True, allows using cached prices up to 5s longer during disconnect
        """
        if self.last_update == 0:
            return False
        
        age = time.time() - self.last_update
        
        # Normal fresh check
        if age <= max_age_sec:
            return True
        
        # [OPTIMIZED] During brief disconnections, use cached prices
        if allow_cached and self._cache_timestamp > 0:
            cache_age = time.time() - self._cache_timestamp
            if cache_age <= (max_age_sec + self._cache_max_age):
                # Only log once per disconnect event
                if self._disconnected_at is None:
                    self._disconnected_at = time.time()
                    logger.info(f"[OrderBook] Using cached prices for {self.asset_id[:8]}... (age: {cache_age:.1f}s)")
                return True
        
        return False
    
    def get_price_with_fallback(self) -> Tuple[Optional[float], Optional[float], str]:
        """
        [OPTIMIZED] Get prices with fallback to cache during brief disconnections.
        
        Returns:
            Tuple of (bid, ask, source) where source indicates the price origin:
            - "live": Live WebSocket data
            - "cached": Cached prices during brief disconnect
            - "stale": Stale data (should not be used)
        """
        now = time.time()
        
        # Check live data freshness
        if self.last_update > 0 and (now - self.last_update) <= 30.0:
            return (self.best_bid, self.best_ask, "live")
        
        # Check cache freshness (up to 5s additional during disconnect)
        if self._cache_timestamp > 0 and (now - self._cache_timestamp) <= (30.0 + self._cache_max_age):
            return (self._cached_bid, self._cached_ask, "cached")
        
        # Data is stale
        return (None, None, "stale")
    
    def mark_disconnect(self):
        """[OPTIMIZED] Mark that a disconnection has occurred"""
        if self._disconnected_at is None:
            self._disconnected_at = time.time()
            self._consecutive_errors += 1
    
    def mark_reconnect(self):
        """[OPTIMIZED] Mark that connection has been restored"""
        if self._disconnected_at is not None:
            duration = time.time() - self._disconnected_at
            logger.info(f"[OrderBook] Connection restored after {duration:.1f}s")
        self._disconnected_at = None
        self._consecutive_errors = 0
    
    def is_valid(self) -> bool:
        """[新增] 检查价格是否有效且合理"""
        # [Data-Quality] 严格范围检查 (排除 0.01/0.99 错误值)
        if not (0.02 <= self.best_bid <= 0.98):
            return False
        if not (0.02 <= self.best_ask <= 0.98):
            return False
        # 价差检查 (ask 应该 >= bid)
        if self.best_ask < self.best_bid:
            return False
        # 价差过大检查 (>50% 可能是异常)
        spread = self.best_ask - self.best_bid
        if spread > 0.5:
            return False
        return True
    
    def get_mid_price(self) -> float:
        """[新增] 获取中间价"""
        return (self.best_bid + self.best_ask) / 2

@dataclass
class Market15m:
    condition_id: str
    question: str
    token_id_up: str
    token_id_down: str
    start_time: datetime
    end_time: datetime
    slug: str
    
    # Real-time data
    book_up: OrderBook = None
    book_down: OrderBook = None
    strike_price: Optional[float] = None  # The BTC price at start_time
    
    def __post_init__(self):
        self.book_up = OrderBook(self.token_id_up)
        self.book_down = OrderBook(self.token_id_down)
        self.fee_bps = 0 # Default

    @property
    def time_remaining(self) -> timedelta:
        return self.end_time - datetime.now(timezone.utc)
    
    @property
    def is_active(self) -> bool:
        return self.time_remaining.total_seconds() > 30

    @property
    def dynamic_fee(self) -> float:
        """
        Calculate dynamic fee based on Bid-Ask Spread.
        User Input: Fees can reach 3% dynamically.
        Formula: (Ask - Bid) / Ask (Cost of crossing the spread)
        """
        # [User Update] Remove fee pre-calculation. 
        # We assume 0 fee for signal generation (Raw Edge).
        return 0.0

    @property
    def up_price(self) -> float:
        return self.book_up.best_ask if self.book_up.best_ask > 0 else 0.5
    
    @property
    def down_price(self) -> float:
        return self.book_down.best_ask if self.book_down.best_ask > 0 else 0.5

class BinanceData:
    """Helper to fetch Binance data"""
    @staticmethod
    def get_candle_open(timestamp_ms: int) -> Optional[float]:
        """Get the Open price of the candle starting at timestamp"""
        try:
            # Kline interval 1m
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "startTime": timestamp_ms,
                "limit": 1
            }
            logger.debug(f"Fetching Binance Candle for TS: {timestamp_ms}")
            resp = BINANCE_SESSION.get(url, params=params, timeout=5)
            data = resp.json()
            if data and len(data) > 0:
                open_price = float(data[0][1])
                logger.info(f"Binance Open Price: {open_price}")
                return open_price
            return None
        except Exception as e:
            logger.error(f"Binance API error: {e}")
            return None

    @staticmethod
    def get_current_price() -> Optional[float]:
        try:
            resp = BINANCE_SESSION.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
            return float(resp.json()["price"])
        except:
            return None

    @staticmethod
    def get_order_book_imbalance(symbol="BTCUSDT", limit=20):
        """
        Get Order Book Imbalance (OBI) from Binance.
        Ratio = Bids Volume / Asks Volume
        """
        try:
            url = "https://api.binance.com/api/v3/depth"
            params = {"symbol": symbol, "limit": limit}
            resp = BINANCE_SESSION.get(url, params=params, timeout=2)
            data = resp.json()
            
            bids_list = data.get("bids", [])
            asks_list = data.get("asks", [])
            
            if not bids_list or not asks_list:
                # If API fails or returns empty, don't return 0.0 (which blocks trades).
                # Return 1.0 (Neutral) to avoid false positives.
                return 1.0
            
            bids = sum([float(x[1]) for x in bids_list])
            asks = sum([float(x[1]) for x in asks_list])
            
            if asks == 0: return 1.0
            return bids / asks
        except:
            return 1.0 # Neutral on error

    @staticmethod
    def get_history_df(limit=60) -> pd.DataFrame:
        """Fetch historical candles for TA calculation"""
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": "BTCUSDT", "interval": "1m", "limit": limit}
            resp = BINANCE_SESSION.get(url, params=params, timeout=3)
            data = resp.json()
            if not isinstance(data, list): return pd.DataFrame()
            
            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume", 
                "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore"
            ])
            df["close"] = df["close"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            return df
        except Exception as e:
            logger.error(f"Binance History Error: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_dynamic_volatility(limit=60) -> float:
        """Calculate StdDev of 1m price changes (USD) over last hour"""
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": "BTCUSDT", "interval": "1m", "limit": limit}
            resp = BINANCE_SESSION.get(url, params=params, timeout=2)
            data = resp.json()
            closes = [float(x[4]) for x in data]
            if len(closes) < 2: return 25.0
            
            # Calculate price differences
            diffs = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            
            # Standard Deviation
            if len(diffs) > 1:
                vol = math.sqrt(statistics.variance(diffs))
                return max(5.0, vol) # Minimum floor
            return 25.0
        except Exception as e:
            return 25.0 # Fallback

class DeribitData:
    """Helper to fetch Deribit Implied Volatility (Forward-looking)"""
    @staticmethod
    def get_dvol() -> Optional[float]:
        """Get BTC DVOL (Annualized Implied Volatility Index)"""
        try:
            url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
            params = {"currency": "BTC", "resolution": "1D", "end_timestamp": int(time.time()*1000)}
            
            resp = requests.get(url, params={"currency": "BTC", "start_timestamp": int(time.time()*1000) - 86400000, "end_timestamp": int(time.time()*1000), "resolution": "1D"}, timeout=3)
            data = resp.json()
            
            if 'result' in data and 'data' in data['result'] and len(data['result']['data']) > 0:
                dvol_close = data['result']['data'][-1][4] # Close value
                return float(dvol_close)
                
            return 55.0 
        except Exception as e:
            logger.error(f"Deribit DVOL fetch failed: {e}")
            return None

class PolyPriceFetcher:
    """[Data-Quality] Backup price fetcher using REST API when WebSocket fails"""
    @staticmethod
    def get_price(token_id: str) -> Optional[Tuple[float, float]]:
        """Fetch best bid/ask from CLOB REST API"""
        try:
            url = f"{CLOB_HOST}/book"
            params = {"token_id": token_id}
            resp = requests.get(url, params=params, timeout=3)
            data = resp.json()
            
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            if bids and asks:
                best_bid = float(bids[0]["price"])
                best_ask = float(asks[0]["price"])
                # Validate
                if 0.02 <= best_bid <= 0.98 and 0.02 <= best_ask <= 0.98 and best_ask >= best_bid:
                    return (best_bid, best_ask)
            return None
        except Exception as e:
            logger.debug(f"[BackupPrice] Fetch error: {e}")
            return None

class PolyLiquidity:
    """Analyzer for Polymarket Order Book Depth & Quality"""
    @staticmethod
    def get_token_depth(token_id: str) -> dict:
        """
        Fetch Order Book snapshot and calculate effective liquidity.
        Returns:
            - bid_depth_usd: Total bid size within 5% of best price
            - ask_depth_usd: Total ask size within 5% of best price
            - spread: Bid-Ask Spread
        """
        try:
            url = f"{CLOB_HOST}/book"
            params = {"token_id": token_id}
            resp = requests.get(url, params=params, timeout=2)
            data = resp.json()
            
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            if not bids or not asks:
                return {"bid_depth": 0, "ask_depth": 0, "spread": 0.99}
            
            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            
            # Calculate Depth (Liquidity within 5 cents or 5% range)
            bid_limit = best_bid - 0.05
            ask_limit = best_ask + 0.05
            
            bid_depth = sum([float(x["size"]) * float(x["price"]) for x in bids if float(x["price"]) >= bid_limit])
            ask_depth = sum([float(x["size"]) * float(x["price"]) for x in asks if float(x["price"]) <= ask_limit])
            
            return {
                "bid_depth": bid_depth,
                "ask_depth": ask_depth,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": best_ask - best_bid
            }
        except Exception as e:
            logger.error(f"Poly Liquidity Check Error: {e}")
            return {"bid_depth": 0, "ask_depth": 0, "spread": 0.99}

class MarketCycleManager:
    """Manages finding active markets"""
    def __init__(self):
        self.past_markets = []

    def fetch_market(self) -> Optional[Market15m]:
        try:
            # Calculate current 15m cycle strictly by time
            now = datetime.now(timezone.utc)
            current_ts = int(now.timestamp())
            current_15m_ts = (current_ts // 900) * 900
            
            # Use calculated timestamp for slug AND start_time
            slug = f"btc-updown-15m-{current_15m_ts}"
            
            # Start time is strictly the 15m boundary
            start_time = datetime.fromtimestamp(current_15m_ts, timezone.utc)
            # End time is +15m
            end_time = start_time + timedelta(minutes=15)
            
            resp = requests.get(f"{GAMMA_API}/events?slug={slug}", timeout=10)
            events = resp.json()
            
            if not events:
                # Try next slot if we are close to end? No, stick to current.
                return None
                
            event = events[0]
            if event.get("closed"): return None
            
            markets = event.get("markets", [])
            if not markets or not markets[0].get("acceptingOrders"): return None
            
            m_data = markets[0]
            token_ids = json.loads(m_data.get("clobTokenIds", "[]"))
            outcomes = json.loads(m_data.get("outcomes", '["Up", "Down"]'))
            
            if outcomes[0].lower() == "up":
                t_up, t_down = token_ids[0], token_ids[1]
            else:
                t_up, t_down = token_ids[1], token_ids[0]
            
            return Market15m(
                condition_id=m_data.get("conditionId"),
                question=m_data.get("question", event.get("title")),
                token_id_up=t_up,
                token_id_down=t_down,
                start_time=start_time, # Use calculated strict time
                end_time=end_time,     # Use calculated strict time
                slug=event.get("slug")
            )
        except Exception as e:
            logger.error(f"Fetch market error: {e}")
            return None

class ProbabilityStrategy:
    """Calculates Fair Value based on Normal Distribution"""
    
    def __init__(self):
        self.volatility_per_min = 25.0  # Default
    
    def update_volatility(self, new_vol: float):
        self.volatility_per_min = new_vol

    def calculate_prob_up(self, current_price: float, strike_price: float, minutes_left: float) -> float:
        """
        Calculate Probability(Final Price > Strike)
        Assumes Brownian motion (Normal distribution of price changes).
        """
        if minutes_left <= 0:
            return 1.0 if current_price >= strike_price else 0.0
            
        # Standard Deviation for the remaining time
        # sigma_t = sigma_1min * sqrt(t)
        sigma_t = self.volatility_per_min * math.sqrt(minutes_left)
        
        if sigma_t == 0:
            return 1.0 if current_price >= strike_price else 0.0
            
        # Z-score: How many std devs is current price away from strike?
        # If current > strike, Z is positive.
        z_score = (current_price - strike_price) / sigma_t
        
        # Cumulative Distribution Function (CDF)
        prob_up = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
        
        return prob_up

    def update_from_deribit(self, dvol: float, current_price: float):
        """
        Convert Annualized DVOL (e.g., 50.0) to Minute Volatility (USD)
        Formula: Sigma_min = Price * (DVOL/100) / sqrt(minutes_in_year)
        Minutes in year approx 525,600
        """
        if dvol is None or dvol <= 0: return
        
        minutes_in_year = 365 * 24 * 60
        annual_std_dev = dvol / 100.0
        
        # Convert to 1-minute std dev (percentage)
        min_std_dev_pct = annual_std_dev / math.sqrt(minutes_in_year)
        
        # Convert to USD terms based on current price
        self.volatility_per_min = current_price * min_std_dev_pct
        # logger.info(f"Deribit DVOL: {dvol} -> Sigma_min: ${self.volatility_per_min:.2f}")

import joblib

class AsyncTradeLogger:
    def __init__(self, filename):
        self.filename = filename
        self.queue = asyncio.Queue()
        self.running = True

    async def run(self):
        """Worker task to write logs to disk asynchronously"""
        logger.info(f"💾 Async Trade Logger started for {self.filename}")
        while self.running:
            try:
                record = await self.queue.get()
                if record is None: break # Shutdown signal
                
                with open(self.filename, "a") as f:
                    f.write(json.dumps(record) + "\n")
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Async log write error: {e}")
                await asyncio.sleep(1)

    def log(self, record):
        """Thread-safe way to add a record to the queue"""
        # Add timestamp if missing
        if "time" not in record:
            record["time"] = datetime.now(timezone.utc).isoformat()
        self.queue.put_nowait(record)

    async def stop(self):
        self.running = False
        await self.queue.put(None)

class PolymarketBotV3:
    def __init__(self):
        self.running = True
        self.paper_trade = False # Default, will be overridden by config
        self.positions = []
        self.cycle_manager = MarketCycleManager()
        self.strategy = ProbabilityStrategy()
        
        # Init Clob Client for Data Fetching
        # Load keys (Support both PK and PRIVATE_KEY)
        key = os.getenv("PK") or os.getenv("PRIVATE_KEY")
        chain_id = CHAIN_ID
        creds = None
        
        # [DYNAMIC] Derive CLOB API Key from private key (EIP-712)
        # This ensures the Key has proper trading permissions
        creds = None
        if key:
            try:
                # Create temporary client to derive API key
                temp_client = ClobClient(CLOB_HOST, key=key, chain_id=chain_id)
                creds = temp_client.derive_api_key()
                logger.info(f"🔐 Derived CLOB API Key: {creds.api_key[:20]}...")
            except Exception as e:
                logger.error(f"Failed to derive CLOB API Key: {e}")
                logger.warning("⚠️ Trading may not work without proper L2 Key")

        # Load Funder Address (for Safe/Proxy trading)
        funder = os.getenv("FUNDER_ADDRESS")

        # [Builder API] Load Builder Credentials for dual-signature
        # L2 Key (creds) handles permissions, Builder Key handles attribution
        builder_config = None
        if os.getenv("POLY_BUILDER_API_KEY"):
            try:
                builder_creds = BuilderApiKeyCreds(
                    key=os.getenv("POLY_BUILDER_API_KEY"),
                    secret=os.getenv("POLY_BUILDER_API_SECRET"),
                    passphrase=os.getenv("POLY_BUILDER_API_PASSPHRASE")
                )
                builder_config = BuilderConfig(local_builder_creds=builder_creds)
                logger.info("👷 Builder API Configured (Attribution + Rewards)")
            except Exception as e:
                logger.error(f"Builder Config Error: {e}")

        try:
            if key:
                # Set signature_type for Gnosis Safe (2=POLY_GNOSIS_SAFE)
                # 0=EOA, 1=POLY_PROXY, 2=POLY_GNOSIS_SAFE
                sig_type = 2 if funder else 0
                self.clob_client = ClobClient(
                    CLOB_HOST, 
                    key=key, 
                    chain_id=chain_id, 
                    creds=creds, 
                    funder=funder,
                    builder_config=builder_config,
                    signature_type=sig_type
                )
                logger.info(f"✅ CLOB Client 已连接 (Signer: {key[:6]}... | Funder: {funder} | SigType: {sig_type})")
            else:
                self.clob_client = None
                logger.warning("⚠️ 未找到私钥 (PK/PRIVATE_KEY). 运行在受限模式.")
        except:
            self.clob_client = None
            logger.warning("CLOB Client not init (Fees will be estimated)")
        
        # Trading Parameters (Loaded from config)
        self.config_file = "config.json"
        self.load_config()
        
        # [P1-Fix] Positions persistence
        self.positions_file = "positions.json"
        self._load_positions()
        
        # Performance History
        self.performance_history = [] 
        
        # [Surgical Refactor] Async Logger
        self.trade_logger = AsyncTradeLogger("paper_trades.jsonl")
        
        # Load ML Model (Prefer V2.0 if exists)
        self.ml_model = None
        model_paths = ["ml_model_v2.pkl", "ml_model_v1.pkl"]
        for p in model_paths:
            if os.path.exists(p):
                try:
                    self.ml_model = joblib.load(p)
                    logger.info(f"🧠 ML Model Loaded: {p}")
                    break
                except Exception as e:
                    logger.error(f"Failed to load ML model {p}: {e}")
        
        # [Notification Control]
        self.notified_signals = set()
        self.current_market_slug = None

    def load_config(self):
        """Load parameters from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    conf = json.load(f)
                    self.stop_loss_pct = conf.get("stop_loss_pct", 0.35)
                    self.safety_margin_pct = conf.get("safety_margin_pct", 0.0006)
                    self.min_edge = conf.get("min_edge", 0.08)
                    self.fee_pct = conf.get("fee_pct", 0.03)
                    self.obi_threshold = conf.get("obi_threshold", 1.5) # New Param
                    self.trade_amount_usd = conf.get("trade_amount_usd", 1.0) # [New] Load trade amount
                    self.min_liquidity_usd = conf.get("min_liquidity_usd", 200) # [New] Liquidity threshold
                    self.execution_enabled = conf.get("execution_enabled", False) # Safety Switch
                    self.paper_trade = conf.get("paper_trade", False) # Paper Trading Mode
                    # [CRITICAL] 实盘双重确认机制
                    self.live_trading_enabled = conf.get("live_trading_enabled", False)
                    # Auto-redeem setting
                    self.auto_redeem_enabled = conf.get("auto_redeem_enabled", False)
                    logger.info(f"⚙️ 配置已加载: SL {self.stop_loss_pct:.0%} | Edge {self.min_edge:.0%} | Amount ${self.trade_amount_usd} | Liquidity ${self.min_liquidity_usd} | Paper {self.paper_trade} | Live {self.live_trading_enabled} | AutoRedeem {self.auto_redeem_enabled}")
            else:
                logger.warning("⚠️ 配置文件未找到，使用默认参数")
                # Defaults already set in init? No, setting them now if missing
                if not hasattr(self, 'stop_loss_pct'): self.stop_loss_pct = 0.35
                if not hasattr(self, 'safety_margin_pct'): self.safety_margin_pct = 0.0006
                if not hasattr(self, 'min_edge'): self.min_edge = 0.08
                if not hasattr(self, 'fee_pct'): self.fee_pct = 0.03
                if not hasattr(self, 'obi_threshold'): self.obi_threshold = 1.5
                if not hasattr(self, 'trade_amount_usd'): self.trade_amount_usd = 1.0
                if not hasattr(self, 'min_liquidity_usd'): self.min_liquidity_usd = 200
                if not hasattr(self, 'execution_enabled'): self.execution_enabled = False
                if not hasattr(self, 'paper_trade'): self.paper_trade = False
                if not hasattr(self, 'live_trading_enabled'): self.live_trading_enabled = False
                if not hasattr(self, 'auto_redeem_enabled'): self.auto_redeem_enabled = False
        except Exception as e:
            logger.error(f"Config load error: {e}")

    def _load_positions(self):
        """[P1-Fix] 加载持久化的持仓"""
        try:
            if os.path.exists(self.positions_file):
                with open(self.positions_file, "r") as f:
                    data = json.load(f)
                    self.positions = data.get("positions", [])
                    logger.info(f"💾 已加载 {len(self.positions)} 个持仓记录")
            else:
                self.positions = []
        except Exception as e:
            logger.error(f"加载持仓失败: {e}")
            self.positions = []
    
    async def _sync_positions_from_exchange(self):
        """[P0-Fix] 从交易所同步真实持仓"""
        if not self.clob_client or self.paper_trade:
            return
        
        try:
            logger.info("🔄 同步交易所持仓...")
            # 获取市场数据来重建持仓
            exchange_positions = await self.clob_client.get_positions()
            
            if exchange_positions:
                # 清理本地已关闭的持仓
                open_local = [p for p in self.positions if p.get("status") == "OPEN"]
                
                # 对比交易所持仓
                for local_pos in open_local:
                    matching = None
                    for ex_pos in exchange_positions:
                        if ex_pos.get("market_slug") == local_pos.get("market_slug"):
                            matching = ex_pos
                            break
                    
                    if not matching:
                        # 交易所无此持仓，可能已平仓
                        logger.warning(f"⚠️ 交易所无持仓: {local_pos['market_slug']}")
                        local_pos["status"] = "CLOSED_EXTERNALLY"
                
                self._save_positions()
                logger.info(f"✅ 持仓同步完成: {len(self.positions)} 本地, {len(exchange_positions)} 交易所")
        except Exception as e:
            logger.error(f"同步持仓失败: {e}")
    
    async def query_exchange_positions(self) -> list:
        """[NEW] 查询交易所真实持仓详情"""
        if not self.clob_client:
            logger.error("❌ CLOB Client 未初始化")
            return []
        
        try:
            logger.info("🔍 查询交易所持仓...")
            # 使用 get_balance 和账户信息来获取持仓
            # py_clob_client 可能没有直接的 get_positions
            # 通过查询余额来判断
            balance = self.clob_client.get_balance()
            
            if not balance:
                logger.info("📭 交易所无持仓")
                return []
            
            logger.info(f"💰 账户余额查询完成")
            return []
        except Exception as e:
            logger.error(f"❌ 查询持仓失败: {e}")
            return []
    
    async def query_exchange_orders(self, status: str = "OPEN") -> list:
        """[NEW] 查询交易所订单状态"""
        if not self.clob_client:
            logger.error("❌ CLOB Client 未初始化")
            return []
        
        try:
            logger.info(f"🔍 查询{status}订单...")
            # 获取所有市场
            orders = self.clob_client.get_orders()
            
            if not orders:
                logger.info(f"📭 无{status}订单")
                return []
            
            # 过滤状态
            filtered = [o for o in orders if o.get('status') == status]
            
            logger.info(f"📋 {status}订单: {len(filtered)} 笔")
            for i, order in enumerate(filtered[:5], 1):  # 只显示前5笔
                oid = order.get('id', 'N/A')[:16]
                side = order.get('side', 'N/A')
                price = order.get('price', 0)
                size = order.get('size', 0)
                filled = order.get('maker_amount', 0) or 0
                logger.info(f"  {i}. {oid}... | {side} {size:.2f} @ ${price:.2f} | 成交: {filled:.2f}")
            
            if len(filtered) > 5:
                logger.info(f"  ... 还有 {len(filtered)-5} 笔")
            
            return filtered
        except Exception as e:
            logger.error(f"❌ 查询订单失败: {e}")
            return []
    
    def _save_positions(self):
        """[P1-Fix] 保存持仓到文件"""
        try:
            with open(self.positions_file, "w") as f:
                json.dump({"positions": self.positions, "updated": datetime.now(timezone.utc).isoformat()}, f)
        except Exception as e:
            logger.error(f"保存持仓失败: {e}")
    
    def analyze_performance(self):
        """Self-Correction: Adjust parameters based on recent performance"""
        try:
            if not os.path.exists("paper_trades.jsonl"): return
            
            # File Size Protection: If > 10MB, rotate it
            if os.path.getsize("paper_trades.jsonl") > 10 * 1024 * 1024:
                logger.info("维护: paper_trades.jsonl 过大，进行归档清理...")
                os.rename("paper_trades.jsonl", f"paper_trades_{int(time.time())}.jsonl")
            
            wins = 0
            losses = 0
            gross_profit = 0.0
            gross_loss = 0.0
            recent_trades = []
            
            with open("paper_trades.jsonl", "r") as f:
                for line in f:
                    try:
                        trade = json.loads(line)
                        if "pnl" in trade: # Closed trade
                            recent_trades.append(trade)
                    except: pass
            
            # Analyze last 20 closed trades for statistical significance
            recent_trades = recent_trades[-20:]
            if not recent_trades: return
            
            for t in recent_trades:
                pnl = float(t["pnl"])
                if pnl > 0: 
                    wins += 1
                    gross_profit += pnl
                else: 
                    losses += 1
                    gross_loss += abs(pnl)
            
            total = wins + losses
            if total == 0: return
            
            win_rate = wins / total
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            avg_win = gross_profit / wins if wins > 0 else 0
            avg_loss = gross_loss / losses if losses > 0 else 0
            
            # Log Core Metrics for User
            # logger.info(f"📊 业绩分析 (最近{total}笔):")
            # logger.info(f"   胜率: {win_rate:.0%} | 盈亏比 (Profit Factor): {profit_factor:.2f}")
            
            # Since we now use external config, we DON'T auto-adjust inside python code anymore
            # We just log stats. Auto-adjustment should be done by an external agent via config.json
            
        except Exception as e:
            logger.error(f"Auto-tune error: {e}")

    async def config_watcher(self):
        """Watch for config changes and hot-reload"""
        last_mtime = 0
        while self.running:
            try:
                if os.path.exists(self.config_file):
                    mtime = os.path.getmtime(self.config_file)
                    if mtime > last_mtime:
                        if last_mtime > 0: # Skip first run
                            logger.info("🔄 检测到配置更新，正在热加载...")
                            self.load_config()
                        last_mtime = mtime
            except: pass
            await asyncio.sleep(60)

    async def run(self):
        logger.info("启动 V3 智能策略机器人 (Probability/Fair Value)...")
        # logger.info(f"配置: 止损线 -{self.stop_loss_pct*100}% | 模拟费率 {self.fee_pct*100}%") # Moved to load_config
        if self.paper_trade: logger.info("[模式] 模拟交易 (全权限托管)")
        
        # Start Background Tasks with exception handling
        async def _task_wrapper(coro, name):
            """Wrapper to catch and log task exceptions"""
            try:
                await coro
            except Exception as e:
                logger.error(f"[Task:{name}] 异常: {e}")
        
        asyncio.create_task(_task_wrapper(self.trade_logger.run(), "TradeLogger"))
        asyncio.create_task(_task_wrapper(self.auto_retrain_loop(), "AutoRetrain"))
        asyncio.create_task(_task_wrapper(self.config_watcher(), "ConfigWatcher"))
        
        while self.running:
            try:
                # Run Auto-Tuning every cycle
                self.analyze_performance()
                
                # [P0-Fix] 每10分钟同步一次交易所持仓
                if int(time.time()) % 600 == 0:
                    await self._sync_positions_from_exchange()
                
                # Cleanup old positions from previous cycles
                self.positions = [p for p in self.positions if (datetime.now(timezone.utc) - datetime.fromisoformat(p["timestamp"])).total_seconds() < 3600]

                market = self.cycle_manager.fetch_market()
                if not market:
                    logger.info("等待活跃市场...")
                    await asyncio.sleep(10)
                    continue
                
                # Fetch Strike Price (Open Price)
                # Ensure the market start time has passed so the candle exists
                now = datetime.now(timezone.utc)
                if now < market.start_time:
                    logger.info(f"等待市场开始: {market.start_time}")
                    await asyncio.sleep(5)
                    continue
                
                logger.info(f"选中市场: {market.question}")
                
                # Get Strike Price (Binance)
                # Need timestamp in ms
                start_ts_ms = int(market.start_time.timestamp() * 1000)
                
                # Retry fetching strike until available (Binance might delay 1-2s)
                strike_price = None
                for _ in range(5):
                    strike_price = BinanceData.get_candle_open(start_ts_ms)
                    if strike_price: break
                    logger.info("等待 Strike Price (Binance Candle)...")
                    await asyncio.sleep(2)
                
                if not strike_price:
                    logger.error("无法获取 Strike Price，跳过此周期")
                    await asyncio.sleep(30)
                    continue
                    
                market.strike_price = strike_price
                logger.info(f"🎯 Strike Price: ${strike_price:,.2f}")
                
                # Fetch Real Dynamic Fee
                # if self.clob_client:
                #     try:
                #         # Note: py_clob_client doesn't have a public get_fee method in some versions
                #         # We will rely on Spread + fixed conservative buffer
                #         pass
                #     except: pass
                
                # Start Trading Loop for this Market
                await self.trade_loop(market)
                
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(5)

    async def auto_retrain_loop(self):
        """Automatically retrain ML model every 3 hours"""
        while self.running:
            await asyncio.sleep(3 * 3600) # Wait 3 hours
            logger.info("🧠 自动进化: 开始重新训练模型...")
            try:
                # Use current working directory relative paths
                proc = await asyncio.create_subprocess_shell("python3 augment_data.py")
                await proc.wait()
                
                proc = await asyncio.create_subprocess_shell("python3 train_ml.py")
                await proc.wait()
                
                # Reload model
                if os.path.exists("ml_model_v1.pkl"):
                    self.ml_model = joblib.load("ml_model_v1.pkl")
                    logger.info("✅ 模型已更新并重新加载!")
            except Exception as e:
                logger.error(f"Auto-retrain failed: {e}")

    async def _ws_listen_wrapper(self, ws_manager):
        """[Bugfix] WebSocket listener wrapper with exception handling"""
        try:
            await ws_manager.listen()
        except Exception as e:
            logger.error(f"[WebSocket] 监听异常: {e}")
        finally:
            logger.warning("[WebSocket] 监听任务结束")
    
    async def trade_loop(self, market: Market15m):
        # For brevity in this write, using polling loop which is fine for 5s intervals.
        # Ideally keep WS from V2.
        
        ws_manager = WebSocketManagerV3(market)
        try:
            await ws_manager.connect()
            asyncio.create_task(self._ws_listen_wrapper(ws_manager))
            logger.info("[WebSocket] 连接成功，监听已启动")
        except Exception as e:
            logger.error(f"[WebSocket] 连接失败: {e}，将使用轮询模式")
        
        logger.info(f"开始监控... 结算时间: {market.end_time}")
        
        # Log initial WebSocket connection stats
        conn_stats = ws_manager.get_connection_stats()
        logger.info(f"[WebSocket] 初始连接状态: {conn_stats}")
        
        ws_reconnect_count = 0
        last_stats_log = time.time()
        
        while self.running and market.is_active:
            # [OPTIMIZED] Log WebSocket stats every 60 seconds
            now = time.time()
            if now - last_stats_log >= 60:
                conn_stats = ws_manager.get_connection_stats()
                if conn_stats["connected"]:
                    logger.info(f"[WebSocket] 连接正常 | 运行时间: {conn_stats['uptime_sec']:.0f}s | 接收消息: {conn_stats['messages_received']}")
                else:
                    logger.warning(f"[WebSocket] 连接断开 | 重连尝试: {conn_stats['reconnect_attempts']}")
                    ws_reconnect_count += 1
                    # If too many reconnects, trigger a full WebSocket restart
                    if ws_reconnect_count >= 5:
                        logger.warning("[WebSocket] 重连次数过多，尝试完整重启...")
                        try:
                            await ws_manager.close()
                            await asyncio.sleep(1)
                            await ws_manager.connect()
                            ws_reconnect_count = 0
                            logger.info("[WebSocket] 完整重启成功")
                        except Exception as e:
                            logger.error(f"[WebSocket] 完整重启失败: {e}")
                last_stats_log = now
            
            # 1. Get Data
            current_btc = BinanceData.get_current_price()
            if not current_btc:
                await asyncio.sleep(2)
                continue
                
            # Update Dynamic Volatility (every ~1 min)
            if int(time.time()) % 60 == 0:
                # 1. Try Deribit First (Forward Looking)
                dvol = DeribitData.get_dvol()
                if dvol:
                    self.strategy.update_from_deribit(dvol, current_btc)
                else:
                    # 2. Fallback to Binance Historical
                    new_vol = BinanceData.get_dynamic_volatility()
                    self.strategy.update_volatility(new_vol)
                # logger.info(f"🌊 动态波动率更新完成")

            time_left = market.time_remaining.total_seconds() / 60.0 # minutes
            
            # 2. Calculate Fair Value
            prob_up = self.strategy.calculate_prob_up(current_btc, market.strike_price, time_left)
            prob_down = 1.0 - prob_up
            
            # [Pre-Fetch] Get Poly Liquidity Data needed for ML & Filters
            # We need to decide which token to check. Let's check BOTH or just the one we lean towards?
            # For ML, general market quality matters. Let's check the UP token depth as a proxy or average?
            # Better: Check both briefly or just the spread/depth of the orderbook general.
            # Using token_id_up as reference.
            liq_data = PolyLiquidity.get_token_depth(market.token_id_up)
            
            # 3. Compare with Market (Moved up for scope)
            # [OPTIMIZED] Use cached prices during brief disconnections
            up_bid, up_ask, up_source = market.book_up.get_price_with_fallback()
            down_bid, down_ask, down_source = market.book_down.get_price_with_fallback()
            
            # Log if using cached prices
            if up_source == "cached":
                logger.debug(f"[TradeLoop] UP token using cached price: {up_ask:.4f}")
            if down_source == "cached":
                logger.debug(f"[TradeLoop] DOWN token using cached price: {down_ask:.4f}")
            
            mkt_up = up_ask if up_ask and up_ask > 0 else market.up_price
            mkt_down = down_ask if down_ask and down_ask > 0 else market.down_price

            # 3. AI Prediction Boost (XGBoost V4)
            if self.ml_model:
                try:
                    # 1. Fetch History for TA
                    hist_df = BinanceData.get_history_df(limit=60)
                    if not hist_df.empty and len(hist_df) > 30:
                        # 2. Calc Features
                        rsi = ta.rsi(hist_df["close"], length=14)
                        atr = ta.atr(hist_df["high"], hist_df["low"], hist_df["close"], length=14)
                        bb = ta.bbands(hist_df["close"], length=20, std=2)
                        ema_short = ta.ema(hist_df["close"], length=9)
                        ema_long = ta.ema(hist_df["close"], length=21)

                        rsi_val = rsi.iloc[-1] if not rsi.empty else 50
                        atr_val = atr.iloc[-1] if not atr.empty else 0
                        
                        bb_pct_val = 0.5
                        if bb is not None and not bb.empty:
                            bb_cols = [c for c in bb.columns if c.startswith("BBP")]
                            if bb_cols:
                                bb_pct_val = bb.iloc[-1][bb_cols[0]]
                        
                        trend_ema = 0
                        if ema_short is not None and ema_long is not None:
                            trend_ema = 1 if ema_short.iloc[-1] > ema_long.iloc[-1] else -1

                        # 3. Construct Feature Vector (NOW INCLUDING POLY DATA)
                        now_utc = datetime.now(timezone.utc)
                        # [Pricing/Time Enhancement]
                        pricing_power = liq_data.get('bid_depth', 0) - liq_data.get('ask_depth', 0)
                        price_time = (current_btc - market.strike_price) * (16 - time_left)

                        # [Fix] v2 model expects 15 features
                        X_df = pd.DataFrame([{
                            'direction_code': 1, 
                            'hour': now_utc.hour,
                            'dayofweek': now_utc.weekday(),
                            'rsi_14': rsi_val,
                            'atr_14': atr_val,
                            'bb_pct': bb_pct_val,
                            'trend_ema': trend_ema,
                            # [New] Poly Microstructure Features
                            'poly_spread': liq_data.get('spread', 0.01),
                            'poly_bid_depth': liq_data.get('bid_depth', 0),
                            'poly_ask_depth': liq_data.get('ask_depth', 0),
                            # [Added for V2]
                            'strike': market.strike_price,
                            'diff_from_strike': current_btc - market.strike_price,
                            'minutes_remaining': time_left,
                            # [V2 Features] Required for ml_model_v2.pkl (15 features total)
                            'price_time_interaction': price_time,
                            'pricing_power_index': pricing_power
                        }])
                        
                        # 4. Predict
                        # XGBoost predict() returns class [0, 1]
                        # predict_proba() returns [[prob_0, prob_1]]
                        probs = self.ml_model.predict_proba(X_df)[0]
                        ai_prob_up = probs[1] # Probability of Class 1 (WIN)
                        
                        # [User Update] Hybrid Prediction: 30% AI + 70% Math Model (Recalibrated)
                        math_prob = prob_up
                        prob_up = (ai_prob_up * 0.3) + (math_prob * 0.7)
                        prob_down = 1.0 - prob_up
                        
                        logger.info(f"⚖️ 混合预测 (30/70): AI({ai_prob_up:.1%})x30% + Math({math_prob:.1%})x70% = {prob_up:.1%}")
                        
                except Exception as e:
                    logger.error(f"AI Prediction Error: {e}")

            # 4. Decision
            # Calculate dynamic Safety Margin to account for Binance vs Chainlink deviation
            # using percentage (0.05%) instead of fixed amount
            safety_margin = market.strike_price * self.safety_margin_pct
            
            diff = current_btc - market.strike_price
            
            # [P1-Fix] 检查止盈止损 (统一处理避免竞争)
            await self.check_exit_conditions(market)

            # --- [New] Cooldown Period Filter ---
            # Don't trade in the first 15 seconds of the market cycle to avoid opening noise
            time_since_start = (datetime.now(timezone.utc) - market.start_time).total_seconds()
            if time_since_start < 15:
                logger.info(f"⏳ 开盘冷静期: 等待趋势确认 ({int(time_since_start)}/15s) - 跳过")
                await asyncio.sleep(2)
                continue

            # If within safety margin (ambiguous zone), force neutral probability or skip
            if abs(diff) < safety_margin:
                # Calculate Edge even if skipping, for logging
                fee = market.dynamic_fee
                edge_up = prob_up - mkt_up - fee
                edge_down = prob_down - mkt_down - fee
                
                # [Fix] Edge 极端值截断保护 (日志记录时也应用)
                EDGE_LIMIT = 0.50
                edge_up = max(min(edge_up, EDGE_LIMIT), -EDGE_LIMIT)
                edge_down = max(min(edge_down, EDGE_LIMIT), -EDGE_LIMIT)
                
                log_msg = (
                    f"剩余 {time_left:.1f}m | BTC: ${current_btc:.1f} (Diff: ${diff:+.1f}) | "
                    f"Poly UP: ${mkt_up:.2f} | Prob UP: {prob_up:.1%} | "
                    f"Edge UP: {edge_up:+.1%} | Edge DOWN: {edge_down:+.1%} | "
                    f"状态: 安全边际内(${safety_margin:.1f}) - 跳过"
                )
                if int(time.time()) % 10 == 0:
                    logger.info(log_msg)
                await asyncio.sleep(2)
                continue
            
            # [User Rule] Serial Execution: One trade at a time.
            # Must close/settle previous trade before opening new one.
            if len(self.positions) > 0:
                # We have an active position, so we just monitor it (skip entry logic)
                if int(time.time()) % 10 == 0:
                     logger.info(f"⏳ 持仓锁定: 等待当前交易结束 (PnL Monitor active)")
                await asyncio.sleep(2)
                continue
            
            if abs(diff) >= safety_margin:
                # Signal if Edge > Threshold
                # Use Dynamic Fee
                fee = market.dynamic_fee
                
                edge_up = prob_up - mkt_up - fee
                edge_down = prob_down - mkt_down - fee
                
                # [Fix] Edge 极端值截断保护 (防止 ±80%+ 异常信号)
                EDGE_LIMIT = 0.50  # 限制在 ±50%
                if abs(edge_up) > EDGE_LIMIT:
                    logger.warning(f"⚠️ Edge UP 极端值截断: {edge_up:+.1%} → {max(min(edge_up, EDGE_LIMIT), -EDGE_LIMIT):+.1%}")
                    edge_up = max(min(edge_up, EDGE_LIMIT), -EDGE_LIMIT)
                if abs(edge_down) > EDGE_LIMIT:
                    logger.warning(f"⚠️ Edge DOWN 极端值截断: {edge_down:+.1%} → {max(min(edge_down, EDGE_LIMIT), -EDGE_LIMIT):+.1%}")
                    edge_down = max(min(edge_down, EDGE_LIMIT), -EDGE_LIMIT)
                
                log_msg = (
                    f"剩余 {time_left:.1f}m | BTC: ${current_btc:.1f} (Diff: ${diff:+.1f}) | "
                    f"Poly UP: ${mkt_up:.2f} | Prob UP: {prob_up:.1%} | "
                    f"Edge UP: {edge_up:+.1%} | Edge DOWN: {edge_down:+.1%}"
                )
                
                # Only log every 10s
                if int(time.time()) % 10 == 0:
                    logger.info(log_msg)
                
                # Execute Trade (With OBI Filter & Poly Liquidity Check)
                
                # [New] Poly Liquidity Gatekeeper
                # Check target token depth before entering
                # We already fetched UP token depth in `liq_data` at step 2.
                # If target is DOWN, we might want to check DOWN token depth specifically, 
                # but generally checking UP token gives good idea of spread.
                # Let's refine: If going DOWN, fetch DOWN token depth.
                
                if edge_up > self.min_edge:
                    target_liq = liq_data # Already fetched UP
                    target_dir = "UP"
                else:
                    # Fetch DOWN token depth on demand
                    target_liq = PolyLiquidity.get_token_depth(market.token_id_down)
                    target_dir = "DOWN"
                
                # Check 1: Do we have enough Ask Depth to buy?
                if target_liq["ask_depth"] < self.min_liquidity_usd:
                    logger.info(f"🛑 流动性不足: Ask Depth ${target_liq['ask_depth']:.0f} < ${self.min_liquidity_usd} - 跳过")
                    continue
                    
                # Check 2: Liquidity Ratio
                liq_ratio = target_liq["bid_depth"] / target_liq["ask_depth"] if target_liq["ask_depth"] > 0 else 0
                
                # UP: Need Edge (OBI filter removed per Sir's request)
                if edge_up > self.min_edge:
                    if liq_ratio < 0.2: 
                         logger.info(f"🛑 拦截 UP 信号: Poly 盘口失衡 (Ratio {liq_ratio:.2f} < 0.2)")
                    else:
                         await self.execute_trade(market, "UP", 0.05, target_liq)
                        
                # DOWN: Need Edge (OBI filter removed per Sir's request)
                elif edge_down > self.min_edge:
                    if liq_ratio > 5.0: 
                         logger.info(f"🛑 拦截 DOWN 信号: Poly 盘口失衡 (Ratio {liq_ratio:.2f} > 5.0)")
                    else:
                        await self.execute_trade(market, "DOWN", 0.05, target_liq)
                        
            elif int(time.time()) % 10 == 0:
                 logger.info(f"监控中... 持仓数: {len(self.positions)} | 价格差: ${diff:+.1f}")
                
            await asyncio.sleep(2)
        
        # [OPTIMIZED] Gracefully close WebSocket with stats
        final_stats = ws_manager.get_connection_stats()
        logger.info(f"[WebSocket] 市场结束，关闭连接 | 总运行时间: {final_stats['uptime_sec']:.0f}s | 总消息数: {final_stats['messages_received']}")
        await ws_manager.close()
        
        # MARKET SETTLEMENT (Simulated)
        # Fetch Final Price (Binance Candle Open of the NEXT candle, or just current price if immediate)
        # To be precise: The resolution price is typically the price AT expiration.
        await asyncio.sleep(5) # Wait for dust to settle
        final_price = BinanceData.get_current_price()
        
        if final_price:
            logger.info(f"市场结算! Final BTC: ${final_price}")
            await self.settle_positions(market, final_price)

    def _get_safe_nonce(self):
        """Fetch Safe Nonce via Public RPC"""
        try:
            w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
            # Gnosis Safe nonce() ABI
            abi = '[{"constant":true,"inputs":[],"name":"nonce","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]'
            contract = w3.eth.contract(address=FUNDER_ADDRESS, abi=json.loads(abi))
            return contract.functions.nonce().call()
        except Exception as e:
            logger.error(f"Nonce fetch failed: {e}")
            return None

    def _raw_redeem(self, condition_id):
        """Execute Auto-Redeem via Relayer V2 with Builder Authentication (Gasless)"""
        if not FUNDER_ADDRESS:
            logger.error("❌ 无法赎回: 缺少代理地址")
            return

        try:
            logger.info(f"🏦 启动自动赎回流程 (Relayer V2 + Builder API)... Condition: {condition_id[:8]}")
            
            # Load Builder credentials from env
            builder_key = os.getenv("POLY_BUILDER_API_KEY")
            builder_secret = os.getenv("POLY_BUILDER_API_SECRET")
            builder_passphrase = os.getenv("POLY_BUILDER_API_PASSPHRASE")
            
            if not all([builder_key, builder_secret, builder_passphrase]):
                logger.error("❌ 无法赎回: 缺少 Builder API 凭据")
                return
            
            # Use Builder API for gasless redemption
            from py_builder_signing_sdk.config import BuilderConfig
            from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds
            
            builder_creds = BuilderApiKeyCreds(
                key=builder_key,
                secret=builder_secret,
                passphrase=builder_passphrase
            )
            builder_config = BuilderConfig(local_builder_creds=builder_creds)
            
            # TODO: Implement actual redemption call using Builder API
            # For now, log that we would redeem
            logger.info(f"✅ Builder API configured for redemption: {builder_key[:20]}...")
            logger.info(f"📝 赎回请求: Condition {condition_id[:20]}... for Safe {FUNDER_ADDRESS[:20]}...")
            
            # Placeholder: In production, this would call the relayer endpoint
            # with proper Builder headers to execute gasless redemption
            
        except Exception as e:
            logger.error(f"❌ 赎回过程异常: {e}")
            self._notify_user(f"❌ 赎回异常: {str(e)[:100]}\n请手动赎回")

        if not self.clob_client or not FUNDER_ADDRESS:
            logger.error("❌ 无法赎回: 缺 Client 或 代理地址")
            return

        try:
            logger.info(f"🏦 启动自动赎回流程 (Relayer V2)... Condition: {condition_id[:8]}")
            
            # Import and use Relayer V2 Client
            from relayer_v2_client import RelayerV2Client
            
            client = RelayerV2Client()
            result = client.redeem_positions(condition_id)
            
            if result["success"]:
                tx_id = result.get("transaction_id", "N/A")
                tx_hash = result.get("transaction_hash", "N/A")
                logger.info(f"🎉 自动赎回提交成功! TX ID: {tx_id}")
                # [Disabled] self._notify_user(f"💰 自动赎回提交成功!\nTX ID: {tx_id[:20]}...\nHash: {tx_hash[:20]}...")
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"❌ Relayer V2 失败: {error_msg}")
                
                # Fallback to manual notification
                # [Disabled] self._notify_user(f"⚠️ 自动赎回失败\n错误: {error_msg[:50]}...\n请手动赎回:\nhttps://polymarket.com/portfolio")
            
        except Exception as e:
            logger.error(f"❌ 赎回过程异常: {e}")
            # [Disabled] self._notify_user(f"❌ 赎回异常: {str(e)[:100]}\n请手动赎回")
            # [Disabled] self._notify_user(f"⚠️ 自动赎回失败，请手动赎回:\nhttps://polymarket.com/market/{condition_id}")
    
    def _redeem_direct(self, condition_id, cond_id_bytes, parent_id, index_sets):
        """Direct CTF contract interaction (fallback when relayer fails)"""
        try:
            from web3 import Web3
            
            # Connect to Polygon
            w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com", request_kwargs={'timeout': 10}))
            if not w3.is_connected():
                logger.error("❌ 无法连接到 Polygon RPC")
                return
            
            # Get signing account
            pk = os.getenv("PRIVATE_KEY") or os.getenv("PK")
            if not pk:
                logger.error("❌ 缺少私钥，无法直接赎回")
                return
                
            account = Account.from_key(pk)
            
            # Check MATIC balance
            balance = w3.eth.get_balance(account.address)
            if balance < w3.to_wei(0.01, 'ether'):
                logger.error(f"❌ MATIC 余额不足: {w3.from_wei(balance, 'ether'):.4f} MATIC")
                # [Disabled] self._notify_user(f"⚠️ 自动赎回失败 - 余额不足\n请手动赎回:\nhttps://polymarket.com/market/{condition_id}")
                return
            
            logger.info(f"💰 使用直接合约交互赎回，账户: {account.address[:10]}...")
            
            # CTF Exchange ABI (redeemPositions function)
            abi = [
                {
                    "inputs": [
                        {"name": "collateralToken", "type": "address"},
                        {"name": "parentCollectionId", "type": "bytes32"},
                        {"name": "conditionId", "type": "bytes32"},
                        {"name": "indexSets", "type": "uint256[]"}
                    ],
                    "name": "redeemPositions",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
            # Initialize contract
            ctf_contract = w3.eth.contract(
                address=Web3.to_checksum_address(CTF_EXCHANGE),
                abi=abi
            )
            
            # Build transaction
            tx = ctf_contract.functions.redeemPositions(
                USDC_ADDRESS,
                parent_id,
                cond_id_bytes,
                index_sets
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 300000,
                'gasPrice': w3.eth.gas_price,
                'chainId': 137
            })
            
            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, pk)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"⏳ 直接赎回交易已发送: {tx_hash.hex()[:20]}...")
            
            # Wait for receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                logger.info(f"🎉 直接赎回成功! TX Hash: {tx_hash.hex()}")
                # [Disabled] self._notify_user(f"💰 赎回成功 (直接)!\nTX: {tx_hash.hex()[:30]}...\nGas Used: {receipt['gasUsed']}")
            else:
                logger.error(f"❌ 直接赎回交易失败")
                # [Disabled] self._notify_user(f"⚠️ 赎回失败 - 请手动赎回:\nhttps://polymarket.com/market/{condition_id}")
                
        except Exception as e:
            logger.error(f"❌ 直接赎回失败: {e}")
            # [Disabled] self._notify_user(f"⚠️ 自动赎回失败，请手动赎回:\nhttps://polymarket.com/market/{condition_id}")

    async def settle_positions(self, market, final_price):
        """Settle open positions (Works for both Live and Paper)"""
        strike = market.strike_price
        if not strike: return
        
        # Determine Winner: "Up" if Final >= Strike
        winner = "UP" if final_price >= strike else "DOWN"
        logger.info(f"🏆 结算结果: {winner} (Strike: {strike} vs Final: {final_price})")
        self._notify_user(f"🏁 市场结算: {winner} 赢了 | 行权价: ${strike:,.2f}")
        
        # [Real Trading] Auto-Redeem Logic - Only redeem if we have positions in this market
        has_open_position = any(p.get("market_slug") == market.slug for p in self.positions)
        if has_open_position and getattr(self, 'auto_redeem_enabled', False) and not self.paper_trade and self.clob_client:
            try:
                logger.info(f"🏦 检测到有持仓，启动自动赎回: {market.condition_id[:8]}...")
                self._raw_redeem(market.condition_id)
            except Exception as e:
                logger.error(f"赎回失败: {e}")
        
        # Iterate remaining positions for this market
        for p in list(self.positions):
            if p["market_slug"] != market.slug: continue
            if p.get("status") != "OPEN": continue  # Skip already closed
            
            payout = 1.0 if p["direction"] == winner else 0.0
            pnl_amt = payout - p["entry_price"]
            pnl_pct = pnl_amt / p["entry_price"]
            
            # Update position
            p["status"] = "SETTLED"
            p["exit_price"] = payout
            p["exit_time"] = datetime.now(timezone.utc).isoformat()
            p["pnl"] = pnl_pct
            p["result"] = "WIN" if payout > 0 else "LOSS"
            
            logger.info(f"💰 结算归档: {p['direction']} -> PnL: {pnl_pct:.1%}")
            # 结算已在止盈止损时通知，这里不再重复
            
            self.trade_logger.log({
                "time": datetime.now(timezone.utc).isoformat(),
                "type": "SETTLED_PAPER" if self.paper_trade else "SETTLED",
                "market": market.slug,
                "condition_id": market.condition_id,
                "direction": p["direction"],
                "entry_price": p["entry_price"],
                "exit_price": payout,
                "pnl": pnl_pct,
                "result": "WIN" if payout > 0 else "LOSS",
                "mode": "PAPER" if self.paper_trade else "LIVE"
            })
            
            self.positions.remove(p)
        
        self._save_positions()  # [P1-Fix] 结算后保存持仓

    async def check_exit_conditions(self, market: Market15m):
        """[P1-Fix] 统一处理止盈止损，避免竞争条件"""
        for p in list(self.positions):
            if p["market_slug"] != market.slug: continue
            if p.get("status") != "OPEN": continue
            if p.get("exit_checked", False): continue
            
            # [CRITICAL-Fix] 选择正确的 OrderBook
            if p["direction"] == "UP":
                book = market.book_up
            else:
                book = market.book_down
            
            # [OPTIMIZED] 使用新的价格获取方法，支持缓存
            current_bid = None
            current_ask = None
            price_source = "none"
            
            # 1. 尝试使用 WebSocket 数据 (包括缓存)
            bid, ask, source = book.get_price_with_fallback()
            if bid is not None and book.is_valid():
                current_bid = bid
                current_ask = ask
                price_source = source
                if source == "cached":
                    logger.debug(f"[check_exit] {p['direction']} 使用缓存价格: bid={current_bid:.4f}")
                else:
                    logger.debug(f"[check_exit] {p['direction']} 使用 WebSocket 价格: bid={current_bid:.4f}")
            
            # 2. [Data-Quality] WebSocket 失效，尝试 REST API 备用
            if current_bid is None:
                token_id = market.token_id_up if p["direction"] == "UP" else market.token_id_down
                backup_price = PolyPriceFetcher.get_price(token_id)
                if backup_price:
                    current_bid, current_ask = backup_price
                    price_source = "rest_api"
                    logger.info(f"[check_exit] {p['direction']} WebSocket 失效，使用 REST API 备用价格: bid={current_bid}")
                    # 更新 OrderBook 以便后续使用
                    book.best_bid = current_bid
                    book.best_ask = current_ask
                    book.last_update = time.time()
                    book.mark_reconnect()  # Reset disconnect state
                else:
                    # Mark disconnect for caching
                    book.mark_disconnect()
                    logger.warning(f"[check_exit] {p['direction']} 所有价格源失效，跳过检查")
                    continue
            
            if current_bid is None:
                book.mark_disconnect()
                logger.warning(f"[check_exit] {p['direction']} 无法获取有效价格，跳过")
                continue
            
            # Mark successful price retrieval
            if price_source != "cached":
                book.mark_reconnect()
            entry_price = p["entry_price"]
            pnl_pct = (current_bid - entry_price) / entry_price
            exit_price = round(current_bid, 2)
            
            # [DEBUG] 每10秒记录一次价格检查
            if int(time.time()) % 10 == 0:
                logger.info(f"[DEBUG] 持仓检查: {p['direction']} entry={entry_price:.2f} current_bid={current_bid:.2f} pnl={pnl_pct:.1%}")
            
            # [User Update] 止盈止损采用"挂单追逐"模式 (同开单逻辑)
            # 1. 触发条件时挂限价单 (Best Bid)
            # 2. 5秒未成交则撤单重挂
            
            # [P1-Fix] 优先检查止损
            if pnl_pct < -self.stop_loss_pct:
                if self.paper_trade:
                    # [Fix] 模拟交易直接记录止损
                    logger.warning(f"🛑 [模拟] 止损触发! {p['direction']} PnL: {pnl_pct:.1%}")
                    self._log_paper_exit(p, "STOP_LOSS_PAPER", exit_price, pnl_pct)
                    self.positions.remove(p)
                    self._save_positions()
                elif p.get("exit_order_id") is None:  # 实盘还未挂出场单
                    logger.warning(f"🛑 止损触发! {p['direction']} 当前PnL: {pnl_pct:.1%}，准备挂出场单...")
                    await self._place_exit_order(market, p, "STOP_LOSS", current_bid)
                else:
                    # 已有出场单在挂，等待成交或超时重挂
                    logger.debug(f"⏳ 止损单 {p['exit_order_id'][:8]}... 等待成交")
                continue
            
            # [P1-Fix] 再检查止盈
            tp_price = entry_price * 1.15
            if tp_price >= 0.99: tp_price = 0.99
            
            if current_bid >= tp_price:
                if self.paper_trade:
                    # [Fix] 模拟交易直接记录止盈
                    logger.info(f"💰 [模拟] 止盈触发! {p['direction']} PnL: {pnl_pct:.1%}")
                    self._log_paper_exit(p, "TAKE_PROFIT_PAPER", exit_price, pnl_pct)
                    self.positions.remove(p)
                    self._save_positions()
                elif p.get("exit_order_id") is None:  # 实盘还未挂出场单
                    logger.info(f"💰 止盈触发! {p['direction']} 当前PnL: {pnl_pct:.1%}，准备挂出场单...")
                    await self._place_exit_order(market, p, "TAKE_PROFIT", current_bid)
                else:
                    # 已有出场单在挂，等待成交或超时重挂
                    logger.debug(f"⏳ 止盈单 {p['exit_order_id'][:8]}... 等待成交")
                continue

    def _calc_minutes_remaining(self):
        """计算距离当前15分钟周期结束还有多少分钟"""
        now = datetime.now(timezone.utc)
        minute = now.minute
        if minute < 15:
            target = 15
        elif minute < 30:
            target = 30
        elif minute < 45:
            target = 45
        else:
            target = 60
        remaining = target - minute
        if remaining < 0:
            remaining += 60
        return remaining

    def _log_paper_exit(self, position: dict, exit_type: str, exit_price: float, pnl_pct: float):
        """[Fix] 统一记录模拟交易出场日志"""
        self.trade_logger.log({
            "time": datetime.now(timezone.utc).isoformat(),
            "type": exit_type,
            "market": position.get("market_slug", ""),
            "direction": position["direction"],
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "pnl": pnl_pct,
            "mode": "PAPER"
        })
        self._notify_user(f"✅ [模拟] {exit_type.replace('_PAPER', '')} @ ${exit_price:.2f}\nPnL: {pnl_pct*100:.1f}%")

    def _notify_user(self, message):
        """Send push notification via Telegram Bot API directly"""
        try:
            bot_token = "7657469635:AAENviK3gH_O6MdU0B2LgH_EzlZ7KOKH3-c"
            chat_id = "1640598145"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": f"🤖 [Bot战报] {message}",
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ 推送成功: {message[:30]}...")
            else:
                logger.error(f"❌ 推送失败: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Notify failed: {e}")

    async def execute_trade(self, market, direction, size, liq_stats=None):
        # ... (checks) ...
        
        # [Notification Control] Only notify once per market per direction
        signal_id = f"{market.slug}_{direction}"
        if signal_id in self.notified_signals:
            return
        self.notified_signals.add(signal_id)

        # [Safety Switch]
        if not self.execution_enabled:
             logger.info(f"🚫 信号触发 ({direction}) 但交易功能已暂停 (Dry Run).")
             self._notify_user(f"🔭 发现机会: {direction} (未下单 - 模式: 仅监控)")
             return

        # [Strategy Update] Entry: Hang at Best Bid (Maker Strategy) - "盘口第一单"
        # Logic: Price = Best Ask - 0.01.
        # Example: If Ask is 0.60, we Bid 0.59. This makes us the Best Bid (First).
        if direction == "UP":
            best_ask = market.book_up.best_ask if market.book_up.best_ask > 0 else market.up_price
            price = best_ask - 0.01
        else:
            best_ask = market.book_down.best_ask if market.book_down.best_ask > 0 else market.down_price
            price = best_ask - 0.01

        # Safety clamps
        price = min(0.99, max(0.01, price))
        
        logger.info(f"🔥 SIGNAL: BUY {direction} @ {price:.2f} (Maker/Best Bid)")
        self._notify_user(f"🔥 挂单进场: {direction} @ ${price:.2f} (盘口一单)\n🎯 Strike: ${market.strike_price}")

        if self.paper_trade:
            # 模拟交易逻辑 - 完整复刻实盘流程
            try:
                # [CRITICAL-Fix] 开仓前检查数据健康
                if direction == "UP":
                    book = market.book_up
                else:
                    book = market.book_down
                
                # 检查数据新鲜度和有效性
                if not book.is_fresh(max_age_sec=30.0):
                    logger.warning(f"[开仓] {direction} 数据不新鲜，跳过开仓")
                    return
                
                if not book.is_valid():
                    logger.warning(f"[开仓] {direction} 价格数据无效 (bid={book.best_bid}, ask={book.best_ask})，跳过开仓")
                    return
                
                # [CRITICAL-Fix] 开仓价格必须与止盈检查一致！
                # 用实际能成交的价格，不是中间价
                if direction == "UP":
                    # 买 UP，用 best_ask (卖一价)
                    fill_price = market.book_up.best_ask if market.book_up.best_ask > 0 else price
                else:
                    # 买 DOWN，用 best_ask (卖一价)
                    fill_price = market.book_down.best_ask if market.book_down.best_ask > 0 else price
                
                fill_price = round(min(0.99, max(0.01, fill_price)), 2)
                
                # [User Config] Use configured trade amount
                amount_usd = self.trade_amount_usd
                if amount_usd <= 0: amount_usd = 1.0 # Fallback
                
                # [P1-Fix] 防止除以零
                if fill_price <= 0:
                    logger.error(f"❌ 无效价格: {fill_price}, 跳过开仓")
                    return
                shares = amount_usd / fill_price
                
                # [Fix] 持仓和日志使用统一的 fill_price
                position = {
                    "market_slug": market.slug,
                    "direction": direction,
                    "entry_price": fill_price,  # [Fix] 使用撮合价，不是 price
                    "size": size,
                    "shares": shares,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tp_placed": False,
                    "sl_placed": False,
                    "status": "OPEN"
                }
                self.positions.append(position)
                
                # 记录交易日志 [增强版 - 捕获所有特征数据]
                if direction == "UP":
                    book = market.book_up
                else:
                    book = market.book_down
                
                # 获取当前BTC价格
                current_btc_price = BinanceData.get_current_price() or 0.0
                
                trade_record = {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "type": "V3_SMART_PAPER",
                    "direction": direction,
                    "entry_price": fill_price,
                    "shares": shares,
                    "strike": market.strike_price,
                    "fee": self.fee_pct,
                    "status": "OPEN",
                    "market": market.slug,
                    # [新增] 盘口特征数据
                    "poly_spread": round(book.best_ask - book.best_bid, 4),
                    "poly_bid": book.best_bid,
                    "poly_ask": book.best_ask,
                    "poly_bid_depth": book.best_bid_size,
                    "poly_ask_depth": book.best_ask_size,
                    # [新增] 时间特征
                    "hour": datetime.now(timezone.utc).hour,
                    "dayofweek": datetime.now(timezone.utc).weekday(),
                    "minutes_remaining": self._calc_minutes_remaining(),
                    # [新增] BTC价格特征
                    "btc_price": current_btc_price,
                    "diff_from_strike": current_btc_price - market.strike_price if current_btc_price else 0.0
                }
                self.trade_logger.log(trade_record)
                
                # 模拟挂止盈止损单 (复刻实单的 "hang order" 逻辑)
                tp_price = min(0.99, fill_price * 1.15)  # +15% 止盈
                sl_price = fill_price * (1 - self.stop_loss_pct)  # -35% 止损
                
                # [DEBUG] 记录详细价格信息用于排查
                if direction == "UP":
                    logger.info(f"[DEBUG] UP价格 - bid: {market.book_up.best_bid}, ask: {market.book_up.best_ask}")
                else:
                    logger.info(f"[DEBUG] DOWN价格 - bid: {market.book_down.best_bid}, ask: {market.book_down.best_ask}")
                
                logger.info(f"📊 [模拟] 开仓成功: {direction} {shares:.2f}份 @ {fill_price:.2f}")
                logger.info(f"📊 [模拟] 已挂止盈: {tp_price:.2f} | 止损: {sl_price:.2f}")
                
                self._notify_user(
                    f"🎯 开单 [{direction}] @ ${fill_price:.2f}\n"
                    f"📈 止盈: ${tp_price:.2f} | 📉 止损: ${sl_price:.2f}"
                )
                
            except Exception as e:
                logger.error(f"[模拟交易] 开仓失败: {e}")
                self._notify_user(f"❌ [模拟] 开仓失败: {e}")
        else:
             # [CRITICAL] 实盘双重确认检查
             if not getattr(self, 'live_trading_enabled', False):
                 logger.error("🚨 [安全拦截] 尝试执行实盘但 live_trading_enabled=false")
                 logger.error("🚨 如需实盘，请修改 config.json: paper_trade=false + live_trading_enabled=true")
                 self._notify_user(f"🚨 安全拦截: 实盘未启用\n当前模式: 模拟交易\n如需实盘请修改配置并重启")
                 return
             
             # Real Execution (双重确认通过)
             logger.warning("🔥 [实盘模式] 立即执行真实下单！")
             try:
                 if self.clob_client:
                     # [Strategy Update] Entry: Hang at Best Bid (Maker Strategy)
                     # Logic: Price = Best Bid.
                     if direction == "UP":
                         price = market.book_up.best_bid if market.book_up.best_bid > 0 else market.up_price
                     else:
                         price = market.book_down.best_bid if market.book_down.best_bid > 0 else market.down_price
                         
                     # Safety clamps
                     price = min(0.99, max(0.01, price))
                     price = round(price, 2)
                     
                     # [User Config] Use configured trade amount
                     amount_usd = self.trade_amount_usd
                     if amount_usd <= 0: amount_usd = 1.0 # Fallback
                     shares = amount_usd / price
                     shares = round(shares, 4)
                     
                     # [Fix] 通知移至订单成功后发送
                     
                     order_args = OrderArgs(
                         price=price,
                         size=shares,
                         side=BUY,
                         token_id=market.token_id_up if direction == "UP" else market.token_id_down,
                         # [Fix] OrderType.LIMIT is not in enum, use GTC (Good Til Cancelled) which is standard limit
                         # OrderType.GTC = "GTC"
                         # OrderArgs class doesn't have order_type field in some versions, but create_order needs it
                     )
                     # Manually passing order_type to create_order if needed, or OrderArgs.
                     # Wait, OrderArgs definition above shows NO order_type field.
                     # It seems we should use create_order(order_args, options=...) or similar?
                     # No, py_clob_client.client.create_order usually takes OrderArgs.
                     # Let's check how to specify order type. 
                     # If OrderArgs doesn't have it, maybe it defaults to GTC?
                     # Re-reading clob_types.py: OrderArgs has price, size, side... NO order_type.
                     # PostOrdersArgs has orderType.
                     # Client.create_order(order_args: OrderArgs) -> calls internal logic.
                     # It likely defaults to GTC (Limit).
                     # So I should REMOVE order_type from OrderArgs constructor.
                     
                     # [P0-Fix] 实盘立即下单 + 订单跟踪
                     logger.info(f"🚀 执行实盘下单: {direction} @ {price:.2f}")
                     try:
                         # [Fix] Use create_and_post_order to actually submit the order
                         order_result = self.clob_client.create_and_post_order(order_args)
                         
                         # [DEBUG] 打印完整响应
                         logger.info(f"[DEBUG] 订单响应: {order_result}")
                         
                         order_id = order_result.get("order_id") if order_result else None
                         
                         if order_id:
                             logger.info(f"✅ 订单提交成功: {order_id}")
                             self._notify_user(f"✅ 实盘已提交: {direction} {shares:.2f}份 @ ${price:.2f}\n订单ID: {order_id[:16]}...")
                             
                             # [CRITICAL-Fix] 先创建持仓记录，包含 order_id
                             position = {
                                 "market_slug": market.slug,
                                 "direction": direction,
                                 "entry_price": price,
                                 "shares": shares,
                                 "size": size,
                                 "timestamp": datetime.now(timezone.utc).isoformat(),
                                 "tp_placed": False,
                                 "sl_placed": False,
                                 "status": "PENDING",  # 等待成交
                                 "order_id": order_id,  # 保存订单ID
                                 "exit_checked": False
                             }
                             self.positions.append(position)
                             self._save_positions()
                             
                             # [P0-Fix] 异步跟踪订单状态
                             asyncio.create_task(self._track_order(order_id, position))
                         else:
                             logger.error(f"❌ 订单提交失败: 无订单ID返回. 响应: {order_result}")
                             self._notify_user(f"❌ 订单提交失败\n响应: {order_result}")
                             return
                     except Exception as e:
                         logger.error(f"❌ 下单异常: {e}")
                         self._notify_user(f"❌ 下单失败: {str(e)[:100]}")
                         return
                 else:
                     logger.error("❌ CLOB Client 未初始化，无法实盘")
                     self._notify_user("❌ 实盘失败: CLOB Client 未连接")
             except Exception as e:
                 self._notify_user(f"❌ 下单失败: {e}")

             trade_record = {
                 "time": datetime.now(timezone.utc).isoformat(),
                 "type": "V3_SMART",
                 "direction": direction,
                 "entry_price": price,  # [Fix] 统一使用 entry_price
                 "shares": shares,  # [P2-Fix] 记录份额
                 "strike": market.strike_price,
                 "fee": self.fee_pct,
                 "market": market.slug,  # [Fix] 添加 market 字段
                 "mode": "LIVE"  # [Fix] 添加 mode 字段
             }
             
             # Log Liquidity Stats for ML Training
             if liq_stats:
                 trade_record["poly_spread"] = liq_stats.get("spread", 0)
                 trade_record["poly_bid_depth"] = liq_stats.get("bid_depth", 0)
                 trade_record["poly_ask_depth"] = liq_stats.get("ask_depth", 0)
                 
             self.trade_logger.log(trade_record)
             
             # Notify User
             self._notify_user(f"🔥 开仓: {direction} @ ${price:.2f}\n🎯 Strike: ${market.strike_price}\n💰 预计投入: $1.0")

             await asyncio.sleep(10) # Cooldown

    async def _place_exit_order(self, market: Market15m, position: dict, exit_type: str, current_bid: float):
        """[New] 挂出场单 (止盈/止损)，采用追逐模式"""
        try:
            if not self.clob_client:
                logger.error("❌ CLOB Client 未初始化，无法挂出场单")
                return
            
            # 确定token_id和方向
            token_id = market.token_id_up if position["direction"] == "UP" else market.token_id_down
            
            # 出场价格：使用当前 Best Bid (买一价)
            exit_price = current_bid
            exit_price = min(0.99, max(0.01, exit_price))
            
            # 构造卖出订单
            order_args = OrderArgs(
                price=exit_price,
                size=position["shares"],
                side="SELL",  # 卖出
                token_id=token_id
            )
            
            logger.info(f"🔥 挂{exit_type}单: {position['direction']} {position['shares']:.2f}份 @ ${exit_price:.2f}")
            
            # [Fix] Use create_and_post_order to actually submit the order
            order_result = self.clob_client.create_and_post_order(order_args)
            order_id = order_result.get("order_id") if order_result else None
            
            if order_id:
                logger.info(f"✅ {exit_type}单已提交: {order_id[:16]}...")
                position["exit_order_id"] = order_id
                position["exit_order_type"] = exit_type
                position["exit_order_price"] = exit_price
                position["exit_order_time"] = time.time()
                self._save_positions()
                
                # 启动追踪任务 (5秒超时)
                asyncio.create_task(self._track_exit_order(order_id, position, market))
            else:
                logger.error(f"❌ {exit_type}单提交失败")
                
        except Exception as e:
            logger.error(f"❌ 挂{exit_type}单异常: {e}")
    
    async def _track_exit_order(self, order_id: str, position: dict, market: Market15m):
        """[New] 追踪出场单状态，5秒未成交则撤单重挂 (追逐模式)"""
        max_wait = 5
        check_interval = 1
        
        logger.info(f"⏳ 追踪{position.get('exit_order_type', '出场')}单 {order_id[:8]}... (超时: {max_wait}s)")
        
        for i in range(0, max_wait, check_interval):
            try:
                order_status = await self.clob_client.get_order(order_id)
                
                if order_status:
                    status = order_status.get("status")
                    
                    if status == "FILLED":
                        # 成交了！
                        avg_price = float(order_status.get("avg_price", position.get("exit_order_price", 0)))
                        filled_size = float(order_status.get("size", position["shares"]))
                        
                        exit_type = position.get("exit_order_type", "EXIT")
                        pnl_pct = (avg_price - position["entry_price"]) / position["entry_price"]
                        
                        position["status"] = f"{exit_type}_FILLED"
                        position["exit_price"] = avg_price
                        position["exit_time"] = datetime.now(timezone.utc).isoformat()
                        position["pnl"] = pnl_pct
                        
                        self.positions.remove(position)
                        self._save_positions()
                        
                        logger.info(f"✅ {exit_type}单成交: {avg_price:.2f} x {filled_size:.4f}, PnL: {pnl_pct:.1%}")
                        self._notify_user(f"✅ {exit_type}成交 @ ${avg_price:.2f}\nPnL: {pnl_pct*100:.1f}%")
                        
                        # 记录日志
                        self.trade_logger.log({
                            "time": datetime.now(timezone.utc).isoformat(),
                            "type": f"{exit_type}_FILLED",
                            "market": position.get("market_slug", ""),
                            "direction": position["direction"],
                            "entry_price": position["entry_price"],
                            "exit_price": avg_price,
                            "pnl": pnl_pct,
                            "mode": "LIVE"
                        })
                        return
                        
                    elif status in ["CANCELLED", "REJECTED"]:
                        logger.warning(f"⚠️ {position.get('exit_order_type', '出场')}单 {status}")
                        position["exit_order_id"] = None
                        self._save_positions()
                        return
                        
            except Exception as e:
                logger.error(f"查询出场单状态失败: {e}")
            
            await asyncio.sleep(check_interval)
        
        # 5秒超时，撤单重挂
        logger.warning(f"⏰ {position.get('exit_order_type', '出场')}单 5秒未成交，撤单重挂...")
        try:
            self.clob_client.cancel(order_id)
            logger.info(f"✅ 撤单成功: {order_id[:8]}")
            
            # 重置订单状态，让check_exit_conditions重新检测并挂新单
            position["exit_order_id"] = None
            position["exit_order_time"] = None
            self._save_positions()
            logger.info("🔄 出场单状态已重置，准备重挂...")
            
        except Exception as e:
            logger.error(f"❌ 撤单失败: {e}")

    async def _track_order(self, order_id: str, position: dict):
        """[P0-Fix] 跟踪订单成交状态 (Updated: 5秒不成交 -> 撤单 -> 追单)"""
        max_wait = 5   # [User Update] 最多等待5秒
        check_interval = 1  # 每1秒检查一次
        
        logger.info(f"⏳ 正在跟踪订单 {order_id[:8]}... (超时时间: {max_wait}s)")
        
        for i in range(0, max_wait, check_interval):
            try:
                # 查询订单状态
                order_status = await self.clob_client.get_order(order_id)
                
                if order_status:
                    status = order_status.get("status")
                    
                    if status == "FILLED":
                        # 订单已成交
                        avg_price = float(order_status.get("avg_price", position["entry_price"]))
                        filled_size = float(order_status.get("size", position["shares"]))
                        
                        position["status"] = "OPEN"
                        position["entry_price"] = avg_price
                        position["shares"] = filled_size
                        self._save_positions()
                        
                        logger.info(f"✅ 订单 {order_id[:8]}... 已成交: {avg_price:.2f} x {filled_size:.4f}")
                        self._notify_user(f"✅ 订单成交\n价格: ${avg_price:.2f}\n份额: {filled_size:.4f}")
                        return
                        
                    elif status in ["CANCELLED", "REJECTED"]:
                        # 订单被取消或拒绝
                        position["status"] = "CANCELLED"
                        self.positions.remove(position)
                        self._save_positions()
                        
                        logger.warning(f"⚠️ 订单 {order_id[:8]}... {status}")
                        return
                        
            except Exception as e:
                logger.error(f"查询订单状态失败: {e}")
            
            await asyncio.sleep(check_interval)
        
        # [User Update] 超时未成交 -> 撤单 -> 并清理持仓 (让主循环立即发起追单)
        logger.warning(f"⏰ 订单 {order_id[:8]}... 5秒未成交，执行撤单并追单")
        try:
            self.clob_client.cancel(order_id)
            logger.info(f"✅ 撤单请求已发送: {order_id[:8]}")
            self._notify_user(f"🗑️ 挂单5秒未成交，已撤单\n订单ID: {order_id[:8]}...\n等待重新挂单")
            
            # 关键：从持仓列表中移除，以便主循环下一轮 (2秒后) 检测到无持仓，
            # 从而根据最新价格重新计算 Edge 并发起新挂单 (即“追单”)
            if position in self.positions:
                self.positions.remove(position)
                self._save_positions()
                logger.info("🔄 持仓状态已重置，准备追单...")
                
        except Exception as e:
            logger.error(f"❌ 撤单失败: {e}")

# --- [OPTIMIZED] WebSocket Manager V3 with Heartbeat, Pooling & Resilience ---
class WebSocketManagerV3:
    """
    Optimized WebSocket manager with:
    - Ping/pong heartbeat (every 20s)
    - Connection pooling and persistent connections
    - Price caching during brief disconnections (up to 5s)
    - Improved error handling and exponential backoff
    - Market switch resilience
    """
    def __init__(self, market):
        self.market = market
        self.ws = None
        self.running = False
        self.connected = False
        self.connection_lock = asyncio.Lock()
        
        # Heartbeat configuration
        self.ping_interval = 20  # Send ping every 20 seconds
        self.pong_timeout = 10   # Wait up to 10s for pong response
        self.last_pong_time = 0
        self.last_ping_time = 0
        self.heartbeat_task = None
        
        # Reconnection configuration
        self.reconnect_delay = 1.0   # Start with 1s delay
        self.max_reconnect_delay = 30.0  # Cap at 30s
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 100  # Per session limit
        
        # Connection state tracking
        self.connection_start_time = None
        self.messages_received = 0
        self.connection_id = 0  # Increment on each successful connect
        
        # Graceful shutdown
        self._closing = False
        
    async def connect(self):
        """Establish WebSocket connection with retry logic"""
        async with self.connection_lock:
            if self.connected or self._closing:
                return
                
            self.connection_id += 1
            conn_id = self.connection_id
            
            try:
                logger.info(f"[WebSocket #{conn_id}] Connecting to {WS_URL}...")
                
                # Configure connection with proper timeouts and keepalive
                self.ws = await websockets.connect(
                    WS_URL,
                    ping_interval=None,  # We handle ping/pong manually for more control
                    ping_timeout=None,
                    close_timeout=5.0,
                    open_timeout=10.0,
                    max_size=10 * 1024 * 1024,  # 10MB max message size
                    compression=None,  # Disable compression for lower latency
                )
                
                # Subscribe to market data
                msg = {
                    "assets_ids": [self.market.token_id_up, self.market.token_id_down],
                    "type": "market"
                }
                await self.ws.send(json.dumps(msg))
                
                self.connected = True
                self.running = True
                self.connection_start_time = time.time()
                self.messages_received = 0
                self.last_pong_time = time.time()
                self.reconnect_attempts = 0
                
                logger.info(f"[WebSocket #{conn_id}] Connected and subscribed successfully")
                
                # Start heartbeat task
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
            except Exception as e:
                logger.error(f"[WebSocket #{conn_id}] Connection failed: {e}")
                self.connected = False
                raise
    
    async def _heartbeat_loop(self):
        """Send periodic ping messages and monitor connection health"""
        conn_id = self.connection_id
        
        while self.running and self.connected and not self._closing:
            try:
                now = time.time()
                
                # Check if we've received a pong recently
                if self.last_ping_time > 0 and (now - self.last_pong_time) > (self.ping_interval + self.pong_timeout):
                    logger.warning(f"[WebSocket #{conn_id}] Pong timeout detected (last pong: {now - self.last_pong_time:.1f}s ago)")
                    # Trigger reconnection
                    asyncio.create_task(self._trigger_reconnect())
                    break
                
                # Send ping
                if self.ws and self.connected:
                    try:
                        await self.ws.send(json.dumps({"type": "ping"}))
                        self.last_ping_time = now
                        logger.debug(f"[WebSocket #{conn_id}] Ping sent")
                    except Exception as e:
                        logger.warning(f"[WebSocket #{conn_id}] Failed to send ping: {e}")
                        break
                
                await asyncio.sleep(self.ping_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WebSocket #{conn_id}] Heartbeat error: {e}")
                break
        
        logger.debug(f"[WebSocket #{conn_id}] Heartbeat loop stopped")
    
    async def _trigger_reconnect(self):
        """Trigger a reconnection from the heartbeat loop"""
        if self.connected:
            self.connected = False
            try:
                if self.ws:
                    await self.ws.close()
            except:
                pass
    
    async def listen(self):
        """[OPTIMIZED] WebSocket listener with auto-reconnect and health monitoring"""
        while self.running and not self._closing:
            conn_id = self.connection_id
            
            try:
                # Ensure connection is established
                if not self.connected:
                    try:
                        await self.connect()
                    except Exception as e:
                        await self._handle_reconnect_failure(e)
                        continue
                
                # Main message loop
                async for msg in self.ws:
                    if not self.running or self._closing:
                        break
                    
                    # Update stats
                    self.messages_received += 1
                    
                    # Handle different message types
                    try:
                        if msg == "PONG" or msg == "pong":
                            self.last_pong_time = time.time()
                            logger.debug(f"[WebSocket #{conn_id}] Pong received")
                            continue
                        
                        # Parse and process data
                        data = json.loads(msg)
                        if isinstance(data, list):
                            for item in data:
                                self._process(item)
                        else:
                            self._process(data)
                            
                    except json.JSONDecodeError as e:
                        logger.debug(f"[WebSocket #{conn_id}] Invalid JSON: {msg[:100]}")
                    except Exception as e:
                        logger.debug(f"[WebSocket #{conn_id}] Message processing error: {e}")
                
                # If we get here, the connection closed normally
                if self.running and not self._closing:
                    logger.warning(f"[WebSocket #{conn_id}] Connection closed unexpectedly")
                    self.connected = False
                    
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"[WebSocket #{conn_id}] Connection closed: {e.code} - {e.reason}")
                self.connected = False
                
            except websockets.exceptions.InvalidStatusCode as e:
                logger.error(f"[WebSocket #{conn_id}] Invalid status code: {e.status_code}")
                self.connected = False
                # Back off more aggressively for auth/rate limit errors
                if e.status_code in [401, 403, 429]:
                    await asyncio.sleep(30)
                    
            except Exception as e:
                logger.error(f"[WebSocket #{conn_id}] Listener error: {e}")
                self.connected = False
            
            # Attempt reconnection if still running
            if self.running and not self._closing:
                await self._handle_reconnect_failure()
        
        logger.info("[WebSocket] Listener stopped")
    
    async def _handle_reconnect_failure(self, error=None):
        """Handle reconnection with exponential backoff"""
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.critical(f"[WebSocket] Max reconnect attempts ({self.max_reconnect_attempts}) reached. Giving up.")
            self.running = False
            return
        
        # Calculate delay with exponential backoff and jitter
        delay = min(self.reconnect_delay * (2 ** (self.reconnect_attempts // 5)), self.max_reconnect_delay)
        delay += (asyncio.get_event_loop().time() % 1)  # Add up to 1s jitter
        
        if error:
            logger.warning(f"[WebSocket] Connection error: {error}")
        
        logger.info(f"[WebSocket] Reconnecting in {delay:.1f}s... (attempt {self.reconnect_attempts})")
        await asyncio.sleep(delay)
        
        # Don't reset delay here - only reset on successful connection
    
    def _process(self, data):
        """Process incoming WebSocket data"""
        try:
            asset = data.get("asset_id")
            
            if asset == self.market.token_id_up:
                self.market.book_up.update(data)
            elif asset == self.market.token_id_down:
                self.market.book_down.update(data)
            elif data.get("event_type") == "price_change":
                for p in data.get("price_changes", []):
                    aid = p.get("asset_id")
                    target_book = None
                    if aid == self.market.token_id_up:
                        target_book = self.market.book_up
                    elif aid == self.market.token_id_down:
                        target_book = self.market.book_down
                    
                    if target_book:
                        new_bid = p.get("best_bid")
                        if new_bid is not None:
                            target_book.best_bid = float(new_bid)
                        new_bid_size = p.get("best_bid_size")
                        if new_bid_size is not None:
                            target_book.best_bid_size = float(new_bid_size)
                        new_ask = p.get("best_ask")
                        if new_ask is not None:
                            target_book.best_ask = float(new_ask)
                        new_ask_size = p.get("best_ask_size")
                        if new_ask_size is not None:
                            target_book.best_ask_size = float(new_ask_size)
                        # Update timestamp on price change
                        target_book.last_update = time.time()
                        
        except Exception as e:
            logger.debug(f"[WebSocket] Process error: {e}")
    
    async def close(self):
        """Gracefully close the WebSocket connection"""
        logger.info("[WebSocket] Closing connection...")
        self._closing = True
        self.running = False
        self.connected = False
        
        # Cancel heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close websocket
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        
        logger.info("[WebSocket] Connection closed")
    
    def get_connection_stats(self) -> dict:
        """Get connection statistics for monitoring"""
        uptime = 0
        if self.connection_start_time:
            uptime = time.time() - self.connection_start_time
        
        return {
            "connected": self.connected,
            "connection_id": self.connection_id,
            "uptime_sec": uptime,
            "messages_received": self.messages_received,
            "reconnect_attempts": self.reconnect_attempts,
            "last_pong_sec_ago": time.time() - self.last_pong_time if self.last_pong_time > 0 else None
        }

# Resource monitoring
_last_resource_check = 0
_resource_check_interval = 300  # Check every 5 minutes

def check_system_resources():
    """Check disk/CPU/memory and alert if critical"""
    global _last_resource_check
    
    current_time = time.time()
    if current_time - _last_resource_check < _resource_check_interval:
        return  # Too soon
    
    _last_resource_check = current_time
    
    try:
        # Check disk usage
        import shutil
        disk = shutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        
        if disk_percent > 95:
            logger.critical(f"🚨 CRITICAL: Disk usage {disk_percent:.1f}%! Free: {disk.free // (1024**3)}GB")
        elif disk_percent > 85:
            logger.warning(f"⚠️ WARNING: Disk usage {disk_percent:.1f}%")
        
        # Check memory
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            total = int(meminfo.split('MemTotal:')[1].split('kB')[0].strip())
            available = int(meminfo.split('MemAvailable:')[1].split('kB')[0].strip())
            mem_percent = ((total - available) / total) * 100
            
            if mem_percent > 95:
                logger.critical(f"🚨 CRITICAL: Memory usage {mem_percent:.1f}%!")
            elif mem_percent > 85:
                logger.warning(f"⚠️ WARNING: Memory usage {mem_percent:.1f}%")
                
        except Exception:
            pass
            
    except Exception as e:
        logger.debug(f"Resource check failed: {e}")

async def main_loop_with_restart():
    """[CRITICAL-Fix] Main loop with crash recovery and auto-healing"""
    restart_count = 0
    max_restarts = 100  # Prevent infinite restart loops
    healer = AutoHealer()
    
    # Initial resource check
    check_system_resources()
    
    while restart_count < max_restarts:
        try:
            logger.info(f"🚀 Starting Bot (attempt #{restart_count + 1})")
            logger.info(healer.get_health_report())
            
            # Check resources before starting
            check_system_resources()
            
            bot = PolymarketBotV3()
            await bot.run()
            # If run() returns normally, break the loop
            logger.info("Bot stopped normally")
            break
            
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user (KeyboardInterrupt)")
            break
            
        except Exception as e:
            restart_count += 1
            error_msg = str(e)
            
            # Get stack trace
            import traceback
            stack_trace = traceback.format_exc()
            
            logger.critical(f"💥 CRITICAL ERROR - Bot crashed: {e}")
            logger.critical(f"💥 Stack trace:\n{stack_trace}")
            
            # Auto-healing
            diagnosis, healed = healer.record_crash(error_msg, stack_trace)
            logger.info(f"🩺 Auto-healer diagnosis: {diagnosis['type']}")
            logger.info(f"🩺 Healing action applied: {healed}")
            logger.info(f"🩺 Actions taken: {healer.healing_actions[-1:]}")
            
            logger.critical(f"🔄 Restarting in 10 seconds... (attempt {restart_count}/{max_restarts})")
            
            # Notify user of crash with healing info
            try:
                import requests
                TOKEN_FILE = "/home/ubuntu/clawd/.telegram_bot_token"
                if os.path.exists(TOKEN_FILE):
                    with open(TOKEN_FILE, 'r') as f:
                        token = f.read().strip()
                    heal_msg = f"✅ Auto-fix applied" if healed else f"⚠️ Auto-fix failed"
                    msg = (
                        f"🚨 Bot CRASHED #{restart_count}!\n"
                        f"Error: {error_msg[:80]}\n"
                        f"Type: {diagnosis['type']}\n"
                        f"{heal_msg}\n"
                        f"Restarting..."
                    )
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        data={"chat_id": "1640598145", "text": msg},
                        timeout=5
                    )
            except:
                pass
            
            await asyncio.sleep(10)
    
    if restart_count >= max_restarts:
        logger.critical("❌ Max restarts reached. Bot will not restart automatically.")

if __name__ == "__main__":
    # Set up top-level exception handler
    try:
        asyncio.run(main_loop_with_restart())
    except Exception as e:
        logger.critical(f"💥 FATAL ERROR in main: {e}", exc_info=True)
        raise
