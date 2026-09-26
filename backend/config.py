"""Settings for the Phase 3 study store. Every value can be overridden with an environment variable."""
import os
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = pathlib.Path(os.getenv("DMF_DATA_DIR", BASE_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"                                           # one JSON file per ClinicalTrials.gov page
DB_PATH = pathlib.Path(os.getenv("DMF_DB_PATH", DATA_DIR / "studies.db"))

# ClinicalTrials.gov API v2: no key, no auth. The unofficial limit is about 50 requests a minute per IP;
# the default filter needs ~15 requests in total, so a short pause between pages is plenty.
CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"
# Race composition only exists for studies that posted results, hence "results:with" by default.
# Set DMF_AGG_FILTERS="phase:3" (or pass --agg-filters) to take every Phase 3 study, results or not.
AGG_FILTERS = os.getenv("DMF_AGG_FILTERS", "phase:3,results:with")
PAGE_SIZE = 1000                                                     # API maximum
REQUEST_PAUSE_SECONDS = 1.5
HTTP_TIMEOUT = 60
USER_AGENT = "DrugMeFinder-query/0.1 (TigerHacks 2026; student project)"

AGE_CAP = 100   # upper bound of the age range, per the schema
