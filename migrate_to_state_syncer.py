#!/usr/bin/env python3
"""
Migrate existing paper_trades.jsonl to State Syncer JSON format
"""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/home/ubuntu/clawd/skills/state-syncer/src')
from state_syncer import StateSyncer, Entity

def migrate_trades():
    syncer = StateSyncer(storage_path="~/.local/share/state-syncer")
    trades_file = Path("/home/ubuntu/clawd/bots/polymarket/paper_trades.jsonl")
    
    if not trades_file.exists():
        print("❌ paper_trades.jsonl not found")
        return
    
    count = 0
    with open(trades_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                trade = json.loads(line)
                
                # Determine entity type and tags
                trade_type = trade.get('type', 'UNKNOWN')
                
                if 'V3_SMART' in trade_type:
                    entity_type = 'trade'
                    tags = ['trade', 'paper', trade.get('direction', 'unknown').lower(), 'v3_smart']
                    importance = 'high'
                elif 'TAKE_PROFIT' in trade_type or 'STOP_LOSS' in trade_type or 'SETTLED' in trade_type:
                    entity_type = 'exit'
                    exit_kind = 'take_profit' if 'TAKE_PROFIT' in trade_type else ('stop_loss' if 'STOP_LOSS' in trade_type else 'settled')
                    tags = ['exit', 'paper', trade.get('direction', 'unknown').lower(), exit_kind]
                    importance = 'high'
                else:
                    entity_type = 'trade'
                    tags = ['trade', 'legacy']
                    importance = 'medium'
                
                # Parse timestamp
                time_str = trade.get('time', datetime.now(timezone.utc).isoformat())
                try:
                    timestamp = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                except:
                    timestamp = datetime.now(timezone.utc)
                
                # Create entity
                entity = Entity(
                    id=f"migrated_{trade.get('market', 'unknown')}_{count}",
                    type=entity_type,
                    timestamp=timestamp,
                    content=trade,
                    tags=tags,
                    importance=importance
                )
                
                syncer.save(entity)
                count += 1
                
            except Exception as e:
                print(f"❌ Failed to migrate line: {e}")
                continue
    
    print(f"✅ Migrated {count} trades to State Syncer")
    
    # Generate compact file
    compact_path = syncer.compact()
    print(f"📦 Compact file: {compact_path}")
    
    # Show summary
    trades = syncer.load('trade')
    exits = syncer.load('exit')
    print(f"\n📊 Summary:")
    print(f"  - Trade entities: {len(trades)}")
    print(f"  - Exit entities: {len(exits)}")
    print(f"  - Total: {len(trades) + len(exits)}")

if __name__ == '__main__':
    migrate_trades()
