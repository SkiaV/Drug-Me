"""Build the researcher table: one row per drug (MeSH intervention term) across the whole harvest.

    python build_table.py
No external API calls: everything comes from the harvested trials, so it runs in seconds.
"""
import re
import time
from collections import defaultdict

import db
import scoring
from harmonize import PLACEBO_LIKE

# skip non-drug interventions that show up as MeSH terms
_SKIP = re.compile(r"placebo|saline|vehicle|standard of care|sodium chloride|water|vaccines?$|adjuvant|antigen|receptor|"
                   r"^antibodies|^immunoglobulin|^proteins?$|^peptides?$|"
                   r"(agonists|antagonists|inhibitors|agents|blockers|modulators|analogs|derivatives|hormones|steroids|"
                   r"combinations|preparations|acids|products|extracts|supplements)$", re.I)  # MeSH class terms, not drugs


def build(min_trials: int = 1) -> list[dict]:
    by_drug: dict[str, list] = defaultdict(list)
    for t in db.all_trials():
        names = t.get("mesh_drugs") or []
        for name in set(names):
            if name and not _SKIP.search(name):
                by_drug[name].append(t)
    rows = []
    for name, trials in by_drug.items():
        used = []
        for t in trials:
            types = set()
            for i in t.get("interventions", []):
                if name in i["name"] or any(name in o for o in i.get("other_names", [])):
                    types.update(i.get("arm_types", []))
            comparator_only = bool(types) and "EXPERIMENTAL" not in types
            if not comparator_only:
                used.append(t)
        if len(used) < min_trials:
            continue
        agg = scoring.aggregate(used)
        g = {}
        for grp in agg["groups"]:
            g[grp["key"]] = {"share": grp["trial_share"], "ppr": grp["ppr_pop"], "band": grp["band_pop"],
                             "coverage": grp["coverage"], "missing": grp["trials_missing"],
                             "design_excluded": grp["trials_design_excluded"]}
        reported = [(k, v["ppr"]) for k, v in g.items()
                    if v["ppr"] is not None and v["band"] != "na_by_design" and k not in ("male", "under18")]
        least = min(reported, key=lambda kv: kv[1])[0] if reported else None
        areas = defaultdict(int)
        for t in used:
            for a in t.get("disease_areas", []):
                areas[a] += 1
        conds = defaultdict(int)
        sponsors = defaultdict(int)
        countries = set()
        for t in used:
            for c in t.get("condition_meshes", []):
                conds[c] += 1
            if t.get("sponsor"):
                sponsors[t["sponsor"]] += 1
            countries.update(t.get("countries") or [])
        score_all = scoring.score(agg, ["female", "age65", "black", "hispanic", "asian"])
        rows.append({
            "drug": name,
            "disease_area": max(areas, key=areas.get) if areas else None,
            "conditions": [c for c, _ in sorted(conds.items(), key=lambda kv: -kv[1])[:6]],
            "sponsors": [s for s, _ in sorted(sponsors.items(), key=lambda kv: -kv[1])[:8]],
            "countries": sorted(countries),
            "trials": agg["trials"], "participants": agg["participants"], "years": agg["years"],
            "industry_share": agg["industry_share"], "us_site_share": agg["us_site_share"],
            "mean_age": agg["mean_age"],
            "race_missing_share": round(agg["missing"]["race"] / agg["trials"], 2),
            "age_cat_missing_share": round(agg["missing"]["age_categorical"] / agg["trials"], 2),
            "design_excl_65_share": round(g["age65"]["design_excluded"] / agg["trials"], 2),
            "least_represented": least,
            "score_pop": score_all["population"],
            "g": g,
            "ncts": [t["nct"] for t in used][:50],
        })
    return rows


if __name__ == "__main__":
    t0 = time.time()
    rows = build()
    db.store_drug_rows(rows)
    print(f"{len(rows)} drug rows built in {time.time() - t0:.1f}s")
