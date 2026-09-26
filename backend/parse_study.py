"""Turn one raw ClinicalTrials.gov API v2 study into one `studies` row of schema.sql, plus its race and drug rows.

Pure functions, no I/O, so every rule can be unit-tested against real study JSON (tests/test_parse_study.py).

Scope, per schema.sql ("phase III, completed studies only, enforced at load time"): parse_study raises SkipStudy
for a study that is not COMPLETED, does not list PHASE3, or cannot fill a NOT NULL column (no non-placebo drug,
no condition, no participant count). ingest.py counts the reasons and carries on.

Column by column:
  drug, drug_mesh   interventions of type DRUG / BIOLOGICAL / COMBINATION_PRODUCT in EXPERIMENTAL arms, placebo-like
                    names dropped, each paired with its MeSH term from derivedSection.interventionBrowseModule.
                    A drug ClinicalTrials.gov gave no MeSH term keeps its own name, minus the dose, as drug_mesh.
  condition         protocolSection.conditionsModule.conditions, "; "-joined.
  sex               M / F / MF: who enrolled (baseline "Sex: Female, Male" counts), else who the protocol allowed.
  age_lower/upper   protocolSection.eligibilityModule.minimumAge / maximumAge in whole years; NULL when the
                    protocol sets no bound. Nothing is capped: "130 Years" is stored as 130.
  participants      baseline "Total" head count, else the protocol's enrollment count.
  study_races       resultsSection.baselineCharacteristicsModule.measures[] whose title starts with "race" or
                    "ethnic": one (demographic label, head count) per category, from the "Total" column, or the
                    arms summed when the sponsor posted no Total column.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import SCOPE_PHASE, SCOPE_STATUS

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
    drug: str               # the reported name(s) behind this MeSH term, lower-cased, "; "-joined
    drug_mesh: str          # MeSH term, or the dose-stripped reported name when ClinicalTrials.gov derived none


@dataclass
class StudyRecord:
    """One `studies` row; the field names are the column names in schema.sql."""
    nct_id: str
    drug: str
    drug_mesh: str
    condition: str
    sex: str                            # M / F / MF
    age_lower: int | None
    age_upper: int | None
    female_count: int | None
    male_count: int | None
    participants: int
    race_reported: int
    races: list[RaceRow] = field(default_factory=list)
    drugs: list[DrugRow] = field(default_factory=list)


class SkipStudy(ValueError):
    """The study is out of scope or cannot fill a NOT NULL column. `reason` is a short bucket for the ingest log."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


# ----------------------------------------------------------------------------- scope


def check_scope(status: str | None, phases: list[str] | None) -> None:
    """Raise SkipStudy unless the study is completed and lists Phase 3 (PHASE2/PHASE3 counts)."""
    if (status or "").upper() != SCOPE_STATUS:
        raise SkipStudy("status", status or "missing")
    if SCOPE_PHASE not in {(p or "").upper() for p in phases or []}:
        raise SkipStudy("phase", "/".join(phases or []) or "missing")


# ----------------------------------------------------------------------------- race composition

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


# ----------------------------------------------------------------------------- sex, participants


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
    """"M", "F" or "MF": who was actually enrolled, else who the protocol allowed."""
    if (female or 0) > 0 or (male or 0) > 0:
        if female and male:
            return "MF"
        return "F" if female else "M"
    return {"FEMALE": "F", "MALE": "M"}.get((eligible_sex or "").upper(), "MF")


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


# ----------------------------------------------------------------------------- age range

_AGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(year|month|week|day|hour|minute)", re.I)
_UNITS_PER_YEAR = {"year": 1.0, "month": 12.0, "week": 52.0, "day": 365.0, "hour": 8760.0, "minute": 525600.0}


def parse_age_years(raw: str | None) -> int | None:
    """"18 Years" -> 18, "6 Months" -> 0, "130 Years" -> 130, "N/A" or None -> None."""
    m = _AGE_RE.search(raw or "")
    if not m:
        return None
    return int(float(m.group(1)) / _UNITS_PER_YEAR[m.group(2).lower()])


def age_range(min_raw: str | None, max_raw: str | None) -> tuple[int | None, int | None]:
    """(lower, upper) in whole years, None where the protocol sets no bound. An upper bound below the lower
    bound (a data-entry slip) is raised to the lower bound so the schema's CHECK holds."""
    lo = parse_age_years(min_raw)
    hi = parse_age_years(max_raw)
    if lo is not None and hi is not None and hi < lo:
        hi = lo
    return lo, hi


# ----------------------------------------------------------------------------- drug

DRUG_TYPES = {"DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT"}
PLACEBO_LIKE = re.compile(r"placebo|dummy|sham|vehicle|matching|matched", re.I)
_ARM_ROLE = {"EXPERIMENTAL": "experimental", "ACTIVE_COMPARATOR": "comparator",
             "PLACEBO_COMPARATOR": "placebo", "SHAM_COMPARATOR": "placebo"}
_ROLE_RANK = ("experimental", "comparator", "placebo", "other")
# "10 mg", "75mg", "5%", "100 U/mL", "1 MMOLE/ML", "2 mg/kg": a number, a unit, an optional "per" unit
_DOSE = re.compile(r"(?<![a-z0-9])\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|g|kg|ml|l|%|iu|u|units?|mmole?)"
                   r"(?:\s*/\s*(?:ml|kg|l|day|dose|d|h|hr|m2))?(?![a-z0-9])", re.I)


