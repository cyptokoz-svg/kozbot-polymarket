import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Strategy:
    """
    Strategy Skeleton
    - Implement calculate_signal() to return a signal dict or None
    - Expected signal format:
        {
            "direction": "UP" or "DOWN",
            "price": float,
            "edge": float,
            "fair_value": float (optional),
            "meta": dict (optional)
        }
    """

    def __init__(self, **kwargs):
        self.params = kwargs

    def calculate_signal(self, market_data, btc_price):
        """
        Decide whether to trade.

        Args:
            market_data (dict): includes ask_up/ask_down, strike, expiry, etc.
            btc_price (float): current BTC price

        Returns:
            dict | None
        """
        if not market_data or not btc_price:
            return None

        # TODO: implement your strategy here
        return None

