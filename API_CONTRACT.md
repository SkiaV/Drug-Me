# Uploaded Flask Backend Integration

The frontend is connected to the Flask application in `src/backend`.

## Running locally

Install the Python dependencies from the uploaded backend:

```sh
python -m pip install -r src/backend/requirements.txt
```

Populate the SQLite database:

```sh
pnpm backend:ingest
```

Start Flask on port 5001:

```sh
pnpm backend
```

The hosted Figma preview intentionally uses sample fallback data because it
cannot run the Python process. To use Flask locally through the Vite proxy, set:

```text
VITE_USE_BACKEND=true
```

The Vite development server then proxies `/api/*` to
`http://127.0.0.1:5001`. Override the proxy target with `BACKEND_URL`, or set
`VITE_API_BASE_URL` when the browser should call a separately hosted Flask
service directly. Supplying `VITE_API_BASE_URL` also enables backend requests.

## Backend routes used by the frontend

### `GET /api/studies`

Used for the generalized dashboard, advanced search, and report evidence.

Supported backend query parameters:

- `drug`
- `condition`
- `sex`: `Male` or `Female`
- `age`: integer
- `race`: harmonized backend category such as `white`, `black`, `asian`,
  `aian`, `nhpi`, or `multiracial`
- `has_results`: `0` or `1`
- `limit`: capped by the backend at 200
- `offset`

The frontend translates its display values to these parameters. Study status,
phase, and start-date filters are applied to the returned study page because
the uploaded route does not currently accept them as query parameters.

### `GET /api/studies/aggregate`

Used by individualized reports to obtain:

- Matching study and participant counts
- Female and male participant counts
- Age eligibility envelope
- Race composition
- Number of studies reporting race

### `GET /api/studies/stats`

Used for live dashboard totals and the latest ingest timestamp.

### `GET /api/studies/:nct_id`

Available for future study-detail views. The current report links directly to
the ClinicalTrials.gov `source_url` supplied by each study record.

## Frontend adaptation

The uploaded backend is study-oriented while the dashboard is drug-oriented.
`src/api.ts` groups returned studies by the normalized generic/MeSH drug name
and derives the presentation model:

- The most common condition becomes the primary use.
- Trial and participant counts are aggregated per generic drug.
- Age coverage uses the study eligibility envelope.
- Sex coverage uses reported female/male counts when available.
- Race coverage measures how many matching studies report race composition.
- The provisional overall score is the mean of those three components.

These calculations are explicitly provisional and can be replaced when the
final scoring methodology is defined.

## Missing backend capability

The uploaded backend contains ClinicalTrials.gov data but no openFDA route.
The report identifies FDA labeling as unavailable rather than presenting mock
label content as backend data.

If Flask cannot be reached, the UI keeps a clearly labeled sample fallback so
the preview remains usable. When Flask responds successfully, the dashboard
labels its source as **Flask backend** and uses backend-derived values.
