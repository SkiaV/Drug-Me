"""Unit tests for parse_study.py against real ClinicalTrials.gov API v2 shapes (trimmed from live studies)."""
import pytest

import parse_study as ps

FETCHED = "2026-09-26T00:00:00+00:00"


def _measure(title, categories, unit="Participants", param="COUNT_OF_PARTICIPANTS", cls_title=None):
    """categories: {label: [(groupId, value), ...]} -> one baseline measure with one class."""
    cls = {"categories": [{"title": label, "measurements": [{"groupId": g, "value": v} for g, v in ms]}
                          for label, ms in categories.items()]}
    if cls_title is not None:
        cls["title"] = cls_title
    return {"title": title, "paramType": param, "unitOfMeasure": unit, "classes": [cls]}


def three(a, b, c):
    return [("BG000", a), ("BG001", b), ("BG002", c)]


GROUPS_WITH_TOTAL = [{"id": "BG000", "title": "SLS-005"}, {"id": "BG001", "title": "Matching Placebo"},
                     {"id": "BG002", "title": "Total"}]
DENOMS = [{"units": "Participants", "counts": [{"groupId": "BG000", "value": "120"}, {"groupId": "BG001", "value": "41"},
                                               {"groupId": "BG002", "value": "161"}]}]

# NCT05136885, trimmed: NIH/OMB race and ethnicity tables with a Total column.
NIH_OMB_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT05136885", "briefTitle": "SLS-005 in ALS"},
        "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2021-11-29"}},
        "designModule": {"phases": ["PHASE2", "PHASE3"], "enrollmentInfo": {"count": 161}},
        "eligibilityModule": {"sex": "ALL", "minimumAge": "18 Years", "maximumAge": "80 Years"},
        "conditionsModule": {"conditions": ["Amyotrophic Lateral Sclerosis"]},
        "armsInterventionsModule": {
            "armGroups": [{"label": "SLS-005", "type": "EXPERIMENTAL"}, {"label": "Placebo", "type": "PLACEBO_COMPARATOR"}],
            "interventions": [{"type": "DRUG", "name": "SLS-005", "armGroupLabels": ["SLS-005"]},
                              {"type": "DRUG", "name": "Matching Placebo", "armGroupLabels": ["Placebo"]}]},
    },
    "derivedSection": {
        "conditionBrowseModule": {"meshes": [{"term": "Amyotrophic Lateral Sclerosis"}, {"term": "Motor Neuron Disease"}]},
        "interventionBrowseModule": {"meshes": [{"term": "Trehalose"}]}},
    "resultsSection": {"baselineCharacteristicsModule": {
        "groups": GROUPS_WITH_TOTAL, "denoms": DENOMS,
        "measures": [
            _measure("Age, Continuous", {"": three("59.3", "61.3", "59.8")}, unit="years", param="MEAN"),
            _measure("Sex: Female, Male", {"Female": three("55", "24", "79"), "Male": three("65", "17", "82")}),
            _measure("Ethnicity (NIH/OMB)", {"Hispanic or Latino": three("2", "1", "3"),
                                             "Not Hispanic or Latino": three("115", "40", "155"),
                                             "Unknown or Not Reported": three("3", "0", "3")}),
            _measure("Race (NIH/OMB)", {"American Indian or Alaska Native": three("0", "0", "0"),
                                        "Asian": three("5", "1", "6"),
                                        "Native Hawaiian or Other Pacific Islander": three("0", "0", "0"),
                                        "Black or African American": three("2", "1", "3"),
                                        "White": three("109", "39", "148"),
                                        "More than one race": three("1", "0", "1"),
                                        "Unknown or Not Reported": three("3", "0", "3")}),
        ]}},
}

