#!/usr/bin/env python3
"""
Resource Guardian Monitor - Runs as a background service
Integrated with Polymarket Bot for system health monitoring
"""
import sys
import time
import json
from datetime import datetime
from pathlib import Path

# Add skill path
sys.path.insert(0, '/home/ubuntu/clawd/skills/resource-guardian')
from resource_guardian import ResourceGuardian

def main():
    storage_path = Path.home() / '.local' / 'share' / 'resource-guardian'
    guardian = ResourceGuardian(storage_path=str(storage_path))
    
    print(f"[{datetime.utcnow().isoformat()}] Resource Guardian started")
    
    while True:
        try:
            # Collect metrics
            metrics = guardian.collect_metrics()
            
            # Check thresholds and get alerts
            alerts = guardian.check_thresholds(metrics)
            
            # Save metrics
            guardian.save_metrics(metrics)
            
            # Log alerts if any
            if alerts:
                for alert in alerts:
                    log_msg = f"[{datetime.utcnow().isoformat()}] ALERT: {alert.level.upper()} - {alert.message}"
                    print(log_msg, flush=True)
                    
                    # Write to bot_run.log if critical
                    if alert.level == 'critical':
                        bot_log = Path('/home/ubuntu/clawd/bots/polymarket/bot_run.log')
                        if bot_log.exists():
                            with open(bot_log, 'a') as f:
                                f.write(f"{log_msg}\n")
            
            # Sleep for 60 seconds
            time.sleep(60)
            
        except KeyboardInterrupt:
            print(f"[{datetime.utcnow().isoformat()}] Resource Guardian stopped")
            break
        except Exception as e:
            print(f"[{datetime.utcnow().isoformat()}] Error: {e}", flush=True)
            time.sleep(60)

if __name__ == '__main__':
    main()
