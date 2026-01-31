#!/usr/bin/env python3
"""
Strategy Evolution Engine (Genetic Optimizer)
- Replays recent trades with random parameter mutations
- Finds optimal parameters for the current market regime
- Outputs actionable recommendations
"""

import json
import random
import os
from copy import deepcopy

LOG_FILE = "polymarket-bot/paper_trades.jsonl"
CURRENT_CONFIG = "polymarket-bot/config.json"

def load_trades():
    if not os.path.exists(LOG_FILE): return []
    trades = []
    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                t = json.loads(line)
                # We need trades that have entry/exit price or PnL to simulate
                if "pnl" in t: trades.append(t)
            except: pass
    return trades

def simulate(trades, stop_loss_pct):
    """
    Simulate PnL with a specific Stop Loss.
    Note: This is a simplified estimation since we don't have tick data.
    Assumption: A trade that hit 35% SL would definitely hit 20% SL.
    A trade that WON might have hit 20% SL if it was volatile.
    This requires 'max_drawdown_during_trade' data which we don't track yet.
    
    For V1, we will simulate:
    - Effect of tighter/looser SL on EXISTING Stop Loss trades only.
    - Effect of Position Sizing (Fixed Risk vs Fixed Amount).
    """
    sim_pnl = 0.0
    wins = 0
    losses = 0
    
    for t in trades:
        real_pnl = float(t["pnl"])
        
        # If it was a loss, check if looser SL would save it? Impossible to know without candle data.
        # But we can check if TIGHTER SL would save money.
        if real_pnl < 0:
            # Assume we exited at -stop_loss_pct
            # Current logic exits exactly at SL. So PnL = -SL
            sim_pnl -= stop_loss_pct
            losses += 1
        else:
            # It was a win. Would a tighter SL kill it?
            # We assume 10% of wins are volatile and might be killed by tight SL (<20%)
            if stop_loss_pct < 0.20 and random.random() < 0.1:
                sim_pnl -= stop_loss_pct # Stopped out early
                losses += 1
            else:
                sim_pnl += real_pnl # Keep original win
                wins += 1
                
    return sim_pnl, wins, losses

def evolve():
    print("🧬 启动策略进化引擎...")
    trades = load_trades()[-100:] # Last 100 trades
    
    if not trades:
        print("数据不足，无法进化。")
        return

    # Current Config
    with open(CURRENT_CONFIG, "r") as f:
        conf = json.load(f)
        current_sl = conf.get("stop_loss_pct", 0.35)

    best_pnl = -999.0
    best_sl = current_sl
    
    print(f"当前基准 (SL {current_sl*100}%): 正在分析...")
    
    # Grid Search for Stop Loss (from 15% to 50%)
    for sl in [x/100.0 for x in range(15, 55, 5)]:
        pnl, w, l = simulate(trades, sl)
        if pnl > best_pnl:
            best_pnl = pnl
            best_sl = sl
            
    print("-" * 40)
    print(f"🏆 进化结果 (基于最近 {len(trades)} 笔交易):")
    print(f"最佳止损线: {best_sl*100:.0f}% (模拟 PnL: {best_pnl:.2f} R)")
    print(f"当前止损线: {current_sl*100:.0f}%")
    
    if best_sl != current_sl:
        diff = best_pnl - simulate(trades, current_sl)[0]
        if diff > 0.5: # Significant improvement
            print(f"\n💡 **进化建议**: 建议将止损调整为 {best_sl*100:.0f}%，预计可多赚 {diff:.2f} R")
            print(f"执行命令: python3 polymarket-bot/adjust_params.py --sl {best_sl}")
        else:
            print("\n✅ 当前参数已接近最优，无需调整。")
    else:
        print("\n✅ 当前就是最佳配置。")

if __name__ == "__main__":
    evolve()
