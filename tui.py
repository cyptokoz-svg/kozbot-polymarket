from datetime import datetime
from threading import Lock
import time

from rich.console import Console
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich.live import Live

class BotTUI:
    def __init__(self):
        self.console = Console(no_color=True)
        self.layout = Layout()
        
        # State data
        self.state = {
            "status": "Starting...",
            "market_slug": "---",
            "btc_price": 0.0,
            "strike": 0.0,
            "ask_up": 0.0,
            "bid_up": 0.0,
            "ask_down": 0.0,
            "bid_down": 0.0,
            "source": "---",
            "last_update": time.time(),
            "logs": [],
            "pnl": 0.0,
            "positions": []
        }
        self.lock = Lock()
        
    def update_state(self, **kwargs):
        with self.lock:
            self.state.update(kwargs)
            self.state["last_update"] = time.time()

    def add_log(self, message):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.state["logs"].append(f"{ts} {message}")
            if len(self.state["logs"]) > 6:
                self.state["logs"].pop(0)

    def render(self) -> Table:
        # Outer container
        grid = Table.grid(expand=True)
        
        # 1. Header (Single Line)
        # Polymarket Bot V4 [Running] 14:03:00 | SRC: WebSocket
        header_text = f"Polymarket Bot V4 [{self.state['status']}] {datetime.now().strftime('%H:%M:%S')} | SRC: {self.state.get('source','REST')}"
        grid.add_row(Text(header_text, style="bold"))
        grid.add_row(Text("-" * 80, style="dim"))

        # 2. Market Info (Aligned columns)
        # Market: btc-15m-123456   Strike: $78,100.00
        #                          BTC:    $78,200.00
        #                          Delta:     +100.00
        market_table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
        market_table.add_column("Label", justify="right", width=12)
        market_table.add_column("Value", justify="left", width=25)
        market_table.add_column("Label2", justify="right", width=8)
        market_table.add_column("Value2", justify="right", width=12)
        
        market_table.add_row("Market:", self.state["market_slug"][-15:] if len(self.state["market_slug"])>15 else self.state["market_slug"], "Strike:", f"${self.state['strike']:,.2f}")
        market_table.add_row("", "", "BTC:", f"${self.state['btc_price']:,.2f}")
        
        diff = self.state["btc_price"] - self.state["strike"]
        diff_str = f"{'+' if diff > 0 else ''}{diff:.2f}"
        market_table.add_row("PnL:", f"{self.state.get('pnl', 0.0):.2f}%", "Delta:", diff_str)
        
        grid.add_row(market_table)
        grid.add_row(Text("-" * 80, style="dim"))
        
        # 3. Orderbook (Strictly Aligned)
        # Token      Bid      Ask
        # UP       0.320    0.330
        # DOWN     0.670    0.680
        ob_table = Table(header_style="bold", box=None, padding=(0, 4), expand=False)
        ob_table.add_column("Token", justify="left", width=8)
        ob_table.add_column("Bid", justify="right", width=10)
        ob_table.add_column("Ask", justify="right", width=10)
        
        ob_table.add_row("UP", f"{self.state['bid_up']:.3f}", f"{self.state['ask_up']:.3f}")
        ob_table.add_row("DOWN", f"{self.state['bid_down']:.3f}", f"{self.state['ask_down']:.3f}")
        
        grid.add_row(ob_table)
        
        # 4. Positions (Compact)
        if self.state["positions"]:
            grid.add_row(Text("-" * 80, style="dim"))
            pos_text = "POS: " + ", ".join([f"{p['direction']}@{p['entry_price']:.3f}" for p in self.state["positions"]])
            grid.add_row(pos_text)

        grid.add_row(Text("-" * 80, style="dim"))

        # 5. Logs (Raw text)
        for log in self.state["logs"]:
            grid.add_row(Text(log, style="dim"))

        return grid
