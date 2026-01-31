import json
import requests
import os
from datetime import datetime, timezone

# Configuration (Add these to your env or config.json)
CONFIG_FILE = "polymarket-bot/config.json"

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except: return {}

conf = load_config()
NOTION_TOKEN = conf.get("notion_token")
DATABASE_ID = conf.get("notion_database_id")
LOG_FILE = "polymarket-bot/paper_trades.jsonl"

def get_daily_stats():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trades = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                try:
                    t = json.loads(line)
                    if t["time"].startswith(today_str):
                        trades.append(t)
                except: pass
    
    if not trades: return None

    wins = len([t for t in trades if float(t.get("pnl", 0)) > 0])
    losses = len([t for t in trades if float(t.get("pnl", 0)) < 0])
    total_pnl = sum([float(t.get("pnl", 0)) for t in trades])
    
    return {
        "date": today_str,
        "pnl": total_pnl,
        "trades": len(trades),
        "wins": wins,
        "losses": losses
    }

def push_to_notion(stats):
    if not NOTION_TOKEN or not DATABASE_ID:
        print("❌ Notion credentials missing. Skipping sync.")
        return

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Payload matching a Notion Database with columns: Date, PnL, Trades, WinRate
    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Date": {"title": [{"text": {"content": stats["date"]}}]},
            "Net PnL (R)": {"number": round(stats["pnl"], 2)},
            "Total Trades": {"number": stats["trades"]},
            "Win Count": {"number": stats["wins"]},
            "Loss Count": {"number": stats["losses"]}
        }
    }
    
    try:
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code == 200:
            print(f"✅ Successfully synced {stats['date']} stats to Notion!")
        else:
            print(f"❌ Notion API Error: {resp.text}")
    except Exception as e:
        print(f"❌ Network Error: {e}")

if __name__ == "__main__":
    stats = get_daily_stats()
    if stats:
        push_to_notion(stats)
    else:
        print("No trades today.")
