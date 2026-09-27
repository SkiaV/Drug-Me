"""/api/v1 — the contract the React app (Clinical Trial Representation prototype) was designed against.

Shapes follow API_CONTRACT.md (camelCase, integer 0-100 scores, tiers Limited/Developing/Strong,
errors as {"error": {"code", "message"}}) and add richer fields the report page renders when present.
"""
import re

from flask import Blueprint, jsonify, request

import db
import registry
import report as report_mod
import rxnorm
import scoring

bp = Blueprint("v1", __name__, url_prefix="/api/v1")

SEX_IN = {"female": "female", "male": "male"}
RACE_IN = {"american indian or alaska native": "aian", "asian": "asian", "black or african american": "black",
           "multiracial": "multiracial", "native hawaiian or pacific islander": "nhpi", "white": "white"}
ETH_IN = {"hispanic or latino": "hispanic", "not hispanic or latino": "not_hispanic"}
GROUP_LABEL = {
    "female": ("Sex", "Female participants"), "male": ("Sex", "Male participants"),
    "age65": ("Age", "Adults 65 and older"), "under18": ("Age", "Children and adolescents"),
    "white": ("Race", "White participants"), "black": ("Race", "Black participants"),
    "asian": ("Race", "Asian participants"), "aian": ("Race", "American Indian or Alaska Native participants"),
    "nhpi": ("Race", "Native Hawaiian or Pacific Islander participants"),
    "multiracial": ("Race", "Multiracial participants"), "hispanic": ("Ethnicity", "Hispanic or Latino participants"),
}
RACE_KEYS = ("black", "asian", "aian", "nhpi", "multiracial", "hispanic")


slug = registry.slug  # one definition for dashboard ids and report ids


def _err(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message}}), status


def tier(score):
    if score is None:
        return "Limited"
    return "Strong" if score >= 75 else "Developing" if score >= 55 else "Limited"


def _weighted(pairs):
    """pairs: [(ppr, weight)] -> 0-100 or None. min(ppr, 1) so over-representation never lifts the score."""
    pairs = [(p, w or 0) for p, w in pairs if p is not None]
    tot = sum(w for _, w in pairs)
    if not pairs or tot <= 0:
        return None
    return round(100 * sum(min(p, 1.0) * w for p, w in pairs) / tot)


def profile_keys(args):
    age = args.get("age", type=int)
    sex = SEX_IN.get((args.get("sex") or "").lower())
    race = RACE_IN.get((args.get("race") or "").lower())
    eth = ETH_IN.get((args.get("ethnicity") or "").lower())
    return scoring.profile_groups(sex, age, race, eth), {"age": age, "sex": args.get("sex") or "All or not specified",
                                                         "race": args.get("race") or "All or not specified",
                                                         "ethnicity": args.get("ethnicity") or "All or not specified"}, (sex, age, race, eth)


# ---------- rows from the harvest table ----------

def _components_from_row(g):
    return {
        "age": _weighted([(g["age65"]["ppr"], g["age65"]["coverage"])]),
        "sex": _weighted([(g["female"]["ppr"], g["female"]["coverage"]), (g["male"]["ppr"], g["male"]["coverage"])]),
        "race": _weighted([(g[k]["ppr"], g[k]["coverage"]) for k in RACE_KEYS]),
    }


def _row_summary(r, keys=None, updated=None):
    g = r["g"]
    if keys:
        score = _weighted([(g[k]["ppr"], g[k]["coverage"]) for k in keys if k in g])
    else:
        score = r.get("score_pop")
    least = r.get("least_represented")
    dim, grp = GROUP_LABEL.get(least, ("Race", "Not reported"))
    conds = r.get("conditions") or []
    return {
        "id": slug(r["drug"]),
        "name": r["drug"].capitalize(),
        "primaryUse": conds[0] if conds else (r.get("disease_area") or "Not classified"),
        "otherUses": conds[1:],
        "diseaseArea": r.get("disease_area"),
        "leastResearched": {"dimension": dim, "group": grp},
        "score": score,
        "tier": tier(score),
        "components": _components_from_row(g),
        "groups": {k: {"share": v["share"], "ppr": v["ppr"], "band": v["band"], "missingTrials": v["missing"]} for k, v in g.items()},
        "trialCount": r["trials"],
        "participantCount": r["participants"],
        "years": r.get("years"),
        "raceMissingShare": r.get("race_missing_share"),
        "designExcluded65Share": r.get("design_excl_65_share"),
        "usSiteShare": r.get("us_site_share"),
        "updatedAt": updated,
    }


