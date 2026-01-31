import requests
import json
import time
import os
from datetime import datetime, timezone, timedelta

GAMMA_API = "https://gamma-api.polymarket.com"

# Fetch past 24h of BTC 15m markets
# We need to reconstruct the "slugs" or just search by tag/series
# Series slug: "btc-up-or-down-15m" (From previous inspect)

def fetch_historical_markets():
    print("Fetching historical markets from Gamma API...")
    
    # Calculate timestamps
    now = int(time.time())
    # Extended: Look back 30 days to get massive data for V6
    start_ts = now - (86400 * 30) 
    
    # Align to 15m
    start_ts = (start_ts // 900) * 900
    
    # Load existing slugs to avoid duplicates
    existing_slugs = set()
    if os.path.exists("polymarket-bot/paper_trades.jsonl"):
        with open("polymarket-bot/paper_trades.jsonl", "r") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if "market" in rec: existing_slugs.add(rec["market"])
                except: pass
    print(f"Found {len(existing_slugs)} existing records. Skipping duplicates.")

    markets_data = []
    
    # Iterate
    start_time = time.time()
    count = 0
    
    for ts in range(start_ts, now, 900):
        # SELF-PROTECTION: Exit if running longer than 120 seconds
        if time.time() - start_time > 120:
             print("⏳ Time limit reached (120s). Stopping to prevent crash.")
             break
             
        slug = f"btc-updown-15m-{ts}"
        
        if slug in existing_slugs:
            continue
            
        try:
            resp = requests.get(f"{GAMMA_API}/events?slug={slug}", timeout=5)
            data = resp.json()
            
            if not data:
                print(f"Skipping {slug} (No data)")
                continue
                
            event = data[0]
            market = event.get("markets", [])[0]
            
            # We need: Strike Price, End Price (Resolution), and Result
            # Strike Price is not explicitly in API, but it's the Open Price of the candle at StartTime
            # We will fetch that from Binance later.
            
            # Result: "outcomePrices": "[\"1\", \"0\"]" -> UP won
            prices = json.loads(market.get("outcomePrices", '["0.5", "0.5"]'))
            winner = "UP" if prices[0] == "1" else "DOWN" if prices[1] == "1" else "UNKNOWN"
            
            if winner == "UNKNOWN": continue
            
            start_time_iso = event.get("startDate") # 2026-01-27T18:30:00Z
            
            markets_data.append({
                "ts": ts,
                "start_time": start_time_iso,
                "winner": winner,
                "slug": slug
            })
            print(f"Found: {slug} -> {winner}")
            time.sleep(0.1) # Rate limit nice
            
        except Exception as e:
            print(f"Error fetching {slug}: {e}")
            
    return markets_data

def enrich_with_binance(markets):
    print("\nEnriching with Binance OHLCV data...")
    enriched = []
    
    for m in markets:
        ts_ms = m["ts"] * 1000
        # Get candle at start time (Strike)
        # And candle at end time (Resolution) - roughly +15m
        
        try:
            # Get Strike (Open of start candle)
            url = "https://api.binance.com/api/v3/klines"
            
            # 1. Strike Price
            params = {"symbol": "BTCUSDT", "interval": "1m", "startTime": ts_ms, "limit": 1}
            resp = requests.get(url, params=params, timeout=5)
            kline_start = resp.json()
            strike = float(kline_start[0][1]) # Open
            
            # 2. Volatility / Trend Feature (Previous 15m candle)
            # Get the candle BEFORE this market started to calculate trend
            params_prev = {"symbol": "BTCUSDT", "interval": "15m", "startTime": ts_ms - 900000, "limit": 1}
            resp_prev = requests.get(url, params=params_prev, timeout=5)
            kline_prev = resp_prev.json()
            prev_open = float(kline_prev[0][1])
            prev_close = float(kline_prev[0][4])
            trend_pct = (prev_close - prev_open) / prev_open
            
            m["strike_price"] = strike
            m["prev_trend"] = trend_pct
            
            enriched.append(m)
            print(f"Enriched {m['slug']}: Strike {strike}, Trend {trend_pct:.4%}")
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Binance error for {m['slug']}: {e}")
            
    return enriched

def save_to_training_data(data):
    # Convert to format compatible with training script
    # We need to simulate "trades". 
    # Since we know the winner, we can generate synthetic "Winning Trades" to teach the model WHAT WINS.
    
    print(f"\nGenerating synthetic training data from {len(data)} markets...")
    
    with open("polymarket-bot/paper_trades.jsonl", "a") as f:
        for m in data:
            # Synthetic Trade: If UP won, we simulate a "BUY UP" trade that won.
            # We want the model to learn to predict the WINNER.
            
            record = {
                "time": m["start_time"],
                "type": "SETTLED", # Mark as settled for training
                "market": m["slug"],
                "direction": m["winner"], # The winning direction
                "entry_price": 0.50, # Assume avg entry
                "exit_price": 1.0,
                "pnl": 1.0, # Dummy positive PnL
                "result": "WIN",
                # Extra features for ML
                "strike_price": m["strike_price"],
                "prev_trend": m["prev_trend"]
            }
            f.write(json.dumps(record) + "\n")
            
    print("✅ Successfully appended historical data to paper_trades.jsonl")

if __name__ == "__main__":
    markets = fetch_historical_markets()
    if markets:
        enriched = enrich_with_binance(markets)
        save_to_training_data(enriched)
