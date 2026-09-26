# Flask Backend Integration

The frontend talks to the Flask application in `backend/`, which serves the SQLite database described by
`backend/schema.sql`: one row per **completed Phase 3 trial with posted results** from ClinicalTrials.gov.

## Running locally

Install the Python dependencies:

```sh
python -m pip install -r backend/requirements.txt
```

Populate the SQLite database (about 13 requests to ClinicalTrials.gov, then a 15-second load):

```sh
pnpm backend:ingest
```

Or reuse pages that were already downloaded, and rebuild after a schema change:

```sh
python backend/ingest.py --load-only --rebuild --raw-dir <folder with ctgov_page_*.json>
```

Start Flask on port 5001:

```sh
pnpm backend
```

Run the backend's offline tests:

```sh
pnpm backend:test
```

The hosted Figma preview intentionally uses sample fallback data because it cannot run the Python process.
To use Flask locally through the Vite proxy, set:

```text
VITE_USE_BACKEND=true
```

The Vite development server then proxies `/api/*` to `http://127.0.0.1:5001`. Override the proxy target
with `BACKEND_URL`, or set `VITE_API_BASE_URL` when the browser should call a separately hosted Flask
service directly. Supplying `VITE_API_BASE_URL` also enables backend requests.

## The study record

Every route returns studies with the column names of `backend/schema.sql`, plus one derived key:

| Key | Type | Meaning |
|---|---|---|
| `nct_id` | string | NCT number |
| `drug` | string | drug(s) in the experimental arm(s), as the sponsor wrote them, `"; "`-joined |
| `drug_mesh` | string | the same drug(s) as MeSH-normalized names; a drug with no MeSH term keeps its own name, dose removed |
| `condition` | string | condition(s) as listed by the sponsor, `"; "`-joined |
| `sex` | `"M"` / `"F"` / `"MF"` | who enrolled (baseline sex counts), else who the protocol allowed |
| `age_lower`, `age_upper` | integer or null | eligibility bounds in years; `null` means the protocol set no bound |
| `female_count`, `male_count` | integer or null | baseline head counts |
| `participants` | integer | baseline "Total" participants, else enrollment |
| `race_reported` | 0 / 1 | whether at least one race row exists |
| `source_url` | string | `https://clinicaltrials.gov/study/<nct_id>`, derived by the API |
| `race_composition` | array | `{demographic, count, category, dimension}` per reported label |

Phase, status, start date and title are no longer stored: every row is a completed Phase 3 trial, so the
frontend no longer offers status, phase or date filters.

## Backend routes used by the frontend

### `GET /api/studies`

Used for the generalized dashboard, advanced search, and report evidence.

Query parameters (values are canonicalized by `backend/validation.py`, so `Female`, `female` and `F` are
the same query; a bad value is a `400` whose `error.details` lists every problem):

- `drug`: substring of the reported or MeSH name
- `condition`: substring of the sponsor's condition list
- `sex`: `F` or `M` (mixed-sex studies match either), or `MF` for mixed-sex studies only
- `age`: whole years; a study matches when the age falls inside its eligibility bounds (a `null` bound
  is no bound)
- `race`: a harmonized category (`white`, `black`, `asian`, `aian`, `nhpi`, `multiracial`, `hispanic`,
  `not_hispanic`, `other`, `unknown`) or a label such as `Black or African American`
- `limit`: capped by the backend at 200
- `offset`

Results are ordered by NCT number, newest registration first. The response echoes the canonical
`filters` it applied.

### `GET /api/studies/aggregate`

Used by individualized reports to obtain, for the same filters:

- `studies`, `participants`, `studies_reporting_race`
- `sex`: `{female, male}` pooled head counts
- `age_range`: `[lower, upper]`; `upper` is `null` when at least one matching study set no upper bound
- `race_composition`: pooled counts per `dimension` and `category`, with the number of contributing studies
- `race_composition_as_reported`: the same, per verbatim label

### `GET /api/studies/stats`

Used for live dashboard totals: `studies`, `participants`, `with_race_composition`, `distinct_drugs`
(case-insensitive count of MeSH names) and `ingest`, the record written by the last load
(`studies`, `skipped` by reason, `loaded_at`, `agg_filters`, `scope`).

### `GET /api/studies/:nct_id`

One study with its `race_composition` (including `measure_title`) and its `drugs` rows
(`{drug, drug_mesh}`). Available for future study-detail views; the report currently links to
`source_url`.

## Frontend adaptation

The backend is study-oriented while the dashboard is drug-oriented. `src/api.ts` groups returned studies
by the first MeSH-normalized drug name and derives the presentation model:

- The most common condition becomes the primary use.
- Trial and participant counts are aggregated per generic drug.
- Age coverage uses the eligibility envelope; a missing bound counts as 0 or 100.
- Sex coverage uses reported female/male counts when available, else the share of mixed-sex (`MF`) studies.
- Race coverage measures how many matching studies report race composition.
- The provisional overall score is the mean of those three components.

These calculations are explicitly provisional and can be replaced when the final scoring methodology is
defined. The dashboard reads the first 200 studies only; a server-side per-drug aggregate would be the
next step for full coverage.

## Missing backend capability

The backend contains ClinicalTrials.gov data only. FDA labeling is not part of the current data plan, and
the report says so rather than presenting mock label content as backend data.

If Flask cannot be reached, the UI keeps a clearly labeled sample fallback so the preview remains usable.
When Flask responds successfully, the dashboard labels its source as **Flask backend** and uses
backend-derived values.