def _clean(text) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_dose(name: str) -> str:
    """'TAK-438 10 mg' -> 'TAK-438', '75mg selumetinib' -> 'selumetinib'. Unchanged when nothing would be left."""
    stripped = _clean(_DOSE.sub(" ", name)).strip(" ,;:-/()")
    return stripped or name


def _contains(haystack: str, needle: str) -> bool:
    """Whole-word containment, so "iron" is not found inside "environmental"."""
    return len(needle) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def _matches(name: str, term: str) -> bool:
    """A MeSH term names an intervention when either string contains the other, dose aside."""
    a, b = strip_dose(name).lower(), term.lower()
    return _contains(a, b) or _contains(b, a)


def pair_mesh(names: list[str], mesh_terms: list[str], wanted: list[str]) -> dict[str, str]:
    """Reported drug name -> MeSH term, for every name in `wanted`.

    ClinicalTrials.gov lists a study's MeSH intervention terms as one flat list, not per intervention, so the
    pairing is by name: a term that appears in a drug name (or vice versa) is that drug's term, the most specific
    one when several fit ("Insulin Glargine" over "Insulin"). When exactly one non-placebo drug and exactly one
    term are left over they belong together: that is how "BAY94-9027" gets "Factor VIII". Anything still
    unpaired keeps its own name, minus the dose.
    """
    paired: dict[str, str] = {}
    used: set[str] = set()
    for name in names:
        hits = [term for term in mesh_terms if _matches(name, term)]
        if hits:
            paired[name] = max(hits, key=len)
            used.update(hits)
    left_names = [n for n in names if n not in paired]
    left_terms = [t for t in mesh_terms if t not in used]
    if len(left_names) == 1 and len(left_terms) == 1 and left_names[0] in wanted:
        paired[left_names[0]] = left_terms[0]
    return {name: paired.get(name) or strip_dose(name) for name in wanted}


def parse_drugs(arms_module: dict | None, mesh_module: dict | None) -> tuple[str, str, list[DrugRow]]:
    """-> (drug string for the experimental arms, the same drugs as MeSH names, one DrugRow per MeSH name).
    Raises SkipStudy when the study has no non-placebo drug."""
    arms_module = arms_module or {}
    arm_role = {_clean(arm.get("label")).lower(): _ARM_ROLE.get(arm.get("type") or "", "other")
                for arm in arms_module.get("armGroups") or []}
    names: list[str] = []                       # every non-placebo drug, in protocol order
    experimental: list[str] = []
    seen: set[str] = set()
    for item in arms_module.get("interventions") or []:
        name = _clean(item.get("name"))
        itype = (item.get("type") or "").upper()
        if not name or itype not in DRUG_TYPES or PLACEBO_LIKE.search(name) or name.lower() in seen:
            continue
        seen.add(name.lower())
        roles = {arm_role.get(_clean(label).lower(), "other") for label in item.get("armGroupLabels") or []}
        # a single-arm study often lists no arm labels at all: that drug is the one being tested
        role = next((r for r in _ROLE_RANK if r in roles), "experimental") if roles else "experimental"
        names.append(name)
        if role == "experimental":
            experimental.append(name)
    chosen = experimental or names              # a study whose drug arms are all comparators still tested those drugs
    if not chosen:
        raise SkipStudy("no drug")
    mesh_terms = [t for t in dict.fromkeys(_clean(m.get("term")) for m in (mesh_module or {}).get("meshes") or []) if t]
    pairing = pair_mesh(names, mesh_terms, chosen)
    by_term: dict[str, list[str]] = {}
    for name in chosen:
        by_term.setdefault(pairing[name], []).append(name.lower())
    rows = [DrugRow(drug="; ".join(raw), drug_mesh=term) for term, raw in by_term.items()]
    return "; ".join(chosen), "; ".join(by_term), rows


# ----------------------------------------------------------------------------- condition


def parse_condition(conditions_module: dict | None) -> str:
    """The sponsor's condition list, "; "-joined. Raises SkipStudy when there is none."""
    listed = [c for c in dict.fromkeys(_clean(c) for c in (conditions_module or {}).get("conditions") or []) if c]
    if not listed:
        raise SkipStudy("no condition")
    return "; ".join(listed)


# ----------------------------------------------------------------------------- one study


def parse_study(study: dict) -> StudyRecord:
    """One raw API v2 study -> StudyRecord. Raises SkipStudy (a ValueError) for a study that does not belong
    in the table: no NCT number, out of scope, or a NOT NULL column that cannot be filled."""
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
        raise SkipStudy("no nct id")
    check_scope(status.get("overallStatus"), design.get("phases"))

    drug, drug_mesh, drug_rows = parse_drugs(protocol.get("armsInterventionsModule"),
                                             derived.get("interventionBrowseModule"))
    condition = parse_condition(protocol.get("conditionsModule"))
    participants = parse_participants(baseline, _int((design.get("enrollmentInfo") or {}).get("count")))
    if participants is None:
        raise SkipStudy("no participant count")
    races = parse_race(baseline)
    female, male = parse_sex_counts(baseline)
    age_lower, age_upper = age_range(eligibility.get("minimumAge"), eligibility.get("maximumAge"))

    return StudyRecord(
        nct_id=nct_id,
        drug=drug,
        drug_mesh=drug_mesh,
        condition=condition,
        sex=derive_sex(eligibility.get("sex"), female, male),
        age_lower=age_lower,
        age_upper=age_upper,
        female_count=female,
        male_count=male,
        participants=participants,
        race_reported=int(any(r.dimension == "race" for r in races)),
        races=races,
        drugs=drug_rows,
    )
