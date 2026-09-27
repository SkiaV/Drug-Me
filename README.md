# Drug Me — "Was this medicine tested on people like me?"

Type a medication (brand or generic) and, optionally, your sex, age, race and ethnicity. Drug Me pools the drug's
Phase 3 clinical trials with posted results from ClinicalTrials.gov, harmonizes their demographic tables, and shows
how well people like you were represented — against the US population **and** against the people who actually have
the condition. It also surfaces the FDA label's own sentences about your group, the split of side-effect reports by
sex, and questions to take to your doctor. A second page turns the same pipeline into a sortable table over every
drug in the registry, for researchers and funders.

Built at TigerHacks 2026 (University of Missouri, theme: Health). Everything is free: no paid APIs, no keys required
to run (an openFDA key is recommended, a Gemini key is optional).

## Run it

```powershell
# 1. backend (Python 3.11+): the JSON API, and the built site once it exists
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
copy backend\.env.example backend\.env        # optional: OPENFDA_API_KEY (free), GEMINI_API_KEY
.\.venv\Scripts\python.exe backend\app.py     # http://127.0.0.1:5000   (PORT=5001 etc. to change)

# 2. frontend (Node 22, pnpm 10): build once, Flask serves dist/ at the same URL
npx pnpm@10.34.3 install --frozen-lockfile
npx pnpm@10.34.3 build

# development instead of a build: hot reload on :5173, /api proxied to Flask
$env:PORT = "5173"; npx pnpm@10.34.3 dev
```

Open http://127.0.0.1:5000 and try **Ambien** with sex = female, age = 67.

The harvested registry ships in the repo (`backend/data/registry.sqlite`: every Phase 3 trial with posted
results, harmonized, plus one precomputed row per drug), so the dashboard and the search work offline. The first
report for a new medicine calls five public APIs (about 15 seconds); every response is cached to disk, so later
requests are instant and offline-safe. To rebuild the registry from ClinicalTrials.gov (about 15 requests):

```powershell
.\.venv\Scripts\python.exe backend\harvest.py
.\.venv\Scripts\python.exe backend\build_table.py
```

Tests:

```powershell
cd backend; python -m pytest -q                        # harmonization rules
cd "Backend copy\SQLite Builder"; python -m pytest -q   # the study-level store: parser, validation, SQL round trip
npx tsc --noEmit -p tsconfig.json --ignoreDeprecations 5.0
```

## What it does, end to end

```
 name / photo ─► RxNorm ──► ingredient rxcui + brands ──┬─► ClinicalTrials.gov (harvest or live) ─► harmonize ─► pool ─► PPR vs Census
                              │                         ├─► RxClass: class + "may treat" conditions ─► CDC CDI prevalence ─► PPR vs disease
                              │                         ├─► openFDA label: group-specific sentences
                              │                         ├─► openFDA FAERS: reports by sex, by year, reactions that skew
                              │                         └─► openFDA Drugs@FDA: first approval date
                              └─────────────────────────────────────────────────────────────► score + card + trials table
```

## Pages

- **Home** (`/`): the "PEOPLE LIKE ME?" banner and a scroll-driven explainer — 100 dots of who was in the trials
  against who takes the medicine, fed by registry-wide numbers from `/api/v1/meta`.
- **Dashboard** (`/dashboard`): metric strip, the generalized table (Name · Most common use · Least researched ·
  Score ring + tier + age/sex/race component bars) over every drug with at least 2 trials and 500 participants,
  least covered first, plus "open a report for any medicine".
- **Advanced search** (`/advanced-search`): demographic profile (age, sex, race, ethnicity) plus clinical filters
  (drug, indication, disease area, minimum participants, country, sponsor, study years) → the same table with
  profile-specific scores.
- **Individual report** (`/report/<drug>?age&sex&race&ethnicity`): score ring and interpretation, coverage
  components, strengths / limitations / questions for your doctor, "Who was in the trials" (per-group bars against
  the US population and the disease population), the trials behind the report, FDA label sentences about your
  group, FAERS side-effect reports by sex, method notes, and a JSON export.

## API

The React app uses `/api/v1` (camelCase, integer 0–100 scores, `{"error": {"code", "message"}}` errors):

| Route | Purpose |
|---|---|
| `GET /api/v1/meta` | drugs reviewed, trials, average coverage, refresh date, disease areas, Census + registry shares |
| `GET /api/v1/drugs?query&sort&order&limit&minParticipants&minTrials` | generalized drug summaries |
| `GET /api/v1/search?age&sex&race&ethnicity&drug&indication&diseaseArea&location&sponsor&fromDate&toDate` | summaries re-scored for a profile |
| `GET /api/v1/drugs/<id>/report?age&sex&race&ethnicity` | the full report (summary shape + `details`) |
| `GET /api/v1/suggest?q=amb` | autocomplete |

