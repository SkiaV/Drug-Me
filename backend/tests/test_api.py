"""HTTP-level check of the blueprint with the Flask test client (skipped when Flask is not installed)."""
import pytest

pytest.importorskip("flask")

import db
import parse_study as ps
from api import create_app
from test_parse_study import CUSTOMIZED_STUDY, NIH_OMB_STUDY


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "studies.db"
    con = db.connect(path)
    db.init_schema(con)
    db.upsert_studies(con, [ps.parse_study(NIH_OMB_STUDY), ps.parse_study(CUSTOMIZED_STUDY)])
    db.set_meta(con, "ingest", {"studies": 2})
    con.close()
    app = create_app(path)
    app.testing = True
    return app.test_client()


def test_list_filters_and_shape(client):
    body = client.get("/api/studies?drug=dapagliflozin&sex=female&age=67&race=Black%20or%20African%20American").get_json()
    assert body["total"] == 1
    assert body["filters"] == {"sex": "F", "age": 67, "race": "black", "drug": "dapagliflozin"}   # canonical form
    study = body["studies"][0]
    assert study["nct_id"] == "NCT01730534" and study["sex"] == "MF"
    assert (study["age_lower"], study["age_upper"]) == (40, 130)
    assert study["drug"] == "Dapagliflozin 10 mg" and study["drug_mesh"] == "Dapagliflozin"
    assert study["participants"] == 17160 and study["race_reported"] == 1
    assert study["source_url"] == "https://clinicaltrials.gov/study/NCT01730534"
    assert study["race_composition"][0] == {"demographic": "White", "count": 13653, "category": "white", "dimension": "race"}
    assert client.get("/api/studies?sex=M&limit=1").get_json()["total"] == 2          # mixed studies match either sex
    assert client.get("/api/studies?unknown=param").status_code == 200               # unknown parameters are ignored


def test_one_aggregate_stats_and_errors(client):
    one = client.get("/api/studies/NCT05136885").get_json()
    assert one["drug"] == "SLS-005" and one["drugs"] == [{"drug": "sls-005", "drug_mesh": "Trehalose"}]
    assert client.get("/api/studies/NCT00000000").status_code == 404
    assert client.get("/api/studies/not-an-id").status_code == 404
    bad = client.get("/api/studies?sex=other&race=martian&age=old")
    assert bad.status_code == 400
    assert len(bad.get_json()["error"]["details"]) == 3                               # every problem is reported
    assert client.get("/api/studies?age=67&age=68").status_code == 400
    assert client.get("/api/studies/aggregate?race=martian").status_code == 400
    agg = client.get("/api/studies/aggregate?condition=diabetes").get_json()
    assert agg["studies"] == 1 and agg["sex"] == {"female": 6422, "male": 10738} and agg["age_range"] == [40, 130]
    stats = client.get("/api/studies/stats").get_json()
    assert stats["studies"] == 2 and stats["distinct_drugs"] == 2 and stats["ingest"] == {"studies": 2}
