# Drug Me Finder: Phase 3 study query store

Pulls every completed Phase 3 study with posted results from ClinicalTrials.gov (API v2), extracts one row per
study, and stores it in SQLite so studies can be queried by drug, condition, sex, age and race, one at a time or
pooled. Python 3.11+, Flask, stdlib `sqlite3`. Last full load: 2026-09-26, 11,976 studies in 14 seconds.

| Column | Where it comes from | Stored as |
|---|---|---|
| Race composition | baseline "Race (NIH/OMB)" / "Race/Ethnicity, Customized" / "Ethnicity" tables, Total column | `study_races` rows: (demographic, count) plus a harmonized `category` |
| Age range | protocol `minimumAge` / `maximumAge`, whole years, NULL when the protocol sets no bound | `studies.age_lower`, `studies.age_upper` |
| Sex | baseline "Sex: Female, Male" counts, else protocol eligibility | `studies.sex`: `M`, `F` or `MF` |
| Drug | interventions in EXPERIMENTAL arms (placebos dropped), each paired with its MeSH term | `studies.drug`, `studies.drug_mesh`, `study_drugs` rows |
| Condition | protocol conditions, `"; "`-joined | `studies.condition` |
| Participants | baseline "Total" head count, else enrollment | `studies.participants` |

## Files

| File | Role |
|---|---|
| `schema.sql` | The schema, hand-edited by the team on 2026-09-26. Three tables: `studies`, `study_races`, `study_drugs` (+ `meta`). |
| `ctgov_client.py` | API v2 paging with retries; keeps each raw page in `data/raw/`. |
| `parse_study.py` | One raw study -> one `studies` row with its race and drug rows, or `SkipStudy`. Pure functions; every rule is unit-tested. |
| `db.py` | Create schema, upsert records, and the search / aggregate queries the API uses. |
| `ingest.py` | CLI that downloads and loads; enforces the scope and counts what it skipped. |
| `api.py` | Flask blueprint (`/api/studies/...`) plus a standalone `create_app()`. |
| `validation.py` | Query-string validation shared with the team app: rejects bad values, canonicalizes the rest (`Female` -> `F`, `Black or African American` -> `black`), reports every problem at once. Standard library only. |
| `config.py` | Paths, API filter, page size, the load-time scope. Overridable via `DMF_*` environment variables. |
| `tests/` | pytest suite (83 tests) using real API shapes trimmed from live studies. No network. |

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                       # offline unit tests

python ingest.py                          # ~13 requests, 12,545 studies -> data/studies.db
python ingest.py --max-pages 1            # smoke test with the first 1,000 studies
python ingest.py --load-only --rebuild --raw-dir <folder with ctgov_page_*.json>   # reuse pages already downloaded
python ingest.py --agg-filters phase:3    # every Phase 3 study; the load still keeps completed ones only

python api.py                             # standalone on :5001
```

`--rebuild` drops the tables first. It is required once when `studies.db` was built by an earlier schema
(the ingest refuses to write into such a file otherwise).

To mount the blueprint in another Flask app, add two lines next to its blueprint registration:

```python
from api import bp as studies_bp
app.register_blueprint(studies_bp)
```

The blueprint opens one SQLite connection per request (`flask.g`) and reads the path from
`app.config["STUDIES_DB_PATH"]`, falling back to `config.DB_PATH`.

## HTTP API

| Route | What it returns |
|---|---|
| `GET /api/studies?drug=metformin&sex=F&age=67&race=black&limit=50` | matching studies, newest registration first, each with its `race_composition` list |
| `GET /api/studies/NCT01730534` | one study with race composition and drug rows |
| `GET /api/studies/aggregate?drug=metformin` | pooled race counts (by category and as reported), sex counts, age envelope |
| `GET /api/studies/stats` | row counts and when the ingest ran |

Filters: `drug` (reported or MeSH name, substring), `condition` (substring), `sex` (`M` or `F`, mixed studies
match either; `MF` for mixed studies only; `Male` / `Female` / `both` are accepted and canonicalized), `age`
(whole years inside the study's eligibility bounds; a NULL bound is no bound), `race` (a category: white,
black, asian, aian, nhpi, multiracial, hispanic, not_hispanic, other, unknown, or a label such as
"Black or African American"; matches studies that reported at least one such participant), `limit` (max 200),
`offset`. A bad value is a 400 that lists every problem; unknown parameters are ignored.

One study, as `/api/studies/<nct_id>` returns it (NCT01730534):

```json
{
  "nct_id": "NCT01730534",
  "drug": "Dapagliflozin 10 mg",
  "drug_mesh": "dapagliflozin",
  "condition": "Diabetes Mellitus, Non-Insulin-Dependent; High Risk for Cardiovascular Event",
  "sex": "MF",
  "age_lower": 40,
  "age_upper": 130,
  "female_count": 6422, "male_count": 10738, "participants": 17160,
  "race_reported": 1,
  "source_url": "https://clinicaltrials.gov/study/NCT01730534",
  "race_composition": [
    {"demographic": "White", "count": 13653, "category": "white", "dimension": "race", "measure_title": "Race/Ethnicity, Customized"},
    {"demographic": "Asian", "count": 2303, "category": "asian", "dimension": "race", "measure_title": "Race/Ethnicity, Customized"},
    {"demographic": "Black or African American", "count": 603, "category": "black", "dimension": "race", "measure_title": "Race/Ethnicity, Customized"},
    {"demographic": "Not Hispanic or Latino", "count": 14592, "category": "not_hispanic", "dimension": "ethnicity", "measure_title": "Ethnicity (NIH/OMB)"}
  ],
  "drugs": [{"drug": "dapagliflozin 10 mg", "drug_mesh": "dapagliflozin"}]
}
```

`source_url` is derived from the NCT number by the API; it is not a column.

## Straight SQL

```sql
-- race composition of one study, as reported
SELECT demographic, count FROM study_races WHERE nct_id = 'NCT01730534' AND dimension = 'race';

