"""Download every Phase 3 trial with posted results (about 15 requests) and load them into SQLite.

    python harvest.py            # download + load
    python harvest.py --load     # reload from data/raw without downloading again
"""
import sys
import time

import ctgov
import db
import harmonize


def load_raw():
    batch, total, t0 = [], 0, time.time()
    for study in ctgov.iter_raw_pages():
        try:
            batch.append(harmonize.parse_study(study))
        except Exception as exc:  # one malformed trial must not stop the load
            print("skip", (study.get("protocolSection", {}).get("identificationModule", {}) or {}).get("nctId"), exc)
        if len(batch) >= 2000:
            db.store_trials(batch)
            total += len(batch)
            batch = []
            print(f"loaded {total} trials ({time.time() - t0:.0f}s)")
    if batch:
        db.store_trials(batch)
        total += len(batch)
    db.set_meta("harvest", {"trials": total, "loaded_at": time.strftime("%Y-%m-%d %H:%M"), "filter": ctgov.AGG})
    print(f"done: {total} trials in SQLite")


if __name__ == "__main__":
    if "--load" not in sys.argv:
        n = ctgov.harvest_all()
        print(f"downloaded {n} trials")
    load_raw()
