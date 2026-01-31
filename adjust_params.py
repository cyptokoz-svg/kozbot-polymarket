#!/usr/bin/env python3
"""
Safe Parameter Adjustment Tool
Usage: python adjust_params.py --sl 0.3 --edge 0.1
"""

import json
import argparse
import sys
import logging
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'bot.log'))
    ]
)
logger = logging.getLogger(__name__)

CONFIG_FILE = "polymarket-bot/config.json"

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_config(conf):
    with open(CONFIG_FILE, "w") as f:
        json.dump(conf, f, indent=4)
    logger.info(f"✅ Config updated: {CONFIG_FILE}")

def main():
    parser = argparse.ArgumentParser(description="Adjust Bot Strategy Parameters")
    parser.add_argument("--sl", type=float, help="Stop Loss % (e.g., 0.35 for 35%)")
    parser.add_argument("--edge", type=float, help="Min Edge % (e.g., 0.08 for 8%)")
    parser.add_argument("--margin", type=float, help="Safety Margin % (e.g., 0.0006 for 0.06%)")
    parser.add_argument("--show", action="store_true", help="Show current config")
    
    args = parser.parse_args()
    
    conf = load_config()
    
    if args.show:
        logger.info(json.dumps(conf, indent=4))
        return

    updated = False
    if args.sl is not None:
        logger.info(f"Changing Stop Loss: {conf.get('stop_loss_pct')} -> {args.sl}")
        conf["stop_loss_pct"] = args.sl
        updated = True
        
    if args.edge is not None:
        logger.info(f"Changing Min Edge: {conf.get('min_edge')} -> {args.edge}")
        conf["min_edge"] = args.edge
        updated = True
        
    if args.margin is not None:
        logger.info(f"Changing Safety Margin: {conf.get('safety_margin_pct')} -> {args.margin}")
        conf["safety_margin_pct"] = args.margin
        updated = True
        
    if updated:
        save_config(conf)
        logger.info("🚀 Changes will be hot-reloaded by the bot in <60s.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
