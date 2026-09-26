-- Drug Me Finder: Phase 3 studies from ClinicalTrials.gov, one row per study.
-- Field numbers follow the spec: 1 race composition, 2 age range, 3 sex, 4 drug, 5 condition, 6 study.
-- Loaded by ingest.py, read by api.py. SQLite, stdlib only.

CREATE TABLE IF NOT EXISTS studies (
    nct_id         TEXT PRIMARY KEY,                        -- 6. study: NCT number, e.g. NCT01730534
    title          TEXT,
    drug           TEXT,                                    -- 4. drug as reported in the experimental arm(s), "; "-joined
    drug_mesh      TEXT,                                    --    the same drug(s) as MeSH-normalized names, e.g. "Dapagliflozin"
    condition      TEXT,                                    -- 5. condition(s) as listed by the sponsor, "; "-joined
    sex            TEXT NOT NULL
                   CHECK (sex IN ('Male', 'Female', 'Male and Female')),   -- 3. who was enrolled
    age_min        INTEGER NOT NULL,                        -- 2. lower bound in years (0 when the protocol sets none)
    age_max        INTEGER NOT NULL,                        -- 2. upper bound in years, capped at 100
    -- provenance and detail behind the six fields
    eligible_sex   TEXT,                                    -- ALL / FEMALE / MALE as written in the protocol
    age_min_raw    TEXT,                                    -- "18 Years", "6 Months", NULL
    age_max_raw    TEXT,                                    -- "65 Years", "130 Years", NULL
    female_count   INTEGER,                                 -- baseline-table head counts, when results were posted
    male_count     INTEGER,
    participants   INTEGER,                                 -- baseline "Total" participants, else enrollment
    phase          TEXT,                                    -- PHASE3 or PHASE2/PHASE3
    status         TEXT,                                    -- COMPLETED, TERMINATED, ...
    start_date     TEXT,                                    -- "2013-04-25" or "2008-09", as published
    has_results    INTEGER NOT NULL DEFAULT 0,              -- 1 when a baseline table was posted
    race_reported  INTEGER NOT NULL DEFAULT 0,              -- 1 when at least one race row exists (missingness is data)
    source_url     TEXT NOT NULL,                           -- https://clinicaltrials.gov/study/<nct_id>
    fetched_at     TEXT NOT NULL                            -- ISO timestamp of the ingest
);

-- 1. race composition: one row per demographic label the sponsor reported, with the number of people.
--    Labels are kept verbatim ("Black or African American", "African American/African Heritage", ...);
--    `category` is the harmonized bucket that makes them addable across studies. Zero counts are kept:
--    "reported 0" and "not reported" are different findings.
CREATE TABLE IF NOT EXISTS study_races (
    nct_id         TEXT    NOT NULL REFERENCES studies(nct_id) ON DELETE CASCADE,
    demographic    TEXT    NOT NULL,                        -- as reported
    count          INTEGER NOT NULL,                        -- number of people
    category       TEXT    NOT NULL,                        -- white | black | asian | aian | nhpi | multiracial | hispanic | not_hispanic | other | unknown
    dimension      TEXT    NOT NULL,                        -- 'race' or 'ethnicity' (NIH/OMB tables report Hispanic origin separately)
    measure_title  TEXT    NOT NULL,                        -- baseline table it came from, e.g. "Race (NIH/OMB)"
    PRIMARY KEY (nct_id, dimension, demographic)
);
CREATE INDEX IF NOT EXISTS ix_study_races_category ON study_races (category, dimension);

-- The "; "-joined strings above, split one per row so WHERE drug = ? and WHERE condition LIKE ? work.
CREATE TABLE IF NOT EXISTS study_drugs (
    nct_id             TEXT NOT NULL REFERENCES studies(nct_id) ON DELETE CASCADE,
    drug               TEXT NOT NULL,                       -- lower-cased for matching
    role               TEXT,                                -- experimental | comparator | placebo | other; NULL for MeSH terms
    intervention_type  TEXT NOT NULL,                       -- DRUG | BIOLOGICAL | COMBINATION_PRODUCT | MESH
    PRIMARY KEY (nct_id, drug)
);
CREATE INDEX IF NOT EXISTS ix_study_drugs_drug ON study_drugs (drug);

CREATE TABLE IF NOT EXISTS study_conditions (
    nct_id     TEXT NOT NULL REFERENCES studies(nct_id) ON DELETE CASCADE,
    condition  TEXT NOT NULL,                               -- lower-cased for matching
    source     TEXT NOT NULL,                               -- 'listed' (protocol) or 'mesh' (derived by ClinicalTrials.gov)
    PRIMARY KEY (nct_id, condition)
);
CREATE INDEX IF NOT EXISTS ix_study_conditions_condition ON study_conditions (condition);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL                                    -- JSON
);
