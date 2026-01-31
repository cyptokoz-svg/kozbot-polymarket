#!/bin/bash
# J.A.R.V.I.S. Auto-Backup Protocol
# Syncs local code changes to GitHub

CDIR="/home/ubuntu/clawd/polymarket-bot"
DATE=$(date "+%Y-%m-%d %H:%M:%S")

cd $CDIR

# Check for changes
if [[ -n $(git status -s) ]]; then
    git add .
    git commit -m "Auto-backup: $DATE"
    git push origin main
    echo "[$DATE] Backup successful." >> backup.log
else
    echo "[$DATE] No changes to backup." >> backup.log
fi
