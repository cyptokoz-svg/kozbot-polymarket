import logging
import requests
from config import config

logger = logging.getLogger(__name__)

class Notifier:
    """Telegram Notification Service"""
    def __init__(self):
        self.token = config.get("TELEGRAM_BOT_TOKEN") or "7657469635:AAENviK3gH_O6MdU0B2LgH_EzlZ7KOKH3-c"
        self.chat_id = config.get("TELEGRAM_CHAT_ID") or "1640598145"
        
    def send(self, message: str):
        """Send notification"""
        if not self.token or not self.chat_id:
            return
            
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": f"🤖 [Bot V4] {message}",
                "parse_mode": "HTML"
            }
            # Use timeout to prevent blocking
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Notify failed: {e}")

# Global instance
notifier = Notifier()