-- pooled race composition of every study that tested a drug (MeSH names keep the source's casing)
SELECT r.category, SUM(r.count) AS people, COUNT(DISTINCT r.nct_id) AS studies
FROM study_races r JOIN study_drugs d ON d.nct_id = r.nct_id
WHERE lower(d.drug_mesh) = 'metformin' AND r.dimension = 'race'
GROUP BY r.category ORDER BY people DESC;

-- studies a 67-year-old woman could have joined, for a condition
SELECT nct_id, drug, sex, age_lower, age_upper
FROM studies
WHERE condition LIKE '%insomnia%' AND sex IN ('F', 'MF')
  AND (age_lower IS NULL OR age_lower <= 67) AND (age_upper IS NULL OR age_upper >= 67);

-- how often race goes unreported
SELECT race_reported, COUNT(*) FROM studies GROUP BY race_reported;
```

## Decisions and limits

- **Scope is enforced at load time**, as `schema.sql` says: a study is kept only when its status is COMPLETED
  and its phases include PHASE3 (PHASE2/PHASE3 counts, as in ClinicalTrials.gov's own `phase:3` filter). The
  default download filter (`phase:3,results:with,status:com`, 12,545 studies on 2026-09-26) matches that
  scope; the team's wider harvest loads the same rows. On that harvest the load kept 11,976 studies and
  skipped 2,231 that were not completed and 569 with no non-placebo drug.
- **NOT NULL means skipped, not invented.** A study with no non-placebo drug (device, procedure or
  placebo-only interventions), no condition or no participant count is skipped and counted by reason in
  `meta.ingest`.
- **Counts are the "Total" column** of the baseline table. When a sponsor posted no Total column the arms are
  summed. Values are strings in the API; "NA" is skipped, "1,203" is read as 1203. Percentage tables are skipped.
- **Labels are stored verbatim** and bucketed by `category` with an ordered regex table (`parse_study.map_race`).
  "Race/Ethnicity, Customized" tables (about 45% of race tables) are free text, so the bucket is the only way to
  add studies together. Zero counts are kept: "reported 0" and "not reported" are different findings.
- **Age range is the protocol eligibility**, not the observed ages, stored as written: a missing bound is NULL
  (55% of studies set no upper bound), "130 Years" is 130. Months and weeks are converted to whole years.
- **Sex is who enrolled** when a baseline sex table exists (nearly every study with results has one), otherwise
  who the protocol allowed.
- **Drug is what the experimental arms received**; comparators are not stored, because `study_drugs` has no
  role column to tell them apart. A study whose drug arms are all comparators keeps those drugs.
- **MeSH pairing is by name.** ClinicalTrials.gov lists a study's MeSH intervention terms as one flat list,
  so each reported drug gets the term that appears in its name (or vice versa, whole words only, the most
  specific term when several fit). When exactly one non-placebo drug and one term are left over they are
  paired ("BAY94-9027" gets "Factor VIII"). Anything still unpaired keeps its own name minus the dose, so
  `drug_mesh` is never empty. Dose arms of one drug collapse into one `study_drugs` row. MeSH terms keep
  the source's casing, which occasionally splits a group ("Bupivacaine" and "bupivacaine"); compare with
  `lower()`.
- **Re-running the ingest is safe.** Studies are upserted by NCT number and their child rows rebuilt.
