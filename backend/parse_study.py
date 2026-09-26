"""Turn one raw ClinicalTrials.gov API v2 study into the six fields of schema.sql.

Pure functions, no I/O, so every rule can be unit-tested against real study JSON (tests/test_parse_study.py).

Field by field:
  1. race composition  resultsSection.baselineCharacteristicsModule.measures[] whose title starts with "race"
                       or "ethnic": one (demographic label, head count) per category. The count is the "Total"
                       column; when the sponsor posted no Total column the arms are summed.
  2. age range         protocolSection.eligibilityModule.minimumAge / maximumAge ("18 Years", "6 Months", absent).
                       Missing lower bound -> 0, missing upper bound -> AGE_CAP, everything capped at AGE_CAP.
  3. sex               who actually enrolled (baseline "Sex: Female, Male" counts); protocol eligibility as fallback.
  4. drug              interventions of type DRUG / BIOLOGICAL / COMBINATION_PRODUCT in EXPERIMENTAL arms,
                       placebo-like names dropped; MeSH-normalized names kept alongside for clean matching.
  5. condition         protocolSection.conditionsModule.conditions (+ MeSH terms for matching).
  6. study             NCT number, title, status, phase, start date, source URL.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import AGE_CAP

# ----------------------------------------------------------------------------- record shapes


@dataclass
class RaceRow:
    demographic: str        # label exactly as the sponsor reported it
    count: int              # number of people
    category: str           # harmonized bucket, one of RACE_CATEGORIES
    dimension: str          # "race" or "ethnicity"
    measure_title: str      # which baseline table it came from


@dataclass
class DrugRow:
    drug: str                       # lower-cased name for matching
    role: str | None                # experimental / comparator / placebo / other; None for MeSH terms
    intervention_type: str          # DRUG / BIOLOGICAL / COMBINATION_PRODUCT / MESH


@dataclass
class StudyRecord:
    nct_id: str
    title: str | None
    drug: str | None
    drug_mesh: str | None
    condition: str | None
    sex: str
    age_min: int
    age_max: int
    eligible_sex: str | None
    age_min_raw: str | None
    age_max_raw: str | None
    female_count: int | None
    male_count: int | None
    participants: int | None
    phase: str | None
    status: str | None
    start_date: str | None
    has_results: int
    race_reported: int
    source_url: str
    fetched_at: str
    races: list[RaceRow] = field(default_factory=list)
    drugs: list[DrugRow] = field(default_factory=list)
    conditions: list[tuple[str, str]] = field(default_factory=list)     # (lower-cased name, "listed" | "mesh")


# ----------------------------------------------------------------------------- 1. race composition

RACE_CATEGORIES = ("white", "black", "asian", "aian", "nhpi", "multiracial", "hispanic", "not_hispanic", "other", "unknown")

# First match wins, so order matters. "white" precedes "black" so that "White - Arabic/North African Heritage"
# is white, and the race rules precede the ethnicity rules so that "Non-Hispanic White" is white.
_RACE_RULES = [
    (re.compile(r"unknown|not reported|not collected|not disclosed|not permitted|not specified|missing|refus|"
                r"declin|prefer not|n/?a\b", re.I), "unknown"),
    (re.compile(r"more than one|multi|two or more|mixed|multiple", re.I), "multiracial"),
    (re.compile(r"white|caucasian|european", re.I), "white"),
    (re.compile(r"black|african", re.I), "black"),
    (re.compile(r"asian.*pacific|pacific.*asian", re.I), "asian"),        # pre-1997 combined OMB category, >95% Asian
    (re.compile(r"hawaiian|pacific island", re.I), "nhpi"),
    (re.compile(r"american indian|alaska|native american|first nation|indigenous|aborigin", re.I), "aian"),
    (re.compile(r"asian|chinese|japanese|korean|filipino|vietnamese|indian|oriental", re.I), "asian"),
    (re.compile(r"not hispanic|non-?\s?hispanic|not latino|non-?\s?latino", re.I), "not_hispanic"),
    (re.compile(r"hispanic|latin", re.I), "hispanic"),
]


def map_race(label: str) -> str:
    """Free-text race or ethnicity label -> one of RACE_CATEGORIES. Anything unrecognized lands in "other"."""
    for rx, key in _RACE_RULES:
        if rx.search(label or ""):
            return key
    return "other"


def _int(value) -> int | None:
    """Counts arrive as strings ("161"), sometimes "1,203" or "NA"."""
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _total_group_id(baseline: dict) -> str | None:
    for group in baseline.get("groups") or []:
        if (group.get("title") or "").strip().lower().startswith("total"):
            return group.get("id")
    return None


def _count(measurements: list, total_id: str | None) -> int | None:
    """Head count in the Total column; when the sponsor posted no Total column, sum the arms."""
    if total_id:
        for m in measurements or []:
            if m.get("groupId") == total_id:
                return _int(m.get("value"))
        return None
    values = [_int(m.get("value")) for m in measurements or []]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _categories(measure: dict):
    """Yield (label, measurements) for every category. An untitled category inherits its class title;
    "Yes"/"No" categories under a titled class ("Hispanic or Latino": Yes/No) become the class label, "No" is dropped."""
    for cls in measure.get("classes") or []:
        cls_title = (cls.get("title") or "").strip()
        for cat in cls.get("categories") or []:
            cat_title = (cat.get("title") or "").strip()
            if cat_title.lower() == "no":
                continue
            label = cls_title if cat_title.lower() == "yes" else (cat_title or cls_title)
            if label:
                yield label, cat.get("measurements") or []


def _is_head_count(measure: dict) -> bool:
    unit = (measure.get("unitOfMeasure") or "").lower()
    return "percent" not in unit and "%" not in unit


def parse_race(baseline: dict | None) -> list[RaceRow]:
    """One RaceRow per reported label. The first race table and the first ethnicity table of a study are used."""
    if not baseline:
        return []
    total_id = _total_group_id(baseline)
    rows: list[RaceRow] = []
    seen_dimensions: set[str] = set()
    for measure in baseline.get("measures") or []:
        title = (measure.get("title") or "").strip()
        lowered = title.lower()
        if lowered.startswith("race"):
            dimension = "race"                      # includes "Race/Ethnicity, Customized"
        elif lowered.startswith("ethnic"):
            dimension = "ethnicity"
        else:
            continue
        # "Race and Ethnicity Not Collected", percentage tables, or a second table for the same dimension
        if "not collected" in lowered or not _is_head_count(measure) or dimension in seen_dimensions:
            continue
        counts: dict[str, int] = {}
        for label, measurements in _categories(measure):
            n = _count(measurements, total_id)
            if n is not None:
                counts[label] = counts.get(label, 0) + n
        if not counts:
            continue
        seen_dimensions.add(dimension)
        rows.extend(RaceRow(demographic=label, count=n, category=map_race(label), dimension=dimension,
                            measure_title=title) for label, n in counts.items())
    return rows


# ----------------------------------------------------------------------------- 3. sex, participants


def parse_sex_counts(baseline: dict | None) -> tuple[int | None, int | None]:
    """(female, male) head counts from the baseline "Sex: Female, Male" table, or (None, None)."""
    if not baseline:
        return None, None
    total_id = _total_group_id(baseline)
    for measure in baseline.get("measures") or []:
        lowered = (measure.get("title") or "").lower()
        if not (lowered.startswith("sex") or "gender" in lowered) or not _is_head_count(measure):
            continue
        female = male = None
        for label, measurements in _categories(measure):
            n = _count(measurements, total_id)
            if n is None:
                continue
            key = label.lower()
            if key.startswith(("female", "women", "woman")):
                female = (female or 0) + n
            elif key.startswith(("male", "men", "man")):
                male = (male or 0) + n
        if female is not None or male is not None:
            return female, male
    return None, None


def derive_sex(eligible_sex: str | None, female: int | None, male: int | None) -> str:
    """"Male", "Female" or "Male and Female": who was actually enrolled, else who the protocol allowed."""
    if (female or 0) > 0 or (male or 0) > 0:
        if female and male:
            return "Male and Female"
        return "Female" if female else "Male"
    return {"FEMALE": "Female", "MALE": "Male"}.get((eligible_sex or "").upper(), "Male and Female")


def parse_participants(baseline: dict | None, enrollment: int | None) -> int | None:
    """Participants in the baseline table (Total column), falling back to the enrollment count of the protocol."""
    if baseline:
        total_id = _total_group_id(baseline)
        for denom in baseline.get("denoms") or []:
            if (denom.get("units") or "").lower().startswith("participant"):
                n = _count(denom.get("counts") or [], total_id)
                if n:
                    return n
    return enrollment


# ----------------------------------------------------------------------------- 2. age range

_AGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(year|month|week|day|hour|minute)", re.I)
_UNITS_PER_YEAR = {"year": 1.0, "month": 12.0, "week": 52.0, "day": 365.0, "hour": 8760.0, "minute": 525600.0}


def parse_age_years(raw: str | None) -> int | None:
    """"18 Years" -> 18, "6 Months" -> 0, "130 Years" -> 130, "N/A" or None -> None."""
    m = _AGE_RE.search(raw or "")
    if not m:
        return None
    return int(float(m.group(1)) / _UNITS_PER_YEAR[m.group(2).lower()])


def age_range(min_raw: str | None, max_raw: str | None, cap: int = AGE_CAP) -> tuple[int, int]:
    """(lower, upper) in whole years. No lower bound -> 0; no upper bound -> cap; both capped at cap."""
    lo = parse_age_years(min_raw)
    hi = parse_age_years(max_raw)
    lo = 0 if lo is None else max(0, min(lo, cap))
    hi = cap if hi is None else max(0, min(hi, cap))
    return lo, max(lo, hi)


# ----------------------------------------------------------------------------- 4. drug

DRUG_TYPES = {"DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT"}
PLACEBO_LIKE = re.compile(r"placebo|dummy|sham|vehicle|matching|matched", re.I)
_ARM_ROLE = {"EXPERIMENTAL": "experimental", "ACTIVE_COMPARATOR": "comparator",
             "PLACEBO_COMPARATOR": "placebo", "SHAM_COMPARATOR": "placebo"}
_ROLE_RANK = ("experimental", "comparator", "placebo", "other")


def _clean(text) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_drugs(arms_module: dict | None, mesh_module: dict | None) -> tuple[str | None, str | None, list[DrugRow]]:
    """-> (drug string for the experimental arms, MeSH-normalized drug string, one DrugRow per distinct name)."""
    arms_module = arms_module or {}
    arm_role = {_clean(arm.get("label")).lower(): _ARM_ROLE.get(arm.get("type") or "", "other")
                for arm in arms_module.get("armGroups") or []}
    experimental: list[str] = []
    others: list[str] = []
    rows: list[DrugRow] = []
    seen: set[str] = set()
    for item in arms_module.get("interventions") or []:
        name = _clean(item.get("name"))
        itype = (item.get("type") or "").upper()
        if not name or itype not in DRUG_TYPES or PLACEBO_LIKE.search(name):
            continue
        roles = {arm_role.get(_clean(label).lower(), "other") for label in item.get("armGroupLabels") or []}
        # a single-arm study often lists no arm labels at all: that drug is the one being tested
        role = next((r for r in _ROLE_RANK if r in roles), "experimental") if roles else "experimental"
        (experimental if role == "experimental" else others).append(name)
        if name.lower() not in seen:
            seen.add(name.lower())
            rows.append(DrugRow(drug=name.lower(), role=role, intervention_type=itype))
    mesh_terms: list[str] = []
    for mesh in (mesh_module or {}).get("meshes") or []:
        term = _clean(mesh.get("term"))
        if term and term not in mesh_terms:
            mesh_terms.append(term)
            if term.lower() not in seen:
                seen.add(term.lower())
                rows.append(DrugRow(drug=term.lower(), role=None, intervention_type="MESH"))
    names = experimental or others
    return "; ".join(dict.fromkeys(names)) or None, "; ".join(mesh_terms) or None, rows


# ----------------------------------------------------------------------------- 5. condition


def parse_conditions(conditions_module: dict | None, mesh_module: dict | None) -> tuple[str | None, list[tuple[str, str]]]:
    """-> (condition string as listed by the sponsor, [(lower-cased name, "listed" | "mesh")])."""
    listed = [c for c in dict.fromkeys(_clean(c) for c in (conditions_module or {}).get("conditions") or []) if c]
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in listed:
        if name.lower() not in seen:
            seen.add(name.lower())
            rows.append((name.lower(), "listed"))
    for mesh in (mesh_module or {}).get("meshes") or []:
        term = _clean(mesh.get("term"))
        if term and term.lower() not in seen:
            seen.add(term.lower())
            rows.append((term.lower(), "mesh"))
    return "; ".join(listed) or None, rows


# ----------------------------------------------------------------------------- 6. study


def parse_study(study: dict, fetched_at: str) -> StudyRecord:
    """One raw API v2 study -> StudyRecord. Raises ValueError when the study has no NCT number."""
    protocol = study.get("protocolSection") or {}
    derived = study.get("derivedSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    eligibility = protocol.get("eligibilityModule") or {}
    results = study.get("resultsSection") or {}
    baseline = results.get("baselineCharacteristicsModule")

    nct_id = (ident.get("nctId") or "").strip().upper()
    if not nct_id:
        raise ValueError("study has no nctId")

    races = parse_race(baseline)
    female, male = parse_sex_counts(baseline)
    age_min, age_max = age_range(eligibility.get("minimumAge"), eligibility.get("maximumAge"))
    drug, drug_mesh, drug_rows = parse_drugs(protocol.get("armsInterventionsModule"),
                                             derived.get("interventionBrowseModule"))
    condition, condition_rows = parse_conditions(protocol.get("conditionsModule"),
                                                 derived.get("conditionBrowseModule"))
    enrollment = _int((design.get("enrollmentInfo") or {}).get("count"))

    return StudyRecord(
        nct_id=nct_id,
        title=ident.get("briefTitle"),
        drug=drug,
        drug_mesh=drug_mesh,
        condition=condition,
        sex=derive_sex(eligibility.get("sex"), female, male),
        age_min=age_min,
        age_max=age_max,
        eligible_sex=eligibility.get("sex"),
        age_min_raw=eligibility.get("minimumAge"),
        age_max_raw=eligibility.get("maximumAge"),
        female_count=female,
        male_count=male,
        participants=parse_participants(baseline, enrollment),
        phase="/".join(design.get("phases") or []) or None,
        status=status.get("overallStatus"),
        start_date=(status.get("startDateStruct") or {}).get("date"),
        has_results=int(bool(results)),
        race_reported=int(any(r.dimension == "race" for r in races)),
        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
        fetched_at=fetched_at,
        races=races,
        drugs=drug_rows,
        conditions=condition_rows,
    )
