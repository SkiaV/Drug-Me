# Drug Me Finder: Phase 3 study query store

Pulls every Phase 3 study from ClinicalTrials.gov (API v2), extracts six fields per study, and stores them in
SQLite so they can be queried by drug, condition, sex, age and race, one study at a time or pooled.
Python 3.11+, Flask, stdlib `sqlite3`. Nothing here has been run yet; see "Run it" below.

| # | Field | Where it comes from | Stored as |
|---|---|---|---|
| 1 | Race composition | baseline "Race (NIH/OMB)" / "Race/Ethnicity, Customized" / "Ethnicity" tables, Total column | `study_races` rows: (demographic, count) plus a harmonized `category` |
| 2 | Age range | protocol `minimumAge` / `maximumAge`, capped at 100 | `studies.age_min`, `studies.age_max` |
| 3 | Sex | baseline "Sex: Female, Male" counts, else protocol eligibility | `studies.sex`: Male, Female, or Male and Female |
| 4 | Drug | interventions in EXPERIMENTAL arms (placebos dropped) + MeSH names | `studies.drug`, `studies.drug_mesh`, `study_drugs` rows |
| 5 | Condition | protocol conditions + MeSH terms | `studies.condition`, `study_conditions` rows |
| 6 | Study | NCT number, title, phase, status, start date, URL | `studies.nct_id` and friends |

## Files

| File | Role |
|---|---|
| `schema.sql` | The schema. Four tables: `studies`, `study_races`, `study_drugs`, `study_conditions` (+ `meta`). |
| `ctgov_client.py` | API v2 paging with retries; keeps each raw page in `data/raw/`. |
| `parse_study.py` | One raw study -> the six fields. Pure functions; every rule is unit-tested. |
| `db.py` | Create schema, upsert records, and the search / aggregate queries the API uses. |
| `ingest.py` | CLI that downloads and loads. |
| `api.py` | Flask blueprint (`/api/studies/...`) plus a standalone `create_app()`. |
| `config.py` | Paths, API filter, page size, age cap. Overridable via `DMF_*` environment variables. |
| `tests/` | pytest suite using real API shapes trimmed from live studies. No network. |

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                       # offline unit tests

python ingest.py                          # ~15 requests, 14,776 studies -> data/studies.db
python ingest.py --max-pages 1            # smoke test with the first 1,000 studies
python ingest.py --raw-dir ../Drug_Me_Finder/backend/data/raw --load-only   # reuse pages already downloaded
python ingest.py --agg-filters phase:3    # every Phase 3 study, results posted or not (~3x more pages)

