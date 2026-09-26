"""Settings for the Phase 3 study store. Every value can be overridden with an environment variable."""
import os
import pathlib

from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
SQLITE_DIR = BASE_DIR.parent / "SQLite"


def _env_path(name: str, default: pathlib.Path) -> pathlib.Path:
	path = pathlib.Path(os.getenv(name, str(default))).expanduser()
	return path if path.is_absolute() else BASE_DIR / path


def _env_int(name: str, default: int) -> int:
	return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
	return float(os.getenv(name, str(default)))


DATA_DIR = _env_path("DMF_DATA_DIR", SQLITE_DIR / "data")
RAW_DIR = DATA_DIR / "raw"                                           # one JSON file per ClinicalTrials.gov page
DB_PATH = _env_path("DMF_DB_PATH", DATA_DIR / "studies.db")

# ClinicalTrials.gov API v2: no key, no auth. The unofficial limit is about 50 requests a minute per IP;
# the default filter needs ~13 requests in total, so a short pause between pages is plenty.
CTGOV_URL = os.getenv("DMF_CTGOV_URL", "https://clinicaltrials.gov/api/v2/studies")
# Phase 3, completed, results posted: 12,545 studies as of 2026-09-26. Race composition only exists for studies
# that posted results. The scope below is enforced again at load time, so a wider harvest (the team's
# 14,776-study "phase:3,results:with" download, or DMF_AGG_FILTERS="phase:3") loads the same rows.
AGG_FILTERS = os.getenv("DMF_AGG_FILTERS", "phase:3,results:with,status:com")
PAGE_SIZE = _env_int("DMF_PAGE_SIZE", 1000)                          # API maximum
REQUEST_PAUSE_SECONDS = _env_float("DMF_REQUEST_PAUSE_SECONDS", 1.5)
HTTP_TIMEOUT = _env_int("DMF_HTTP_TIMEOUT", 60)
USER_AGENT = os.getenv("DMF_USER_AGENT", "DrugMeFinder-query/0.2 (TigerHacks 2026; student project)")

# schema.sql: "phase III, completed studies only (enforced at load time, not here)". parse_study.py skips
# everything else. PHASE2/PHASE3 studies list PHASE3 and are kept, as in ClinicalTrials.gov's own phase:3 filter.
SCOPE_STATUS = os.getenv("DMF_SCOPE_STATUS", "COMPLETED")
SCOPE_PHASE = os.getenv("DMF_SCOPE_PHASE", "PHASE3")
