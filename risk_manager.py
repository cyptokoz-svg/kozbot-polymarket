import logging
from datetime import datetime, timezone
from config import config

logger = logging.getLogger(__name__)

class RiskManager:
    """Risk Management System"""
    def __init__(self):
        self.daily_pnl = 0.0
        self.last_trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.daily_max_loss_usd = config.get("daily_max_loss_usd", 50.0)
        self.trade_amount_usd = config.get("trade_amount_usd", 1.0)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.35)
        self.take_profit_pct = config.get("take_profit_pct", 0.15)
        
    def check_daily_limit(self) -> bool:
        """Check if daily loss limit is reached"""
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Reset daily PnL if new day
        if current_date != self.last_trade_date:
            logger.info(f"📅 New day: Resetting daily PnL (Prev: {self.daily_pnl:.2f})")
            self.daily_pnl = 0.0
            self.last_trade_date = current_date
            
        # Check limit
        daily_loss_usd = abs(min(0, self.daily_pnl)) * self.trade_amount_usd
        if daily_loss_usd >= self.daily_max_loss_usd:
            logger.warning(f"🛑 Daily loss limit reached: ${daily_loss_usd:.2f} >= ${self.daily_max_loss_usd:.2f}")
            return False
            
        return True
        
    def update_daily_pnl(self, pnl_pct: float):
        """Update daily PnL after a trade"""
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if current_date != self.last_trade_date:
            self.daily_pnl = 0.0
            self.last_trade_date = current_date
            
        self.daily_pnl += pnl_pct
        logger.info(f"💰 Daily PnL Updated: {self.daily_pnl:+.2%}")
        
    def check_exit_signal(self, position: dict, current_price: float) -> str:
        """Check stop loss and take profit"""
        entry_price = position["entry_price"]
        pnl_pct = (current_price - entry_price) / entry_price
        
        # Stop Loss
        if pnl_pct <= -self.stop_loss_pct:
            return "STOP_LOSS"
            
        # Take Profit
        tp_price = min(0.99, entry_price * (1 + self.take_profit_pct))
        if current_price >= tp_price:
            return "TAKE_PROFIT"
            
        return "HOLD"
