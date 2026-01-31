#!/usr/bin/env python3
"""
Polymarket Data Miner
- Runs in background
- Fetches Binance history for all trades in paper_trades.jsonl
- Saves to cache for training script
"""
import json
import pandas as pd
import requests
import time
import os
from datetime import datetime

DATA_FILE = "polymarket-bot/paper_trades.jsonl"
CACHE_DIR = "polymarket-bot/candle_cache"

if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)

def get_binance_history_safe(end_time_ms):
    cache_file = f"{CACHE_DIR}/{end_time_ms}.json"
    if os.path.exists(cache_file): return # Already done
    
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "1m", "endTime": end_time_ms, "limit": 60}
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            print("🛑 Rate Limit! Sleep 60s...")
            time.sleep(60)
            return
            
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            with open(cache_file, 'w') as f:
                json.dump(data, f)
            print(f"✅ Cached {end_time_ms}")
        else:
            print(f"⚠️ Empty data for {end_time_ms}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("⛏️ Miner Started...")
    trades = []
    with open(DATA_FILE, "r") as f:
        for line in f:
            try: trades.append(json.loads(line))
            except: pass
            
    total = len(trades)
    print(f"Found {total} trades to process.")
    
    for i, t in enumerate(trades):
        ts_str = t["time"]
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        ts_ms = int(dt.timestamp() * 1000)
        
        get_binance_history_safe(ts_ms)
        
        if i % 10 == 0:
            print(f"Progress: {i}/{total}")
        
        time.sleep(0.5) # Be nice to Binance API

if __name__ == "__main__":
    main()
