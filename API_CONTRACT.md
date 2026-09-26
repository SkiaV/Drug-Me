# Clinical Trial Representation API Contract

The React app calls versioned REST endpoints under `/api/v1`. By default these
are same-origin. Set `VITE_API_BASE_URL` when Flask is hosted separately, for
example:

```text
VITE_API_BASE_URL=http://localhost:5000
```

When an endpoint is unavailable, the current frontend falls back to local sample
data. Successful Flask responses replace that fallback without requiring UI
changes.

## Shared conventions

- Request and response bodies use JSON and UTF-8.
- Property names use `camelCase`.
- Dates use ISO 8601 `YYYY-MM-DD`.
- Scores and coverage components are integer percentages from `0` to `100`.
- Drug IDs are stable URL-safe generic-drug identifiers.
- Brand products should be normalized under their active generic ingredient.
- CORS must allow the Vite origin when Flask is hosted separately.
- Errors should return `{ "error": { "code": string, "message": string } }`.

## Drug summary

```json
{
  "id": "fluoxetine",
  "name": "Fluoxetine",
  "primaryUse": "Major depressive disorder",
  "otherUses": ["Panic disorder", "Bulimia nervosa"],
  "leastResearched": {
    "dimension": "Race",
    "group": "Black participants"
  },
  "score": 62,
  "tier": "Developing",
  "components": {
    "age": 71,
    "sex": 79,
    "race": 38
  },
  "trialCount": 128,
  "participantCount": 28410,
  "updatedAt": "2025-05-14"
}
```

`tier` must be one of `Limited`, `Developing`, or `Strong`.

## GET `/api/v1/drugs`

Returns generalized representation summaries.

Optional query parameters:

- `query`: generic drug name or use
- `sort`: `score`, `name`, or `trialCount`
- `order`: `asc` or `desc`
- `limit`: requested page size
- `cursor`: opaque pagination cursor

The frontend currently accepts a direct array of drug summaries. A later
pagination iteration can wrap this in an object with `items` and `nextCursor`.

## GET `/api/v1/search`

Returns drug summaries with `score` and `tier` recalculated for the selected
demographic profile.

Required query parameters:

- `age`: integer from 0 to 120
- `sex`: `Female`, `Male`, or `All or not specified`
- `race`: one of:
  - `American Indian or Alaska Native`
  - `Asian`
  - `Black or African American`
  - `Multiracial`
  - `Native Hawaiian or Pacific Islander`
  - `White`
  - `All or not specified`

Optional query parameters:

- `drug`: generic drug name
- `indication`: use or condition
- `status`: ClinicalTrials.gov study status
- `phase`: study phase or `Observational`
- `location`: country, state, or city
- `sponsor`: sponsor or collaborator
- `fromDate`: study start lower bound
- `toDate`: study start upper bound

Response: an array of drug summaries in the same shape as `/drugs`.

## GET `/api/v1/drugs/:drugId/report`

Returns the evidence report for one normalized generic drug and demographic
profile.

Required query parameters: `age`, `sex`, and `race`, using the values described
for `/search`.

```json
{
  "drug": {},
  "profile": {
    "age": 67,
    "sex": "Female",
    "race": "Black or African American"
  },
  "personalizedScore": 51,
  "summary": "Plain-language evidence interpretation.",
  "strengths": ["Evidence strength"],
  "gaps": ["Evidence limitation"],
  "fdaContext": {
    "indication": "Major depressive disorder",
    "labelUpdated": "2024-11-19",
    "note": "FDA labeling context.",
    "sourceUrl": "https://open.fda.gov/apis/drug/label/"
  },
  "evidence": [
    {
      "id": "NCT05824182",
      "title": "Trial title",
      "phase": "Phase 4",
      "status": "Completed",
      "enrollment": 2480,
      "match": "High relevance",
      "sourceUrl": "https://clinicaltrials.gov/"
    }
  ]
}
```

The `drug` property contains the complete shared drug-summary shape.

## Source and methodology expectations

- Clinical trial records should be retrieved from ClinicalTrials.gov API v2.
- FDA indication and labeling context should come from the openFDA drug-label
  endpoint.
- Store source record IDs and source URLs so report evidence is auditable.
- Scores must remain marked provisional until the scoring methodology is
  finalized.
- Missing demographic reporting should reduce data confidence rather than be
  interpreted as zero enrollment.
