import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from harmonize import classify_age_band, map_race, parse_baseline, parse_study, trial_uses_drug
import scoring


def _measure(title, cats, total="T", param="COUNT_OF_PARTICIPANTS"):
    return {"title": title, "paramType": param,
            "classes": [{"categories": [{"title": t, "measurements": [{"groupId": total, "value": v}]} for t, v in cats]}]}


BASELINE = {
    "groups": [{"id": "A", "title": "Drug"}, {"id": "B", "title": "Placebo"}, {"id": "T", "title": "Total"}],
    "denoms": [{"units": "Participants", "counts": [{"groupId": "A", "value": "60"}, {"groupId": "B", "value": "40"}, {"groupId": "T", "value": "100"}]}],
    "measures": [
        _measure("Sex: Female, Male", [("Female", "58"), ("Male", "42")]),
        _measure("Age, Categorical", [("<=18 years", "0"), ("Between 18 and 65 years", "88"), (">=65 years", "12")]),
        _measure("Race/Ethnicity, Customized", [("African-American", "9"), ("Caucasian", "80"), ("Hispanic", "7"),
                                               ("Asian/Pacific Islander", "3"), ("Not reported", "1")]),
    ],
}


def test_parse_baseline_counts():
    b = parse_baseline(BASELINE)
    assert b["n_total"] == 100
    assert b["sex"] == {"female": 58, "male": 42}
    assert b["age_cat"] == {"under18": 0, "age18_64": 88, "age65": 12}
    assert b["race"]["black"] == 9 and b["race"]["white"] == 80 and b["race"]["asian"] == 3
    assert b["race"]["unknown"] == 1
    assert b["ethnicity"] == {"hispanic": 7, "not_hispanic": 0}


def test_na_values_and_no_total_group():
    base = {"groups": [{"id": "A", "title": "Arm 1"}, {"id": "B", "title": "Arm 2"}],
            "measures": [{"title": "Sex: Female, Male", "paramType": "COUNT_OF_PARTICIPANTS", "classes": [{"categories": [
                {"title": "Female", "measurements": [{"groupId": "A", "value": "10"}, {"groupId": "B", "value": "NA"}]},
                {"title": "Male", "measurements": [{"groupId": "A", "value": "5"}, {"groupId": "B", "value": "7"}]}]}]}]}
    b = parse_baseline(base)
    assert b["sex"] == {"female": 10, "male": 12}
    assert b["n_total"] == 22


def test_age_bands():
    assert classify_age_band(">=65 years") == "age65"
    assert classify_age_band("65 and over") == "age65"
    assert classify_age_band("75-84") == "age65"
    assert classify_age_band("Between 18 and 65 years") == "age18_64"
    assert classify_age_band("18-64") == "age18_64"
    assert classify_age_band("<=18 years") == "under18"
    assert classify_age_band("60-69") is None  # straddles 65 -> whole table unusable


def test_race_mapping():
    assert map_race("Black or African American") == "black"
    assert map_race("White") == "white"
    assert map_race("Native Hawaiian or Other Pacific Islander") == "nhpi"
    assert map_race("American Indian or Alaska Native") == "aian"
    assert map_race("More than one race") == "multiracial"
    assert map_race("Unknown or Not Reported") == "unknown"
    assert map_race("Hispanic or Latino") == "hispanic"
    assert map_race("Other") == "other"


def test_parse_study_and_drug_match():
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT1", "briefTitle": "x"},
        "statusModule": {"startDateStruct": {"date": "2015-03"}, "primaryCompletionDateStruct": {"date": "2017-01-05"}},
        "eligibilityModule": {"sex": "ALL", "minimumAge": "18 Years", "maximumAge": "64 Years", "stdAges": ["ADULT"]},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Pharma", "class": "INDUSTRY"}},
        "armsInterventionsModule": {
            "armGroups": [{"type": "EXPERIMENTAL", "interventionNames": ["Drug: Lemborexant"]},
                          {"type": "ACTIVE_COMPARATOR", "interventionNames": ["Drug: Zolpidem"]}],
            "interventions": [{"type": "DRUG", "name": "Lemborexant"}, {"type": "DRUG", "name": "Zolpidem", "otherNames": ["Ambien"]}]},
        "contactsLocationsModule": {"locations": [{"country": "United States"}, {"country": "Japan"}]},
        "designModule": {"phases": ["PHASE3"]}},
        "derivedSection": {"conditionBrowseModule": {"meshes": [{"term": "Sleep Initiation and Maintenance Disorders"}],
                                                     "ancestors": [{"term": "Dyssomnias"}, {"term": "Nervous System Diseases"}, {"term": "Mental Disorders"}]},
                           "interventionBrowseModule": {"meshes": [{"term": "Zolpidem"}, {"term": "Lemborexant"}]}},
        "resultsSection": {"baselineCharacteristicsModule": BASELINE}}
    rec = parse_study(study)
    assert rec["max_age"] == 64 and rec["sites_us"] == 1 and rec["countries"] == ["Japan", "United States"]
    assert set(rec["disease_areas"]) == {"Nervous System Diseases", "Mental Disorders"}
    m = trial_uses_drug(rec, ["zolpidem", "Ambien"])
    assert m == {"experimental": False, "comparator_only": True}
    assert trial_uses_drug(rec, ["lemborexant"]) == {"experimental": True, "comparator_only": False}
    assert trial_uses_drug(rec, ["metformin"]) is None


def test_aggregate_and_score():
    t1 = dict(parse_baseline(BASELINE), start_year=2015, completion_year=2017, sponsor_class="INDUSTRY",
              sites_total=2, sites_us=1, countries=["United States"], max_age=64, min_age=18, elig_sex="ALL")
    t2 = {"n_total": 200, "sex": {"female": 100, "male": 100}, "age_cat": None, "race": None, "ethnicity": None,
          "age_mean": 44.0, "start_year": 2018, "completion_year": 2020, "sponsor_class": "NIH", "sites_total": 3,
          "sites_us": 3, "countries": ["United States"], "max_age": None, "min_age": 18, "elig_sex": "ALL"}
    agg = scoring.aggregate([t1, t2], {"female": 0.47})
    g = {x["key"]: x for x in agg["groups"]}
    assert agg["participants"] == 300
    assert g["female"]["trial_share"] == round(158 / 300, 4)
    assert g["female"]["ppr_disease"] == round((158 / 300) / 0.47, 2)
    assert g["age65"]["coverage"] == round(100 / 300, 3) and g["age65"]["trials_missing"] == 1
    assert g["age65"]["trials_design_excluded"] == 1
    assert g["black"]["trial_share"] == round(9 / 92, 4)  # unknown excluded from the denominator
    sc = scoring.score(agg, ["female", "age65", "black"])
    assert 0 < sc["population"] <= 100 and sc["groups_used"] == ["female", "age65", "black"]
    assert scoring.band(0.3) == "very_under" and scoring.band(1.0) == "adequate"
