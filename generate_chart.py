import json
import os
import matplotlib.pyplot as plt
from datetime import datetime, timezone

# Data Source
LOG_FILE = "polymarket-bot/paper_trades.jsonl"
today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# 1. Parse Data
trades = []
cumulative_pnl = [0.0]
timestamps = ["Start"]
running_pnl = 0.0

if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                t = json.loads(line)
                if t["time"].startswith(today_str) and "pnl" in t:
                    running_pnl += float(t["pnl"])
                    cumulative_pnl.append(running_pnl)
                    # Simple timestamp HH:MM
                    ts = t["time"].split("T")[1][:5]
                    timestamps.append(ts)
            except: pass

# 2. Plotting
plt.figure(figsize=(10, 6))
plt.plot(range(len(cumulative_pnl)), cumulative_pnl, marker='o', linestyle='-', color='g', linewidth=2)

# Styling
plt.title(f"Polymarket Bot PnL - {today_str} (UTC)", fontsize=14)
plt.ylabel("Net PnL (Units)", fontsize=12)
plt.xlabel("Trade Sequence", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.6)
plt.axhline(0, color='black', linewidth=1)

# Annotations
if len(cumulative_pnl) > 1:
    final_pnl = cumulative_pnl[-1]
    color = 'green' if final_pnl >= 0 else 'red'
    plt.text(len(cumulative_pnl)-1, final_pnl, f"{final_pnl:+.2f} R", 
             fontsize=12, fontweight='bold', color=color, ha='left', va='bottom')

# Save
output_path = "polymarket-bot/pnl_chart.png"
plt.savefig(output_path)
print(f"Chart saved to {output_path}")
