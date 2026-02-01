#!/bin/bash
# Bot watchdog - auto restart on crash

while true; do
    if ! pgrep -f "btc_15m_bot_v3.py" > /dev/null; then
        echo "$(date): Bot not running, restarting..." >> /tmp/watchdog.log
        cd /home/ubuntu/clawd/bots/polymarket
        source venv/bin/activate
        nohup python3 btc_15m_bot_v3.py > bot_run.log 2>&1 &
        echo "$(date): Bot restarted with PID $!" >> /tmp/watchdog.log
    fi
    sleep 30
done
