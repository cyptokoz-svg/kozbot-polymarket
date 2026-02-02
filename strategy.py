import time
import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class Strategy:
    """Trading Strategy Engine"""
    def __init__(self, min_edge=0.08, safety_margin_pct=0.0006):
        self.min_edge = min_edge
        self.safety_margin_pct = safety_margin_pct
        
    def calculate_signal(self, market_data, btc_price):
        """Calculate trading signal based on Fair Value"""
        if not market_data or not btc_price:
            return None
            
        strike = market_data.get("strike")
        expiry = market_data.get("expiry")
        
        if not strike or not expiry:
            return None
            
        # 1. Calculate Time Remaining
        now = datetime.now(timezone.utc)
        time_diff = (expiry - now).total_seconds()
        if time_diff <= 30: # Don't trade last 30s
            return None
            
        # 2. Calculate Fair Value (Simplified Time-Decay Model)
        diff = btc_price - strike
        volatility_factor = 100.0 # Tuning parameter
        
        # Standard logistic function for probability
        # prob = 1 / (1 + e^(-k * diff))
        k = 0.1 # Steepness
        
        # [Fix] Math overflow protection
        exponent = -k * (diff / volatility_factor)
        exponent = max(-700, min(700, exponent)) # Clamp to avoid overflow
        
        fair_prob_up = 1 / (1 + math.exp(exponent))
        fair_prob_down = 1 - fair_prob_up
        
        # 3. Check Edge
        poly_ask_up = market_data.get("ask_up")
        poly_ask_down = market_data.get("ask_down")
        
        signal = None
        
        # Check UP
        if poly_ask_up:
            edge_up = fair_prob_up - poly_ask_up
            if edge_up > self.min_edge:
                signal = {
                    "direction": "UP",
                    "price": poly_ask_up,
                    "edge": edge_up,
                    "fair_value": fair_prob_up
                }
                
        # Check DOWN
        if poly_ask_down:
            edge_down = fair_prob_down - poly_ask_down
            if edge_down > self.min_edge:
                # Prefer higher edge if both active
                if not signal or edge_down > signal["edge"]:
                    signal = {
                        "direction": "DOWN",
                        "price": poly_ask_down,
                        "edge": edge_down,
                        "fair_value": fair_prob_down
                    }
                    
        return signal
