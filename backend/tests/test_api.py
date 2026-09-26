"""HTTP-level check of the blueprint with the Flask test client (skipped when Flask is not installed)."""
import pytest

pytest.importorskip("flask")

import db
import parse_study as ps
from api import create_app
from test_parse_study import CUSTOMIZED_STUDY, FETCHED, NIH_OMB_STUDY


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "studies.db"
    con = db.connect(path)
    db.init_schema(con)
    db.upsert_studies(con, [ps.parse_study(NIH_OMB_STUDY, FETCHED), ps.parse_study(CUSTOMIZED_STUDY, FETCHED)])
    db.set_meta(con, "ingest", {"studies": 2})
    con.close()
    app = create_app(path)
    app.testing = True
    return app.test_client()


def test_list_filters_and_shape(client):
    body = client.get("/api/studies?drug=dapagliflozin&sex=female&age=67&race=black").get_json()
    assert body["total"] == 1
    study = body["studies"][0]
    assert study["nct_id"] == "NCT01730534" and study["sex"] == "Male and Female"
    assert (study["age_min"], study["age_max"]) == (40, 100)
    assert study["drug"] == "Dapagliflozin 10 mg"
    assert study["race_composition"][0] == {"demographic": "White", "count": 13653, "category": "white", "dimension": "race"}


def test_one_aggregate_stats_and_errors(client):
    assert client.get("/api/studies/NCT05136885").get_json()["drug"] == "SLS-005"
    assert client.get("/api/studies/NCT00000000").status_code == 404
    assert client.get("/api/studies/not-an-id").status_code == 404
    assert client.get("/api/studies?sex=other").status_code == 400
    assert client.get("/api/studies?race=martian").status_code == 400
    assert client.get("/api/studies?age=old").status_code == 400
    agg = client.get("/api/studies/aggregate?condition=diabetes").get_json()
    assert agg["studies"] == 1 and agg["sex"] == {"female": 6422, "male": 10738}
    assert client.get("/api/studies/stats").get_json()["studies"] == 2