def _sorted(items, sort, order):
    key = {"name": lambda d: d["name"].lower(), "trialCount": lambda d: d["trialCount"],
           "participants": lambda d: d["participantCount"]}.get(sort, lambda d: d["score"])
    # rows without a score always go last, whichever direction the scored rows are sorted in
    scored = [d for d in items if key(d) is not None]
    unscored = [d for d in items if key(d) is None]
    scored.sort(key=key, reverse=(order == "desc"))
    return scored + unscored


def _filter_rows(a):
    rows = db.drug_rows()
    q = (a.get("query") or a.get("drug") or "").lower().strip()
    ind = (a.get("indication") or "").lower().strip()
    sponsor = (a.get("sponsor") or "").lower().strip()
    loc = (a.get("location") or "").lower().strip()
    area = a.get("diseaseArea") or ""
    min_p = a.get("minParticipants", 500, type=int)
    min_t = a.get("minTrials", 2, type=int)
    y_from = (a.get("fromDate") or "")[:4]
    y_to = (a.get("toDate") or "")[:4]
    out = []
    for r in rows:
        if r["participants"] < min_p or r["trials"] < min_t:
            continue
        if q and q not in r["drug"] and not any(q in c.lower() for c in r.get("conditions", [])):
            continue
        if ind and not any(ind in c.lower() for c in r.get("conditions", [])) and ind not in (r.get("disease_area") or "").lower():
            continue
        if area and r.get("disease_area") != area:
            continue
        if sponsor and not any(sponsor in s.lower() for s in r.get("sponsors", [])):
            continue
        if loc and not any(loc in c.lower() for c in r.get("countries", [])):
            continue
        if y_from.isdigit() and (r["years"][1] or 0) < int(y_from):
            continue
        if y_to.isdigit() and (r["years"][0] or 9999) > int(y_to):
            continue
        out.append(r)
    return out


_REGISTRY_CACHE: dict = {}


def _registry_summary():
    """Participant-weighted shares across every harvested trial (home-page explainer). Computed once per harvest."""
    key = (db.get_meta("harvest") or {}).get("loaded_at")
    if _REGISTRY_CACHE.get("key") == key and "value" in _REGISTRY_CACHE:
        return _REGISTRY_CACHE["value"]
    trials = list(db.all_trials())
    value = None
    if trials:
        agg = scoring.aggregate(trials)
        shares = {g["key"]: g["trial_share"] for g in agg["groups"]}
        n = agg["trials"]
        value = {
            "trials": n,
            "participants": agg["participants"],
            "shares": {k: shares.get(k) for k in ("female", "age65", "black", "hispanic", "asian", "white")},
            "notReported": {k: round(v / n, 3) for k, v in agg["missing"].items()},
            "meanAge": agg["mean_age"],
        }
    _REGISTRY_CACHE.update(key=key, value=value)
    return value


@bp.get("/meta")
def meta():
    rows = db.drug_rows()
    h = db.get_meta("harvest") or {}
    scores = [r["score_pop"] for r in rows if r.get("score_pop") is not None and r["participants"] >= 500 and r["trials"] >= 2]
    return jsonify({
        "drugsReviewed": len(rows),
        "trials": h.get("trials") or db.trial_count(),
        "overallCoverage": round(sum(scores) / len(scores)) if scores else None,
        "refreshed": (h.get("loaded_at") or "")[:10] or None,
        "diseaseAreas": sorted({r["disease_area"] for r in rows if r.get("disease_area")}),
        "harvestFilter": h.get("filter"),
        "sampleData": not rows,
        # reference population (2020 Census; 65+ is the share of adults, as in scoring) and registry-wide shares
        "population": {"female": scoring.CENSUS["female"], "age65": round(scoring.CENSUS["age65_adults"], 4),
                       "black": scoring.CENSUS["black"], "hispanic": scoring.CENSUS["hispanic"],
                       "asian": scoring.CENSUS["asian"], "white": scoring.CENSUS["white"]},
        "registry": _registry_summary(),
    })


@bp.get("/suggest")
def suggest():
    return jsonify(rxnorm.suggest(request.args.get("q", ""), int(request.args.get("limit", 8))))


@bp.get("/drugs")
def drugs():
    a = request.args
    updated = (db.get_meta("harvest") or {}).get("loaded_at", "")[:10]
    items = [_row_summary(r, None, updated) for r in _filter_rows(a)]
    items = _sorted(items, a.get("sort", "score"), a.get("order", "desc"))
    limit = a.get("limit", 100, type=int)
    return jsonify(items[:limit])


@bp.get("/search")
def search():
    a = request.args
    if a.get("age") is None:
        return _err("missing_profile", "age is required")
    keys, _, _ = profile_keys(a)
    keys = [k for k in keys if k != "age18_64"]
    updated = (db.get_meta("harvest") or {}).get("loaded_at", "")[:10]
    items = [_row_summary(r, keys or None, updated) for r in _filter_rows(a)]
    items = _sorted(items, a.get("sort", "score"), a.get("order", "asc"))
    return jsonify(items[: a.get("limit", 100, type=int)])


