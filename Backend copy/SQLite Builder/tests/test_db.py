"""Round trip through schema.sql: upsert, then the exact queries the API uses, on an in-memory SQLite database."""
import sqlite3

import pytest

import db
import parse_study as ps
from test_parse_study import CUSTOMIZED_STUDY, NIH_OMB_STUDY

OPEN_AGE = ps.StudyRecord(nct_id="NCT00000003", drug="Drug X", drug_mesh="Drug X", condition="Anything", sex="M",
                          age_lower=None, age_upper=None, female_count=None, male_count=None, participants=10,
                          race_reported=0, drugs=[ps.DrugRow(drug="drug x", drug_mesh="Drug X")])


def _loaded():
    con = db.connect(":memory:")
    db.init_schema(con)
    records = [ps.parse_study(NIH_OMB_STUDY), ps.parse_study(CUSTOMIZED_STUDY)]
    db.upsert_studies(con, records)
    db.upsert_studies(con, records)                 # a second run must not duplicate anything
    return con


def test_upsert_is_idempotent():
    con = _loaded()
    assert con.execute("SELECT COUNT(*) FROM studies").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM study_races").fetchone()[0] == (7 + 3) + (6 + 2)
    assert [tuple(r) for r in con.execute("SELECT * FROM study_drugs ORDER BY nct_id")] == [
        ("NCT01730534", "dapagliflozin 10 mg", "Dapagliflozin"), ("NCT05136885", "sls-005", "Trehalose")]


def test_schema_constraints_hold():
    con = _loaded()
    bad = [("sex", "Female"), ("age_lower", -1), ("participants", None), ("race_reported", 2)]
    for column, value in bad:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(f"UPDATE studies SET {column} = ? WHERE nct_id = 'NCT01730534'", (value,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE studies SET age_lower = 90 WHERE nct_id = 'NCT05136885'")      # 90 > age_upper 80
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO study_races VALUES ('NCT01730534', 'x', 1, 'martian', 'race', 't')")


def test_search_filters():
    con = _loaded()
    rows, total = db.search(con, drug="dapagliflozin")
    assert total == 1 and rows[0]["nct_id"] == "NCT01730534"
    assert rows[0]["source_url"] == "https://clinicaltrials.gov/study/NCT01730534"
    assert rows[0]["race_composition"][0] == {"demographic": "White", "count": 13653, "category": "white", "dimension": "race"}
    assert db.search(con, drug="trehalose")[1] == 1                                   # the MeSH name matches too
    assert db.search(con, age=67, sex="F", race="black")[1] == 2
    assert [r["nct_id"] for r in db.search(con, age=90)[0]] == ["NCT01730534"]      # the ALS study stops at 80
    assert db.search(con, sex="M")[1] == 2 and db.search(con, sex="MF")[1] == 2
    assert db.search(con, condition="sclerosis")[1] == 1
    assert db.search(con, race="nhpi")[1] == 1                                        # the ALS study reported 0 NHPI
    assert db.search(con, drug="nothing-like-this")[1] == 0
    assert [r["nct_id"] for r in db.search(con)[0]] == ["NCT05136885", "NCT01730534"]   # newest registration first


def test_null_age_bounds_mean_no_bound():
    con = _loaded()
    db.upsert_studies(con, [OPEN_AGE])
    assert db.search(con, age=99)[1] == 2                          # the dapagliflozin study (40-130) and the open one
    assert db.search(con, age=3)[1] == 1
    assert db.search(con, sex="M")[1] == 3 and db.search(con, sex="F")[1] == 2 and db.search(con, sex="MF")[1] == 2
    assert db.aggregate(con)["age_range"] == [0, None]
    assert db.aggregate(con, condition="sclerosis")["age_range"] == [18, 80]


def test_aggregate_pools_counts():
    con = _loaded()
    agg = db.aggregate(con)
    assert agg["studies"] == 2 and agg["participants"] == 161 + 17160
    assert agg["studies_reporting_race"] == 2
    assert agg["sex"] == {"female": 79 + 6422, "male": 82 + 10738}
    assert agg["age_range"] == [18, 130]
    by_category = {(r["dimension"], r["category"]): r["count"] for r in agg["race_composition"]}
    assert by_category[("race", "black")] == 3 + 603
    assert by_category[("race", "white")] == 148 + 13653
    assert by_category[("ethnicity", "hispanic")] == 3 + 2568
    as_reported = {(r["dimension"], r["demographic"]): r for r in agg["race_composition_as_reported"]}
    assert as_reported[("race", "Black or African American")]["studies"] == 2
    only_als = db.aggregate(con, condition="sclerosis")
    assert only_als["studies"] == 1 and only_als["participants"] == 161
    assert db.aggregate(con, drug="nothing")["age_range"] == [None, None]


def test_study_stats_and_meta():
    con = _loaded()
    one = db.study(con, "NCT05136885")
    assert one["drug"] == "SLS-005" and one["drug_mesh"] == "Trehalose" and len(one["race_composition"]) == 10
    assert one["race_composition"][0]["dimension"] == "race"       # race rows come before ethnicity rows
    assert one["drugs"] == [{"drug": "sls-005", "drug_mesh": "Trehalose"}]
    assert one["source_url"] == "https://clinicaltrials.gov/study/NCT05136885"
    assert set(one) == set(db.STUDY_COLUMNS) | {"source_url", "race_composition", "drugs"}
    assert db.study(con, "NCT99999999") is None
    db.set_meta(con, "ingest", {"studies": 2})
    s = db.stats(con)
    assert s == {"studies": 2, "participants": 161 + 17160, "with_race_composition": 2, "distinct_drugs": 2,
                 "ingest": {"studies": 2}}


def test_old_schema_is_detected_and_rebuilt():
    con = db.connect(":memory:")
    assert db.schema_is_current(con)                               # nothing there yet is fine
    con.execute("CREATE TABLE studies (nct_id TEXT PRIMARY KEY, age_min INTEGER, age_max INTEGER)")
    assert not db.schema_is_current(con)
    db.drop_all(con)
    db.init_schema(con)
    assert db.schema_is_current(con)
    db.upsert_studies(con, [OPEN_AGE])
    assert db.stats(con)["studies"] == 1