Lower-level routes remain for scripts and debugging (`GET /api` lists them): `/api/resolve`, `/api/report`,
`/api/drug/<rxcui>/trials|label|faers`, `/api/table`, `/api/table/meta`, `/api/health`, `POST /api/resolve/photo`.

A second, study-level API lives in `Backend copy/SQLite Builder/api.py` (port 5001): one row per trial, filtered by
drug, condition, sex, age and race, over the database that `ingest.py` builds. It is independent of the product
API.

## Repository layout

| Path | What it is |
|---|---|
| `src/` | React app (Vite + TypeScript): `App.tsx` routes, `api.ts` models + requests, `components/`, `hooks.ts`, styles |
| `backend/` | Flask API: `app.py` (routes + serves `dist/`), `api_v1.py` (the contract above), `report.py`, `scoring.py`, `harmonize.py`, `rxnorm.py`, `fda.py`, `prevalence.py`, `card.py`, `harvest.py`, `build_table.py`, `db.py`, `tests/` |
| `backend/data/` | `registry.sqlite` (committed), `displaynames.json` (RxNorm names for autocomplete), `cache/` and `raw/` (built locally, ignored) |
| `Backend copy/SQLite Builder/` | The study-level SQLite store: `ingest.py` → `studies.db`, `parse_study.py`, `validation.py`, `api.py`, `tests/` |
| `.figma/`, `AGENTS.md` | The Figma Make scaffold this frontend started from |

## Why it is built this way

**Precompute the registry instead of querying per drug.** ClinicalTrials.gov returns 1,000 trials per request and
only ~15,000 Phase 3 trials have posted results, so the whole registry is 15 requests. `harvest.py` stores them
harmonized in SQLite; `/report` reads from that store (falling back to a live query for drugs outside it) and the
dashboard is only possible because of it. It also means the demo does not depend on the venue Wi-Fi.

**Every external response is cached to disk** (`backend/data/cache`). openFDA allows 1,000 requests a day per IP
without a key; the cache is what makes that survivable on a shared campus network.

**Two denominators.** The published metric (participation-to-prevalence ratio, Scott et al., JACC 2018) divides a
group's share of trial participants by its share of the *disease* population. The US population alone would flag a
prostate-cancer drug for excluding women and excuse any drug for excluding older adults. So the score is computed
against Census 2020 and, when CDC's Chronic Disease Indicators have the condition, against the people who have it.
The UI shows both.

**Design exclusions count as evidence, not missing data.** A trial with a maximum age of 64 did not "fail to
report" people over 65; it excluded them. `scoring.py` counts such trials as known zeros for that group.

**Comparator trials are excluded.** Searching for zolpidem returns lemborexant's 1,006-person trial, where zolpidem
was the comparator. Only trials with the drug in an EXPERIMENTAL arm count.

**Race harmonization is rule-based and tested.** About 45% of race tables are free text. `harmonize.map_race` maps
labels with an ordered regex table (unit-tested); anything it cannot place lands in "other" rather than
disappearing. "Not reported" is a rendered result, never a blank, because missingness is the finding.

**The LLM is optional and grounded.** The questions card is generated from rules; if `GEMINI_API_KEY` is set,
Gemini rewrites it but receives only our numbers and label quotes, and any failure falls back to the rules text.
Photo reading re-encodes the image in memory (EXIF stripped) and never writes it to disk.

**Flask serves JSON only; React renders.** Both screens are interactive (autocomplete, live re-scoring, sortable
table, export), and the split let the frontend and backend be built in parallel. In production Flask serves the
built app, so there is one URL.

## Limits (also shown in the app)

Trials report groups separately, never intersections. Age bands exist in only ~22% of trials (the rest report a
mean). Race categories are harmonized from free text. Disease denominators use BRFSS-based adult prevalence, with
race compared within the non-Hispanic frame. FAERS counts are voluntary reports, not incidence. None of this is
medical advice.

## Data sources

ClinicalTrials.gov API v2 · RxNorm and RxClass (NLM) · openFDA (labels, FAERS, Drugs@FDA) · CDC Chronic Disease
Indicators (data.cdc.gov) · US Census 2020 · Gemini API (optional).

## AI disclosure

Built with Claude Code as a pair-programmer for code and research; the team designed the product, the pipeline, the
scoring method and the safety model, and reviewed the code. The frontend scaffold and first prototype came from
Figma Make.
