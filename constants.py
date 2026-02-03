"""
Constants for the trading bot
集中定义魔法数字，避免硬编码
"""

# Timing constants (seconds)
MIN_LOOP_INTERVAL = 0.033  # 33ms = 30 Hz - ULTRA-FAST MODE 🚀
DEFAULT_API_TIMEOUT = 5  # Faster failure detection
ORDERBOOK_CACHE_TTL = 0.2  # 200ms - Ultra-aggressive orderbook updates
PRICE_CACHE_TTL = 0.2  # 200ms - Ultra-aggressive price updates
MARKET_CACHE_TTL = 5  # 5s - Less frequent market metadata updates
WS_STALE_THRESHOLD = 2  # 2s - Consider WebSocket data stale after this

# Trading constants
MIN_SHARE_SIZE = 0.0001  # Polymarket minimum order size
PRICE_TOLERANCE = 0.02  # 2% - Order matching tolerance for price differences
MAX_POSITION_SIZE_USD = 1000000  # $1M max position size (sanity check)

# Strategy constants
DEFAULT_MIN_EDGE = 0.08  # 8% - Minimum edge to trigger trades
DEFAULT_VOLATILITY = 0.0575  # 5.75% - Default BTC volatility for fair value
CONSERVATIVE_VOL_BIAS = 1.15  # 15% conservative bias multiplier

# Market timing constants
MARKET_INTERVAL_SECONDS = 900  # 15 minutes = 900 seconds
MINUTES_PER_YEAR = 365 * 24 * 60  # For time-to-expiry normalization

# Retry and backoff constants
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 0.6  # 600ms exponential backoff base

# Validation ranges
MIN_VALID_BTC_PRICE = 10000  # $10k - Sanity check lower bound
MAX_VALID_BTC_PRICE = 500000  # $500k - Sanity check upper bound
MIN_PROBABILITY = 0.0
MAX_PROBABILITY = 1.0

# HTTP/Network
MAX_CONNECTIONS = 20  # httpx connection pool size
HTTP2_ENABLED = True

# Logging
LOG_MAX_LENGTH = 200  # Maximum length for logged strings
