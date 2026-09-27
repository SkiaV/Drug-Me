"""Turn one raw ClinicalTrials.gov study into one flat, harmonized record.

This is the hard part of the whole project. Baseline tables are free-form: counts are strings (sometimes
"NA"), race categories are whatever the sponsor typed, age is sometimes a mean and sometimes bands.
Every rule here is deliberate and unit-tested in tests/test_harmonize.py.
"""
import re

# MeSH top-level disease branches (what CT.gov calls "ancestors" ends at one of these)
TOP_LEVEL_AREAS = {
    "Infections", "Neoplasms", "Musculoskeletal Diseases", "Digestive System Diseases",
    "Stomatognathic Diseases", "Respiratory Tract Diseases", "Otorhinolaryngologic Diseases",
    "Nervous System Diseases", "Eye Diseases", "Urogenital Diseases", "Male Urogenital Diseases",
    "Female Urogenital Diseases and Pregnancy Complications", "Cardiovascular Diseases",
    "Hemic and Lymphatic Diseases", "Congenital, Hereditary, and Neonatal Diseases and Abnormalities",
    "Skin and Connective Tissue Diseases", "Nutritional and Metabolic Diseases", "Endocrine System Diseases",
    "Immune System Diseases", "Disorders of Environmental Origin", "Pathological Conditions, Signs and Symptoms",
    "Occupational Diseases", "Chemically-Induced Disorders", "Wounds and Injuries", "Mental Disorders",
    "Behavior and Behavior Mechanisms",
}

RACE_KEYS = ["white", "black", "asian", "aian", "nhpi", "multiracial", "other"]

# interventions that are not the drug even when they carry its name
PLACEBO_LIKE = re.compile(r"placebo|matched|matching|dummy|sham|vehicle", re.I)

_RACE_RULES = [
    (re.compile(r"unknown|not reported|not collected|missing|refus|declin|prefer not|not specified|n/?a\b", re.I), "unknown"),
    (re.compile(r"more than one|multi|two or more|mixed|multiple", re.I), "multiracial"),
    (re.compile(r"hispanic|latin", re.I), "hispanic"),
    (re.compile(r"black|african", re.I), "black"),
    (re.compile(r"white|caucasian|european", re.I), "white"),
    # pre-1997 combined OMB category; Asian is >95% of it, so it counts as Asian (documented approximation)
    (re.compile(r"asian.*pacific|pacific.*asian", re.I), "asian"),
    (re.compile(r"hawaiian|pacific island", re.I), "nhpi"),
    (re.compile(r"american indian|alaska|native american|first nation|indigenous|aborigin", re.I), "aian"),
    (re.compile(r"asian|chinese|japanese|korean|filipino|vietnamese|indian|south asian|east asian", re.I), "asian"),
]


def map_race(label: str) -> str:
    """Free-text race label -> one of RACE_KEYS, 'hispanic' (an ethnicity that landed in a race table) or 'unknown'."""
    for rx, key in _RACE_RULES:
        if rx.search(label or ""):
            return key
    return "other"


def _int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def classify_age_band(label: str) -> str | None:
    """Map an age-category label to under18 / age18_64 / age65. Returns None if the band straddles 65 or 18."""
    s = (label or "").lower().replace("years", "").replace("year", "").strip()
    if re.search(r"unknown|not reported", s):
        return "unknown"
    if re.search(r"(<=|≤|<|under|less than|up to)\s*18\b", s) or re.search(r"\b(child|pediatric|adolescent)", s):
        return "under18"
    if re.search(r"(>=|≥|>|over|and over|and older|\+)\s*6[5-9]\b|\b6[5-9]\s*(\+|and over|and older|or older|or more)", s) \
            or re.search(r"(>=|≥)\s*([7-9]\d)\b", s):
        return "age65"
    if re.search(r"between\s*18\s*and\s*6[45]", s) or re.search(r"\b18\s*(-|to|–)\s*6[45]\b", s) or "adult" in s:
        return "age18_64"
    m = re.search(r"(\d{1,3})\s*(-|to|–)\s*(\d{1,3})", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(3))
        if hi < 18:
            return "under18"
        if lo >= 65:
            return "age65"
        if lo >= 18 and hi < 65:
            return "age18_64"
        return None
    m = re.search(r"(>=|≥|>|over)\s*(\d{1,3})", s)
    if m and int(m.group(2)) >= 65:
        return "age65"
    m = re.search(r"(<=|≤|<|under)\s*(\d{1,3})", s)
    if m and int(m.group(2)) <= 18:
        return "under18"
    return None


def _age_value(v: str | None) -> int | None:
    m = re.search(r"(\d+)", v or "")
    if not m:
        return None
    n = int(m.group(1))
    if "month" in (v or "").lower():
        return n // 12
    return n


