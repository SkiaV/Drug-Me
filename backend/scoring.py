"""Pool harmonized trials for one drug and score representation.

Metric: participation-to-prevalence ratio, PPR = share of pooled trial participants in a group divided by the
group's share of a reference population (Scott et al., JACC 2018; 0.8-1.2 = comparable). We compute it twice:
against the US population and, where we have prevalence data, against the population that has the disease.
"""
from config import MIN_PARTICIPANTS_TO_SCORE, MIN_TRIALS_TO_SCORE

# US Census 2020 (verified on census.gov). Race = "alone"; ethnicity is a separate question, as in trials.
CENSUS = {
    "total": 331_449_281,
    "female": 0.509, "male": 0.491,
    "age65_all": 0.168,                       # 55.8M of everyone
    "age65_adults": 55.8 / 258.3,             # trials enroll adults, so compare with the adult population
    "under18": 0.221,
    "white": 0.616, "black": 0.124, "asian": 0.060, "aian": 0.011, "nhpi": 0.002,
    "multiracial": 0.102, "other": 0.084,
    "hispanic": 0.187, "not_hispanic": 0.813,
}

GROUPS = [
    # key, label, dimension, population share
    ("female", "Women", "sex", CENSUS["female"]),
    ("male", "Men", "sex", CENSUS["male"]),
    ("age65", "Age 65 and over", "age", CENSUS["age65_adults"]),
    ("under18", "Under 18", "age", CENSUS["under18"]),
    ("white", "White", "race", CENSUS["white"]),
    ("black", "Black or African American", "race", CENSUS["black"]),
    ("asian", "Asian", "race", CENSUS["asian"]),
    ("aian", "American Indian or Alaska Native", "race", CENSUS["aian"]),
    ("nhpi", "Native Hawaiian or Pacific Islander", "race", CENSUS["nhpi"]),
    ("multiracial", "More than one race", "race", CENSUS["multiracial"]),
    ("hispanic", "Hispanic or Latino", "ethnicity", CENSUS["hispanic"]),
]
DIM_FIELD = {"sex": "sex", "age": "age_cat", "race": "race", "ethnicity": "ethnicity"}


def band(ppr):
    if ppr is None:
        return "not_reported"
    if ppr < 0.5:
        return "very_under"
    if ppr < 0.8:
        return "under"
    if ppr <= 1.2:
        return "adequate"
    return "over"


def _design_excluded(rec, key):
    if key == "age65":
        return rec.get("max_age") is not None and rec["max_age"] < 65
    if key == "under18":
        return rec.get("min_age") is not None and rec["min_age"] >= 18
    if key == "female":
        return rec.get("elig_sex") == "MALE"
    if key == "male":
        return rec.get("elig_sex") == "FEMALE"
    return False


