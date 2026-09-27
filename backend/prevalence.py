"""Disease-population denominators from CDC Chronic Disease Indicators (data.cdc.gov, free, no key).

A group's expected share of the *disease* population is
    share_g = prevalence_g * population_g / sum over groups
which is what makes "older people get this disease more" a fair comparison instead of an excuse.
"""
import re

from clients import cdc

CDI = "hksd-2xuw"

# US Census 2020 populations (millions). Adult age bands are approximate (+/- 1M), race uses the
# non-Hispanic frame because CDI reports race that way.
POP = {
    "female": 168.8, "male": 162.7,
    "age18_44": 118.5, "age45_64": 83.4, "age65": 55.8,
    "white_nh": 191.7, "black_nh": 39.9, "asian_nh": 19.6, "aian_nh": 2.3, "nhpi_nh": 0.6,
    "multi_nh": 13.5, "hispanic": 62.1,
}
_RACE_STRATA = {
    "White, non-Hispanic": ("white", "white_nh"),
    "Black, non-Hispanic": ("black", "black_nh"),
    "Asian, non-Hispanic": ("asian", "asian_nh"),
    "American Indian or Alaska Native, non-Hispanic": ("aian", "aian_nh"),
    "Native Hawaiian or Other Pacific Islander, non-Hispanic": ("nhpi", "nhpi_nh"),
    "Multiracial, non-Hispanic": ("multiracial", "multi_nh"),
    "Hispanic": ("hispanic", "hispanic"),
}

# indication text (from RxClass may_treat or the label) -> CDI question. Order matters.
QUESTION_RULES = [
    (r"diabet", "Diabetes among adults"),
    (r"hypertens|blood pressure", "High blood pressure among adults"),
    (r"cholesterol|lipid|lipoprotein", "High cholesterol among adults who have been screened"),
    (r"asthma", "Current asthma among adults"),
    (r"obstructive|emphysema|chronic bronchitis", "Chronic obstructive pulmonary disease among adults"),
    (r"arthritis|osteoarthr|rheumat", "Arthritis among adults"),
    (r"depress", "Depression among adults"),
    (r"kidney|renal", "Chronic kidney disease among adults"),
    (r"obes", "Obesity among adults"),
    (r"insomnia|sleep", "Short sleep duration among adults"),  # proxy: no insomnia prevalence in CDI
    (r"smok|nicotine|tobacco", "Current cigarette smoking among adults"),
    (r"alcohol", "Binge drinking prevalence among adults"),
]

_question_list: list[str] | None = None


def cdi_questions() -> list[str]:
    global _question_list
    if _question_list is None:
        rows = cdc(CDI, **{"$select": "question", "$group": "question", "locationabbr": "US", "$limit": "500"})
        _question_list = [r["question"] for r in rows if r.get("question")]
    return _question_list


def question_for(indications: list[str]) -> tuple[str | None, str | None]:
    """-> (cdi question, the indication text that matched)"""
    questions = cdi_questions()
    for ind in indications:
        for rx, q in QUESTION_RULES:
            if re.search(rx, ind, re.I):
                if q in questions:
                    return q, ind
                # exact name drifted between CDI releases: take the closest question that shares the first word
                first = q.split()[0].lower()
                for cand in questions:
                    if cand.lower().startswith(first) and "among adults" in cand.lower():
                        return cand, ind
    return None, None


def _latest_rows(question: str, category: str) -> dict[str, float]:
    rows = cdc(CDI, question=question, locationabbr="US", stratificationcategory1=category,
               datavaluetype="Crude Prevalence", **{"$limit": "500"})
    if not rows:  # some questions only have age-adjusted values
        rows = cdc(CDI, question=question, locationabbr="US", stratificationcategory1=category, **{"$limit": "500"})
    latest = max((r.get("yearstart") or "0") for r in rows) if rows else None
    out = {}
    for r in rows:
        if r.get("yearstart") == latest and r.get("datavalue") not in (None, ""):
            try:
                out[r["stratification1"]] = float(r["datavalue"])
            except ValueError:
                pass
    return out, latest


def disease_shares(indications: list[str]) -> dict | None:
    """Expected share of the disease population for each group key, or None when no CDI match."""
    q, matched = question_for(indications)
    if not q:
        return None
    sex, year = _latest_rows(q, "Sex")
    age, _ = _latest_rows(q, "Age")
    race, _ = _latest_rows(q, "Race/Ethnicity")
    shares = {}
    if "Female" in sex and "Male" in sex:
        f, m = sex["Female"] * POP["female"], sex["Male"] * POP["male"]
        shares["female"], shares["male"] = f / (f + m), m / (f + m)
    if all(k in age for k in ("Age 18-44", "Age 45-64", "Age >=65")):
        w = {"age18_44": age["Age 18-44"] * POP["age18_44"], "age45_64": age["Age 45-64"] * POP["age45_64"],
             "age65": age["Age >=65"] * POP["age65"]}
        shares["age65"] = w["age65"] / sum(w.values())
    weights = {}
    for label, (key, popkey) in _RACE_STRATA.items():
        if label in race:
            weights[key] = race[label] * POP[popkey]
    if weights:
        total = sum(weights.values())
        if "hispanic" in weights:
            shares["hispanic"] = weights["hispanic"] / total
        nh_total = sum(v for k, v in weights.items() if k != "hispanic")
        for k, v in weights.items():
            if k != "hispanic" and nh_total:
                shares[k] = v / nh_total  # race compared within the non-Hispanic frame (approximation, documented)
    return {"question": q, "matched_indication": matched, "year": year, "shares": shares,
            "proxy": "sleep" in q.lower(),
            "source": "CDC Chronic Disease Indicators (BRFSS), data.cdc.gov/resource/hksd-2xuw"}
