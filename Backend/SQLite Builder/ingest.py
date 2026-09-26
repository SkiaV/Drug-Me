"""Pull completed Phase 3 studies from ClinicalTrials.gov and load them into SQLite (schema.sql).

    python ingest.py                          # download every page to ../SQLite/data/raw, then load ../SQLite/data/studies.db
    python ingest.py --load-only              # skip the download; re-parse whatever is already in ../SQLite/data/raw
    python ingest.py --raw-dir <the team's data/raw> --load-only   # reuse pages that were already downloaded
    python ingest.py --max-pages 1            # smoke test: the first 1,000 studies only
    python ingest.py --rebuild                # drop the tables first (needed once after a schema change)

Scope is enforced here, as schema.sql says: a study that is not COMPLETED, does not list PHASE3, or has no
non-placebo drug, no condition or no participant count is skipped, and the skips are counted by reason in
meta.ingest. Re-running is safe: studies are upserted by NCT number and their child rows rebuilt.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import pathlib
import sys
import time

import ctgov_client
import db
from config import AGG_FILTERS, DB_PATH, RAW_DIR, SCOPE_PHASE, SCOPE_STATUS
from parse_study import SkipStudy, parse_study

BATCH = 1000


def load(con, raw_dir: pathlib.Path, log=print) -> tuple[int, collections.Counter]:
    """Parse every saved page into the database. Returns (loaded, skipped-by-reason)."""
    batch, loaded, skipped, started = [], 0, collections.Counter(), time.time()
    for study in ctgov_client.iter_raw_studies(raw_dir):
        try:
            batch.append(parse_study(study))
        except SkipStudy as exc:                     # out of scope, or a NOT NULL column cannot be filled
            skipped[exc.reason] += 1
        except Exception as exc:                     # one malformed study must not stop the load
            skipped["error"] += 1
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
    parser.add_argument("--rebuild", action="store_true", help="drop the tables before loading (once, after a schema change)")
    args = parser.parse_args(argv)

    if not args.load_only:
        downloaded = ctgov_client.harvest(args.raw_dir, args.agg_filters, args.max_pages)
        print(f"downloaded {downloaded} studies to {args.raw_dir}")
    elif not any(pathlib.Path(args.raw_dir).glob("ctgov_page_*.json")):
        print(f"no ctgov_page_*.json in {args.raw_dir}; run without --load-only first", file=sys.stderr)
        return 1

    con = db.connect(args.db)
    if args.rebuild:
        db.drop_all(con)
    elif not db.schema_is_current(con):
        print(f"{args.db} was built with an earlier schema.sql; run again with --rebuild (or delete the file)",
              file=sys.stderr)
        con.close()
        return 1
    db.init_schema(con)
    loaded_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    loaded, skipped = load(con, args.raw_dir)
    db.set_meta(con, "ingest", {"studies": loaded, "skipped": dict(skipped), "loaded_at": loaded_at,
                                "agg_filters": args.agg_filters, "raw_dir": str(args.raw_dir),
                                "scope": {"status": SCOPE_STATUS, "phase": SCOPE_PHASE}})
    con.close()
    reasons = ", ".join(f"{reason} {n}" for reason, n in skipped.most_common()) or "none"
    print(f"done: {loaded} studies in {args.db}; skipped {sum(skipped.values())} ({reasons})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