def aggregate(trials: list[dict], disease_shares: dict | None = None) -> dict:
    """trials: harmonized records that test the drug. disease_shares: {group_key: expected share} or None."""
    disease_shares = disease_shares or {}
    n_trials = len(trials)
    participants = sum(t.get("n_total") or 0 for t in trials)
    groups = []
    for key, label, dim, pop_share in GROUPS:
        field = DIM_FIELD[dim]
        # A trial "reports" a group if its baseline table has the row, OR its protocol excluded the group
        # (max age 64 => we know the 65+ count is zero). Design exclusions are evidence, not missing data.
        count = denom = part_reporting = 0
        reporting = []
        for t in trials:
            if t.get(field):
                reporting.append(t)
                count += t[field].get(key, 0)
                denom += sum(v for k, v in t[field].items() if k != "unknown")
                part_reporting += t.get("n_total") or 0
            elif _design_excluded(t, key) and t.get("n_total"):
                reporting.append(t)
                denom += t["n_total"]
                part_reporting += t["n_total"]
        share = (count / denom) if denom else None
        exp_dis = disease_shares.get(key)
        ppr_pop = (share / pop_share) if share is not None and pop_share else None
        ppr_dis = (share / exp_dis) if share is not None and exp_dis else None
        # "Not applicable" only when the condition itself is sex-specific (prevalence 0) or every trial was
        # single-sex by protocol. Every trial excluding older adults is NOT "n/a": it is the finding (PPR 0).
        na_by_design = (exp_dis == 0) or (
            key in ("female", "male") and n_trials > 0 and all(_design_excluded(t, key) for t in trials))
        g = {
            "key": key, "label": label, "dimension": dim,
            "count": count if reporting else None,
            "trial_share": round(share, 4) if share is not None else None,
            "expected_pop": pop_share,
            "expected_disease": round(exp_dis, 4) if exp_dis is not None else None,
            "ppr_pop": round(ppr_pop, 2) if ppr_pop is not None else None,
            "ppr_disease": round(ppr_dis, 2) if ppr_dis is not None else None,
            "band_pop": "na_by_design" if na_by_design else band(ppr_pop),
            "band_disease": "na_by_design" if na_by_design else (band(ppr_dis) if exp_dis else None),
            "coverage": round(part_reporting / participants, 3) if participants else 0.0,
            "trials_reporting": len(reporting),
            "trials_missing": n_trials - len(reporting),
            "trials_design_excluded": sum(1 for t in trials if _design_excluded(t, key)),
        }
        groups.append(g)

    mean_ages = [(t["age_mean"], t.get("n_total") or 1) for t in trials if t.get("age_mean") is not None]
    weighted_mean_age = round(sum(a * n for a, n in mean_ages) / sum(n for _, n in mean_ages), 1) if mean_ages else None

    return {
        "trials": n_trials,
        "participants": participants,
        "years": [min((t["start_year"] for t in trials if t.get("start_year")), default=None),
                  max((t["completion_year"] for t in trials if t.get("completion_year")), default=None)],
        "industry_share": round(sum(1 for t in trials if t.get("sponsor_class") == "INDUSTRY") / n_trials, 2) if n_trials else None,
        "us_site_share": round(sum(t.get("sites_us", 0) for t in trials) / max(1, sum(t.get("sites_total", 0) for t in trials)), 2) if n_trials else None,
        "countries": len({c for t in trials for c in t.get("countries", [])}),
        "mean_age": weighted_mean_age,
        "missing": {
            "race": sum(1 for t in trials if not t.get("race")),
            "ethnicity": sum(1 for t in trials if not t.get("ethnicity")),
            "age_categorical": sum(1 for t in trials if not t.get("age_cat")),
            "sex": sum(1 for t in trials if not t.get("sex")),
        },
        "groups": groups,
        "scoreable": n_trials >= MIN_TRIALS_TO_SCORE and participants >= MIN_PARTICIPANTS_TO_SCORE,
    }


def profile_groups(sex: str | None, age: int | None, race: str | None, ethnicity: str | None) -> list[str]:
    keys = []
    if sex in ("female", "male"):
        keys.append(sex)
    if age is not None:
        keys.append("under18" if age < 18 else ("age65" if age >= 65 else "age18_64"))
    if race in ("white", "black", "asian", "aian", "nhpi", "multiracial"):
        keys.append(race)
    if ethnicity == "hispanic":
        keys.append("hispanic")
    return keys


def score(agg: dict, keys: list[str]) -> dict:
    """Coverage-weighted mean of min(PPR, 1) over the profile's groups, 0-100, both denominators."""
    by_key = {g["key"]: g for g in agg["groups"]}
    out = {"population": None, "disease": None, "groups_used": [], "groups_missing": [], "scoreable": agg["scoreable"]}
    if not agg["scoreable"]:
        return out
    num_p = den_p = num_d = den_d = 0.0
    for k in keys:
        g = by_key.get(k)
        if k == "age18_64" or g is None:
            continue  # 18-64 is the default trial population; nothing to under-represent
        if g["trial_share"] is None or g["band_pop"] == "na_by_design":
            out["groups_missing"].append(k)
            continue
        w = g["coverage"] or 0
        num_p += min(g["ppr_pop"], 1.0) * w
        den_p += w
        ppr_d = g["ppr_disease"] if g["ppr_disease"] is not None else g["ppr_pop"]
        num_d += min(ppr_d, 1.0) * w
        den_d += w
        out["groups_used"].append(k)
    if den_p:
        out["population"] = round(100 * num_p / den_p)
        out["disease"] = round(100 * num_d / den_d)
    return out
