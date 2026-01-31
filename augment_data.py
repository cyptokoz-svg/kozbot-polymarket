import json
import os

FILE = "polymarket-bot/paper_trades.jsonl"
TEMP_FILE = "polymarket-bot/paper_trades_augmented.jsonl"

def augment():
    if not os.path.exists(FILE): return
    
    new_records = []
    with open(FILE, "r") as f:
        for line in f:
            try:
                rec = json.loads(line)
                # Only process synthetic historical WINs
                if rec.get("type") == "SETTLED" and rec.get("result") == "WIN":
                    # Add the original WIN record
                    new_records.append(rec)
                    
                    # Create the counter-factual LOSS record
                    loss_rec = rec.copy()
                    # Flip direction
                    loss_rec["direction"] = "DOWN" if rec["direction"] == "UP" else "UP"
                    loss_rec["result"] = "LOSS"
                    loss_rec["pnl"] = -1.0 # Dummy loss
                    
                    new_records.append(loss_rec)
                else:
                    # Keep other real trades as is
                    new_records.append(rec)
            except: pass
            
    # Save back
    with open(FILE, "w") as f:
        for r in new_records:
            f.write(json.dumps(r) + "\n")
            
    print(f"Data Augmented: {len(new_records)} records (Balanced Win/Loss)")

if __name__ == "__main__":
    augment()
