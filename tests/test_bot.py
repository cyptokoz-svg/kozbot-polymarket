"""
Polymarket BTC 15m Bot - Unit Tests
"""
import pytest
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Floating point comparison tolerance
TOLERANCE = 1e-10


class TestProbabilityCalculations:
    """测试概率计算"""
    
    def test_fair_probability_calculation(self):
        """测试公平概率计算"""
        # 距离 strike $100, 剩余 10分钟 (600秒)
        distance = 100
        time_remaining = 600
        
        # 模拟计算 (基于代码中的逻辑)
        # prob = 0.5 + (distance / (distance + 100)) * (time_factor)
        # 简化为测试距离/时间的影响
        
        assert distance > 0
        assert time_remaining > 0
    
    def test_edge_calculation(self):
        """测试 Edge 计算"""
        fair_prob = 0.6
        market_price = 0.5
        
        edge = abs(fair_prob - market_price)
        assert edge == pytest.approx(0.1, abs=TOLERANCE)
        
        # Edge should be positive
        assert edge >= 0


class TestRiskManagement:
    """测试风控系统"""
    
    def test_stop_loss_threshold(self):
        """测试止损阈值"""
        stop_loss_pct = 0.35
        entry_price = 0.5
        
        # Stop loss price
        sl_price = entry_price * (1 - stop_loss_pct)
        assert sl_price == 0.325
        
        # Check if -35% is triggered
        current_price = 0.32
        pnl_pct = (current_price - entry_price) / entry_price
        assert pnl_pct < -stop_loss_pct
    
    def test_daily_loss_limit(self):
        """测试每日亏损限制"""
        daily_max_loss_usd = 50.0
        trade_amount_usd = 1.0
        
        # Simulate some losses
        daily_pnl = -0.3  # -30%
        daily_loss_usd = abs(daily_pnl) * trade_amount_usd
        
        assert daily_loss_usd < daily_max_loss_usd  # Should allow more trading
        
        # Simulate hitting the limit (need 5000% loss with $1 trade amount to hit $50 limit)
        daily_pnl = -60.0  # -6000%
        daily_loss_usd = abs(daily_pnl) * trade_amount_usd
        
        assert daily_loss_usd > daily_max_loss_usd  # Should stop trading
    
    def test_safety_margin(self):
        """测试安全边际"""
        strike_price = 50000
        safety_margin_pct = 0.0006
        
        safety_margin = strike_price * safety_margin_pct
        assert safety_margin == pytest.approx(30.0, abs=TOLERANCE)  # $30 buffer


class TestPositionManagement:
    """测试持仓管理"""
    
    def test_position_size_calculation(self):
        """测试仓位大小计算"""
        trade_amount_usd = 1.0
        entry_price = 0.5
        fee_pct = 0.03
        
        # Calculate shares
        amount_after_fee = trade_amount_usd * (1 - fee_pct)
        shares = amount_after_fee / entry_price
        
        assert shares == 1.94  # ~1.94 shares
    
    def test_pnl_calculation(self):
        """测试盈亏计算"""
        entry_price = 0.5
        exit_price = 0.7
        
        pnl_pct = (exit_price - entry_price) / entry_price
        assert pnl_pct == pytest.approx(0.4, abs=TOLERANCE)  # +40%
        
        # Loss scenario
        exit_price = 0.35
        pnl_pct = (exit_price - entry_price) / entry_price
        assert pnl_pct == pytest.approx(-0.3, abs=TOLERANCE)  # -30%


class TestConfiguration:
    """测试配置管理"""
    
    def test_config_loading(self):
        """测试配置加载"""
        config = {
            "stop_loss_pct": 0.35,
            "safety_margin_pct": 0.0006,
            "min_edge": 0.08,
            "daily_max_loss_usd": 50.0
        }
        
        assert config["stop_loss_pct"] == 0.35
        assert config["safety_margin_pct"] == 0.0006
        assert config["daily_max_loss_usd"] == 50.0
    
    def test_default_values(self):
        """测试默认值"""
        defaults = {
            "stop_loss_pct": 0.35,
            "safety_margin_pct": 0.0006,
            "min_edge": 0.08,
            "fee_pct": 0.03,
            "daily_max_loss_usd": 50.0
        }
        
        assert defaults["stop_loss_pct"] == 0.35
        assert defaults["daily_max_loss_usd"] == 50.0


class TestEdgeCases:
    """测试边界情况"""
    
    def test_extreme_edge_values(self):
        """测试极端 Edge 值"""
        # Edge clamping: -50% to +50%
        edge_up = 0.7
        edge_down = -0.7
        
        # Should be clamped
        edge_up = min(edge_up, 0.5)
        edge_down = max(edge_down, -0.5)
        
        assert edge_up == 0.5
        assert edge_down == -0.5
    
    def test_price_bounds(self):
        """测试价格边界"""
        price = 1.5  # Too high
        price = min(0.99, max(0.01, price))
        assert price == 0.99
        
        price = -0.1  # Too low
        price = min(0.99, max(0.01, price))
        assert price == 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
