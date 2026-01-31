#!/usr/bin/env python3
"""
Auto-Redeemer Daemon
- Monitors trade logs for WINs
- Automatically redeems winnings on-chain
"""

import time
import json
import subprocess
import os
from datetime import datetime, timezone

LOG_FILE = "polymarket-bot/paper_trades.jsonl"
REDEEM_SCRIPT = "polymarket-bot/redeem_ctf.py"

def get_recent_wins():
    wins = []
    if not os.path.exists(LOG_FILE): return []
    
    # Simple logic: Read last 20 lines
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-20:]
            
        for line in lines:
            try:
                t = json.loads(line)
                # Look for SETTLED & WIN
                if t.get("type") == "SETTLED" and t.get("result") == "WIN":
                    cid = t.get("condition_id")
                    if cid and cid not in wins:
                        wins.append(cid)
            except: pass
    except: pass
    return wins

def run_loop():
    print("💰 Auto-Redeemer started...")
    # Keep track of redeemed IDs to avoid spamming
    redeemed = set()
    
    while True:
        wins = get_recent_wins()
        for cid in wins:
            if cid not in redeemed:
                print(f"🎉 Found new WIN! Condition: {cid}")
                print("🚀 Triggering on-chain redeem...")
                subprocess.run(["polymarket-bot/venv/bin/python", REDEEM_SCRIPT, cid])
                redeemed.add(cid)
        
        time.sleep(10) # Check every 10s for test

if __name__ == "__main__":
    run_loop()
