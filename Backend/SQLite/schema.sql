-- ============================================================================
-- Clinical trial studies schema
-- Scope: phase III, completed studies only (enforced at load time, not here).
-- ============================================================================

-- Studies table
-- One row per trial. `drug`/`drug_mesh`/`condition` are "; "-joined summaries
-- for display; `study_drugs` holds the normalized, queryable one-row-per-item
-- version of the drug fields.
--- Only non-placebo results are stored
CREATE TABLE IF NOT EXISTS studies (
    nct_id        TEXT    NOT NULL PRIMARY KEY,               -- NCT number, e.g. NCT01730534
    drug          TEXT    NOT NULL,                           -- drug(s) as reported in the experimental arm(s), "; "-joined
    drug_mesh     TEXT    NOT NULL,                           -- same drug(s) as MeSH-normalized names, e.g. "Dapagliflozin"
    condition     TEXT    NOT NULL,                           -- condition(s) as listed by the sponsor, "; "-joined
    sex           TEXT    NOT NULL CHECK (sex IN ('M', 'F', 'MF')),
    age_lower     INTEGER CHECK (age_lower >= 0),             -- lower bound in years
    age_upper     INTEGER CHECK (age_upper >= 0),             -- upper bound in years
    -- provenance and detail behind the demographic fields above
    female_count  INTEGER CHECK (female_count >= 0),          -- baseline-table head count, when results were posted
    male_count    INTEGER CHECK (male_count >= 0),            -- baseline-table head count, when results were posted
    participants  INTEGER NOT NULL CHECK (participants >= 0), -- baseline "Total" participants, else enrollment
    race_reported INTEGER NOT NULL DEFAULT 0 CHECK (race_reported IN (0, 1)), -- 1 when at least one race row exists (missingness is data)
    CHECK (age_lower IS NULL OR age_upper IS NULL OR age_lower <= age_upper)
);

-- Study races
-- One row per demographic label the sponsor reported, with the number of
-- people. Labels are kept verbatim ("Black or African American",
-- "African American/African Heritage", ...); `category` is the harmonized
-- bucket that makes them addable across studies. Zero counts are kept:
-- "reported 0" and "not reported" are different findings.
CREATE TABLE IF NOT EXISTS study_races (
    nct_id        TEXT    NOT NULL REFERENCES studies (nct_id) ON DELETE CASCADE,
    demographic   TEXT    NOT NULL,             -- label as reported by the sponsor
    count         INTEGER NOT NULL CHECK (count >= 0), -- number of people
    category      TEXT    NOT NULL CHECK (category IN (
                      'white', 'black', 'asian', 'aian', 'nhpi',
                      'multiracial', 'hispanic', 'not_hispanic', 'other', 'unknown'
                  )),
    dimension     TEXT    NOT NULL CHECK (dimension IN ('race', 'ethnicity')), -- NIH/OMB tables report Hispanic origin separately
    measure_title TEXT    NOT NULL,             -- baseline table it came from, e.g. "Race (NIH/OMB)"
    PRIMARY KEY (nct_id, dimension, demographic)
);
CREATE INDEX IF NOT EXISTS ix_study_races_category ON study_races (category, dimension);

-- Study drugs
-- The "; "-joined `drug`/`drug_mesh` strings from `studies`, split one per
-- row so `WHERE drug = ?` and `WHERE condition LIKE ?`-style lookups work.
-- Raw arm-level drugs (DRUG/BIOLOGICAL/COMBINATION_PRODUCT) and their
-- MeSH-normalized counterparts (MESH) both live here;
CREATE TABLE IF NOT EXISTS study_drugs (
    nct_id            TEXT NOT NULL REFERENCES studies (nct_id) ON DELETE CASCADE,
    drug              TEXT NOT NULL,   -- lower-cased for matching
    drug_mesh         TEXT    NOT NULL, -- same drug(s) as MeSH-normalized names, e.g. "Dapagliflozin"
    PRIMARY KEY (nct_id, drug_mesh)
);
CREATE INDEX IF NOT EXISTS ix_study_drugs_drug ON study_drugs (drug);

-- Key/value store for pipeline metadata (e.g. last refresh date, source
-- query parameters). `value` is a JSON-encoded string.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL  -- JSON
);