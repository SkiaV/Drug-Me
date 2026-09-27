"""ClinicalTrials.gov API v2 access.

Two modes:
  * live per-drug query (query.intr=<names>) for any drug the user types, and
  * whole-registry harvest (all Phase 3 trials with posted results, 1,000 per page, ~15 pages)
    which feeds the researcher table and makes /report instant and offline-safe.
"""
import json
import time

from clients import ctgov
from config import RAW_DIR

FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule.startDateStruct",
    "protocolSection.statusModule.primaryCompletionDateStruct",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "protocolSection.designModule",
    "protocolSection.eligibilityModule",
    "protocolSection.conditionsModule",
    "protocolSection.armsInterventionsModule",
    "protocolSection.contactsLocationsModule.locations",
    "derivedSection.conditionBrowseModule",
    "derivedSection.interventionBrowseModule",
    "resultsSection.baselineCharacteristicsModule",
]
AGG = "phase:3,results:with"


def _query_expr(names: list[str]) -> str:
    parts = []
    for n in names:
        n = n.strip()
        if not n:
            continue
        parts.append(f'"{n}"' if " " in n else n)
    return " OR ".join(parts)


def fetch_live(names: list[str], max_pages: int = 5) -> list[dict]:
    """All Phase 3 trials with posted results whose interventions mention any of the names."""
    studies, token = [], None
    for _ in range(max_pages):
        params = {"query.intr": _query_expr(names), "aggFilters": AGG, "fields": ",".join(FIELDS),
                  "pageSize": 100, "countTotal": "true"}
        if token:
            params["pageToken"] = token
        data = ctgov(**params)
        studies.extend(data.get("studies", []))
        token = data.get("nextPageToken")
        if not token:
            break
    return studies


def harvest_all(page_size: int = 1000, log=print) -> int:
    """Download every Phase 3 trial with posted results into data/raw/. Returns number of trials."""
    token, page, total = None, 0, 0
    while True:
        params = {"aggFilters": AGG, "fields": ",".join(FIELDS), "pageSize": page_size, "countTotal": "true"}
        if token:
            params["pageToken"] = token
        t0 = time.time()
        data = ctgov(**params)
        studies = data.get("studies", [])
        (RAW_DIR / f"ctgov_page_{page:03d}.json").write_text(json.dumps(studies), encoding="utf-8")
        total += len(studies)
        log(f"page {page}: {len(studies)} trials in {time.time() - t0:.1f}s (total {total} of {data.get('totalCount')})")
        token = data.get("nextPageToken")
        page += 1
        if not token:
            break
    return total


def iter_raw_pages():
    for path in sorted(RAW_DIR.glob("ctgov_page_*.json")):
        yield from json.loads(path.read_text(encoding="utf-8"))
