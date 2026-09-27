"""A report must render from the registry alone; every external service may fail or hang."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import card
import db
import report

TRIAL = {"nct": "NCT0001", "title": "A trial", "phases": ["PHASE3"], "start_year": 2015, "completion_year": 2017,
         "sponsor": "Acme", "sponsor_class": "INDUSTRY", "sites_total": 10, "sites_us": 8, "countries": ["United States"],
         "elig_sex": "ALL", "min_age": 18, "max_age": 64, "std_ages": ["ADULT"], "conditions": ["Insomnia"],
         "condition_meshes": ["Sleep Initiation and Maintenance Disorders"], "disease_areas": ["Nervous System Diseases"],
         "interventions": [{"name": "testdrug", "type": "DRUG", "other_names": [], "arm_types": ["EXPERIMENTAL"]}],
         "mesh_drugs": ["testdrug"], "n_total": 300, "sex": {"female": 150, "male": 150}, "age_cat": None,
         "age_mean": 44.0, "race": None, "race_title": None, "ethnicity": None}
ROW = {"drug": "testdrug", "disease_area": "Nervous System Diseases"}
RESOLVED = {"query": "testdrug", "matched_name": "testdrug", "matched_tty": "IN", "rxcui": "1", "ingredient": "testdrug",
            "ingredients": [{"rxcui": "1", "name": "testdrug"}], "is_combination": False, "brands": ["Brandy"],
            "search_names": ["testdrug", "Brandy"]}


def _boom(*args, **kwargs):
    raise RuntimeError("service down")


def _registry(monkeypatch, stored=None):
    monkeypatch.setattr(db, "trials_with_name", lambda name: [TRIAL] if name == "testdrug" else [])
    monkeypatch.setattr(db, "get_extras", lambda *a, **k: stored)
    written = {}
    monkeypatch.setattr(db, "set_extras", lambda name, data: written.__setitem__(name, data))
    return written


def test_report_renders_when_every_external_service_fails(monkeypatch):
    written = _registry(monkeypatch)
    for mod, fn in ((report.rxnorm, "resolve"), (report.rxnorm, "classes"), (report.fda, "label"),
                    (report.fda, "approval"), (report.fda, "faers"), (report.prevalence, "disease_shares")):
        monkeypatch.setattr(mod, fn, _boom)
    rep = report.build("testdrug", "female", 67, None, None, registry_row=ROW)
    assert rep is not None
    assert rep["evidence"]["trials"] == 1 and rep["evidence"]["participants"] == 300
    assert rep["score"]["population"] is not None            # trials + score never depend on the network
    assert rep["label_flags"] is None and rep["faers"] is None and rep["approval"] is None
    assert rep["drug"]["ingredient"] == "testdrug" and rep["drug"]["brands"] == []
    assert len(rep["warnings"]) >= 4 and any("RxNorm" in w for w in rep["warnings"])
    assert rep["card"]["summary"] and rep["card"]["questions"]  # the card copes without a label
    assert written == {}                                        # failures are never frozen into extras.sqlite


def test_stored_extras_mean_no_network(monkeypatch):
    stored = {"classes": {"atc": [], "atc_label": "Hypnotics (ATC N05CF)", "va": [], "epc": [],
                          "may_treat": [{"mesh_id": "D007319", "name": "Sleep Initiation and Maintenance Disorders"}]},
              "label": None, "approval": {"date": "1992-12-16", "application": "NDA019908", "matched_name": "Brandy"},
              "faers": None, "prevalence": None, "complete": sorted(report.PIECES)}
    written = _registry(monkeypatch, stored)
    monkeypatch.setattr(report.registry, "row_for_name", lambda name: ROW if name == "testdrug" else None)
    monkeypatch.setattr(report.rxnorm, "resolve", lambda q: RESOLVED)
    for mod, fn in ((report.rxnorm, "classes"), (report.fda, "label"), (report.fda, "approval"),
                    (report.fda, "faers"), (report.prevalence, "disease_shares")):
        monkeypatch.setattr(mod, fn, _boom)
    rep = report.build("Brandy", "female", 67, None, None)      # typed brand -> its registry row
    assert rep["warnings"] == []
    assert rep["drug"]["brands"] == ["Brandy"] and rep["approval"]["date"] == "1992-12-16"
    assert rep["drug"]["class"] == "Hypnotics (ATC N05CF)" and rep["drug"]["indications"] == ["Sleep Initiation and Maintenance Disorders"]
    assert rep["evidence"]["trials"] == 1
    assert written == {}                                        # nothing new to store


def test_successful_pieces_are_stored(monkeypatch):
    written = _registry(monkeypatch)
    monkeypatch.setattr(report.rxnorm, "resolve", lambda q: RESOLVED)
    monkeypatch.setattr(report.rxnorm, "classes", lambda rxcui: dict(report.EMPTY_CLASSES))
    monkeypatch.setattr(report.fda, "label", lambda *a, **k: None)
    monkeypatch.setattr(report.fda, "approval", lambda *a, **k: {"date": "2001-01-01", "application": "X", "matched_name": "testdrug"})
    monkeypatch.setattr(report.fda, "faers", _boom)
    monkeypatch.setattr(report.prevalence, "disease_shares", lambda terms: None)
    rep = report.build("testdrug", None, None, None, None, registry_row=ROW)
    assert [w for w in rep["warnings"] if "FAERS" in w]
    stored = written["testdrug"]
    assert set(stored["complete"]) == {"classes", "label", "approval", "prevalence"}  # faers failed: retried next time
    assert stored["approval"]["date"] == "2001-01-01"


def test_card_without_label_or_years():
    rep = {"drug": {"ingredient": "testdrug"}, "profile": {"groups": ["female"]},
           "evidence": {"trials": 2, "participants": 400, "years": [None, None]},
           "groups": [{"key": "female", "band_pop": "adequate", "trial_share": 0.5, "expected_disease": None,
                       "expected_pop": 0.509, "ppr_pop": 0.98, "ppr_disease": None, "band_disease": None,
                       "trials_design_excluded": 0, "trials_missing": 0}],
           "label_flags": None, "faers": None, "approval": None}
    out = card.rule_based(rep)
    assert "2 Phase 3 trial(s)" in out["summary"] and "None" not in out["summary"]