# NCT01730534, trimmed: free-text "Race/Ethnicity, Customized" table and a 130-year maximum age.
CUSTOMIZED_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT01730534", "briefTitle": "Dapagliflozin cardiovascular outcomes"},
        "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2013-04-25"}},
        "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": 17190}},
        "eligibilityModule": {"sex": "ALL", "minimumAge": "40 Years", "maximumAge": "130 Years"},
        "conditionsModule": {"conditions": ["Diabetes Mellitus, Non-Insulin-Dependent", "High Risk for Cardiovascular Event"]},
        "armsInterventionsModule": {
            "armGroups": [{"label": "Dapagliflozin", "type": "EXPERIMENTAL"}, {"label": "Placebo", "type": "PLACEBO_COMPARATOR"}],
            "interventions": [{"type": "DRUG", "name": "Dapagliflozin 10 mg", "armGroupLabels": ["Dapagliflozin"]},
                              {"type": "DRUG", "name": "Placebo tablet", "armGroupLabels": ["Placebo"]}]},
    },
    "derivedSection": {"interventionBrowseModule": {"meshes": [{"term": "Dapagliflozin"}]}},
    "resultsSection": {"baselineCharacteristicsModule": {
        "groups": [{"id": "BG000", "title": "Dapa 10 mg"}, {"id": "BG001", "title": "Placebo"}, {"id": "BG002", "title": "Total"}],
        "denoms": [{"units": "Participants", "counts": [{"groupId": "BG000", "value": "8582"}, {"groupId": "BG001", "value": "8578"},
                                                        {"groupId": "BG002", "value": "17160"}]}],
        "measures": [
            _measure("Sex: Female, Male", {"Female": three("3171", "3251", "6422"), "Male": three("5411", "5327", "10738")}),
            _measure("Ethnicity (NIH/OMB)", {"Hispanic or Latino": three("1298", "1270", "2568"),
                                             "Not Hispanic or Latino": three("7284", "7308", "14592")}),
            _measure("Race/Ethnicity, Customized", {"White": three("6843", "6810", "13653"),
                                                    "Black or African American": three("295", "308", "603"),
                                                    "Asian": three("1148", "1155", "2303"),
                                                    "American Indian or Alaska Native": three("52", "52", "104"),
                                                    "Native Hawaiian or other Pacific Islander": three("9", "13", "22"),
                                                    "Other": three("235", "240", "475")}),
        ]}},
}


def test_nih_omb_study_fields():
    rec = ps.parse_study(NIH_OMB_STUDY, FETCHED)
    assert rec.nct_id == "NCT05136885"
    assert rec.sex == "Male and Female" and (rec.female_count, rec.male_count) == (79, 82)
    assert rec.participants == 161
    assert (rec.age_min, rec.age_max) == (18, 80)
    assert rec.phase == "PHASE2/PHASE3"
    assert rec.drug == "SLS-005"                                   # the matching placebo is not a drug
    assert rec.drug_mesh == "Trehalose"
    assert rec.condition == "Amyotrophic Lateral Sclerosis"
    assert rec.has_results == 1 and rec.race_reported == 1
    race = {r.demographic: r for r in rec.races if r.dimension == "race"}
    assert race["Black or African American"].count == 3
    assert race["Black or African American"].category == "black"
    assert race["White"].count == 148 and race["White"].category == "white"
    assert race["American Indian or Alaska Native"].count == 0     # a reported zero is kept
    assert race["More than one race"].category == "multiracial"
    assert race["Unknown or Not Reported"].category == "unknown"
    assert all(r.measure_title == "Race (NIH/OMB)" for r in race.values())
    ethnicity = {r.demographic: r for r in rec.races if r.dimension == "ethnicity"}
    assert ethnicity["Hispanic or Latino"].count == 3 and ethnicity["Hispanic or Latino"].category == "hispanic"
    assert ethnicity["Not Hispanic or Latino"].category == "not_hispanic"
    drugs = {d.drug: d for d in rec.drugs}
    assert drugs["sls-005"].role == "experimental" and drugs["sls-005"].intervention_type == "DRUG"
    assert drugs["trehalose"].role is None and drugs["trehalose"].intervention_type == "MESH"
    assert ("amyotrophic lateral sclerosis", "listed") in rec.conditions
    assert ("motor neuron disease", "mesh") in rec.conditions
    assert rec.source_url == "https://clinicaltrials.gov/study/NCT05136885"
    assert rec.fetched_at == FETCHED


