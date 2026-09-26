"""Pull every Phase 3 study from ClinicalTrials.gov and load the six schema fields into SQLite.

    python ingest.py                          # download every page to data/raw, then load data/studies.db
    python ingest.py --load-only              # skip the download; re-parse whatever is already in data/raw
    python ingest.py --raw-dir ../Drug_Me_Finder/backend/data/raw --load-only   # reuse the harvest the team already has
    python ingest.py --max-pages 1            # smoke test: the first 1,000 studies only
    python ingest.py --agg-filters phase:3    # every Phase 3 study, including those without posted results

Re-running is safe: studies are upserted by NCT number and their child rows rebuilt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
import time

import ctgov_client
import db
from config import AGG_FILTERS, DB_PATH, RAW_DIR
from parse_study import parse_study

BATCH = 1000


def load(con, raw_dir: pathlib.Path, fetched_at: str, log=print) -> tuple[int, int]:
    """Parse every saved page into the database. Returns (loaded, skipped)."""
    batch, loaded, skipped, started = [], 0, 0, time.time()
    for study in ctgov_client.iter_raw_studies(raw_dir):
        try:
            batch.append(parse_study(study, fetched_at))
        except Exception as exc:                     # one malformed study must not stop the load
            skipped += 1
            nct = ((study.get("protocolSection") or {}).get("identificationModule") or {}).get("nctId")
            log(f"skip {nct}: {exc}")
        if len(batch) >= BATCH:
            db.upsert_studies(con, batch)
            loaded += len(batch)
            batch = []
            log(f"loaded {loaded} studies ({time.time() - started:.0f}s)")
    if batch:
        db.upsert_studies(con, batch)
        loaded += len(batch)
    return loaded, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=pathlib.Path, default=RAW_DIR, help="where raw API pages are kept")
    parser.add_argument("--db", type=pathlib.Path, default=DB_PATH, help="SQLite file to write")
    parser.add_argument("--agg-filters", default=AGG_FILTERS, help='ClinicalTrials.gov aggFilters, e.g. "phase:3"')
    parser.add_argument("--max-pages", type=int, default=None, help="stop after this many pages (smoke test)")
    parser.add_argument("--load-only", action="store_true", help="do not download; parse the saved pages")
    args = parser.parse_args(argv)

    if not args.load_only:
        downloaded = ctgov_client.harvest(args.raw_dir, args.agg_filters, args.max_pages)
        print(f"downloaded {downloaded} studies to {args.raw_dir}")
    elif not any(pathlib.Path(args.raw_dir).glob("ctgov_page_*.json")):
        print(f"no ctgov_page_*.json in {args.raw_dir}; run without --load-only first", file=sys.stderr)
        return 1

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    con = db.connect(args.db)
    db.init_schema(con)
    loaded, skipped = load(con, args.raw_dir, fetched_at)
    db.set_meta(con, "ingest", {"studies": loaded, "skipped": skipped, "fetched_at": fetched_at,
                                "agg_filters": args.agg_filters, "raw_dir": str(args.raw_dir)})
    con.close()
    print(f"done: {loaded} studies in {args.db} ({skipped} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