# ---------- one drug, one profile ----------

def _strengths_and_gaps(rep):
    ev, by_key = rep["evidence"], {g["key"]: g for g in rep["groups"]}
    prof = rep["profile"]["groups"]
    strengths, gaps = [], []
    if ev["trials"]:
        strengths.append(f"{ev['trials']} Phase 3 trial(s) with posted results, {ev['participants']:,} participants pooled ({ev['years'][0]}–{ev['years'][1]}).")
    if ev.get("us_site_share") is not None:
        (strengths if ev["us_site_share"] >= 0.3 else gaps).append(f"{round(100 * ev['us_site_share'])}% of study sites were in the United States.")
    for k in prof or ["female", "age65", "black", "hispanic"]:
        g = by_key.get(k)
        if not g or k == "age18_64":
            continue
        who = GROUP_LABEL[k][1]
        band = g["band_disease"] or g["band_pop"]
        ppr = g["ppr_disease"] if g["ppr_disease"] is not None else g["ppr_pop"]
        if band == "na_by_design":
            continue
        if g["trial_share"] is None:
            gaps.append(f"{who}: not reported in {g['trials_missing']} of {ev['trials']} trials.")
        elif band in ("adequate", "over"):
            strengths.append(f"{who}: {round(100 * g['trial_share'])}% of participants, ratio {ppr} to the reference population.")
        else:
            gaps.append(f"{who}: {round(100 * g['trial_share'])}% of participants, ratio {ppr} — {band.replace('_', ' ')}-represented.")
        if g["trials_design_excluded"]:
            gaps.append(f"{g['trials_design_excluded']} trial(s) excluded {who.lower()} by protocol.")
    if ev["missing"]["race"]:
        gaps.append(f"{ev['missing']['race']} of {ev['trials']} trials reported no race data at all.")
    if ev["missing"]["age_categorical"] == ev["trials"] and ev["trials"]:
        gaps.append("No trial reported age in bands; only a mean age is available.")
    if ev.get("note"):
        gaps.append(ev["note"])
    return strengths[:6], gaps[:8]


def _label_note(label_missing: bool, warnings: list[str]) -> str:
    if not label_missing:
        return "No sentence in the current label singles out a sex, age or ancestry group for dosing or risk."
    if any("label" in w.lower() for w in warnings):
        return "The FDA label could not be fetched right now; reload the report to try again."
    return ("openFDA has no label under this name (biologics, investigational and discontinued products are often "
            "missing), so the label check could not run.")


