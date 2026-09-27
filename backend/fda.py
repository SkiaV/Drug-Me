"""openFDA: the drug label (what FDA admits about your group), FAERS (who reports side effects), approval date."""
import concurrent.futures as cf
import datetime as dt
import re

from clients import openfda

# type -> (who-pattern, what-pattern, sections, exclude-pattern). A sentence must name the group AND say something
# about dose/exposure/risk/evidence, so "30 healthy male subjects" or lactation boilerplate doesn't get flagged.
_WHAT = re.compile(r"dos(e|ing)|clear(ance|ed)|exposure|concentration|higher|lower|greater|increase|decrease|differ|"
                   r"recommend|sufficient|risk|sensitiv|metaboli|not (been )?(established|studied)|should|contraindicat|"
                   r"impair|adjust|initiat", re.I)
FLAG_PATTERNS = {
    "sex": (re.compile(r"\b(women|woman|females?)\b", re.I), _WHAT,
            ("dosage_and_administration", "use_in_specific_populations", "clinical_pharmacology", "warnings_and_cautions", "boxed_warning"),
            re.compile(r"lactat|pregnan|breast|nursing|contracept|fertil", re.I)),
    "older_adults": (re.compile(r"\b(aged 65|65 years|over 65|elderly|geriatric|older (adults|patients|subjects))", re.I), _WHAT,
                     ("geriatric_use", "use_in_specific_populations", "dosage_and_administration", "boxed_warning", "warnings_and_cautions"),
                     None),
    "children": (re.compile(r"\b(pediatric|children|child\b|younger than|adolescen|infants?)", re.I), _WHAT,
                 ("boxed_warning", "pediatric_use", "warnings_and_cautions", "dosage_and_administration"), None),
    "ancestry_genetics": (re.compile(r"\b(ancestry|asian (patients|subjects|ancestry)|chinese|japanese|black (patients|subjects)|"
                                     r"african[- ]american|white (patients|subjects)|caucasian|hispanic|HLA-B|poor metaboli|"
                                     r"ultra-?rapid metaboli|G6PD|genotyp|polymorphism|allele)", re.I), _WHAT,
                          ("boxed_warning", "dosage_and_administration", "warnings_and_cautions", "warnings",
                           "clinical_pharmacology", "use_in_specific_populations"),
                          re.compile(r"\binhibitor|inducer|coadministr|concomitant", re.I)),
}
_HEADING = re.compile(r"^\s*(\d+(\.\d+)?\s+[A-Z][A-Z &/-]{3,}\s+)+")
_INSUFFICIENT_65 = re.compile(r"did not include sufficient numbers of (subjects|patients) aged 65", re.I)


def _sentences(text: str):
    text = re.sub(r"\s+", " ", text)
    # split at sentence ends and at embedded section headings ("... . 2.2 Special Populations ...")
    parts = re.split(r"(?<=[.!?\]])\s+(?=[A-Z(])|\s+(?=\d+\.\d+\s+[A-Z][a-z])", text)
    return [s.strip() for s in parts if len(s.strip()) > 20]


def _pick_label(results: list[dict], brand_hint: str | None):
    if not results:
        return None
    def key(r):
        b = [x.lower() for x in r.get("openfda", {}).get("brand_name", [])]
        hit = 1 if brand_hint and brand_hint.lower() in b else 0
        return (hit, r.get("effective_time", ""))
    return max(results, key=key)


def _labels(search: str) -> list[dict]:
    return openfda("label", search=search, sort="effective_time:desc", limit=3).get("results", [])


def label(rxcui: str | None, generic: str, brand_hint: str | None = None) -> dict | None:
    """The newest label for the drug, preferring the brand the user named. One small request in the common case
    (was: two requests of 25 whole labels, about 20 MB per drug). rxcui may be None when RxNorm did not know the name."""
    results = []
    bases = ([f'openfda.generic_name:"{generic}"'] if generic else []) + ([f'openfda.rxcui:"{rxcui}"'] if rxcui else [])
    for base in bases:
        if brand_hint:
            results = _labels(f'{base} AND openfda.brand_name:"{brand_hint}"')
            if results:
                break
        results = _labels(base)
        if results:
            break
    lab = _pick_label(results, brand_hint)
    if not lab:
        return None
    text = lambda sec: " ".join(lab.get(sec, []) or [])
    ind = text("indications_and_usage")
    ind = re.sub(r"^\s*1\s+INDICATIONS AND USAGE\s*", "", ind, flags=re.I)
    summary = next((s for s in _sentences(ind) if "indicated" in s.lower()), (_sentences(ind) or [""])[0])

    flags, seen = [], set()
    for ftype, (who, what, sections, exclude) in FLAG_PATTERNS.items():
        candidates = []
        for sec in sections:
            for s in _sentences(text(sec)):
                s = _HEADING.sub("", s).strip()
                if not who.search(s) or not what.search(s) or (exclude and exclude.search(s)):
                    continue
                if s[:120] in seen:
                    continue
                strength = len(who.findall(s)) + len(what.findall(s)) + (3 if sec in ("boxed_warning", "dosage_and_administration") else 0)
                candidates.append((strength, sec, s))
        for strength, sec, s in sorted(candidates, key=lambda c: -c[0])[:2]:  # two best sentences per type
            seen.add(s[:120])
            flags.append({"type": ftype, "section": sec, "quote": s[:400]})
    insufficient_65 = bool(_INSUFFICIENT_65.search(text("geriatric_use") + " " + text("use_in_specific_populations")))
    eff = lab.get("effective_time", "")
    return {
        "brand": (lab.get("openfda", {}).get("brand_name") or [None])[0],
        "generic": (lab.get("openfda", {}).get("generic_name") or [generic])[0],
        "manufacturer": (lab.get("openfda", {}).get("manufacturer_name") or [None])[0],
        "effective_time": f"{eff[:4]}-{eff[4:6]}-{eff[6:8]}" if len(eff) == 8 else eff,
        "set_id": lab.get("set_id"),
        "summary": summary[:400],
        "insufficient_65_boilerplate": insufficient_65,
        "flags": flags,
        "labels_found": len(results),
    }