def _total_group_id(baseline) -> str | None:
    groups = baseline.get("groups", []) or []
    for g in groups:
        if (g.get("title") or "").strip().lower().startswith("total"):
            return g["id"]
    return None


def _measure_value(measurements, total_id):
    """Count for the Total group; if the table has no Total group, sum the arms."""
    if total_id:
        for m in measurements:
            if m.get("groupId") == total_id:
                return _int(m.get("value"))
        return None
    vals = [_int(m.get("value")) for m in measurements]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _categories(measure):
    """Flatten classes/categories. A category without a title inherits its class title (common for sex)."""
    out = []
    for cls in measure.get("classes", []) or []:
        for cat in cls.get("categories", []) or []:
            title = cat.get("title") or cls.get("title") or ""
            out.append((title.strip(), cat.get("measurements", []) or []))
    return out


def parse_baseline(baseline: dict | None) -> dict:
    """-> {n_total, sex, age_cat, age_mean, race, ethnicity, race_title, has_*}"""
    out = {"n_total": None, "sex": None, "age_cat": None, "age_mean": None, "race": None, "ethnicity": None,
           "race_title": None, "age_title": None}
    if not baseline:
        return out
    total_id = _total_group_id(baseline)

    for d in baseline.get("denoms", []) or []:
        if (d.get("units") or "").lower().startswith("participant"):
            n = _measure_value(d.get("counts", []), total_id)
            if n:
                out["n_total"] = n
                break

    for measure in baseline.get("measures", []) or []:
        title = (measure.get("title") or "").strip()
        tl = title.lower()
        cats = _categories(measure)

        if tl.startswith("sex") or "gender" in tl:
            female = male = 0
            found = False
            for ct, ms in cats:
                v = _measure_value(ms, total_id)
                if v is None:
                    continue
                c = ct.lower()
                if c.startswith(("female", "women", "woman")):
                    female += v; found = True
                elif c.startswith(("male", "men", "man")):
                    male += v; found = True
            if found:
                out["sex"] = {"female": female, "male": male}

        elif tl.startswith("age"):
            if "continuous" in tl or measure.get("paramType") in ("MEAN", "MEDIAN"):
                for ct, ms in cats:
                    for m in ms:
                        if (not total_id or m.get("groupId") == total_id):
                            try:
                                val = float(m.get("value"))
                            except (TypeError, ValueError):
                                continue
                            if "month" in (measure.get("unitOfMeasure") or "").lower():
                                val /= 12
                            out["age_mean"] = round(val, 1)
                            break
                    if out["age_mean"] is not None:
                        break
                if out["age_mean"] is None and total_id is None:
                    # no Total group: participant-weighted mean across arms is not available; take mean of arms
                    vals = []
                    for ct, ms in cats:
                        for m in ms:
                            try:
                                vals.append(float(m.get("value")))
                            except (TypeError, ValueError):
                                pass
                    if vals:
                        out["age_mean"] = round(sum(vals) / len(vals), 1)
            else:
                bands = {"under18": 0, "age18_64": 0, "age65": 0}
                ok = bool(cats)
                for ct, ms in cats:
                    key = classify_age_band(ct)
                    v = _measure_value(ms, total_id)
                    if key is None:
                        ok = False
                        break
                    if key == "unknown" or v is None:
                        continue
                    bands[key] += v
                if ok and sum(bands.values()) > 0 and out["age_cat"] is None:
                    out["age_cat"] = bands
                    out["age_title"] = title

        elif tl.startswith("race") or tl.startswith("ethnic"):
            if "not collected" in tl:
                continue
            race = {k: 0 for k in RACE_KEYS}
            race_unknown = 0
            eth = {"hispanic": 0, "not_hispanic": 0}
            eth_found = race_found = False
            for ct, ms in cats:
                v = _measure_value(ms, total_id)
                if v is None:
                    continue
                key = map_race(ct)
                c = ct.lower()
                if key == "hispanic" or c.startswith("not hispanic") or "non-hispanic" in c or "non hispanic" in c:
                    if key == "hispanic" and not (c.startswith("not") or "non" in c.split("hispanic")[0]):
                        eth["hispanic"] += v
                    else:
                        eth["not_hispanic"] += v
                    eth_found = True
                    # In "Race/Ethnicity, Customized" tables Hispanic is often one of the race rows;
                    # it still belongs to the ethnicity dimension, not race.
                    continue
                if key == "unknown":
                    race_unknown += v
                    continue
                race[key] += v
                race_found = True
            if race_found and sum(race.values()) > 0 and out["race"] is None:
                race["unknown"] = race_unknown
                out["race"] = race
                out["race_title"] = title
            if eth_found and sum(eth.values()) > 0 and out["ethnicity"] is None:
                out["ethnicity"] = eth
    if out["n_total"] is None and out["sex"]:
        out["n_total"] = out["sex"]["female"] + out["sex"]["male"]
    return out


