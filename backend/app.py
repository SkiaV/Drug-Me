"""Drug Me API. JSON only; the React app in ../src talks to /api/v1, and Flask serves the built app from ../dist.

Run:  python app.py          (http://127.0.0.1:5000; PORT=... to change)
Docs: GET /api               (lists every route)
"""
import base64
import io
import json
import time

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import db
import fda
import report as report_mod
import rxnorm
from config import FRONTEND_DIST, GEMINI_API_KEY, GEMINI_MODEL, HOST, PORT

from api_v1 import bp as v1

app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.register_blueprint(v1)  # /api/v1/* — the contract the React app uses (camelCase, integer scores)

ROUTES = {
    "GET /api/health": "status + whether the registry harvest is loaded",
    "GET /api/v1/meta": "drugs reviewed, trials, average coverage, refresh date, disease areas, population + registry shares",
    "GET /api/v1/drugs?query&sort&order&limit&minParticipants&minTrials": "generalized drug summaries (the dashboard)",
    "GET /api/v1/search?age&sex&race&ethnicity&drug&indication&diseaseArea&location&sponsor&fromDate&toDate": "summaries re-scored for a profile",
    "GET /api/v1/drugs/<id>/report?age&sex&race&ethnicity": "the full report: score, groups, label sentences, FAERS, trials, questions",
    "GET /api/v1/suggest?q=amb": "autocomplete (RxNorm display names)",
    "GET /api/suggest?q=amb": "autocomplete names (RxNorm display names)",
    "GET /api/resolve?q=ambien": "brand/generic -> one ingredient rxcui + brands",
    "GET /api/report?q=ambien&sex=female&age=67&race=black&ethnicity=not_hispanic": "the whole report (snake_case, lower level)",
    "GET /api/drug/<rxcui>/trials": "harmonized trials only",
    "GET /api/drug/<rxcui>/label": "label flags only",
    "GET /api/drug/<rxcui>/faers": "adverse-event split by sex only",
    "GET /api/table?disease_area=&group=&min_participants=&min_trials=&sort=&order=&q=": "researcher table (one row per drug)",
    "GET /api/table/meta": "filter values for the table",
    "POST /api/resolve/photo (multipart 'image')": "Rx label photo -> drug name via Gemini (needs GEMINI_API_KEY)",
}


def _err(msg, code=400):
    return jsonify({"error": msg}), code


@app.errorhandler(Exception)
def _unhandled(exc):
    """Always JSON, never the HTML debugger page: the React app shows `error` to the user."""
    app.logger.exception("unhandled")
    return jsonify({"error": {"code": "server_error", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}}), 500


@app.get("/api")
def index():
    return jsonify({"name": "Drug Me API", "routes": ROUTES})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "harvested_trials": db.trial_count(), "table_rows": len(db.drug_rows()),
                    "gemini": bool(GEMINI_API_KEY), "time": time.time()})


@app.get("/api/suggest")
def suggest():
    return jsonify(rxnorm.suggest(request.args.get("q", ""), int(request.args.get("limit", 8))))


@app.get("/api/resolve")
def resolve():
    q = request.args.get("q", "")
    if not q:
        return _err("q is required")
    r = rxnorm.resolve(q)
    if not r:
        return jsonify({"error": f"no RxNorm match for '{q}'", "suggestions": rxnorm.suggest(q, 5)}), 404
    r["classes"] = rxnorm.classes(r["rxcui"])
    return jsonify(r)


def _profile_args():
    a = request.args
    age = a.get("age", type=int)
    sex = a.get("sex") or None
    race = a.get("race") or None
    eth = a.get("ethnicity") or None
    if sex and sex not in ("female", "male"):
        raise ValueError("sex must be female or male")
    if race and race not in ("white", "black", "asian", "aian", "nhpi", "multiracial"):
        raise ValueError("race must be one of white, black, asian, aian, nhpi, multiracial")
    if eth and eth not in ("hispanic", "not_hispanic"):
        raise ValueError("ethnicity must be hispanic or not_hispanic")
    return sex, age, race, eth


@app.get("/api/report")
def report():
    q = request.args.get("q", "")
    if not q:
        return _err("q (drug name) is required")
    try:
        sex, age, race, eth = _profile_args()
    except ValueError as e:
        return _err(str(e))
    rep = report_mod.build(q, sex, age, race, eth, include_faers=request.args.get("faers", "1") != "0")
    if not rep:
        sugg = rxnorm.suggest(q, 5)
        return jsonify({"error": f"No drug called '{q}' found." + (f" Did you mean: {', '.join(sugg)}?" if sugg else ""),
                        "suggestions": sugg}), 404
    return jsonify(rep)


