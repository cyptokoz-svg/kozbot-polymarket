#!/usr/bin/env python3
"""
Daily Report Generator
- Aggregates stats from paper_trades.jsonl
- Generates PnL chart
- Formats a Markdown summary for Telegram
"""

import json
import os
import subprocess
from datetime import datetime, timezone

LOG_FILE = "polymarket-bot/paper_trades.jsonl"

def generate_daily_report():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trades = []
    
    # 1. Load Data
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                try:
                    t = json.loads(line)
                    if t["time"].startswith(today_str):
                        trades.append(t)
                except: pass
    
    if not trades:
        return "📅 **今日战报**\n暂无交易数据。"

    # 2. Calculate Stats
    wins = 0
    losses = 0
    total_pnl = 0.0
    
    for t in trades:
        if "pnl" in t:
            pnl = float(t["pnl"])
            total_pnl += pnl
            if pnl > 0: wins += 1
            else: losses += 1
            
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    pf = "∞" # Todo: accurate calc
    
    # Generate Chart first
    subprocess.run(["polymarket-bot/venv/bin/python", "polymarket-bot/generate_chart.py"])
    
    # Format Message
    msg = f"""📅 **量化实战日报 ({today_str})**

💰 **净利润**: `{total_pnl:+.2f} R` (本金倍数)
📊 **胜率**: `{win_rate:.1f}%` ({wins}胜 {losses}负)
📈 **交易数**: {total} 笔

**今日最佳交易**:
"""
    # Find best trade
    best_trade = max(trades, key=lambda x: float(x.get("pnl", -99)), default=None)
    if best_trade and "pnl" in best_trade:
        msg += f"🚀 `{best_trade['direction']}` 获利 `+{float(best_trade['pnl'])*100:.1f}%` ({best_trade['time'].split('T')[1][:5]})\n"
        
    msg += "\n*系统运行正常，策略参数：SL 35% / Edge 8%*"
    return msg

if __name__ == "__main__":
    print(generate_daily_report())
