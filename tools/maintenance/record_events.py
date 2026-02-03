#!/usr/bin/env python3
"""Record today's system events to State Syncer"""
import sys
sys.path.insert(0, '/home/ubuntu/clawd/skills/state-syncer/src')
from state_syncer import StateSyncer, Entity
from datetime import datetime, timezone

syncer = StateSyncer(storage_path="/home/ubuntu/clawd/memory/state-syncer")

# Event 1: Disk Full Crisis
event1 = Entity(
    id=f"sys_{datetime.now(timezone.utc).strftime('%Y%m%d')}_001",
    type="system",
    timestamp=datetime.now(timezone.utc),
    content={
        "event": "disk_full_crisis",
        "severity": "critical",
        "details": {
            "before": "96%",
            "after": "91%",
            "actions": [
                "Removed old snap versions (mesa-2404, core22)",
                "Cleaned APT cache",
                "Cleaned journal logs"
            ],
            "freed_mb": 700
        },
        "resolution": "Resource monitoring enabled"
    },
    tags=["system", "disk", "critical", "resource-guardian"],
    importance="critical"
)

# Event 2: Resource Guardian Fixed
event2 = Entity(
    id=f"sys_{datetime.now(timezone.utc).strftime('%Y%m%d')}_002",
    type="system",
    timestamp=datetime.now(timezone.utc),
    content={
        "event": "resource_guardian_enabled",
        "severity": "high",
        "details": {
            "problem": "Resource Guardian skill existed but was not integrated",
            "solution": [
                "Added disk/memory checks to Bot code",
                "Created cron job for periodic monitoring"
            ],
            "check_interval": "300 seconds (5 min)"
        }
    },
    tags=["system", "resource-guardian", "monitoring", "fix"],
    importance="high"
)

# Event 3: State Syncer Clarification
event3 = Entity(
    id=f"sys_{datetime.now(timezone.utc).strftime('%Y%m%d')}_003",
    type="system",
    timestamp=datetime.now(timezone.utc),
    content={
        "event": "state_syncer_purpose_clarified",
        "severity": "medium",
        "details": {
            "misuse_attempted": "Used State Syncer for trade data storage",
            "correct_usage": "System memory/events only",
            "trade_data_location": "paper_trades.jsonl",
            "memory_data_location": "memory/state-syncer/"
        },
        "lesson": "Skills are tools with specific purposes"
    },
    tags=["system", "state-syncer", "lesson", "architecture"],
    importance="medium"
)

# Save all events
for event in [event1, event2, event3]:
    syncer.save(event)
    print(f"✅ Saved: {event.content['event']}")

# Generate compact
compact_path = syncer.compact()
print(f"\n📦 Compact file: {compact_path}")

# Show summary
all_system = syncer.load('system')
print(f"\n📊 Total system events: {len(all_system)}")