def test_customized_race_table_and_age_cap():
    rec = ps.parse_study(CUSTOMIZED_STUDY, FETCHED)
    assert (rec.age_min, rec.age_max) == (40, 100)                  # "130 Years" is capped at 100
    assert rec.age_max_raw == "130 Years"
    assert rec.participants == 17160                                # baseline Total beats the enrollment count
    assert rec.drug == "Dapagliflozin 10 mg" and rec.drug_mesh == "Dapagliflozin"
    assert rec.condition == "Diabetes Mellitus, Non-Insulin-Dependent; High Risk for Cardiovascular Event"
    race = {r.demographic: r for r in rec.races if r.dimension == "race"}
    assert race["Native Hawaiian or other Pacific Islander"].category == "nhpi"
    assert race["American Indian or Alaska Native"].category == "aian"
    assert race["Other"].category == "other"
    assert all(r.measure_title == "Race/Ethnicity, Customized" for r in race.values())
    assert sum(r.count for r in race.values()) == 17160


def test_no_total_column_sums_arms_and_skips_na():
    baseline = {
        "groups": [{"id": "BG000", "title": "Drug"}, {"id": "BG001", "title": "Control"}],
        "measures": [_measure("Race (NIH/OMB)", {"White": [("BG000", "1,203"), ("BG001", "97")],
                                                 "Asian": [("BG000", "NA"), ("BG001", "NA")],
                                                 "Black or African American": [("BG000", "10"), ("BG001", "NA")]})],
    }
    rows = {r.demographic: r.count for r in ps.parse_race(baseline)}
    assert rows == {"White": 1300, "Black or African American": 10}


def test_percent_tables_not_collected_and_second_table_are_ignored():
    baseline = {
        "groups": GROUPS_WITH_TOTAL,
        "measures": [
            _measure("Race and Ethnicity Not Collected", {"Not collected": three("0", "0", "0")}),
            _measure("Race (NIH/OMB)", {"White": three("50", "50", "100")}, unit="percentage of participants", param="NUMBER"),
        ],
    }
    assert ps.parse_race(baseline) == []
    baseline["measures"].append(_measure("Race (NIH/OMB)", {"White": three("60", "40", "100")}))
    baseline["measures"].append(_measure("Race, Customized", {"Caucasian": three("1", "1", "2")}))
    assert [(r.demographic, r.count) for r in ps.parse_race(baseline)] == [("White", 100)]   # first usable table wins


def test_yes_no_categories_use_the_class_title():
    baseline = {"groups": GROUPS_WITH_TOTAL,
                "measures": [_measure("Ethnicity, Customized", {"Yes": three("4", "1", "5"), "No": three("116", "40", "156")},
                                      cls_title="Hispanic or Latino")]}
    rows = ps.parse_race(baseline)
    assert [(r.demographic, r.count, r.category, r.dimension) for r in rows] == [("Hispanic or Latino", 5, "hispanic", "ethnicity")]


@pytest.mark.parametrize("label, expected", [
    ("Black or African American", "black"), ("African American/African Heritage", "black"), ("BLACK OR AFRICAN AMERICAN", "black"),
    ("White", "white"), ("Caucasian", "white"), ("White - Arabic/North African Heritage", "white"), ("Non-Hispanic White", "white"),
    ("Asian", "asian"), ("Asian - East Asian Heritage", "asian"), ("Japanese", "asian"), ("Vietnamese", "asian"),
    ("Asian/Oriental", "asian"), ("Asian or Pacific Islander", "asian"),
    ("Native Hawaiian or Other Pacific Islander", "nhpi"), ("Pacific Islander", "nhpi"),
    ("American Indian or Alaska Native", "aian"), ("Native American", "aian"), ("American Indian/Alaskan Native", "aian"),
    ("More than one race", "multiracial"), ("Mixed Race", "multiracial"), ("Other/Mixed", "multiracial"),
    ("Hispanic or Latino", "hispanic"), ("Hispanic", "hispanic"),
    ("Not Hispanic or Latino", "not_hispanic"), ("Non-Hispanic", "not_hispanic"),
    ("Unknown or Not Reported", "unknown"), ("Not Permitted", "unknown"), ("Not collected per local regulations", "unknown"),
    ("Missing", "unknown"), ("NA", "unknown"),
    ("Other", "other"), ("Middle Eastern", "other"),
])
def test_map_race(label, expected):
    assert ps.map_race(label) == expected


