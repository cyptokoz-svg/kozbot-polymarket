#!/usr/bin/env python3
"""
Web Data Sync Tool
- Reads trade logs
- Generates data.json for the Web Dashboard
- Pushes to GitHub
"""

import json
import os
import subprocess
from datetime import datetime, timezone

LOG_FILE = "polymarket-bot/paper_trades.jsonl"
OUTPUT_FILE = "public/data.json"

def generate_web_data():
    trades = []
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                try:
                    t = json.loads(line)
                    # Add simple timestamp for chart
                    if "time" in t:
                        t["shortTime"] = t["time"].split("T")[1][:5]
                    trades.append(t)
                except: pass

    # Calculate Stats
    closed_trades = [t for t in trades if "pnl" in t]
    wins = len([t for t in closed_trades if float(t["pnl"]) > 0])
    losses = len([t for t in closed_trades if float(t["pnl"]) < 0])
    total_pnl = sum([float(t["pnl"]) for t in closed_trades])
    win_rate = (wins / (wins + losses)) if (wins + losses) > 0 else 0
    
    gross_profit = sum([float(t["pnl"]) for t in closed_trades if float(t["pnl"]) > 0])
    gross_loss = abs(sum([float(t["pnl"]) for t in closed_trades if float(t["pnl"]) < 0]))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

    # Generate Chart Data (Equity Curve)
    chart_data = []
    running_pnl = 0.0
    for t in trades:
        if "pnl" in t and t["time"].startswith(today_str):
            running_pnl += float(t["pnl"])
            chart_data.append({
                "time": t["shortTime"],
                "pnl": round(running_pnl, 2)
            })

    data = {
        "updatedAt": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "stats": {
            "netPnL": f"{total_pnl:+.2f} R",
            "winRate": f"{win_rate:.1%}",
            "profitFactor": f"{profit_factor:.2f}",
            "totalTrades": len(trades)
        },
        "chartData": chart_data,
        "recentTrades": trades[-10:][::-1] # Last 10 reversed
    }
    
    # Ensure dirs exist
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Double-write for robustness
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Generated {OUTPUT_FILE} and root data.json")

def push_to_github():
    try:
        # Commit all data files
        subprocess.run(["git", "add", OUTPUT_FILE, "data.json"], check=True)
        subprocess.run(["git", "commit", "-m", "chore: update trade data (hotfix)"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("🚀 Data pushed to GitHub!")
    except Exception as e:
        print(f"Git Error: {e}")

if __name__ == "__main__":
    import time
    while True:
        generate_web_data()
        push_to_github()
        print("Waiting 300s...")
        time.sleep(300)
