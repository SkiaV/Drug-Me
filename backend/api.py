"""Flask blueprint over studies.db.

Standalone:      python api.py                 ->  http://127.0.0.1:5001/api/studies/stats
In the team app  (Drug_Me_Finder/backend/app.py, next to the existing blueprint registration):
                 from api import bp as studies_bp
                 app.register_blueprint(studies_bp)

Routes (all GET, JSON; keys are the column names in schema.sql):
  /api/studies              filters: drug, condition, sex (Male|Female), age (int), race (category),
                            has_results (0|1), limit (<=200), offset
  /api/studies/<nct_id>     one study with its race composition, drugs and conditions
  /api/studies/aggregate    same filters; pooled race composition, sex counts, age envelope
  /api/studies/stats        row counts and when the ingest ran
"""
from __future__ import annotations

import re

from flask import Blueprint, Flask, current_app, g, jsonify, request

import db
from config import DB_PATH
from parse_study import RACE_CATEGORIES

bp = Blueprint("studies", __name__, url_prefix="/api/studies")

SEX_VALUES = ("Male", "Female")
MAX_LIMIT = 200
_NCT = re.compile(r"^NCT\d{8}$")


def get_db():
    """One connection per request, closed by close_db below."""
    if "studies_db" not in g:
        g.studies_db = db.connect(current_app.config.get("STUDIES_DB_PATH", DB_PATH))
    return g.studies_db


@bp.teardown_app_request
def close_db(_exc):
    con = g.pop("studies_db", None)
    if con is not None:
        con.close()


def _error(message: str, status: int = 400):
    code = {400: "bad_request", 404: "not_found"}.get(status, "error")
    return jsonify({"error": {"code": code, "message": message}}), status


def _filters() -> dict:
    """Validate the shared query parameters. Raises ValueError with a message the client can show."""
    args = request.args
    sex = (args.get("sex") or "").strip().capitalize() or None
    if sex and sex not in SEX_VALUES:
        raise ValueError("sex must be Male or Female")
    race = (args.get("race") or "").strip().lower() or None
    if race and race not in RACE_CATEGORIES:
        raise ValueError(f"race must be one of: {', '.join(RACE_CATEGORIES)}")
    age = args.get("age", type=int)
    if args.get("age") and age is None:
        raise ValueError("age must be an integer")
    has_results = args.get("has_results", type=int)
    return {"drug": (args.get("drug") or "").strip() or None,
            "condition": (args.get("condition") or "").strip() or None,
            "sex": sex, "age": age, "race": race, "has_results": has_results}


@bp.get("")
def list_studies():
    try:
        filters = _filters()
    except ValueError as exc:
        return _error(str(exc))
    limit = max(1, min(request.args.get("limit", 50, type=int) or 50, MAX_LIMIT))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)
    rows, total = db.search(get_db(), limit=limit, offset=offset, **filters)
    return jsonify({"total": total, "limit": limit, "offset": offset, "filters": filters, "studies": rows})


@bp.get("/aggregate")
def aggregate():
    try:
        filters = _filters()
    except ValueError as exc:
        return _error(str(exc))
    return jsonify({"filters": filters, **db.aggregate(get_db(), **filters)})


@bp.get("/stats")
def stats():
    return jsonify(db.stats(get_db()))


@bp.get("/<nct_id>")
def one_study(nct_id: str):
    nct_id = nct_id.strip().upper()
    if not _NCT.match(nct_id):
        return _error("expected an NCT number such as NCT01730534", 404)
    row = db.study(get_db(), nct_id)
    if not row:
        return _error(f"no study {nct_id} in the database", 404)
    return jsonify(row)


def create_app(db_path=DB_PATH) -> Flask:
    """Standalone app for local testing. The team app registers `bp` on its own Flask instance instead."""
    app = Flask(__name__)
    app.config["STUDIES_DB_PATH"] = db_path
    app.register_blueprint(bp)
    try:
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    except ImportError:                      # optional here; the team app already configures CORS
        pass
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5001, debug=False)