def _resolved_from_rxcui(rxcui):
    props = rxnorm.rxnav(f"rxcui/{rxcui}/properties.json").get("properties")
    if not props:
        return None
    return rxnorm.resolve(props["name"])


@app.get("/api/drug/<rxcui>/trials")
def drug_trials(rxcui):
    r = _resolved_from_rxcui(rxcui)
    if not r:
        return _err("unknown rxcui", 404)
    trials, meta = report_mod.trials_for_drug(r)
    return jsonify({"drug": r, "meta": meta, "trials": [report_mod.trial_summary(t) for t in trials]})


@app.get("/api/drug/<rxcui>/label")
def drug_label(rxcui):
    r = _resolved_from_rxcui(rxcui)
    if not r:
        return _err("unknown rxcui", 404)
    return jsonify(fda.label(rxcui, r["ingredient"], r["brands"][0] if r["brands"] else None) or {})


@app.get("/api/drug/<rxcui>/faers")
def drug_faers(rxcui):
    r = _resolved_from_rxcui(rxcui)
    if not r:
        return _err("unknown rxcui", 404)
    return jsonify(fda.faers(r["ingredient"]))


@app.get("/api/table/meta")
def table_meta():
    rows = db.drug_rows()
    return jsonify({"rows": len(rows), "disease_areas": sorted({r["disease_area"] for r in rows if r.get("disease_area")}),
                    "groups": ["female", "age65", "under18", "white", "black", "asian", "aian", "nhpi", "multiracial", "hispanic"],
                    "harvest": db.get_meta("harvest")})


@app.get("/api/table")
def table():
    a = request.args
    rows = db.drug_rows()
    if not rows:
        return jsonify({"rows": [], "total": 0, "note": "run: python harvest.py && python build_table.py"})
    area, group, q = a.get("disease_area"), a.get("group"), (a.get("q") or "").lower()
    min_p, min_t = a.get("min_participants", 0, type=int), a.get("min_trials", 0, type=int)
    year_from = a.get("year_from", type=int)
    out = []
    for r in rows:
        if area and r.get("disease_area") != area:
            continue
        if q and q not in r["drug"]:
            continue
        if r["participants"] < min_p or r["trials"] < min_t:
            continue
        if year_from and (r["years"][0] or 0) < year_from:
            continue
        if group and (r["g"].get(group) or {}).get("share") is None and a.get("include_missing", "1") == "0":
            continue
        out.append(r)
    sort = a.get("sort", "score_pop")
    order = a.get("order", "asc")

    def sort_key(r):
        if sort.startswith("g."):  # e.g. g.black.ppr
            _, k, f = sort.split(".", 2)
            v = (r["g"].get(k) or {}).get(f)
        else:
            v = r.get(sort)
        return (v is None, v if v is not None else 0)
    out.sort(key=sort_key, reverse=(order == "desc"))
    limit, offset = a.get("limit", 200, type=int), a.get("offset", 0, type=int)
    return jsonify({"total": len(out), "rows": out[offset:offset + limit], "sort": sort, "order": order})


@app.post("/api/resolve/photo")
def resolve_photo():
    if not GEMINI_API_KEY:
        return _err("Photo reading needs GEMINI_API_KEY in backend/.env", 503)
    f = request.files.get("image")
    if not f:
        return _err("multipart field 'image' is required")
    from PIL import Image  # re-encode: strips EXIF (location, device); the image is never written to disk
    img = Image.open(f.stream).convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    prompt = ('This is a photo of a prescription or medicine label. Return JSON {"drug_name": string (the medication name only, '
              'brand or generic, no strength), "strength": string|null, "form": string|null, "confidence": 0-1}. '
              'If no drug is visible return {"drug_name": null}.')
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                          params={"key": GEMINI_API_KEY},
                          json={"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
                                "generationConfig": {"response_mime_type": "application/json", "temperature": 0}},
                          timeout=60)
        r.raise_for_status()
        parsed = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as exc:
        return _err(f"Gemini failed: {str(exc)[:200]}", 502)
    resolved = rxnorm.resolve(parsed.get("drug_name") or "") if parsed.get("drug_name") else None
    return jsonify({"read": parsed, "resolved": resolved,
                    "notice": "The photo was processed in memory only and not stored. Labels usually show your name; nothing from it is kept."})


# ---- serve the built React app if it exists (client-side routes fall back to index.html) ----
@app.get("/")
@app.get("/<path:path>")
def frontend(path="index.html"):
    if FRONTEND_DIST.exists():
        target = FRONTEND_DIST / path
        if target.is_file():
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify({"message": "API is running. Build the frontend (pnpm build at the repo root) or open /api.",
                    "routes": ROUTES})


if __name__ == "__main__":
    print(f"Drug Me API on http://{HOST}:{PORT}  (built app: {'found' if FRONTEND_DIST.exists() else 'not built yet'})")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