python api.py                             # standalone on :5001
```

To mount it in the team backend, add two lines to `Drug_Me_Finder/backend/app.py` next to the v1 blueprint:

```python
from api import bp as studies_bp
app.register_blueprint(studies_bp)
```

The blueprint opens one SQLite connection per request (`flask.g`) and reads the path from
`app.config["STUDIES_DB_PATH"]`, falling back to `config.DB_PATH`.

## HTTP API

| Route | What it returns |
|---|---|
| `GET /api/studies?drug=zolpidem&sex=Female&age=67&race=black&limit=50` | matching studies, newest first, each with its `race_composition` list |
| `GET /api/studies/NCT01730534` | one study with race composition, drugs and conditions |
| `GET /api/studies/aggregate?drug=zolpidem` | pooled race counts (by category and as reported), sex counts, age envelope |
| `GET /api/studies/stats` | row counts and when the ingest ran |

Filters: `drug` (matches reported or MeSH name, substring), `condition` (substring), `sex` (Male or Female;
mixed studies match either), `age` (integer inside the study age range), `race` (a category:
white, black, asian, aian, nhpi, multiracial, hispanic, not_hispanic, other, unknown; matches studies that
reported at least one such participant), `has_results` (0 or 1), `limit` (max 200), `offset`.

One study, as `/api/studies/<nct_id>` would return it (values from NCT01730534):

```json
{
  "nct_id": "NCT01730534",
  "title": "Multicenter Trial to Evaluate the Effect of Dapagliflozin on the Incidence of Cardiovascular Events",
  "drug": "Dapagliflozin 10 mg",
  "drug_mesh": "Dapagliflozin",
  "condition": "Diabetes Mellitus, Non-Insulin-Dependent; High Risk for Cardiovascular Event",
  "sex": "Male and Female",
  "age_min": 40,
  "age_max": 100,
  "eligible_sex": "ALL", "age_min_raw": "40 Years", "age_max_raw": "130 Years",
  "female_count": 6422, "male_count": 10738, "participants": 17160,
  "phase": "PHASE3", "status": "COMPLETED", "start_date": "2013-04-25",
  "has_results": 1, "race_reported": 1,
  "source_url": "https://clinicaltrials.gov/study/NCT01730534",
  "race_composition": [
    {"demographic": "White", "count": 13653, "category": "white", "dimension": "race", "measure_title": "Race/Ethnicity, Customized"},
    {"demographic": "Asian", "count": 2303, "category": "asian", "dimension": "race", "measure_title": "Race/Ethnicity, Customized"},
    {"demographic": "Black or African American", "count": 603, "category": "black", "dimension": "race", "measure_title": "Race/Ethnicity, Customized"},
    {"demographic": "Not Hispanic or Latino", "count": 14592, "category": "not_hispanic", "dimension": "ethnicity", "measure_title": "Ethnicity (NIH/OMB)"}
  ],
  "drugs": [{"drug": "dapagliflozin 10 mg", "role": "experimental", "intervention_type": "DRUG"},
            {"drug": "dapagliflozin", "role": null, "intervention_type": "MESH"}],
  "conditions": [{"condition": "diabetes mellitus, non-insulin-dependent", "source": "listed"}]
}
```

## Straight SQL

```sql
-- race composition of one study, as reported
SELECT demographic, count FROM study_races WHERE nct_id = 'NCT01730534' AND dimension = 'race';

-- pooled race composition of every study that tested a drug
SELECT r.category, SUM(r.count) AS people, COUNT(DISTINCT r.nct_id) AS studies
FROM study_races r JOIN study_drugs d ON d.nct_id = r.nct_id
WHERE d.drug = 'zolpidem' AND r.dimension = 'race'
GROUP BY r.category ORDER BY people DESC;

-- studies a 67-year-old woman could have joined, for a condition
SELECT s.nct_id, s.drug, s.sex, s.age_min, s.age_max
FROM studies s JOIN study_conditions c ON c.nct_id = s.nct_id
WHERE c.condition LIKE '%insomnia%' AND s.sex IN ('Female', 'Male and Female') AND 67 BETWEEN s.age_min AND s.age_max;

-- how often race goes unreported
SELECT race_reported, COUNT(*) FROM studies GROUP BY race_reported;
```

## Decisions and limits

- **Default filter is Phase 3 with posted results** (`phase:3,results:with`, 14,776 studies as of 2026-09-25).
  Race composition only exists for studies that posted results. `--agg-filters phase:3` widens it to every
  Phase 3 study; those rows carry age range, sex, drug and condition but no race rows.
- **Counts are the "Total" column** of the baseline table. When a sponsor posted no Total column the arms are
  summed. Values are strings in the API; "NA" is skipped, "1,203" is read as 1203. Percentage tables are skipped.
- **Labels are stored verbatim** and bucketed by `category` with an ordered regex table (`parse_study.map_race`).
  "Race/Ethnicity, Customized" tables (about 45% of race tables) are free text, so the bucket is the only way to
  add studies together. Zero counts are kept: "reported 0" and "not reported" are different findings.
- **Age range is the protocol eligibility**, not the observed ages. Missing lower bound -> 0, missing upper
  bound -> 100, anything above 100 (sponsors write "130 Years") -> 100. Months and weeks are converted to whole years.
- **Sex is who enrolled** when a baseline sex table exists (every study with results has one), otherwise who the
  protocol allowed.
- **Drug is what the experimental arms received.** Comparators are kept in `study_drugs` with `role = comparator`,
  so a search by drug still finds them and the role tells you which is which. Devices, procedures and behavioral
  interventions are not drugs and are not stored.
- **Re-running the ingest is safe.** Studies are upserted by NCT number and their child rows rebuilt.