@pytest.mark.parametrize("raw, expected", [
    ("18 Years", 18), ("6 Months", 0), ("23 Months", 1), ("130 Years", 130), ("2 Weeks", 0), ("N/A", None), (None, None), ("", None),
])
def test_parse_age_years(raw, expected):
    assert ps.parse_age_years(raw) == expected


def test_age_range_defaults_and_cap():
    assert ps.age_range(None, None) == (0, 100)
    assert ps.age_range("18 Years", None) == (18, 100)
    assert ps.age_range("6 Months", "17 Years") == (0, 17)
    assert ps.age_range("65 Years", "130 Years") == (65, 100)
    assert ps.age_range("18 Years", "12 Years") == (18, 18)        # inverted bounds never give max < min


def test_derive_sex():
    assert ps.derive_sex("ALL", 79, 82) == "Male and Female"
    assert ps.derive_sex("ALL", 40, 0) == "Female"                  # who enrolled beats who was eligible
    assert ps.derive_sex("FEMALE", None, None) == "Female"
    assert ps.derive_sex("MALE", None, None) == "Male"
    assert ps.derive_sex(None, None, None) == "Male and Female"


def test_parse_drugs_roles_and_exclusions():
    arms = {"armGroups": [{"label": "Lemborexant", "type": "EXPERIMENTAL"}, {"label": "Zolpidem", "type": "ACTIVE_COMPARATOR"},
                          {"label": "Placebo", "type": "PLACEBO_COMPARATOR"}],
            "interventions": [{"type": "DRUG", "name": "Lemborexant 5 mg", "armGroupLabels": ["Lemborexant"]},
                              {"type": "DRUG", "name": "Zolpidem ER 6.25 mg", "armGroupLabels": ["Zolpidem"]},
                              {"type": "DRUG", "name": "Zolpidem-matched placebo", "armGroupLabels": ["Placebo"]},
                              {"type": "DEVICE", "name": "Actigraph", "armGroupLabels": ["Lemborexant"]}]}
    drug, mesh, rows = ps.parse_drugs(arms, {"meshes": [{"term": "Zolpidem"}, {"term": "Lemborexant"}]})
    assert drug == "Lemborexant 5 mg"                               # the comparator is not what the study tested
    assert mesh == "Zolpidem; Lemborexant"
    roles = {r.drug: (r.role, r.intervention_type) for r in rows}
    assert roles["lemborexant 5 mg"] == ("experimental", "DRUG")
    assert roles["zolpidem er 6.25 mg"] == ("comparator", "DRUG")
    assert roles["zolpidem"] == (None, "MESH")
    assert "zolpidem-matched placebo" not in roles and "actigraph" not in roles


def test_single_arm_without_labels_is_experimental():
    drug, mesh, rows = ps.parse_drugs({"interventions": [{"type": "BIOLOGICAL", "name": "Vaccine X"}]}, None)
    assert drug == "Vaccine X" and mesh is None and rows[0].role == "experimental"


def test_study_without_results():
    study = {"protocolSection": {"identificationModule": {"nctId": "nct00000001"},
                                 "eligibilityModule": {"sex": "FEMALE", "minimumAge": "12 Years"},
                                 "conditionsModule": {"conditions": ["Breast Cancer"]}}}
    rec = ps.parse_study(study, FETCHED)
    assert rec.nct_id == "NCT00000001"
    assert rec.has_results == 0 and rec.race_reported == 0 and rec.races == []
    assert rec.sex == "Female" and (rec.age_min, rec.age_max) == (12, 100)
    assert rec.participants is None and rec.drug is None and rec.condition == "Breast Cancer"
    assert rec.conditions == [("breast cancer", "listed")]


def test_study_without_nct_id_is_rejected():
    with pytest.raises(ValueError):
        ps.parse_study({"protocolSection": {}}, FETCHED)
