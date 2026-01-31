#!/usr/bin/env python3
"""
Polymarket Machine Learning Training Script V5 (Real Data Edition)
- Uses real captured feature data from trade records
- Auto-cleanup after training
- Archives old data with compression
"""

import json
import pandas as pd
import numpy as np
import xgboost as xgb
import pandas_ta as ta
import os
import joblib
import gzip
import shutil
from datetime import datetime, timezone, timedelta
from sklearn.metrics import accuracy_score, roc_auc_score
from xgboost import XGBClassifier

DATA_FILE = "polymarket-bot/paper_trades.jsonl"
MODEL_FILE = "polymarket-bot/ml_model_v2.pkl"
CACHE_DIR = "polymarket-bot/candle_cache"
ARCHIVE_DIR = "polymarket-bot/archive"

# Ensure archive directory exists
if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

def archive_old_data():
    """Archive and compress old trade data after training"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    # Archive trades
    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
        archive_file = f"{ARCHIVE_DIR}/trades_{timestamp}.jsonl.gz"
        with open(DATA_FILE, 'rb') as f_in:
            with gzip.open(archive_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"📦 Archived trades to: {archive_file}")
        
        # Clear current trades file (keep only last 100 lines for context)
        with open(DATA_FILE, 'r') as f:
            lines = f.readlines()
        with open(DATA_FILE, 'w') as f:
            f.writelines(lines[-100:])  # Keep last 100 records
        print(f"🧹 Cleaned {DATA_FILE} (kept last 100 records)")
    
    # Archive old candle cache (keep last 7 days)
    if os.path.exists(CACHE_DIR):
        cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith('.json')]
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
        
        archived_count = 0
        for cache_file in cache_files:
            file_path = os.path.join(CACHE_DIR, cache_file)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
            
            if file_mtime < cutoff_time:
                # Archive old cache file
                archive_path = f"{ARCHIVE_DIR}/cache_{timestamp}/{cache_file}.gz"
                os.makedirs(os.path.dirname(archive_path), exist_ok=True)
                
                with open(file_path, 'rb') as f_in:
                    with gzip.open(archive_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                os.remove(file_path)
                archived_count += 1
        
        if archived_count > 0:
            print(f"📦 Archived {archived_count} old cache files to: {ARCHIVE_DIR}/cache_{timestamp}/")

def get_binance_history(symbol="BTCUSDT", end_time_ms=None, limit=100):
    """Get cached candle data for technical indicators"""
    candle_ms = (end_time_ms // 900000) * 900000
    cache_file = f"{CACHE_DIR}/{candle_ms}.json"
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
        except:
            data = []
    else:
        return pd.DataFrame() 

    if not data or not isinstance(data, list) or len(data) == 0:
        return pd.DataFrame()
    
    if isinstance(data[0], list):
         df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume", 
            "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore"
         ])
    else:
         return pd.DataFrame()

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    return df

def load_data():
    """Load trade records with all captured features"""
    if not os.path.exists(DATA_FILE):
        return None
    
    data = []
    with open(DATA_FILE, "r") as f:
        for line in f:
            try:
                r = json.loads(line)
                # Process exit records (STOP_LOSS, TAKE_PROFIT, SETTLED)
                if r.get("type") in ["STOP_LOSS", "STOP_LOSS_PAPER"]:
                    r["result"] = "LOSS"
                    data.append(r)
                elif r.get("type") in ["TAKE_PROFIT", "TAKE_PROFIT_PAPER"]:
                    r["result"] = "WIN"
                    data.append(r)
                elif r.get("type") in ["SETTLED", "SETTLED_PAPER"]:
                    # Determine WIN/LOSS based on PnL
                    pnl = r.get("pnl", 0)
                    r["result"] = "WIN" if pnl > 0 else "LOSS"
                    data.append(r)
            except:
                pass
    
    return pd.DataFrame(data) if data else None

def enrich_with_technical_indicators(df):
    """Add technical indicators from candle cache"""
    print(f"⏳ Enriching {len(df)} trades with technical indicators...")
    enriched_rows = []
    
    for idx, row in df.iterrows():
        ts_str = row["time"]
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        ts_ms = int(dt.timestamp() * 1000)
        
        hist_df = get_binance_history(end_time_ms=ts_ms, limit=60)
        
        if len(hist_df) < 30:
            # Skip if no history, but keep the row with default values
            row["rsi_14"] = 50
            row["atr_14"] = 0
            row["bb_pct"] = 0.5
            row["trend_ema"] = 0
        else:
            # Calculate technical indicators
            rsi = ta.rsi(hist_df["close"], length=14)
            row["rsi_14"] = float(rsi.iloc[-1]) if not rsi.empty else 50
            
            atr = ta.atr(hist_df["high"], hist_df["low"], hist_df["close"], length=14)
            row["atr_14"] = float(atr.iloc[-1]) if not atr.empty else 0
            
            bb = ta.bbands(hist_df["close"], length=20, std=2)
            if bb is not None and not bb.empty:
                bb_cols = [c for c in bb.columns if c.startswith("BBP")]
                row["bb_pct"] = float(bb.iloc[-1][bb_cols[0]]) if bb_cols else 0.5
            else:
                row["bb_pct"] = 0.5

            ema_short = ta.ema(hist_df["close"], length=9)
            ema_long = ta.ema(hist_df["close"], length=21)
            if ema_short is not None and ema_long is not None:
                 row["trend_ema"] = 1 if ema_short.iloc[-1] > ema_long.iloc[-1] else -1
            else:
                 row["trend_ema"] = 0
        
        # Use captured features or defaults
        row["poly_spread"] = row.get("poly_spread", 0.01)
        row["poly_bid_depth"] = row.get("poly_bid_depth", 500.0)
        row["poly_ask_depth"] = row.get("poly_ask_depth", 500.0)
        row["btc_price"] = row.get("btc_price", 0.0)
        row["diff_from_strike"] = row.get("diff_from_strike", 0.0)
        row["hour"] = row.get("hour", dt.hour)
        row["dayofweek"] = row.get("dayofweek", dt.weekday())
        row["minutes_remaining"] = row.get("minutes_remaining", 0)
             
        enriched_rows.append(row)
        
    return pd.DataFrame(enriched_rows)

def train():
    print("🚀 ML Model Training Started (V5 - Real Data Edition)")
    print("=" * 60)
    
    # Load data
    df = load_data()
    if df is None or df.empty:
        print("❌ No training data available")
        return False

    print(f"📊 Loaded {len(df)} trade records")
    
    # Enrich with technical indicators
    df = enrich_with_technical_indicators(df)
    print(f"🔧 Enriched {len(df)} records with technical indicators")

    # Prepare target variable
    df['target'] = df['result'].apply(lambda x: 1 if x == 'WIN' else 0)
    
    # Extract features
    df['direction_code'] = df['direction'].apply(lambda x: 1 if x == 'UP' else 0)
    df = df.fillna(0)

    # Feature list - all real captured data
    features = [
        'direction_code', 'hour', 'dayofweek',
        'rsi_14', 'atr_14', 'bb_pct', 'trend_ema',
        'poly_spread', 'poly_bid_depth', 'poly_ask_depth',
        'btc_price', 'diff_from_strike', 'minutes_remaining',
        'entry_price', 'pnl'
    ]
    
    # Filter to only use features that exist in dataframe
    available_features = [f for f in features if f in df.columns]
    print(f"📋 Using features: {available_features}")
    
    X = df[available_features]
    y = df['target']
    
    if len(X) < 5:
        print(f"⚠️ Not enough samples for training (need >= 5, got {len(X)})")
        return False
    
    print(f"🎯 Training XGBoost on {len(X)} records...")
    
    # Model configuration
    model = XGBClassifier(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='binary:logistic',
        eval_metric='logloss',
        random_state=42,
        importance_type='gain'
    )
    
    # Train model
    model.fit(X, y)
    
    # Evaluate
    y_pred = model.predict(X)
    acc = accuracy_score(y, y_pred)
    
    try:
        auc = roc_auc_score(y, y_pred) if len(set(y)) > 1 else 0.5
    except:
        auc = 0.5
    
    print(f"\n🏆 Model Performance:")
    print(f"   Accuracy: {acc:.2%}")
    print(f"   AUC: {auc:.3f}")
    
    # Feature importance
    imps = model.feature_importances_
    sorted_idx = np.argsort(imps)[::-1]
    print(f"\n📊 Feature Importance:")
    for i in sorted_idx[:8]:
        print(f"   {available_features[i]}: {imps[i]:.4f}")
    
    # Save model
    joblib.dump(model, MODEL_FILE)
    print(f"\n✅ Model saved to {MODEL_FILE}")
    
    # Archive and cleanup old data
    print(f"\n🧹 Auto-cleanup starting...")
    archive_old_data()
    
    return True

if __name__ == "__main__":
    success = train()
    exit(0 if success else 1)
