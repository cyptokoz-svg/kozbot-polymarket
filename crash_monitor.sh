#!/bin/bash
# Crash Monitor - Detects and reports bot crashes

BOT_NAME="btc_15m_bot_v3.py"
LOG_FILE="/home/ubuntu/clawd/bots/polymarket/bot_run.log"
ALERT_INTERVAL=60  # Alert every 60 seconds if down
LAST_ALERT=0

check_bot() {
    pgrep -f "$BOT_NAME" > /dev/null
}

get_last_log() {
    tail -5 "$LOG_FILE" 2>/dev/null | head -1
}

while true; do
    if ! check_bot; then
        NOW=$(date +%s)
        if [ $((NOW - LAST_ALERT)) -gt $ALERT_INTERVAL ]; then
            echo "🚨 $(date): Bot CRASHED! Last log: $(get_last_log)"
            # Restart
            cd /home/ubuntu/clawd/bots/polymarket
            source venv/bin/activate
            nohup python3 btc_15m_bot_v3.py > bot_run.log 2>&1 &
            echo "✅ $(date): Bot restarted"
            LAST_ALERT=$NOW
        fi
    fi
    sleep 5
done
