#!/bin/bash
# Smart Bot Watchdog - monitors log activity, not just process

LOG_FILE="/home/ubuntu/clawd/bots/polymarket/bot_run.log"
MAX_IDLE_SECONDS=120  # 2 minutes without log update = dead
RESTART_COUNT=0

send_alert() {
    local msg="$1"
    echo "$(date): $msg" | tee -a /tmp/watchdog.log
    # Send to Telegram if possible
    if [ -f "/home/ubuntu/clawd/.telegram_bot_token" ]; then
        TOKEN=$(cat /home/ubuntu/clawd/.telegram_bot_token 2>/dev/null)
        CHAT_ID="1640598145"
        curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}" \
            -d "text=🚨 ${msg}" > /dev/null 2>&1 || true
    fi
}

while true; do
    sleep 30
    
    # Check 1: Process exists
    if ! pgrep -f "btc_15m_bot_v3.py" > /dev/null; then
        send_alert "Bot 进程不存在，正在重启..."
        cd /home/ubuntu/clawd/bots/polymarket
        source venv/bin/activate
        nohup python3 btc_15m_bot_v3.py > bot_run.log 2>&1 &
        sleep 5
        NEW_PID=$(pgrep -f "btc_15m_bot_v3.py" | head -1)
        send_alert "Bot 已重启，PID: ${NEW_PID}"
        RESTART_COUNT=$((RESTART_COUNT + 1))
        continue
    fi
    
    # Check 2: Log activity (process alive but stuck?)
    if [ -f "$LOG_FILE" ]; then
        LAST_MODIFIED=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo "0")
        CURRENT_TIME=$(date +%s)
        IDLE_TIME=$((CURRENT_TIME - LAST_MODIFIED))
        
        if [ $IDLE_TIME -gt $MAX_IDLE_SECONDS ]; then
            send_alert "Bot 卡住！${IDLE_TIME}秒无日志更新，强制重启..."
            pkill -f "btc_15m_bot_v3.py"
            sleep 2
            cd /home/ubuntu/clawd/bots/polymarket
            source venv/bin/activate
            nohup python3 btc_15m_bot_v3.py > bot_run.log 2>&1 &
            sleep 5
            NEW_PID=$(pgrep -f "btc_15m_bot_v3.py" | head -1)
            send_alert "Bot 已强制重启，PID: ${NEW_PID}"
            RESTART_COUNT=$((RESTART_COUNT + 1))
        fi
    fi
done
