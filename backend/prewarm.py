"""Fill extras.sqlite (and the disk cache) for the drugs on the dashboard, so their reports are instant and work
offline. Run it on good Wi-Fi before a demo. It is resumable: drugs that are already complete cost nothing.

    python prewarm.py                 # dashboard rows (>=2 trials, >=500 participants), least covered first
    python prewarm.py --limit 60      # just the top of the dashboard
    python prewarm.py --all           # every registry row
    python prewarm.py --budget 800    # stop after this many live openFDA requests

Budget: a drug that has FAERS reports costs about 20 openFDA requests, an obscure one about 4. Without a key
openFDA allows 1,000 requests per day per IP address (shared venue Wi-Fi counts as one address), so roughly
50 drugs a day; the default budget stops at 900. With OPENFDA_API_KEY in backend/.env (free, instant) the quota is
120,000 per day and the whole dashboard takes an hour or two.
"""
import argparse
import sys
import time

import clients
import db
import report
from config import OPENFDA_API_KEY

ALL_PIECES = set(report.PIECES)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="only the first N drugs in dashboard order")
    ap.add_argument("--all", action="store_true", help="every registry row, not just the dashboard's")
    ap.add_argument("--min-trials", type=int, default=2)
    ap.add_argument("--min-participants", type=int, default=500)
    ap.add_argument("--budget", type=int, default=100_000 if OPENFDA_API_KEY else 900,
                    help="stop after this many live openFDA requests")
    args = ap.parse_args()

    rows = db.drug_rows()
    if not args.all:
        rows = [r for r in rows if r["trials"] >= args.min_trials and r["participants"] >= args.min_participants]
    rows.sort(key=lambda r: (r.get("score_pop") is None, r.get("score_pop") or 0))  # least covered first, as shown
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} drugs | openFDA key: {'yes' if OPENFDA_API_KEY else 'NO (1,000 requests/day per IP)'} | "
          f"budget: {args.budget} live openFDA requests | extras stored so far: {db.extras_count()}", flush=True)

    t0, done, skipped, partial, failed = time.time(), 0, 0, 0, 0
    for i, r in enumerate(rows, 1):
        stored = db.get_extras(r["drug"], max_age_days=30) or {}
        if ALL_PIECES <= set(stored.get("complete", [])):
            skipped += 1
            continue
        used = clients.STATS["api.fda.gov"]
        if used >= args.budget:
            print(f"\nbudget reached: {used} live openFDA requests. Rerun tomorrow, or add OPENFDA_API_KEY to backend/.env.")
            break
        t1 = time.time()
        try:
            rep = report.build(r["drug"], registry_row=r, with_card=False)
        except Exception as exc:  # build() is designed not to raise; belt and braces
            failed += 1
            print(f"[{i}/{len(rows)}] {r['drug'][:44]:44s} FAILED: {exc}", flush=True)
            continue
        warnings = (rep or {}).get("warnings", [])
        if warnings:
            partial += 1
        else:
            done += 1
        note = f"  ! {warnings[0][:70]}" if warnings else ""
        print(f"[{i}/{len(rows)}] {r['drug'][:44]:44s} {time.time() - t1:5.1f}s  openFDA live: {clients.STATS['api.fda.gov']:>5}{note}",
              flush=True)
        if any("quota is spent" in w for w in warnings):
            print("\nopenFDA answered 429 (quota spent). Stopping; rerun later or add OPENFDA_API_KEY to backend/.env.")
            break
    print(f"\n{done} complete, {partial} partial (rerun fills the gaps), {skipped} already done, {failed} failed "
          f"in {(time.time() - t0) / 60:.1f} min. Live requests: {dict(clients.STATS)}. Extras stored: {db.extras_count()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
