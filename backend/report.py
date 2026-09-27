"""Assemble everything for one drug + one profile. This is the function the /api/v1 report route wraps.

Two layers, deliberately separated:
  * registry layer (SQLite, no network): which trials tested the drug, pooled demographics, PPR, score. The trial
    selection is registry.select_trials, the same rule the dashboard table uses, so a row and its report agree.
  * extras layer (network, cached twice): RxNorm brands and class, FDA label sentences, FAERS split, approval date,
    CDC prevalence. Each piece is fetched independently under one deadline; a failure or a timeout becomes a line
    in report["warnings"], never a 500. Pieces that succeed are stored in extras.sqlite, so the next report for
    the drug needs no network at all.
"""
import concurrent.futures as cf
import logging
import time

import card
import ctgov
import db
import fda
import harmonize
import prevalence
import registry
import rxnorm
import scoring
from clients import QuotaError
from config import CACHE_TTL_DAYS, REPORT_DEADLINE_S

log = logging.getLogger("drugme.report")

PIECES = ("classes", "label", "approval", "faers", "prevalence")
PIECE_LABEL = {
    "classes": "Drug class and indications (RxClass)",
    "label": "FDA label sentences (openFDA)",
    "approval": "Approval date (Drugs@FDA)",
    "faers": "Side-effect reports by sex (FAERS)",
    "prevalence": "Disease-population denominator (CDC)",
}
EMPTY_CLASSES = {"atc": [], "atc_label": None, "va": [], "epc": [], "may_treat": []}


def _harvest_age_days() -> float | None:
    loaded = (db.get_meta("harvest") or {}).get("loaded_at")
    try:
        return (time.time() - time.mktime(time.strptime(loaded, "%Y-%m-%d %H:%M"))) / 86400
    except (TypeError, ValueError):
        return None


def _meta(used, comparator_only, source="harvest"):
    return {"source": source, "found": len(used) + len(comparator_only), "comparator_only": len(comparator_only),
            "comparator_only_ncts": [t["nct"] for t in comparator_only]}


def trials_for_drug(resolved: dict) -> tuple[list[dict], dict]:
    """Trials for an RxNorm-resolved drug: its dashboard row's set when the registry has one, else a free-text
    match over intervention names, else (only when the harvest is stale) a live ClinicalTrials.gov query."""
    names = resolved["search_names"]
    row = registry.row_for_name(resolved["ingredient"])
    if row:
        used, cmp = registry.trials_for_registry_drug(row["drug"], aliases=names)
    else:
        used, cmp = registry.trials_for_typed_drug(names)
    if used or cmp:
        return used, _meta(used, cmp)
    age = _harvest_age_days()
    if db.trial_count() and age is not None and age <= 14:
        return [], _meta([], [])  # the harvest is complete for "Phase 3 with results"; live can add nothing yet
    try:
        live = [harmonize.parse_study(s) for s in ctgov.fetch_live(names, max_pages=2)]
        used, cmp = registry.select_trials(live, names[0], names[1:], require_mesh=False)
        return used, _meta(used, cmp, source="live")
    except Exception as exc:
        log.warning("live ClinicalTrials.gov query failed for %s: %s", names[0], exc)
        return [], _meta([], [])


def trial_summary(t: dict) -> dict:
    keys = ("nct", "title", "phases", "start_year", "completion_year", "sponsor", "sponsor_class", "sites_total", "sites_us",
            "countries", "elig_sex", "min_age", "max_age", "std_ages", "conditions", "disease_areas", "n_total", "sex",
            "age_cat", "age_mean", "race", "race_title", "ethnicity", "comparator_only")
    out = {k: t.get(k) for k in keys}
    out["url"] = f"https://clinicaltrials.gov/study/{t['nct']}"
    return out


def _why(exc: BaseException) -> str:
    if isinstance(exc, QuotaError):
        return "the service's request quota is spent for now"
    name = type(exc).__name__
    if "Connection" in name or "Timeout" in name or "RequestException" in name:
        return "network problem"
    return name


def _collect(futures: dict, out: dict, complete: set, warnings: list, deadline: float):
    if not futures:
        return
    done, _ = cf.wait(list(futures.values()), timeout=max(0.1, deadline - time.monotonic()))
    for piece, fut in futures.items():
        if fut in done:
            try:
                out[piece] = fut.result()
                complete.add(piece)
            except Exception as exc:
                log.warning("%s failed: %s", piece, exc)
                out[piece] = None
                warnings.append(f"{PIECE_LABEL[piece]} unavailable right now ({_why(exc)}).")
        else:  # the thread keeps running and fills the disk cache, so a reload usually has it
            out[piece] = None
            warnings.append(f"{PIECE_LABEL[piece]} took too long; reload the report in a moment.")


