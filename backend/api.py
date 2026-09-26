"""Flask blueprint over studies.db.

Standalone:      python api.py                 ->  http://127.0.0.1:5001/api/studies/stats
In the team app  (next to the existing blueprint registration):
                 from api import bp as studies_bp
                 app.register_blueprint(studies_bp)

Routes (all GET, JSON; keys are the column names in schema.sql, plus a derived `source_url`):
  /api/studies              filters: drug, condition (substring), sex (M | F | MF, or Male / Female / both),
                            age (whole years), race (a study_races.category, or a label such as
                            "Black or African American"); limit (<= 200), offset
  /api/studies/<nct_id>     one study with its race composition and drug rows
  /api/studies/aggregate    same filters; pooled race composition, sex counts, age envelope
  /api/studies/stats        row counts and when the ingest ran

Filter values are canonicalized by validation.py (the same module the team app uses), so "female", "F" and
"Female" are one query. A bad value is a 400 that lists every problem. Unknown query parameters are ignored.
"""
from __future__ import annotations

import re

from flask import Blueprint, Flask, current_app, g, jsonify, request

import db
from config import DB_PATH
from validation import QUERY_PARAMS, QueryError, process_search_query

bp = Blueprint("studies", __name__, url_prefix="/api/studies")

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


def _error(message: str, status: int = 400, details: list[str] | None = None):
    code = {400: "bad_request", 404: "not_found"}.get(status, "error")
    body = {"code": code, "message": message}
    if details:
        body["details"] = details
    return jsonify({"error": body}), status


@bp.errorhandler(QueryError)
def bad_query(exc: QueryError):
    return _error(str(exc), 400, exc.errors)


def _filters() -> dict:
    """The canonical filter parameters that were given, and only those. Raises QueryError."""
    given = {key: request.args.getlist(key) for key in QUERY_PARAMS if key in request.args}
    return process_search_query(given)


@bp.get("")
def list_studies():
    filters = _filters()
    limit = max(1, min(request.args.get("limit", 50, type=int) or 50, MAX_LIMIT))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)
    rows, total = db.search(get_db(), limit=limit, offset=offset, **filters)
    return jsonify({"total": total, "limit": limit, "offset": offset, "filters": filters, "studies": rows})


@bp.get("/aggregate")
def aggregate():
    filters = _filters()
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
