#!/bin/bash
# High-Performance Data Miner (Bash Edition)
# Robust, resumable, parallel fetching using curl

DATA_FILE="polymarket-bot/paper_trades.jsonl"
CACHE_DIR="polymarket-bot/candle_cache"
STATUS_FILE="polymarket-bot/miner_status.txt"

mkdir -p "$CACHE_DIR"

# Extract timestamps from JSONL using jq (fast)
echo "Extracting timestamps..."
timestamps=$(cat "$DATA_FILE" | grep -o '"time": "[^"]*"' | cut -d'"' -f4)

# Convert to milliseconds and deduplicate
targets=""
count=0
for ts in $timestamps; do
    # Convert ISO to MS timestamp (portable python one-liner)
    ms=$(date -d "$ts" +%s)000
    targets="$targets $ms"
    ((count++))
done

echo "Found $count targets." > "$STATUS_FILE"

fetch_one() {
    ts_ms=$1
    cache_file="$CACHE_DIR/$ts_ms.json"
    
    if [ -f "$cache_file" ]; then
        return
    fi
    
    # Random sleep 0.1-0.5s to avoid rate limit
    sleep 0.$(($RANDOM % 5))
    
    url="https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&endTime=$ts_ms&limit=60"
    
    # Fetch with curl, retry 3 times, max 5s timeout
    curl -s --retry 3 --retry-connrefused --connect-timeout 5 --max-time 10 "$url" > "$cache_file.tmp"
    
    # Validate
    if grep -q "\[\[" "$cache_file.tmp"; then
        mv "$cache_file.tmp" "$cache_file"
        echo "$(date): Cached $ts_ms" >> "$STATUS_FILE"
    else
        # Rate limit or error
        if grep -q "429" "$cache_file.tmp"; then
            echo "$(date): RATE LIMIT (429) - Sleeping 30s" >> "$STATUS_FILE"
            sleep 30
        else
            echo "$(date): Failed $ts_ms" >> "$STATUS_FILE"
        fi
        rm "$cache_file.tmp"
    fi
}

export -f fetch_one
export CACHE_DIR
export STATUS_FILE

# Run in parallel (slowly to respect rate limits, ~5 jobs)
# Using standard for loop instead of xargs/parallel to control rate better if tools missing
for ms in $targets; do
    fetch_one $ms &
    
    # Throttle: ensure not too many background jobs
    while [ $(jobs -r | wc -l) -ge 5 ]; do
        sleep 0.5
    done
done

wait
echo "Done." >> "$STATUS_FILE"
