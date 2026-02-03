import os
import json
import logging
from typing import Any, Optional
from validators import sanitize_log_data
from typing import Dict, Any
from dotenv import load_dotenv

# Load .env
load_dotenv()

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        # Load from multiple possible config files (backwards compatibility)
        self.config = self._load_config()
        
        # Load critical secrets
        self.private_key = os.getenv("PRIVATE_KEY") or os.getenv("PK")
        self.funder_address = os.getenv("FUNDER_ADDRESS")
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.private_key:
            logger.warning("⚠️ No Private Key found in environment variables!")
            
    def _load_config(self) -> Dict[str, Any]:
        """Load config from file"""
        config_files = ["config.json", "bot_config.json"]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        data = json.load(f)
                        logger.info(f"Loaded config from {config_file}")
                        return data
                except Exception as e:
                    logger.error(f"Failed to load {config_file}: {e}")
        
        # Return default config
        logger.info("Using default configuration")
        return {
            "paper_trade": True,
            "execution_enabled": False,
            "live_trading_enabled": False,
            "max_position_usd": 100,
            "min_edge": 0.08,
            "cancel_unfilled_orders": True,
            "sync_on_startup": True,
            "market_cache_sec": 5,
            "orderbook_cache_sec": 0.5,
            "price_cache_sec": 0.5,
            "ws_stale_sec": 2,
            "api_timeout_sec": 5,
            "api_retries": 3,
            "api_backoff_sec": 0.6,
        }
    
    def get(self, key: str, default=None):
        if key == "PRIVATE_KEY":
            return self.private_key
        if key == "FUNDER_ADDRESS":
            return self.funder_address
        if key == "TELEGRAM_BOT_TOKEN":
            return self.telegram_token
        if key == "TELEGRAM_CHAT_ID":
            return self.telegram_chat_id
        return self.config.get(key, default)
        
    def update(self, key: str, value: Any):
        self.config[key] = value
        # Optional: Save back to file
    
    def validate_config(self):
        """Validate critical configuration values"""
        errors = []
        warnings = []
        
        # Validate timeouts
        api_timeout = self.get("api_timeout_sec", 5)
        try:
            api_timeout = float(api_timeout)
            if api_timeout <= 0:
                errors.append("api_timeout_sec must be > 0")
            elif api_timeout > 60:
                warnings.append(f"api_timeout_sec ({api_timeout}s) is very high")
        except (ValueError, TypeError):
            errors.append("api_timeout_sec must be numeric")
        
        # Validate edge threshold
        min_edge = self.get("min_edge", 0.08)
        try:
            min_edge = float(min_edge)
            if not (0 < min_edge < 1):
                errors.append("min_edge must be between 0 and 1")
        except (ValueError, TypeError):
            errors.append("min_edge must be numeric")
        
        # Log results
        if errors:
            error_msg = "\n".join([f"  - {e}" for e in errors])
            logger.error(f"Config validation errors:\n{error_msg}")
            raise ValueError("Config validation failed")
        
        if warnings:
            warning_msg = "\n".join([f"  - {w}" for w in warnings])
            logger.warning(f"Config warnings:\n{warning_msg}")
        
        logger.info("Config validation passed")

# Global config instance
config = Config()
