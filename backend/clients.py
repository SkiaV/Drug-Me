"""One HTTP client for every external API.

Every GET is cached to data/cache/<sha1(url)>.json the first time it succeeds, so:
  * the demo keeps working if the venue Wi-Fi dies,
  * we never burn openFDA's 1,000/day keyless quota twice on the same question,
  * teammates get identical results.
The api_key is stripped from the cache key so cached files don't depend on whose key was used.
"""
import hashlib
import json
import time

import requests

from config import CACHE_DIR, CACHE_TTL_DAYS, HTTP_TIMEOUT, OPENFDA_API_KEY, SOCRATA_APP_TOKEN, USER_AGENT

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_session.headers["Accept"] = "application/json"


class ApiError(Exception):
    pass


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

    last = None
    for attempt in range(4):
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
        if resp.status_code in (429, 500, 502, 503, 504):
            last = ApiError(f"{resp.status_code} from {url}")
            time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            raise ApiError(f"{resp.status_code} from {full_url[:200]}: {resp.text[:200]}")
        data = resp.json()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data
    raise ApiError(f"gave up on {url}: {last}")


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
