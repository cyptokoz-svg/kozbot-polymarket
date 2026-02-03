#!/bin/bash
# Install polymarket-bot systemd service
# Run with sudo

set -e

BOT_DIR="/home/ubuntu/clawd/bots/polymarket"
SERVICE_FILE="$BOT_DIR/polymarket-bot.service"
SYSTEMD_PATH="/etc/systemd/system/polymarket-bot.service"

echo "=== Polymarket Bot Service Installer ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo"
    exit 1
fi

# Stop existing bot if running
echo "Stopping any existing bot processes..."
pkill -f main.py || true
sleep 2

# Copy service file
echo "Installing service file..."
cp "$SERVICE_FILE" "$SYSTEMD_PATH"

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

# Enable service
echo "Enabling service..."
systemctl enable polymarket-bot

# Start service
echo "Starting service..."
systemctl start polymarket-bot

# Status
echo ""
echo "=== Service Status ==="
systemctl status polymarket-bot --no-pager

echo ""
echo "=== Installation Complete ==="
echo "View logs: sudo journalctl -u polymarket-bot -f"
echo "Check status: sudo systemctl status polymarket-bot"
