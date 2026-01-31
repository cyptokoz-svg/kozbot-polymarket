import os
import google.generativeai as genai
from google.generativeai import caching
import datetime
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core import exceptions

logger = logging.getLogger(__name__)

class GeminiTraderAI:
    def __init__(self, api_key=None, model_name='models/gemini-1.5-flash-001'):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self.cache = None

    @retry(
        retry=retry_if_exception_type((exceptions.ResourceExhausted, exceptions.ServiceUnavailable)),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def update_knowledge_base(self, history_text):
        """Cache large historical data to avoid 429s and save costs"""
        try:
            # Cleanup old session caches
            for c in caching.CachedContent.list():
                if c.display_name == "trader_knowledge":
                    c.delete()

            self.cache = caching.CachedContent.create(
                model=self.model_name,
                display_name="trader_knowledge",
                system_instruction="You are an expert Quant Trader. Analyze history to optimize the current BTC 15m strategy.",
                contents=[history_text],
                ttl=datetime.timedelta(minutes=65),
            )
            logger.info(f"✅ Context Cache Updated: {self.cache.name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update cache: {e}")
            return False

    @retry(
        retry=retry_if_exception_type(exceptions.ResourceExhausted),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3)
    )
    def get_decision(self, prompt):
        """Get trading decision using cached context"""
        if not self.cache:
            # Fallback to no cache if not initialized
            model = genai.GenerativeModel(self.model_name)
            return model.generate_content(prompt).text
        
        model = genai.GenerativeModel.from_cached_content(cached_content=self.cache)
        response = model.generate_content(prompt)
        return response.text
