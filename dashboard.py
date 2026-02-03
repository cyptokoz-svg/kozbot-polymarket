"""
Polymarket Bot Web Dashboard
轻量级监控面板
"""
from flask import Flask, jsonify, render_template_string
import json
from datetime import datetime, timedelta
import os
import socket

app = Flask(__name__)

# 路径配置
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(BOT_DIR, "paper_trades.jsonl")
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")
MARKET_STATE_FILE = os.path.join(BOT_DIR, "market_state.json")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Polymarket Bot Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e27;
            color: #fff;
            padding: 20px;
        }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .header .status { 
            display: inline-block; 
            padding: 5px 15px; 
            border-radius: 20px; 
            font-size: 14px;
        }
        .status.running { background: #22c55e; }
        .status.stopped { background: #ef4444; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #1a1f3a;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #2d3748;
        }
        .stat-card h3 {
            font-size: 14px;
            color: #94a3b8;
            margin-bottom: 10px;
            text-transform: uppercase;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
        }
        .stat-card .value.positive { color: #22c55e; }
        .stat-card .value.negative { color: #ef4444; }
        
        .section {
            background: #1a1f3a;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #2d3748;
        }
        .section h2 {
            font-size: 18px;
            margin-bottom: 15px;
            color: #e2e8f0;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #2d3748;
        }
        th {
            color: #94a3b8;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
        }
        tr:hover { background: #252b4d; }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge.win { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .badge.loss { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .badge.up { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
        .badge.down { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        
        .chart-placeholder {
            height: 200px;
            background: #252b4d;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #64748b;
        }
        
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: 1fr; }
            table { font-size: 12px; }
            th, td { padding: 8px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Polymarket Bot Dashboard</h1>
        <span class="status running">● Running</span>
        <div id="live-indicator" style="display:none; color:#22c55e; font-size:12px; margin-top:5px;">⚡ LIVE DATA</div>
    </div>
    
    <!-- Real-Time Market Section -->
    <div class="section" id="market-section">
        <h2>⚡ Real-Time Market</h2>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <div>
                <div style="font-size: 12px; color: #94a3b8;">ACTIVE MARKET</div>
                <div id="market-slug" style="font-size: 16px; font-weight: bold; color: #fff;">Wait...</div>
            </div>
            <div style="text-align: right;">
                 <div style="font-size: 12px; color: #94a3b8;">DATA SOURCE</div>
                 <div id="data-source" class="badge">Wait...</div>
            </div>
        </div>
        
        <div class="stats-grid" style="margin-bottom: 0;">
            <div class="stat-card" style="background: #1e293b;">
                <h3>BTC Price (Binance)</h3>
                <div id="btc-price" class="value" style="color: #f59e0b;">---</div>
            </div>
            <div class="stat-card" style="background: #1e293b;">
                <h3>Strike Price</h3>
                <div id="strike-price" class="value" style="color: #fff;">---</div>
            </div>
            <div class="stat-card" style="background: #1e293b;">
                <h3>Delta (Price - Strike)</h3>
                <div id="price-delta" class="value">---</div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
            <!-- UP Token -->
            <div style="background: rgba(34, 197, 94, 0.05); padding: 15px; border-radius: 8px; border: 1px solid rgba(34, 197, 94, 0.2);">
                <div style="color: #22c55e; font-weight: bold; margin-bottom: 10px;">📈 UP TOKEN</div>
                <div style="display: flex; justify-content: space-between;">
                    <div>
                        <div style="font-size: 12px; color: #94a3b8;">BEST ASK</div>
                        <div id="ask-up" style="font-size: 24px; font-weight: bold;">---</div>
                    </div>
                     <div>
                        <div style="font-size: 12px; color: #94a3b8;">BEST BID</div>
                        <div id="bid-up" style="font-size: 24px; font-weight: bold; color: #94a3b8;">---</div>
                    </div>
                </div>
            </div>
            
            <!-- DOWN Token -->
            <div style="background: rgba(239, 68, 68, 0.05); padding: 15px; border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.2);">
                <div style="color: #ef4444; font-weight: bold; margin-bottom: 10px;">📉 DOWN TOKEN</div>
                <div style="display: flex; justify-content: space-between;">
                    <div>
                        <div style="font-size: 12px; color: #94a3b8;">BEST ASK</div>
                        <div id="ask-down" style="font-size: 24px; font-weight: bold;">---</div>
                    </div>
                     <div>
                        <div style="font-size: 12px; color: #94a3b8;">BEST BID</div>
                        <div id="bid-down" style="font-size: 24px; font-weight: bold; color: #94a3b8;">---</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="stats-grid">
        <div class="stat-card">
            <h3>Win Rate</h3>
            <div class="value positive">{{ stats.win_rate }}%</div>
        </div>
        <div class="stat-card">
            <h3>Total PnL</h3>
            <div class="value {% if stats.total_pnl > 0 %}positive{% else %}negative{% endif %}">
                {{ "+%.2f" % stats.total_pnl if stats.total_pnl > 0 else "%.2f" % stats.total_pnl }}%
            </div>
        </div>
        <div class="stat-card">
            <h3>Total Trades</h3>
            <div class="value">{{ stats.total_trades }}</div>
        </div>
        <div class="stat-card">
            <h3>Today's PnL</h3>
            <div class="value {% if stats.today_pnl > 0 %}positive{% else %}negative{% endif %}">
                {{ "+%.2f" % stats.today_pnl if stats.today_pnl > 0 else "%.2f" % stats.today_pnl }}%
            </div>
        </div>
    </div>
    
    <div class="section">
        <h2>📊 PnL Chart (Last 30 Days)</h2>
        <div class="chart-placeholder">Chart visualization would go here</div>
    </div>
    
    <div class="section">
        <h2>📈 Recent Trades</h2>
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Market</th>
                    <th>Direction</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>PnL</th>
                    <th>Type</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in recent_trades %}
                <tr>
                    <td>{{ trade.time }}</td>
                    <td>{{ trade.market }}</td>
                    <td><span class="badge {{ trade.direction.lower() }}">{{ trade.direction }}</span></td>
                    <td>${{ "%.2f" % trade.entry }}</td>
                    <td>${{ "%.2f" % trade.exit }}</td>
                    <td class="{% if trade.pnl > 0 %}positive{% else %}negative{% endif %}">
                        {{ "+%.1f" % (trade.pnl * 100) if trade.pnl > 0 else "%.1f" % (trade.pnl * 100) }}%
                    </td>
                    <td>
                        <span class="badge {% if 'PROFIT' in trade.type %}win{% else %}loss{% endif %}">
                            {{ trade.type.replace('_PAPER', '').replace('_', ' ') }}
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h2>📋 Open Positions</h2>
        {% if open_positions %}
        <table>
            <thead>
                <tr>
                    <th>Market</th>
                    <th>Direction</th>
                    <th>Entry Price</th>
                    <th>Shares</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for pos in open_positions %}
                <tr>
                    <td>{{ pos.market }}</td>
                    <td><span class="badge {{ pos.direction.lower() }}">{{ pos.direction }}</span></td>
                    <td>${{ "%.2f" % pos.entry_price }}</td>
                    <td>{{ "%.4f" % pos.shares }}</td>
                    <td>{{ pos.status }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color: #64748b; text-align: center;">No open positions</p>
        {% endif %}
    </div>
    
    <div style="text-align: center; color: #64748b; margin-top: 30px; font-size: 12px;">
        Last updated: {{ last_updated }} | <a href="/api/stats" style="color: #3b82f6;">API</a>
    </div>

    <script>
        function updateMarketData() {
            fetch('/api/market_state')
                .then(response => response.json())
                .then(data => {
                    if (data.error) return;
                    
                    document.getElementById('live-indicator').style.display = 'block';
                    document.getElementById('market-slug').innerText = data.market_slug || 'No Active Market';
                    
                    // Source badge
                    const sourceEl = document.getElementById('data-source');
                    sourceEl.innerText = data.source || 'REST';
                    sourceEl.className = 'badge ' + (data.source === 'WebSocket' ? 'win' : 'loss');
                    
                    // Prices
                    document.getElementById('btc-price').innerText = '$' + (data.btc_price ? data.btc_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '---');
                    document.getElementById('strike-price').innerText = '$' + (data.strike ? data.strike.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '---');
                    
                    // Delta
                    if (data.btc_price && data.strike) {
                        const delta = data.btc_price - data.strike;
                        const deltaEl = document.getElementById('price-delta');
                        deltaEl.innerText = (delta > 0 ? '+' : '') + delta.toFixed(2);
                        deltaEl.className = 'value ' + (delta > 0 ? 'positive' : 'negative');
                    }
                    
                    // Orderbook
                    document.getElementById('ask-up').innerText = data.ask_up ? data.ask_up.toFixed(3) : '---';
                    document.getElementById('bid-up').innerText = data.bid_up ? data.bid_up.toFixed(3) : '---';
                    document.getElementById('ask-down').innerText = data.ask_down ? data.ask_down.toFixed(3) : '---';
                    document.getElementById('bid-down').innerText = data.bid_down ? data.bid_down.toFixed(3) : '---';
                })
                .catch(err => console.error(err));
        }
        
        // Poll every 1 second
        setInterval(updateMarketData, 1000);
        updateMarketData();
    </script>
</body>
</html>
"""


def load_trades():
    """加载交易历史"""
    trades = []
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, 'r') as f:
            for line in f:
                try:
                    trades.append(json.loads(line.strip()))
                except:
                    continue
    return trades


def calculate_stats(trades):
    """计算统计数据"""
    stats = {
        'total_trades': 0,
        'win_count': 0,
        'loss_count': 0,
        'total_pnl': 0.0,
        'today_pnl': 0.0,
        'win_rate': 0.0
    }
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    for trade in trades:
        if 'pnl' in trade:
            stats['total_trades'] += 1
            stats['total_pnl'] += trade['pnl']
            
            if trade['pnl'] > 0:
                stats['win_count'] += 1
            else:
                stats['loss_count'] += 1
            
            # Check if trade is from today
            trade_time = trade.get('time', '')
            if trade_time.startswith(today):
                stats['today_pnl'] += trade['pnl']
    
    if stats['total_trades'] > 0:
        stats['win_rate'] = round(stats['win_count'] / stats['total_trades'] * 100, 1)
    
    return stats


def load_positions():
    """加载当前持仓"""
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('positions', [])
    return []

def build_dashboard_context():
    """构建面板数据"""
    trades = load_trades()
    stats = calculate_stats(trades)
    
    # 格式化最近交易
    recent_trades = []
    for trade in trades[-10:]:  # 最近10笔
        if 'pnl' in trade:
            recent_trades.append({
                'time': trade.get('time', '')[:16].replace('T', ' '),
                'market': trade.get('market', 'Unknown')[-10:],  # 缩短
                'direction': trade.get('direction', ''),
                'entry': trade.get('entry_price', 0),
                'exit': trade.get('exit_price', 0),
                'pnl': trade.get('pnl', 0),
                'type': trade.get('type', '')
            })
    
    open_positions = []
    positions = load_positions()
    for pos in positions:
        if pos.get('status') == 'OPEN':
            open_positions.append({
                'market': pos.get('market_slug', 'Unknown')[-10:],
                'direction': pos.get('direction', ''),
                'entry_price': pos.get('entry_price', 0),
                'shares': pos.get('shares', 0),
                'status': pos.get('status', '')
            })
    
    return {
        'stats': stats,
        'recent_trades': list(reversed(recent_trades)),
        'open_positions': open_positions,
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

@app.route('/')
def dashboard():
    """主面板"""
    context = build_dashboard_context()
    return render_template_string(HTML_TEMPLATE, **context)


@app.route('/api/stats')
def api_stats():
    """API: 统计数据"""
    trades = load_trades()
    stats = calculate_stats(trades)
    return jsonify(stats)


@app.route('/api/trades')
def api_trades():
    """API: 交易历史"""
    trades = load_trades()
    return jsonify(trades[-100:])  # 最近100笔


@app.route('/api/positions')
def api_positions():
    """API: 当前持仓"""
    positions = load_positions()
    return jsonify(positions)

@app.route('/api/market_state')
def api_market_state():
    """API: 实时行情"""
    if os.path.exists(MARKET_STATE_FILE):
        try:
            with open(MARKET_STATE_FILE, 'r') as f:
                return jsonify(json.load(f))
        except:
            pass
    return jsonify({"error": "No market state data"})


if __name__ == '__main__':
    host = os.environ.get('DASHBOARD_HOST', '127.0.0.1')
    port = int(os.environ.get('DASHBOARD_PORT', '5000'))
    print("🚀 Starting Polymarket Bot Dashboard...")
    print(f"📊 URL: http://{host}:{port}")
    can_bind = True
    probe = socket.socket()
    try:
        probe.bind((host, port))
    except PermissionError:
        can_bind = False
    except OSError as e:
        if getattr(e, "errno", None) in (1, 13):
            can_bind = False
        else:
            raise
    finally:
        probe.close()
    if not can_bind:
        output_path = os.path.join(BOT_DIR, "dashboard.html")
        context = build_dashboard_context()
        with app.app_context():
            html = render_template_string(HTML_TEMPLATE, **context)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print("⚠️ Unable to bind local port in this environment.")
        print(f"✅ Static dashboard saved to: {output_path}")
    else:
        app.run(host=host, port=port, debug=False)