def _strip_prefix(name: str) -> str:
    return re.sub(r"^(drug|biological|other|device|procedure|dietary supplement|combination product|"
                  r"radiation|behavioral|genetic|diagnostic test):\s*", "", name or "", flags=re.I).strip().lower()


def parse_study(study: dict) -> dict:
    ps = study.get("protocolSection", {}) or {}
    ds = study.get("derivedSection", {}) or {}
    ident = ps.get("identificationModule", {}) or {}
    status = ps.get("statusModule", {}) or {}
    elig = ps.get("eligibilityModule", {}) or {}
    arms_mod = ps.get("armsInterventionsModule", {}) or {}
    locs = (ps.get("contactsLocationsModule", {}) or {}).get("locations", []) or []
    cond_browse = ds.get("conditionBrowseModule", {}) or {}
    intr_browse = ds.get("interventionBrowseModule", {}) or {}

    countries = sorted({(l.get("country") or "") for l in locs if l.get("country")})
    us_sites = sum(1 for l in locs if l.get("country") == "United States")

    ancestors = [a.get("term") for a in cond_browse.get("ancestors", []) or []]
    meshes = [m.get("term") for m in cond_browse.get("meshes", []) or []]
    areas = [a for a in ancestors if a in TOP_LEVEL_AREAS] or [m for m in meshes if m in TOP_LEVEL_AREAS]
    if not areas and ancestors:
        areas = [ancestors[-1]]

    # which interventions sit in which arm types
    arm_types: dict[str, set] = {}
    for arm in arms_mod.get("armGroups", []) or []:
        for iname in arm.get("interventionNames", []) or []:
            arm_types.setdefault(_strip_prefix(iname), set()).add(arm.get("type") or "UNKNOWN")
    interventions = []
    for i in arms_mod.get("interventions", []) or []:
        nm = (i.get("name") or "").strip().lower()
        if nm:
            interventions.append({"name": nm, "type": i.get("type"),
                                  "other_names": [o.lower() for o in (i.get("otherNames") or [])],
                                  "arm_types": sorted(arm_types.get(nm, set()))})
    mesh_drugs = [m.get("term", "").lower() for m in intr_browse.get("meshes", []) or []]

    start = (status.get("startDateStruct") or {}).get("date") or ""
    comp = (status.get("primaryCompletionDateStruct") or {}).get("date") or ""
    min_age, max_age = _age_value(elig.get("minimumAge")), _age_value(elig.get("maximumAge"))

    rec = {
        "nct": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "phases": (ps.get("designModule") or {}).get("phases", []),
        "start_year": int(start[:4]) if start[:4].isdigit() else None,
        "completion_year": int(comp[:4]) if comp[:4].isdigit() else None,
        "sponsor": ((ps.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name"),
        "sponsor_class": ((ps.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("class"),
        "sites_total": len(locs),
        "sites_us": us_sites,
        "countries": countries,
        "elig_sex": elig.get("sex") or "ALL",
        "min_age": min_age,
        "max_age": max_age,
        "std_ages": elig.get("stdAges", []) or [],
        "conditions": (ps.get("conditionsModule") or {}).get("conditions", []) or [],
        "condition_meshes": meshes,
        "disease_areas": areas,
        "interventions": interventions,
        "mesh_drugs": mesh_drugs,
    }
    rec.update(parse_baseline((study.get("resultsSection") or {}).get("baselineCharacteristicsModule")))
    rec["drug_names"] = sorted({*mesh_drugs, *(i["name"] for i in interventions),
                                *(o for i in interventions for o in i["other_names"])})
    return rec


def trial_uses_drug(rec: dict, names: list[str]) -> dict | None:
    """Does this trial test one of `names`? Returns {'experimental': bool, 'comparator_only': bool} or None."""
    targets = [n.lower() for n in names if n]
    if not targets:
        return None
    pats = [re.compile(r"\b" + re.escape(t) + r"\b") for t in targets]
    matched_types: set = set()
    matched = False
    for i in rec.get("interventions", []):
        if PLACEBO_LIKE.search(i["name"]):  # "zolpidem-matched placebo" is not zolpidem
            continue
        hay = " ".join([i["name"], *i.get("other_names", [])])
        if any(p.search(hay) for p in pats):
            matched = True
            matched_types.update(i.get("arm_types", []))
    if not matched and any(any(p.search(m) for p in pats) for m in rec.get("mesh_drugs", [])):
        matched = True
    if not matched:
        return None
    experimental = "EXPERIMENTAL" in matched_types or not matched_types
    return {"experimental": experimental, "comparator_only": bool(matched_types) and not experimental}
