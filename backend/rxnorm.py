"""RxNorm (drug name -> one ingredient) and RxClass (ingredient -> class + indications).

Why: users type "Ambien", trials say "zolpidem", FAERS says "ZOLPIDEM TARTRATE". RxNorm is the NIH
dictionary that collapses all of that to one ingredient rxcui (39993), and gives us the brand list back
so we can search ClinicalTrials.gov for every name at once.
"""
import difflib
import json
import re

from clients import rxnav
from config import DATA_DIR

_NAMES_FILE = DATA_DIR / "displaynames.json"
_names_cache: list[str] | None = None


def display_names() -> list[str]:
    """28k lowercase brand + ingredient names from RxNav, used for autocomplete and typo tolerance."""
    global _names_cache
    if _names_cache is None:
        if _NAMES_FILE.exists():
            _names_cache = json.loads(_NAMES_FILE.read_text(encoding="utf-8"))
        else:
            data = rxnav("displaynames.json")
            _names_cache = sorted(set(t.lower() for t in data["displayTermsList"]["term"]))
            _NAMES_FILE.write_text(json.dumps(_names_cache), encoding="utf-8")
    return _names_cache


def suggest(q: str, limit: int = 8) -> list[str]:
    q = q.lower().strip()
    if len(q) < 2:
        return []
    names = display_names()
    out = [n for n in names if n.startswith(q)][:limit]
    if len(out) < limit:
        out += [n for n in names if q in n and not n.startswith(q)][: limit - len(out)]
    if len(out) < 3:  # typo tolerance ("ambein" -> "ambien"); RxNav's own approximateTerm is worse at this
        close = [m for m in difflib.get_close_matches(q, names, n=limit * 2, cutoff=0.75) if m not in out]
        # transpositions (same letters, same length) first: "ambein" -> "ambien" beats "ambrein"
        close.sort(key=lambda m: (sorted(m) != sorted(q), abs(len(m) - len(q))))
        out += close
    return out[:limit]


def _concepts(rel_json) -> list[dict]:
    out = []
    for grp in rel_json.get("relatedGroup", {}).get("conceptGroup", []) or []:
        for c in grp.get("conceptProperties", []) or []:
            out.append({"rxcui": c["rxcui"], "name": c["name"], "tty": c["tty"]})
    return out


def _rxcui_for_name(name: str) -> str | None:
    data = rxnav("rxcui.json", name=name, search=2)  # search=2: normalized best match
    ids = data.get("idGroup", {}).get("rxnormId") or []
    return ids[0] if ids else None


def resolve(query: str) -> dict | None:
    """Return the ingredient for any typed name, or None.

    {"query", "matched_name", "rxcui" (ingredient), "ingredient", "ingredients": [...], "brands": [...],
     "is_combination": bool, "search_names": [ingredient + brands]}
    """
    q = query.strip()
    if not q:
        return None
    rxcui = _rxcui_for_name(q)
    matched = q
    if not rxcui:
        # Retired brands (Vicodin) are absent from rxcui.json but approximateTerm still knows them.
        # Accept a candidate only when its name really is the query; "ambein" -> "ambrein" must not pass.
        for c in rxnav("approximateTerm.json", term=q, maxEntries=5).get("approximateGroup", {}).get("candidate", []) or []:
            nm = (c.get("name") or "").lower()
            if nm and nm == q.lower():  # exact name only: "ambein" must not become "ambrein"
                rxcui, matched = c["rxcui"], c["name"]
                break
    if not rxcui:
        # Typos are NOT auto-corrected here ("ambein" is closer to "ambrein" than to "ambien" by edit distance);
        # the API returns 404 + suggestions and the UI asks "did you mean".
        return None

    props = rxnav(f"rxcui/{rxcui}/properties.json").get("properties") or {}
    tty, name = props.get("tty"), props.get("name", matched)

    if tty == "IN":
        ingredients = [{"rxcui": rxcui, "name": name}]
    else:
        ingredients = [c for c in _concepts(rxnav(f"rxcui/{rxcui}/related.json", tty="IN")) if c["tty"] == "IN"]
        if not ingredients:  # retired concepts (Vicodin) keep their ingredients only in the history record
            hist = rxnav(f"rxcui/{rxcui}/historystatus.json").get("rxcuiStatusHistory", {}) or {}
            for c in (hist.get("derivedConcepts", {}) or {}).get("ingredientConcept", []) or []:
                rid = c.get("ingredientRxcui") or c.get("ingredientRXCUI")
                if rid:
                    ingredients.append({"rxcui": rid, "name": c.get("ingredientName", ""), "tty": "IN"})
    if not ingredients:
        ingredients = [{"rxcui": rxcui, "name": name}]

    primary = ingredients[0]
    brands = sorted({c["name"] for c in _concepts(rxnav(f"rxcui/{primary['rxcui']}/related.json", tty="BN"))})
    return {
        "query": query,
        "matched_name": name,
        "matched_tty": tty,
        "rxcui": primary["rxcui"],
        "ingredient": primary["name"].lower(),
        "ingredients": [{"rxcui": i["rxcui"], "name": i["name"].lower()} for i in ingredients],
        "is_combination": len(ingredients) > 1,
        "brands": brands,
        "search_names": [primary["name"]] + brands,
    }


def classes(rxcui: str) -> dict:
    """Drug class + indications from RxClass. MED-RT 'may_treat' rows are MeSH diseases, which is the key
    we later use to find disease prevalence."""
    data = rxnav("rxclass/class/byRxcui.json", rxcui=rxcui)
    rows = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", []) or []
    atc, va, epc, may_treat, seen = [], [], [], [], set()
    for r in rows:
        c = r["rxclassMinConceptItem"]
        key = (c["classType"], c["classId"], r.get("rela"))
        if key in seen:
            continue
        seen.add(key)
        if c["classType"] == "ATC1-4":
            atc.append({"id": c["classId"], "name": c["className"]})
        elif c["classType"] == "VA":
            va.append(c["className"])
        elif c["classType"] == "EPC":
            epc.append(c["className"])
        elif c["classType"] == "DISEASE" and r.get("rela") == "may_treat":
            may_treat.append({"mesh_id": c["classId"], "name": c["className"]})
    # ATC codes get more specific as they get longer (N05 -> N05C -> N05CF); show the most specific
    atc.sort(key=lambda a: len(a["id"]))
    return {
        "atc": atc,
        "atc_label": (atc[-1]["name"] + f" (ATC {atc[-1]['id']})") if atc else (va[0].title() if va else None),
        "va": va,
        "epc": epc,
        "may_treat": may_treat,
    }


def clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())
