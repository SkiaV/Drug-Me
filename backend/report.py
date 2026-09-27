"""Assemble everything for one drug + one profile. This is the function the /api/report route wraps."""
import concurrent.futures as cf

import card
import ctgov
import db
import fda
import harmonize
import prevalence
import rxnorm
import scoring


def trials_for_drug(resolved: dict) -> tuple[list[dict], dict]:
    """Harmonized trials that test this drug, from the local harvest when present, else live from CT.gov."""
    names = resolved["search_names"]
    source = "harvest"
    candidates = db.trials_for_names([resolved["ingredient"]]) if db.trial_count() else []
    if not candidates:
        source = "live"
        candidates = [harmonize.parse_study(s) for s in ctgov.fetch_live(names)]
    used, comparator_only = [], []
    for rec in candidates:
        m = harmonize.trial_uses_drug(rec, names)
        if not m:
            continue
        rec = dict(rec, comparator_only=m["comparator_only"])
        (comparator_only if m["comparator_only"] else used).append(rec)
    return used, {"source": source, "found": len(used) + len(comparator_only), "comparator_only": len(comparator_only),
                  "comparator_only_ncts": [t["nct"] for t in comparator_only]}


def trial_summary(t: dict) -> dict:
    keys = ("nct", "title", "phases", "start_year", "completion_year", "sponsor", "sponsor_class", "sites_total", "sites_us",
            "countries", "elig_sex", "min_age", "max_age", "std_ages", "conditions", "disease_areas", "n_total", "sex",
            "age_cat", "age_mean", "race", "race_title", "ethnicity", "comparator_only")
    out = {k: t.get(k) for k in keys}
    out["url"] = f"https://clinicaltrials.gov/study/{t['nct']}"
    return out


def build(query: str, sex=None, age=None, race=None, ethnicity=None, include_faers=True) -> dict | None:
    resolved = rxnorm.resolve(query)
    if not resolved:
        return None
    rxcui, generic, brands = resolved["rxcui"], resolved["ingredient"], resolved["brands"]

    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        f_classes = ex.submit(rxnorm.classes, rxcui)
        f_trials = ex.submit(trials_for_drug, resolved)
        f_label = ex.submit(fda.label, rxcui, generic, brands[0] if brands else None)
        f_appr = ex.submit(fda.approval, generic, brands)
        f_faers = ex.submit(fda.faers, generic) if include_faers else None
        classes = f_classes.result()
        trials, meta = f_trials.result()
        lab = f_label.result()
        appr = f_appr.result()
        faers = f_faers.result() if f_faers else None

    indications = [m["name"] for m in classes["may_treat"]]
    if not indications and lab:
        indications = [lab["summary"]]
    # Disease denominator: the drug's own indications first; only when it has none, the trials' condition terms
    # (otherwise a single odd trial, e.g. codeine after bariatric surgery, would pick "obesity").
    prev = prevalence.disease_shares(indications or [c for t in trials for c in t.get("condition_meshes", [])][:5])
    agg = scoring.aggregate(trials, prev["shares"] if prev else None)
    keys = scoring.profile_groups(sex, age, race, ethnicity)
    sc = scoring.score(agg, keys)

    areas = {}
    for t in trials:
        for a in t.get("disease_areas", []):
            areas[a] = areas.get(a, 0) + 1
    report = {
        "drug": {
            "rxcui": rxcui, "ingredient": generic, "brands": brands, "matched_name": resolved["matched_name"],
            "is_combination": resolved["is_combination"], "ingredients": resolved["ingredients"],
            "class": classes["atc_label"], "epc": classes["epc"], "indications": indications[:6],
            "disease_area": max(areas, key=areas.get) if areas else None,
            "summary": (lab or {}).get("summary"),
        },
        "approval": appr,
        "evidence": {**{k: agg[k] for k in ("trials", "participants", "years", "industry_share", "us_site_share", "countries",
                                             "mean_age", "missing", "scoreable")}, **meta,
                     "note": ("Approval trials predate ClinicalTrials.gov results reporting (2008+); showing later trials."
                              if appr and appr["date"] < "2008-01-01" else None)},
        "profile": {"sex": sex, "age": age, "race": race, "ethnicity": ethnicity, "groups": keys},
        "denominators": {"population": "US Census 2020", "disease": prev},
        "groups": agg["groups"],
        "score": sc,
        "label_flags": lab,
        "faers": faers,
        "trials": [trial_summary(t) for t in trials],
        "method": {
            "metric": "participation-to-prevalence ratio (PPR) = group share of pooled participants / group share of reference population; 0.8-1.2 comparable (Scott et al., JACC 2018)",
            "score": "100 x coverage-weighted mean of min(PPR, 1) over the groups in your profile; coverage = share of participants from trials that reported the row",
            "limits": ["Trials report groups separately, never intersections (e.g. Black women over 65).",
                       "Race categories are harmonized from free text; 'other' collects labels we could not map.",
                       "Disease denominators use BRFSS-based crude prevalence in adults; race is compared within the non-Hispanic frame."],
        },
    }
    report["card"] = card.generate(report)
    return report
