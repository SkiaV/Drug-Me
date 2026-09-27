"""One HTTP client for every external API.

Every GET is cached to data/cache/<sha1(url)>.json the first time it succeeds, so:
  * the demo keeps working if the venue Wi-Fi dies,
  * we never burn openFDA's 1,000/day keyless quota twice on the same question,
  * teammates get identical results.
The api_key is stripped from the cache key so cached files don't depend on whose key was used.
STATS counts live (uncached) requests per host since startup; prewarm.py uses it to stay inside the quota.
"""
import collections
import hashlib
import json
import threading
import time
from urllib.parse import urlparse

import requests

from config import CACHE_DIR, CACHE_TTL_DAYS, HTTP_RETRIES, HTTP_TIMEOUT, OPENFDA_API_KEY, SOCRATA_APP_TOKEN, USER_AGENT

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_session.headers["Accept"] = "application/json"

STATS: collections.Counter = collections.Counter()
_stats_lock = threading.Lock()


class ApiError(Exception):
    pass


class QuotaError(ApiError):
    """HTTP 429: the per-minute or per-day quota is spent. Callers should stop hammering, not retry."""


def _cache_path(url: str):
    return CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".json")


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             ttl_days: int = CACHE_TTL_DAYS, empty_on_404: bool = True):
    prepared = requests.Request("GET", url, params=params or {}).prepare()
    full_url = prepared.url
    key_url = full_url.replace(f"api_key={OPENFDA_API_KEY}", "api_key=REDACTED") if OPENFDA_API_KEY else full_url
    path = _cache_path(key_url)
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl_days * 86400:
        return json.loads(path.read_text(encoding="utf-8"))

    host = urlparse(url).netloc
    last: Exception | None = None
    for attempt in range(HTTP_RETRIES):
        with _stats_lock:
            STATS[host] += 1
        try:
            resp = _session.get(full_url, headers=headers, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:  # network blip: back off and retry
            last = exc
            time.sleep(1.5 ** attempt)
            continue
        if resp.status_code == 404 and empty_on_404:
            # openFDA answers 404 for "no matching records"; that's data, not an error
            data = {"results": [], "meta": {"results": {"total": 0}}}
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        if resp.status_code == 429:
            last = QuotaError(f"429 rate limit from {host}")
            time.sleep(2 * (attempt + 1))  # the per-minute window passes quickly; a spent daily quota will not
            continue
        if resp.status_code in (500, 502, 503, 504):
            last = ApiError(f"{resp.status_code} from {host}")
            time.sleep(1 + attempt)
            continue
        if resp.status_code >= 400:
            raise ApiError(f"{resp.status_code} from {full_url[:200]}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError(f"non-JSON response from {host}: {exc}") from exc
        path.write_text(json.dumps(data), encoding="utf-8")
        return data
    if isinstance(last, ApiError):
        raise last
    raise ApiError(f"gave up on {host}: {last}")


def openfda(endpoint: str, **params):
    """endpoint: 'label', 'event' (FAERS) or 'drugsfda'."""
    if OPENFDA_API_KEY:
        params["api_key"] = OPENFDA_API_KEY
    return get_json(f"https://api.fda.gov/drug/{endpoint}.json", params)


def rxnav(path: str, **params):
    return get_json(f"https://rxnav.nlm.nih.gov/REST/{path}", params, empty_on_404=False)


def ctgov(**params):
    return get_json("https://clinicaltrials.gov/api/v2/studies", params, empty_on_404=False)


def cdc(dataset: str, **params):
    headers = {"X-App-Token": SOCRATA_APP_TOKEN} if SOCRATA_APP_TOKEN else None
    return get_json(f"https://data.cdc.gov/resource/{dataset}.json", params, headers=headers, empty_on_404=False)
