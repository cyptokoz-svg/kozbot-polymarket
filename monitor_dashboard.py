#!/usr/bin/env python3
"""
Polymarket Bot Monitor Dashboard (Server Guardian Edition)
- Real-time display of today's performance
- Server Health Monitoring (Disk, RAM, CPU)
- Auto-Healing (Restart service, Clean disk)
"""

import os
import time
import json
import shutil
import psutil
import subprocess
from datetime import datetime, timezone

LOG_FILE = "polymarket-bot/paper_trades.jsonl"
BOT_SERVICE = "polymarket-bot"

def clear_screen():
    print("\033[H\033[J", end="")

def get_today_trades():
    trades = []
    if not os.path.exists(LOG_FILE):
        return []
    
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                t = json.loads(line)
                if t["time"].startswith(today_str):
                    trades.append(t)
            except: pass
    return trades

def calculate_stats(trades):
    wins = 0
    losses = 0
    total_pnl = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    pnl_history = [0.0]
    
    for t in trades:
        if "pnl" in t:
            pnl = float(t["pnl"])
            total_pnl += pnl
            pnl_history.append(total_pnl)
            
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)
                
    total_closed = wins + losses
    win_rate = (wins / total_closed) if total_closed > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
    
    return {
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "pnl_history": pnl_history
    }

def get_bot_status():
    try:
        res = subprocess.run(["systemctl", "is-active", BOT_SERVICE], capture_output=True, text=True)
        active = res.stdout.strip() == "active"
        res_log = subprocess.run("journalctl -u polymarket-bot -n 1 --no-hostname", shell=True, capture_output=True, text=True)
        last_log = res_log.stdout.strip().split("\n")[-1] if res_log.stdout else "暂无日志"
        return active, last_log
    except:
        return False, "获取状态出错"

def get_system_health():
    """Check Disk, Memory, CPU"""
    disk = shutil.disk_usage("/")
    disk_pct = (disk.used / disk.total) * 100
    mem = psutil.virtual_memory()
    mem_pct = mem.percent
    cpu_pct = psutil.cpu_percent(interval=None)
    return {"disk_pct": disk_pct, "mem_pct": mem_pct, "cpu_pct": cpu_pct}

def auto_heal_system(health, active):
    """Simple auto-healing logic"""
    healed = []
    
    # 1. Disk Cleanup
    if health["disk_pct"] > 90.0:
        try:
            subprocess.run("rm -rf ~/.cache/pip", shell=True)
            subprocess.run("journalctl --vacuum-time=1d", shell=True)
            healed.append("已清理磁盘")
        except: pass

    # 2. Service Restart
    if not active:
        try:
            # subprocess.run(["sudo", "systemctl", "restart", BOT_SERVICE])
            # healed.append("已重启机器人服务")
            pass # 暂时禁用自动重启，以免刷屏报错
        except: pass

    return healed

def draw_ascii_chart(data, height=10):
    if not data: return ""
    min_val = min(data)
    max_val = max(data)
    range_val = max_val - min_val if max_val != min_val else 1
    chart = []
    for i in range(height):
        row = ""
        level = max_val - (i * (range_val / (height - 1)))
        row += f"{level:5.1f} | "
        for val in data:
            if val >= level: row += "█"
            else: row += " "
        chart.append(row)
    chart.append("      " + "-" * len(data))
    return "\n".join(chart)

def main():
    try:
        trades = get_today_trades()
        stats = calculate_stats(trades)
        active, last_log = get_bot_status()
        health = get_system_health()
        
        # Auto-Heal
        healed_actions = auto_heal_system(health, active)
        
        print("="*60)
        print(f"🤖 Polymarket 量化仪表盘           {datetime.now().strftime('%H:%M:%S UTC')}")
        print("="*60)
        
        # System Health
        status_icon = "🟢 运行中" if active else "🔴 已停止"
        disk_color = "\033[91m" if health['disk_pct'] > 90 else "\033[92m"
        mem_color = "\033[91m" if health['mem_pct'] > 90 else "\033[92m"
        reset = "\033[0m"

        print(f"系统状态: {status_icon}")
        print(f"服务器健康: 磁盘 {disk_color}{health['disk_pct']:.1f}%{reset} | 内存 {mem_color}{health['mem_pct']:.1f}%{reset} | CPU {health['cpu_pct']}%")
        
        if healed_actions:
            print(f"\033[93m🛡️ 自动修复: {', '.join(healed_actions)}{reset}")
            
        print(f"最新日志:    {last_log[:80]}...")
        print("-" * 60)
        
        # Performance
        pf_color = "" 
        print(f"今日交易:    {stats['wins'] + stats['losses']} 笔")
        print(f"胜率:        {stats['win_rate']:.1%} ({stats['wins']}胜 - {stats['losses']}负)")
        print(f"盈亏比:      {pf_color}{stats['profit_factor']:.2f}{reset}")
        print(f"净盈亏:      {pf_color}{stats['total_pnl']:+.2f} R{reset} (单位)")
        print("-" * 60)
        
        print("📈 资金曲线 (日内):")
        print(draw_ascii_chart(stats['pnl_history']))
        print("="*60)
        
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    main()
