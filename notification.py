import logging
import requests
from config import config

logger = logging.getLogger(__name__)

class Notifier:
    """Telegram Notification Service"""
    def __init__(self):
        self.token = None
        self.chat_id = None
        self.parse_mode = None
        self._refresh_config()
        if not self.token or not self.chat_id:
            logger.warning("⚠️ Telegram credentials not set (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)")
    
    def _refresh_config(self):
        # Support env keys and config.json keys
        self.token = config.get("TELEGRAM_BOT_TOKEN") or config.get("telegram_token")
        self.chat_id = config.get("TELEGRAM_CHAT_ID") or config.get("telegram_chat_id")
        self.parse_mode = config.get("telegram_parse_mode") or None
        
    def send(self, message: str):
        """Send notification"""
        self._refresh_config()
        if not self.token or not self.chat_id:
            return
            
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": f"🤖 [Bot V4] {message}",
                "disable_web_page_preview": True
            }
            if self.parse_mode:
                payload["parse_mode"] = self.parse_mode
            # Use timeout to prevent blocking
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code != 200:
                logger.error(f"Notify failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Notify failed: {e}")

# Global instance
notifier = Notifier()
