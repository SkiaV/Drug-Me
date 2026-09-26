"""Page through ClinicalTrials.gov API v2 and keep every raw page on disk.

The default filter (Phase 3, results posted) is about 15 requests of 1,000 studies. Raw pages are kept in
SQLite/data/raw by default so the parser can be re-run offline as the schema evolves, and so the demo never
depends on Wi-Fi.
"""
from __future__ import annotations

import json
import pathlib
import time

import requests

from config import AGG_FILTERS, CTGOV_URL, HTTP_TIMEOUT, PAGE_SIZE, RAW_DIR, REQUEST_PAUSE_SECONDS, USER_AGENT

# Only the pieces parse_study.py reads. Trimming the payload is what makes 1,000 studies per page feasible.
FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.statusModule.startDateStruct",
    "protocolSection.designModule.phases",
    "protocolSection.designModule.enrollmentInfo",
    "protocolSection.eligibilityModule.sex",
    "protocolSection.eligibilityModule.minimumAge",
    "protocolSection.eligibilityModule.maximumAge",
    "protocolSection.conditionsModule.conditions",
    "protocolSection.armsInterventionsModule",
    "derivedSection.conditionBrowseModule.meshes",
    "derivedSection.interventionBrowseModule.meshes",
    "resultsSection.baselineCharacteristicsModule",
]


class CtGovError(Exception):
    pass


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


def fetch_page(session: requests.Session, page_token: str | None = None, agg_filters: str = AGG_FILTERS,
               page_size: int = PAGE_SIZE) -> dict:
    """One page: {"studies": [...], "nextPageToken": str | absent, "totalCount": int (first page only)}."""
    params = {"aggFilters": agg_filters, "fields": ",".join(FIELDS), "pageSize": page_size, "countTotal": "true"}
    if page_token:
        params["pageToken"] = page_token
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            resp = session.get(CTGOV_URL, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:            # network blip: back off and retry
            last_error = exc
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):     # throttled or upstream hiccup: same treatment
            last_error = CtGovError(f"HTTP {resp.status_code} from ClinicalTrials.gov")
            time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            raise CtGovError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()
    raise CtGovError(f"gave up after 5 attempts: {last_error}")


def harvest(raw_dir: pathlib.Path = RAW_DIR, agg_filters: str = AGG_FILTERS, max_pages: int | None = None,
            log=print) -> int:
    """Download every page to raw_dir/ctgov_page_NNN.json. Returns the number of studies written."""
    raw_dir = pathlib.Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = _session()
    token, page, total, expected = None, 0, 0, None
    while True:
        started = time.time()
        data = fetch_page(session, token, agg_filters)
        studies = data.get("studies") or []
        expected = data.get("totalCount") or expected            # the API only reports the total on the first page
        (raw_dir / f"ctgov_page_{page:03d}.json").write_text(json.dumps(studies), encoding="utf-8")
        total += len(studies)
        log(f"page {page}: {len(studies)} studies in {time.time() - started:.1f}s (total {total} of {expected or '?'})")
        token = data.get("nextPageToken")
        page += 1
        if not token or (max_pages is not None and page >= max_pages):
            break
        time.sleep(REQUEST_PAUSE_SECONDS)
    return total


def iter_raw_studies(raw_dir: pathlib.Path = RAW_DIR):
    """Yield every study dict from the saved pages, in page order."""
    for path in sorted(pathlib.Path(raw_dir).glob("ctgov_page_*.json")):
        yield from json.loads(path.read_text(encoding="utf-8"))
