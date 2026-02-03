# Polymarket Trading Bot

High-performance automated trading bot for Polymarket binary options markets, optimized for real-time data acquisition and low-latency execution.

## ✨ Features

- **Real-Time Data**: Fully asynchronous architecture with <100ms response time
- **Multiple Data Sources**: Hyperliquid (<50ms), Binance, Polymarket WebSocket
- **Smart Execution**: Order validation, position tracking, automatic redemption
- **Risk Management**: Configurable limits, edge thresholds, position sizing
- **Paper Trading**: Test strategies risk-free before going live

## 🛠️ Installation

```bash
# Clone repository
git clone <your-repo-url>
cd kozbot-polymarket

# Install dependencies
pip3 install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Configure bot settings
cp config.json.template config.json
# Edit config.json
```

## ⚙️ Configuration

### Required Environment Variables

```bash
PRIVATE_KEY=your_ethereum_private_key
FUNDER_ADDRESS=your_safe_wallet_address  # For Gnosis Safe users
```

### Optional Environment Variables

```bash
# Telegram notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Polymarket Builder API (for advanced order routing)
POLY_BUILDER_API_KEY=your_key
POLY_BUILDER_API_SECRET=your_secret
POLY_BUILDER_API_PASSPHRASE=your_passphrase
```

### Configuration File (config.json)

Key settings (see `config.json.template` for full options):

```json
{
  "paper_trade": true,              // Start in paper trading mode
  "execution_enabled": false,       // Enable live trading
  "min_edge": 0.08,                 // 8% minimum edge to trade
  "max_position_usd": 100,          // Maximum position size
  "api_timeout_sec": 5,             // API request timeout
  "orderbook_cache_sec": 0.5,       // Orderbook cache TTL
  "price_cache_sec": 0.5            // Price cache TTL
}
```

## 🚀 Usage

### Paper Trading (Recommended for Testing)

```bash
python3 main.py
```

### Live Trading

1. Set `execution_enabled: true` in `config.json`
2. Ensure `.env` has valid `PRIVATE_KEY`
3. Start with small `max_position_usd` to test

```bash
python3 main.py
```

### Dry Run Mode (No Order Placement)

```bash
python3 main.py --dry-run
```

## 📊 System Architecture

```
┌─────────────┐
│   main.py   │  ← Entry point, main loop
└──────┬──────┘
       │
       ├─→ Data Sources (data_source.py)
       │   ├─→ Binance (price feeds)
       │   ├─→ Hyperliquid (<50ms latency)
       │   └─→ Polymarket (WebSocket + REST)
       │
       ├─→ Strategy (strategy.py)
       │   └─→ Calculate signals & edge
       │
       ├─→ Risk Manager (risk_manager.py)
       │   └─→ Validate trade limits
       │
       └─→ Executor (executor.py)
           ├─→ Place orders
           ├─→ Track positions
           └─→ Auto redemption
```

## 🔍 Performance Metrics

- **Main Loop Frequency**: 10 Hz (100ms interval)
- **API Request Timeout**: 5s (fails fast)
- **Orderbook Freshness**: <500ms
- **Price Data Freshness**: <500ms
- **WebSocket Latency**: Real-time (<100ms)

## 📁 Project Structure

```
kozbot-polymarket/
├── main.py              # Main bot logic
├── data_source.py       # Data fetching (async)
├── api_client.py        # HTTP client (httpx)
├── executor.py          # Order execution
├── strategy.py          # Strategy interface
├── risk_manager.py      # Risk checks
├── config.py            # Configuration management
├── validators.py        # Input validation NEW
├── constants.py         # Constants definition NEW
├── notification.py      # Telegram alerts
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
└── tools/              # Utility scripts
    ├── maintenance/     # Debugging tools
    ├── data/           # Data analysis
    └── redeem/         # Redemption utilities
```

## 🐛 Troubleshooting

### "Config validation failed"

Check `config.json` values:
- `api_timeout_sec` must be > 0 and < 60
- `min_edge` must be between 0 and 1
- All cache TTLs must be >= 0

### "No Private Key found"

Ensure `.env` contains:
```bash
PRIVATE_KEY=0x...your...key...
```

### "Order validation failed"

Orders automatically validate:
- Price must be between 0 and 1
- Size must be > 0.0001 shares
- Token ID must be valid

Check logs for specific validation errors.

### WebSocket Connection Issues

WebSocket auto-reconnects. If persistent issues:
1. Check internet connection
2. Verify Polymarket API status
3. Review logs for specific errors

## 📈 Strategy Development

Create custom strategies by extending the `Strategy` base class:

```python
from strategy import Strategy

class MyStrategy(Strategy):
    def calculate_signal(self, market_data, btc_price):
        # Your logic here
        if some_condition:
            return {
                "direction": "UP",
                "price": 0.65,
                "edge": 0.15,
                "fair_value": 0.80
            }
        return None
```

## 🔐 Security Best Practices

- ✅ Never commit `.env` or `config.json` with real credentials
- ✅ Use separate wallets for testing and production
- ✅ Start with small position sizes
- ✅ Monitor logs for unusual activity
- ✅ Keep private keys secure (use hardware wallets for large amounts)

## 📝 Logs

Logs are written to `bot_v4.log` and console:

```
2026-02-03 12:00:00 - INFO - 🔍 Validating configuration...
2026-02-03 12:00:00 - INFO - ✅ Config validation passed
2026-02-03 12:00:01 - INFO - 🚀 Starting bot...
```

## 🧪 Testing

Run validation tests:

```bash
# Test validators
python3 -c "from validators import validate_price, validate_size; print('OK')"

# Test config
python3 -c "from config import config; config.validate_config()"

# Test market data
python3 market_report.py
```

## 🤝 Contributing

Contributions welcome! Please ensure:

1. Code follows existing style
2. Add docstrings to new functions
3. Update README if adding features
4. Test before submitting PR

## ⚠️ Disclaimer

This software is for educational purposes. Trading involves risk of loss. Use at your own risk. The authors are not responsible for any financial losses.

## 📄 License

MIT License - see LICENSE file for details

---

**Need Help?** Check `tools/README.md` for utility scripts or open an issue.
