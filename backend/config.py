"""Central configuration. Everything that can vary between machines lives here or in .env."""
import os
import pathlib

from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"      # one JSON file per external request (offline demo insurance)
RAW_DIR = DATA_DIR / "raw"          # ClinicalTrials.gov harvest pages
# SQLite. Named .sqlite on purpose: the repo's .gitattributes sends *.db to Git LFS, and this file must clone as a
# plain file so the app works from a fresh checkout. Swap for Postgres later by changing db.py only.
DB_PATH = DATA_DIR / "registry.sqlite"
# Per-drug enrichment (label sentences, FAERS split, approval, class, prevalence): small, committed, filled by
# prewarm.py or the first report for a drug. Separate file so a pre-warm never rewrites the 42 MB registry.
EXTRAS_PATH = DATA_DIR / "extras.sqlite"
for _d in (CACHE_DIR, RAW_DIR):
    _d.mkdir(parents=True, exist_ok=True)

OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN", "")

USER_AGENT = "DrugMeFinder/0.1 (TigerHacks 2026; student project)"
# One external request: 20 s and 3 attempts is plenty for these APIs; a report waits at most REPORT_DEADLINE_S for
# its optional pieces (label, FAERS, approval, class, prevalence) and then renders with a note about what is missing.
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))
REPORT_DEADLINE_S = int(os.getenv("REPORT_DEADLINE_S", "25"))
CACHE_TTL_DAYS = int(os.getenv("CACHE_TTL_DAYS", "30"))

# Where Flask listens. PORT=5001 etc. when 5000 is taken.
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))

# Built React app (../dist, written by `pnpm build` at the repo root). If it exists Flask serves it; otherwise
# only the JSON API runs.
FRONTEND_DIST = BASE_DIR.parent / "dist"

# Smallest evidence base we are willing to score. Below this the UI says "insufficient data".
MIN_TRIALS_TO_SCORE = 1
MIN_PARTICIPANTS_TO_SCORE = 100
