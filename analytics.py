#!/usr/bin/env python3
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser

def load_trades(filepath="paper_trades.jsonl"):
    if not os.path.exists(filepath):
        return []
    
    trades = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return trades

def analyze_performance(trades, hours=24):
    """Analyze trades from the last N hours."""
    # Ensure now is timezone-aware UTC
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    
    relevant_trades = []
    
    # Identify unique open positions by looking for 'V3_SMART' entries 
    # that don't have a corresponding 'SETTLED' or 'STOP_LOSS' entry later.
    # But our logs structure is flat events. 
    # A SETTLED event implies a closed trade, but it doesn't explicitly link to the open event ID in my V3 log format yet (it logs market slug).
    # Simplified logic: 
    # 1. Collect all events in window
    # 2. Count SETTLED/STOP_LOSS as closed trades
    
    for t in trades:
        ts_str = t.get("time", "")
        if not ts_str: continue
        try:
            # Robust parsing using dateutil
            ts = date_parser.parse(ts_str)
            # If naive, assume UTC
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            
            if ts > cutoff:
                relevant_trades.append(t)
        except Exception:
            continue
            
    # Filter types
    settled_events = [t for t in relevant_trades if t.get("type") in ("SETTLED", "STOP_LOSS")]
    
    # Calculate Metrics
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    
    for t in settled_events:
        pnl = t.get("pnl", 0)
        # Check result field or pnl
        if pnl > 0:
            wins += 1
            gross_profit += pnl
        else:
            losses += 1
            gross_loss += abs(pnl)
            
    total = wins + losses
    win_rate = (wins / total) if total > 0 else 0.0
    
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0
    net_pnl = gross_profit - gross_loss

    return {
        "period_hours": hours,
        "total_closed_trades": total,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "net_pnl_units": round(net_pnl, 2),
        "wins": wins,
        "losses": losses
    }

def main():
    try:
        trades = load_trades()
        
        # Analyze last 24 hours
        stats_24h = analyze_performance(trades, hours=24)
        
        # Analyze All Time (since log start)
        stats_all = analyze_performance(trades, hours=24*365)
        
        report = {
            "status": "OK",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "24h": stats_24h,
            "all_time": stats_all
        }
        
        print(json.dumps(report, indent=2))
        
    except Exception as e:
        print(json.dumps({"status": "ERROR", "message": str(e)}))

if __name__ == "__main__":
    main()