def fetch_extras(drug_key: str, rxcui: str | None, generic: str, brands: list[str], fallback_terms: list[str],
                 include_faers: bool, warnings: list) -> dict:
    """The network-derived pieces for one drug, from extras.sqlite when complete, else fetched under a deadline."""
    stored = db.get_extras(drug_key, max_age_days=CACHE_TTL_DAYS) or {}
    complete = set(stored.get("complete", []))
    out = {p: stored.get(p) for p in PIECES}
    wanted = ["classes", "label", "approval"] + (["faers"] if include_faers else [])
    missing = [p for p in wanted if p not in complete]
    if not missing and "prevalence" in complete:
        return out

    before = set(complete)
    deadline = time.monotonic() + REPORT_DEADLINE_S
    ex = cf.ThreadPoolExecutor(max_workers=5)
    try:
        futures = {}
        if "classes" in missing and rxcui:
            futures["classes"] = ex.submit(rxnorm.classes, rxcui)
        if "label" in missing:
            futures["label"] = ex.submit(fda.label, rxcui, generic, brands[0] if brands else None)
        if "approval" in missing:
            futures["approval"] = ex.submit(fda.approval, generic, brands)
        if "faers" in missing:
            futures["faers"] = ex.submit(fda.faers, generic)
        _collect(futures, out, complete, warnings, deadline)

        if "prevalence" not in complete and ("classes" in complete or not rxcui):
            # Disease denominator: the drug's own indications first; only when it has none, the trials' conditions
            # (otherwise a single odd trial, e.g. codeine after bariatric surgery, would pick "obesity").
            indications = [m["name"] for m in (out.get("classes") or {}).get("may_treat", [])]
            if not indications and out.get("label"):
                indications = [out["label"]["summary"]]
            _collect({"prevalence": ex.submit(prevalence.disease_shares, indications or fallback_terms[:5])},
                     out, complete, warnings, deadline)
    finally:
        ex.shutdown(wait=False)

    if complete - before:  # store only what succeeded; failures are retried next time, never frozen in
        db.set_extras(drug_key, {**{p: out.get(p) for p in PIECES}, "complete": sorted(complete)})
    return out


def build(query: str, sex=None, age=None, race=None, ethnicity=None, include_faers=True,
          registry_row: dict | None = None, with_card: bool = True) -> dict | None:
    """The report, or None when the name is neither a registry drug nor anything RxNorm knows."""
    warnings: list[str] = []
    resolved = None
    try:
        resolved = rxnorm.resolve(query)
    except Exception as exc:
        log.warning("RxNorm failed for %r: %s", query, exc)
        warnings.append(f"RxNorm unavailable ({_why(exc)}): brand names and drug class are missing.")
    if registry_row is None and resolved is None:
        registry_row = registry.row_for_name(query)
    if registry_row is None and resolved is None:
        return None
    if registry_row is None:
        registry_row = registry.row_for_name(resolved["ingredient"])  # a typed brand lands on its dashboard row

    if registry_row:
        drug_key = registry_row["drug"]
        trials, cmp = registry.trials_for_registry_drug(drug_key, aliases=resolved["search_names"] if resolved else ())
        meta = _meta(trials, cmp)
    else:
        drug_key = resolved["ingredient"]
        trials, meta = trials_for_drug(resolved)

    rxcui = resolved["rxcui"] if resolved else None
    generic = resolved["ingredient"] if resolved else drug_key  # the name openFDA and FAERS are asked about
    brands = resolved["brands"] if resolved else []
    fallback_terms = [c for t in trials for c in t.get("condition_meshes", [])]
    extras = fetch_extras(drug_key, rxcui, generic, brands, fallback_terms, include_faers, warnings)
    classes = extras.get("classes") or EMPTY_CLASSES
    lab, appr = extras.get("label"), extras.get("approval")
    faers = extras.get("faers") if include_faers else None
    prev = extras.get("prevalence")

    indications = [m["name"] for m in classes.get("may_treat", [])]
    if not indications and lab:
        indications = [lab["summary"]]
    agg = scoring.aggregate(trials, prev["shares"] if prev else None)
    keys = scoring.profile_groups(sex, age, race, ethnicity)
    sc = scoring.score(agg, keys)

    areas: dict[str, int] = {}
    for t in trials:
        for a in t.get("disease_areas", []):
            areas[a] = areas.get(a, 0) + 1
    report = {
        "drug": {
            "rxcui": rxcui, "ingredient": drug_key, "brands": brands,
            "matched_name": resolved["matched_name"] if resolved else drug_key,
            "is_combination": resolved["is_combination"] if resolved else False,
            "ingredients": resolved["ingredients"] if resolved else [{"rxcui": None, "name": drug_key}],
            "registry_name": registry_row["drug"] if registry_row else None,
            "class": classes.get("atc_label"), "epc": classes.get("epc", []), "indications": indications[:6],
            "disease_area": max(areas, key=areas.get) if areas else (registry_row or {}).get("disease_area"),
            "summary": (lab or {}).get("summary"),
        },
        "approval": appr,
        "evidence": {**{k: agg[k] for k in ("trials", "participants", "years", "industry_share", "us_site_share", "countries",
                                             "mean_age", "missing", "scoreable")}, **meta,
                     "note": ("Approval trials predate ClinicalTrials.gov results reporting (2008+); showing later trials."
                              if appr and appr.get("date", "9999") < "2008-01-01" else None)},
        "profile": {"sex": sex, "age": age, "race": race, "ethnicity": ethnicity, "groups": keys},
        "denominators": {"population": "US Census 2020", "disease": prev},
        "groups": agg["groups"],
        "score": sc,
        "label_flags": lab,
        "faers": faers,
        "trials": [trial_summary(t) for t in trials],
        "warnings": warnings,
        "method": {
            "metric": "participation-to-prevalence ratio (PPR) = group share of pooled participants / group share of reference population; 0.8-1.2 comparable (Scott et al., JACC 2018)",
            "score": "100 x coverage-weighted mean of min(PPR, 1) over the groups in your profile; coverage = share of participants from trials that reported the row",
            "limits": ["Trials report groups separately, never intersections (e.g. Black women over 65).",
                       "Race categories are harmonized from free text; 'other' collects labels we could not map.",
                       "Disease denominators use BRFSS-based crude prevalence in adults; race is compared within the non-Hispanic frame."],
        },
    }
    report["card"] = card.generate(report) if with_card else {"summary": "", "questions": [], "source": "skipped"}
    return report
