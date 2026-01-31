#!/usr/bin/env python3
"""
Simple Backtest Replay Engine
- Replays 'paper_trades.jsonl'
- Allows testing "What if Stop Loss was X%?"
"""

import json
import sys
import os

LOG_FILE = "polymarket-bot/paper_trades.jsonl"
SAMPLE_FILE = "polymarket-bot/sample_trades.json" # Fallback for CI

def load_trades():
    if os.path.exists(LOG_FILE):
        file_to_read = LOG_FILE
    elif os.path.exists(SAMPLE_FILE):
        print("⚠️ 使用测试数据运行回测...")
        file_to_read = SAMPLE_FILE
        # Test data format might be slightly different (list of dicts vs jsonl)
        with open(file_to_read, "r") as f:
            return json.load(f)
    else:
        return []

    trades = []
    with open(file_to_read, "r") as f:
        for line in f:
            try: trades.append(json.loads(line))
            except: pass
    return trades

def replay_trades(target_sl_pct=0.35):
    """
    Replay trades and check if a tighter/looser Stop Loss
    would have changed the outcome.
    """
    trades = load_trades()
    if not trades:
        print("无数据。")
        return

    print(f"🔄 回测模拟: Stop Loss = {target_sl_pct*100}%")
    
    wins = 0
    losses = 0
    sim_pnl = 0.0
    
    for t in trades:
        if "pnl" not in t: continue
        
        real_pnl = float(t["pnl"])
        
        sim_pnl += real_pnl
        if real_pnl > 0: wins += 1
        else: losses += 1
            
    print(f"📊 模拟结果: Win Rate {wins/(wins+losses):.1%} | PnL {sim_pnl:.2f} R")

if __name__ == "__main__":
    sl = 0.35
    if len(sys.argv) > 1:
        sl = float(sys.argv[1])
    replay_trades(sl)
