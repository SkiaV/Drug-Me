"""Round trip through schema.sql: upsert, then the exact queries the API uses, on an in-memory SQLite database."""
import db
import parse_study as ps
from test_parse_study import CUSTOMIZED_STUDY, FETCHED, NIH_OMB_STUDY


def _loaded():
    con = db.connect(":memory:")
    db.init_schema(con)
    records = [ps.parse_study(NIH_OMB_STUDY, FETCHED), ps.parse_study(CUSTOMIZED_STUDY, FETCHED)]
    db.upsert_studies(con, records)
    db.upsert_studies(con, records)                 # a second run must not duplicate anything
    return con


def test_upsert_is_idempotent():
    con = _loaded()
    assert con.execute("SELECT COUNT(*) FROM studies").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM study_races").fetchone()[0] == (7 + 3) + (6 + 2)
    assert con.execute("SELECT COUNT(*) FROM study_drugs").fetchone()[0] == 2 + 2
    assert con.execute("SELECT COUNT(*) FROM study_conditions").fetchone()[0] == 2 + 2


def test_search_filters():
    con = _loaded()
    rows, total = db.search(con, drug="dapagliflozin")
    assert total == 1 and rows[0]["nct_id"] == "NCT01730534"
    assert rows[0]["race_composition"][0] == {"demographic": "White", "count": 13653, "category": "white", "dimension": "race"}
    assert db.search(con, age=67, sex="Female", race="black")[1] == 2
    assert [r["nct_id"] for r in db.search(con, age=90)[0]] == ["NCT01730534"]      # the ALS study stops at 80
    assert db.search(con, condition="sclerosis")[1] == 1
    assert db.search(con, race="nhpi")[1] == 1                                        # the ALS study reported 0 NHPI
    assert db.search(con, drug="nothing-like-this")[1] == 0


def test_aggregate_pools_counts():
    con = _loaded()
    agg = db.aggregate(con)
    assert agg["studies"] == 2 and agg["participants"] == 161 + 17160
    assert agg["studies_reporting_race"] == 2
    assert agg["sex"] == {"female": 79 + 6422, "male": 82 + 10738}
    assert agg["age_range"] == [18, 100]
    by_category = {(r["dimension"], r["category"]): r["count"] for r in agg["race_composition"]}
    assert by_category[("race", "black")] == 3 + 603
    assert by_category[("race", "white")] == 148 + 13653
    assert by_category[("ethnicity", "hispanic")] == 3 + 2568
    as_reported = {(r["dimension"], r["demographic"]): r for r in agg["race_composition_as_reported"]}
    assert as_reported[("race", "Black or African American")]["studies"] == 2
    only_als = db.aggregate(con, condition="sclerosis")
    assert only_als["studies"] == 1 and only_als["participants"] == 161


def test_study_stats_and_meta():
    con = _loaded()
    one = db.study(con, "NCT05136885")
    assert one["drug"] == "SLS-005" and len(one["race_composition"]) == 10
    assert one["race_composition"][0]["dimension"] == "race"       # race rows come before ethnicity rows
    assert {d["drug"] for d in one["drugs"]} == {"sls-005", "trehalose"}
    assert db.study(con, "NCT99999999") is None
    db.set_meta(con, "ingest", {"studies": 2})
    s = db.stats(con)
    assert s["studies"] == 2 and s["with_results"] == 2 and s["with_race_composition"] == 2
    assert s["distinct_drugs"] == 4 and s["ingest"] == {"studies": 2}
