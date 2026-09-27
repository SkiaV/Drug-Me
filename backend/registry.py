"""The one rule for "which harvested trials tested this drug", shared by the dashboard table and the report.

Before this module existed the table (build_table.py) and the report (report.py) each had their own rule and
disagreed for most drugs: the table counted double-dummy trials where the drug was only the comparator (the
1,006-person lemborexant trial for zolpidem, ROCKET-AF and ENGAGE AF for warfarin) because a "zolpidem-matching
placebo" in the experimental arm made the drug look experimental. The report matched free text and pulled in
combination products. Now both call select_trials().

Rule: a trial tests drug X when X is one of its MeSH intervention terms (ClinicalTrials.gov's own curation), or,
for a drug the registry has no MeSH row for, when an intervention names X or one of its aliases. Interventions
whose name says placebo/matching/dummy never count as X. X counts only if at least one intervention that IS X
sits in an EXPERIMENTAL arm; if the arm types are unknown, the trial is kept. Everything else is comparator-only.
"""
import re

import db
from harmonize import PLACEBO_LIKE

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    return _SLUG.sub("-", (name or "").lower()).strip("-")


def _patterns(names):
    return [re.compile(r"(?<![a-z0-9])" + re.escape(n.lower()) + r"(?![a-z0-9])") for n in names if n and n.strip()]


def _is_drug(intervention: dict, pats) -> bool:
    if PLACEBO_LIKE.search(intervention.get("name") or ""):
        return False
    hay = " ".join([intervention.get("name") or "", *(intervention.get("other_names") or [])]).lower()
    return any(p.search(hay) for p in pats)


def select_trials(candidates, name: str, aliases=(), require_mesh: bool = True):
    """-> (used, comparator_only). `name` is the registry (MeSH) term; `aliases` are RxNorm brands/synonyms."""
    names = [name, *aliases]
    pats = _patterns(names)
    used, comparator_only, seen = [], [], set()
    for t in candidates:
        if not t.get("nct") or t["nct"] in seen:
            continue
        seen.add(t["nct"])
        in_mesh = name.lower() in [m.lower() for m in (t.get("mesh_drugs") or [])]
        matched = [i for i in t.get("interventions", []) if _is_drug(i, pats)]
        if require_mesh and not in_mesh:
            continue
        if not in_mesh and not matched:
            continue
        types = {a for i in matched for a in (i.get("arm_types") or [])}
        experimental = "EXPERIMENTAL" in types or not types  # unknown arm types: keep the trial
        rec = dict(t, comparator_only=not experimental)
        (used if experimental else comparator_only).append(rec)
    return used, comparator_only


def trials_for_registry_drug(name: str, aliases=()):
    """Exactly the trials behind the dashboard row for `name` (a MeSH intervention term)."""
    return select_trials(db.trials_with_name(name), name, aliases, require_mesh=True)


def trials_for_typed_drug(search_names):
    """A drug without a registry row: free-text match on intervention names, same arm-type rule."""
    return select_trials(db.trials_for_names(search_names), search_names[0], search_names[1:], require_mesh=False)


_ROWS: dict = {}


def rows_by_slug() -> dict:
    """slug -> drug row, rebuilt whenever the harvest changes (its loaded_at stamp is the cache key)."""
    key = (db.get_meta("harvest") or {}).get("loaded_at")
    if _ROWS.get("key") != key or "by_slug" not in _ROWS:
        rows = db.drug_rows()
        _ROWS.update(key=key, by_slug={slug(r["drug"]): r for r in rows}, by_name={r["drug"].lower(): r for r in rows})
    return _ROWS["by_slug"]


def row_for_slug(drug_id: str):
    return rows_by_slug().get(drug_id)


def row_for_name(name: str):
    rows_by_slug()
    return _ROWS["by_name"].get((name or "").lower().strip())
