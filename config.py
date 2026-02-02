import os
import json
import logging
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_v4.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Config:
    """Configuration Manager"""
    def __init__(self, config_path: str = "bot_config.json"):
        self.config_path = config_path
        self.config = self._load_defaults()
        self._load_from_file()
        self._load_from_env()
        
    def _load_defaults(self) -> Dict[str, Any]:
        return {
            "stop_loss_pct": 0.35,
            "take_profit_pct": 0.15,
            "safety_margin_pct": 0.0006,
            "min_edge": 0.08,
            "fee_pct": 0.03,
            "trade_amount_usd": 1.0,
            "min_liquidity_usd": 200,
            "daily_max_loss_usd": 50.0,
            "execution_enabled": False,
            "paper_trade": True,
            "live_trading_enabled": False,
            "auto_redeem_enabled": False,
            "max_api_failures": 5,
            "order_timeout_sec": 5,
        }
        
    def _load_from_file(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    file_config = json.load(f)
                    self.config.update(file_config)
                logger.info(f"Loaded config from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load config file: {e}")
                
    def _load_from_env(self):
        # Load critical secrets
        self.private_key = os.getenv("PRIVATE_KEY") or os.getenv("PK")
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.private_key:
            logger.warning("⚠️ No Private Key found in environment variables!")
            
    def get(self, key: str, default=None):
        return self.config.get(key, default)
        
    def update(self, key: str, value: Any):
        self.config[key] = value
        # Optional: Save back to file

# Global config instance
config = Config()
