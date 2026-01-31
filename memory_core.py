#!/usr/bin/env python3
"""
Clawd Memory Core (Async Learner)
- Watches trade logs in real-time
- Builds a knowledge base (mem_db.json)
- Updates strategy config asynchronously
"""

import json
import time
import os
from collections import defaultdict

LOG_FILE = "polymarket-bot/paper_trades.jsonl"
CONFIG_FILE = "polymarket-bot/config.json"
MEM_DB = "polymarket-bot/mem_db.json"

class MemoryCore:
    def __init__(self):
        self.knowledge = self.load_memory()
        self.last_pos = 0
        
    def load_memory(self):
        if os.path.exists(MEM_DB):
            try:
                with open(MEM_DB, "r") as f:
                    return json.load(f)
            except: pass
        return {"hourly_stats": {}, "bad_regimes": []}

    def save_memory(self):
        with open(MEM_DB, "w") as f:
            json.dump(self.knowledge, f, indent=2)

    def process_logs(self):
        """Read new logs incrementally"""
        if not os.path.exists(LOG_FILE): return
        
        with open(LOG_FILE, "r") as f:
            f.seek(self.last_pos)
            lines = f.readlines()
            self.last_pos = f.tell()
            
        for line in lines:
            try:
                trade = json.loads(line)
                if "pnl" in trade:
                    self.learn_from_trade(trade)
            except: pass

    def learn_from_trade(self, trade):
        """Extract patterns from a closed trade"""
        # Pattern 1: Hourly Performance
        # "Is 08:00 UTC a bad time to trade?"
        ts = trade["time"].split("T")[1][:2] # Extract Hour (00-23)
        pnl = float(trade["pnl"])
        
        stats = self.knowledge["hourly_stats"].setdefault(ts, {"wins": 0, "losses": 0, "pnl": 0.0})
        stats["pnl"] += pnl
        if pnl > 0: stats["wins"] += 1
        else: stats["losses"] += 1
        
        self.knowledge["hourly_stats"][ts] = stats
        self.save_memory()
        
        # Trigger Optimization check
        self.apply_wisdom()

    def apply_wisdom(self):
        """
        Async Optimization:
        If we find a pattern (e.g., Hour 03 always loses), 
        we don't block the bot, we just update config.json or alert user.
        """
        # Example: Check for Toxic Hours
        toxic_hours = []
        for hour, stats in self.knowledge["hourly_stats"].items():
            # If we have enough sample size (>5 trades) and Win Rate < 30%
            total = stats["wins"] + stats["losses"]
            if total >= 5 and (stats["wins"] / total) < 0.3:
                toxic_hours.append(hour)
        
        if toxic_hours:
            print(f"🧠 Memory Insight: Trading is toxic at hours {toxic_hours}. Consider pausing.")
            # In V2, we can auto-update config['blackout_hours'] = toxic_hours

    def run(self):
        print("🧠 Memory Core started (Background Mode)...")
        while True:
            self.process_logs()
            time.sleep(10) # Chill, don't eat CPU

if __name__ == "__main__":
    MemoryCore().run()