def _sex_counts(search: str | None) -> dict:
    params = {"count": "patient.patientsex"}
    if search:
        params["search"] = search
    counts = {int(r["term"]): r["count"] for r in openfda("event", **params).get("results", [])}
    return {"female": counts.get(2, 0), "male": counts.get(1, 0), "unknown": counts.get(0, 0)}


def _share(c: dict):
    d = c["female"] + c["male"]
    return round(c["female"] / d, 4) if d else None


def faers(generic: str, years: int = 12) -> dict:
    q = f'patient.drug.openfda.generic_name:"{generic}"'
    this_year = dt.date.today().year
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        f_base, f_drug = ex.submit(_sex_counts, None), ex.submit(_sex_counts, q)
        base, drug = f_base.result(), f_drug.result()
        total = drug["female"] + drug["male"] + drug["unknown"]
        if total == 0:  # investigational / obscure names: no point spending 15 more requests on empty years
            return {"reports": 0, "female": 0, "male": 0, "female_share": None, "baseline_female_share": _share(base),
                    "ratio": None, "by_year": [], "reactions_skew_female": [], "reactions_skew_male": [],
                    "note": "No FAERS reports mention this generic name."}
        f_years = {y: ex.submit(_sex_counts, f'{q} AND receivedate:[{y}0101 TO {y}1231]')
                   for y in range(this_year - years, this_year + 1)}
        f_react = {key: ex.submit(openfda, "event", search=f"{q} AND patient.patientsex:{code}",
                                  count="patient.reaction.reactionmeddrapt.exact", limit=100)
                   for code, key in ((2, "female"), (1, "male"))}
        series = []
        for y, f in f_years.items():
            c = f.result()
            if c["female"] + c["male"]:
                series.append({"year": y, "female": c["female"], "male": c["male"]})
        reactions = {key: {r["term"]: r["count"] for r in f.result().get("results", [])} for key, f in f_react.items()}
    drug_share, base_share = _share(drug), _share(base)
    tw, tm = sum(reactions["female"].values()) or 1, sum(reactions["male"].values()) or 1
    skew = []
    for term, w in reactions["female"].items():
        m = reactions["male"].get(term)
        if m and w >= 100:
            skew.append({"reaction": term.title(), "female": w, "male": m, "ratio": round((w / tw) / (m / tm), 2)})
    skew.sort(key=lambda r: -r["ratio"])
    return {
        "reports": total,
        "female": drug["female"], "male": drug["male"],
        "female_share": drug_share,
        "baseline_female_share": base_share,
        "ratio": round(drug_share / base_share, 2) if drug_share and base_share else None,
        "by_year": series,
        "reactions_skew_female": skew[:8],
        "reactions_skew_male": sorted(skew, key=lambda r: r["ratio"])[:8],
        "note": "Voluntary reports; not incidence. Female share compared with the all-drugs baseline.",
    }


def approval(generic: str, brands: list[str]) -> dict | None:
    for name in (brands or [])[:3] + [generic]:
        field = "openfda.brand_name" if name in (brands or []) else "openfda.generic_name"
        data = openfda("drugsfda", search=f'{field}:"{name}"', limit=25)
        dates = []
        for app in data.get("results", []):
            for sub in app.get("submissions", []) or []:
                if sub.get("submission_type") == "ORIG" and sub.get("submission_status") == "AP" and sub.get("submission_status_date"):
                    d = sub["submission_status_date"]
                    dates.append((d, app.get("application_number"), name))
        if dates:
            d, appno, nm = min(dates)
            return {"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "application": appno, "matched_name": nm}
    return None
