#!/usr/bin/env python3
# chunk_leads.py - emit the next unprocessed batch of leads (work-smart batching).
# Usage: chunk_leads.py MASTER.json PROCESSED.txt OUT.json [BATCH_SIZE=50]
# Reads MASTER (JSON array or {"lead_list":[...]}), skips any lead whose email is
# already in PROCESSED.txt, writes the next BATCH_SIZE unprocessed leads to OUT.json.
# Exit 0 if a batch was written, 3 when the list is exhausted. After uploading OUT,
# append its emails to PROCESSED.txt, then call again to get the next batch.
import json, sys, os
def load(path):
    d = json.load(open(path))
    return (d.get("lead_list") or d.get("leads") or []) if isinstance(d, dict) else d
def main():
    if len(sys.argv) < 4:
        sys.stderr.write("usage: chunk_leads.py MASTER.json PROCESSED.txt OUT.json [BATCH=50]\n"); sys.exit(2)
    master, proc, out = sys.argv[1:4]
    batch = int(sys.argv[4]) if len(sys.argv) > 4 else 50
    leads = load(master)
    done = {l.strip().lower() for l in open(proc)} if os.path.exists(proc) else set()
    remaining = [x for x in leads if x.get("email","").strip().lower() not in done]
    chunk = remaining[:batch]
    json.dump({"lead_list": chunk}, open(out, "w"), indent=2)
    total, left = len(leads), len(remaining)
    print("batch=%d unprocessed_remaining=%d total=%d done=%d -> %s" % (len(chunk), left, total, total-left, out))
    sys.exit(0 if chunk else 3)
if __name__ == "__main__":
    main()
