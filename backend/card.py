"""The plain-language card. Rule-based by default; Gemini (if GEMINI_API_KEY is set) rewrites it but is
given ONLY our numbers and label quotes, so it cannot invent facts. Never medical advice: questions, not verdicts."""
import json

import requests

from config import GEMINI_API_KEY, GEMINI_MODEL

_LABELS = {"female": "women", "male": "men", "age65": "people 65 and over", "under18": "children",
           "white": "White participants", "black": "Black participants", "asian": "Asian participants",
           "aian": "American Indian or Alaska Native participants", "nhpi": "Native Hawaiian or Pacific Islander participants",
           "multiracial": "multiracial participants", "hispanic": "Hispanic or Latino participants"}


def _pct(x):
    return f"{round(100 * x)}%" if x is not None else "unknown"


def rule_based(report: dict) -> dict:
    drug = report["drug"]["ingredient"]
    ev = report["evidence"]
    prof = report["profile"]
    by_key = {g["key"]: g for g in report["groups"]}
    lines, questions = [], []

    if ev["trials"] == 0:
        lines.append(f"We found no Phase 3 trials with posted demographic results for {drug} in ClinicalTrials.gov.")
        if report.get("approval") and report["approval"].get("date", "9999") < "2008":
            lines.append("Its approval predates the registry's results reporting (2008), so the trials that got it approved are not visible here.")
        questions.append(f"Were the studies that approved {drug} done on people like me?")
    else:
        lines.append(f"{ev['trials']} Phase 3 trial(s) with posted results, {ev['participants']:,} participants, {ev['years'][0]}–{ev['years'][1]}.")
        for k in prof.get("groups", []):
            g = by_key.get(k)
            if not g:
                continue
            who = _LABELS.get(k, k)
            if g["band_pop"] == "na_by_design":
                lines.append(f"These trials were not designed to include {who}, so representation is not applicable.")
            elif g["trial_share"] is None:
                lines.append(f"None of the trials reported how many {who} took part ({g['trials_missing']} of {ev['trials']} trials left it out).")
                questions.append(f"Why don't the trials for {drug} report {who}?")
            else:
                exp = g["expected_disease"] if g["expected_disease"] is not None else g["expected_pop"]
                basis = "people with this condition" if g["expected_disease"] is not None else "the US population"
                lines.append(f"{_pct(g['trial_share'])} of participants were {who}, versus {_pct(exp)} of {basis} "
                             f"(ratio {g['ppr_disease'] if g['ppr_disease'] is not None else g['ppr_pop']}, {g['band_disease'] or g['band_pop']}).")
                if g["trials_design_excluded"]:
                    lines.append(f"{g['trials_design_excluded']} trial(s) excluded {who} by protocol.")
                ratio = g["ppr_disease"] if g["ppr_disease"] is not None else g["ppr_pop"]
                if ratio is not None and ratio < 0.8:
                    questions.append(f"The trials under-enrolled {who}. Is there evidence {drug} works the same for me?")
                if g["trials_design_excluded"] and g["trials_design_excluded"] == ev["trials"]:
                    questions.append(f"Every trial excluded {who} by design. What is the dosing for {who} based on?")
    for f in report.get("label_flags", {}).get("flags", [])[:3]:
        lines.append(f"The FDA label says: \"{f['quote'][:220]}\"")
    if report.get("label_flags", {}).get("insufficient_65_boilerplate"):
        questions.append("The label says studies did not include enough people over 65. Does my age change the dose?")
    fa = report.get("faers") or {}
    if fa.get("ratio") and fa["ratio"] >= 1.15:
        lines.append(f"Side-effect reports for {drug} skew female ({_pct(fa['female_share'])} vs {_pct(fa['baseline_female_share'])} for all drugs).")
        questions.append("Are there side effects that show up more in women that I should watch for?")
    questions.append("Are there dose adjustments for my sex, age, or ancestry?")
    return {"summary": " ".join(lines), "questions": questions[:5], "source": "rules"}


def generate(report: dict) -> dict:
    base = rule_based(report)
    if not GEMINI_API_KEY:
        return base
    facts = {"drug": report["drug"], "evidence": report["evidence"], "profile": report["profile"],
             "groups": [{k: g[k] for k in ("key", "label", "trial_share", "expected_pop", "expected_disease", "ppr_pop",
                                           "ppr_disease", "band_pop", "band_disease", "trials_missing", "trials_design_excluded")}
                        for g in report["groups"]],
             "label_flags": report.get("label_flags", {}).get("flags", []),
             "faers": {k: (report.get("faers") or {}).get(k) for k in ("female_share", "baseline_female_share", "ratio")},
             "draft": base}
    prompt = ("You write a short plain-language card for a patient about whether a drug's clinical trials included people "
              "like them. Use ONLY the facts in the JSON. Do not add medical claims, doses or advice. Do not invent numbers. "
              "Return JSON {\"summary\": string (<= 120 words, 8th-grade reading level), \"questions\": [3-5 questions the "
              "person can ask their doctor]}.\n\nFACTS:\n" + json.dumps(facts))
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}},
            timeout=40)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
        if isinstance(out.get("summary"), str) and isinstance(out.get("questions"), list):
            return {"summary": out["summary"], "questions": out["questions"][:5], "source": f"gemini:{GEMINI_MODEL}",
                    "grounded_on": ["groups", "label_flags", "faers"]}
    except Exception as exc:  # any failure -> rules version, never a blank card
        base["gemini_error"] = str(exc)[:200]
    return base