@bp.get("/drugs/<drug_id>/report")
def drug_report(drug_id):
    a = request.args
    keys, profile_out, (sex, age, race, eth) = profile_keys(a)
    include_faers = a.get("faers", "1") != "0"
    # A dashboard row's id is the slug of its registry (MeSH) name: use that exact row, never a name guess, so the
    # report shows the same trials and numbers as the table. Anything else is a typed brand or generic name.
    row = registry.row_for_slug(drug_id) or registry.row_for_slug(registry.slug(drug_id))
    if row:
        name = row["drug"]
        rep = report_mod.build(name, sex, age, race, eth, include_faers=include_faers, registry_row=row)
    else:
        name = drug_id.replace("-", " ")
        rep = report_mod.build(name, sex, age, race, eth, include_faers=include_faers)
        if not rep and "-" in drug_id:  # hyphenated names (interleukin-2, co-trimoxazole) RxNorm knows as typed
            rep = report_mod.build(drug_id, sex, age, race, eth, include_faers=include_faers)
    if not rep:
        sugg = rxnorm.suggest(name, 5)
        hint = f" Did you mean: {', '.join(sugg)}?" if sugg else ""
        return _err("not_found", f"No drug called '{name}' found.{hint}", 404)
    ev, lab = rep["evidence"], rep.get("label_flags") or {}
    label_missing = rep.get("label_flags") is None
    by_key = {g["key"]: g for g in rep["groups"]}

    def ppr_of(k):
        g = by_key[k]
        return g["ppr_disease"] if g["ppr_disease"] is not None else g["ppr_pop"], g["coverage"]
    components = {
        "age": _weighted([ppr_of("age65")]),
        "sex": _weighted([ppr_of("female"), ppr_of("male")]),
        "race": _weighted([ppr_of(k) for k in RACE_KEYS]),
    }
    candidates = [(g["key"], g["ppr_disease"] if g["ppr_disease"] is not None else g["ppr_pop"]) for g in rep["groups"]
                  if g["key"] not in ("male", "under18") and (g["band_disease"] or g["band_pop"]) != "na_by_design"]
    reported = [(k, p) for k, p in candidates if p is not None]
    unreported = [k for k, p in candidates if p is None]
    least_key = min(reported, key=lambda kp: kp[1])[0] if reported else (unreported[0] if unreported else None)
    dim, grp = GROUP_LABEL.get(least_key, ("Race", "Not reported"))
    if least_key in unreported:
        grp += " (not reported)"

    gen_score = _weighted([ppr_of(k) for k in ("female", "age65", "black", "hispanic", "asian")])
    personalized = rep["score"]["disease"] if rep["denominators"]["disease"] else rep["score"]["population"]
    if personalized is None and rep["score"]["scoreable"]:
        personalized = gen_score
    indications = rep["drug"]["indications"] or []
    trial_conds = {}
    for t in rep["trials"]:
        for c in t.get("conditions") or []:
            trial_conds[c] = trial_conds.get(c, 0) + 1
    other = [c for c, _ in sorted(trial_conds.items(), key=lambda kv: -kv[1]) if c not in indications][:5]
    strengths, gaps = _strengths_and_gaps(rep)
    set_id = lab.get("set_id")
    updated = (db.get_meta("harvest") or {}).get("loaded_at", "")[:10]

    drug = {
        "id": slug(rep["drug"]["ingredient"]),
        "name": rep["drug"]["ingredient"].capitalize(),
        "brands": rep["drug"]["brands"],
        "matchedName": rep["drug"]["matched_name"],
        "isCombination": rep["drug"]["is_combination"],
        "ingredients": [i["name"] for i in rep["drug"]["ingredients"]],
        "drugClass": rep["drug"]["class"],
        "primaryUse": (indications[0] if indications else (other[0] if other else "Not classified")),
        "otherUses": indications[1:] + other,
        "diseaseArea": rep["drug"]["disease_area"],
        "leastResearched": {"dimension": dim, "group": grp},
        "score": gen_score,
        "tier": tier(gen_score),
        "components": components,
        "trialCount": ev["trials"],
        "participantCount": ev["participants"],
        "approvedOn": (rep.get("approval") or {}).get("date"),
        "updatedAt": updated,
    }
    evidence = []
    for t in rep["trials"]:
        sex_d = t.get("sex") or {}
        n_sex = (sex_d.get("female", 0) + sex_d.get("male", 0)) or None
        evidence.append({
            "id": t["nct"], "title": t.get("title"), "phase": "Phase 3" if "PHASE3" in (t.get("phases") or []) else ", ".join(t.get("phases") or []),
            "status": "Completed · results posted",
            "enrollment": t.get("n_total") or 0,
            "match": ("Comparator only" if t.get("comparator_only") else "Experimental arm"),
            "sourceUrl": t["url"],
            "years": [t.get("start_year"), t.get("completion_year")],
            "sponsor": t.get("sponsor"), "sponsorClass": t.get("sponsor_class"),
            "sitesTotal": t.get("sites_total"), "sitesUs": t.get("sites_us"),
            "agesAllowed": f"{t.get('min_age') if t.get('min_age') is not None else '?'}–{t.get('max_age') if t.get('max_age') is not None else '∞'}",
            "sexAllowed": t.get("elig_sex"),
            "femaleShare": round(sex_d.get("female", 0) / n_sex, 3) if n_sex else None,
            "age65Share": (round(t["age_cat"]["age65"] / max(1, sum(t["age_cat"].values())), 3) if t.get("age_cat") else None),
            "meanAge": t.get("age_mean"),
            "raceReported": bool(t.get("race")), "raceTitle": t.get("race_title"),
        })
    return jsonify({
        "drug": drug,
        "profile": {**profile_out, "groups": keys},
        "personalizedScore": personalized,
        "populationScore": rep["score"]["population"],
        "diseaseScore": rep["score"]["disease"],
        "scoreable": rep["score"]["scoreable"],
        "summary": rep["card"]["summary"],
        "questions": rep["card"]["questions"],
        "strengths": strengths,
        "gaps": gaps,
        "warnings": rep.get("warnings", []),
        "fdaContext": {
            "indication": rep["drug"]["summary"] or drug["primaryUse"],
            "labelUpdated": lab.get("effective_time"),
            "brand": lab.get("brand"),
            "note": (lab.get("flags") or [{}])[0].get("quote") if lab.get("flags")
                    else _label_note(label_missing, rep.get("warnings", [])),
            "flags": lab.get("flags") or [],
            "insufficient65": lab.get("insufficient_65_boilerplate", False),
            "sourceUrl": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}" if set_id else "https://open.fda.gov/apis/drug/label/",
        },
        "evidence": evidence,
        "details": {k: rep[k] for k in ("groups", "denominators", "evidence", "faers", "method", "approval")},
    })
