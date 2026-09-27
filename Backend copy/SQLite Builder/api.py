"""Study-level query API over studies.db, the SQLite Builder's own store.

Standalone:   python api.py    ->  http://127.0.0.1:5001/search?drug=zolpidem&sex=F&age=67&race=black
The product API that the React app uses is ../../backend/app.py (/api/v1, port 5000). This one answers
study-level questions (one row per trial) and is what ingest.py's database is for.

Routes (GET, JSON):
  /search             filters: drug, condition (substring), sex (M | F | MF or Male / Female / both),
                      age (whole years), race (a study_races.category or a label such as
                      "Black or African American"); up to 10 studies with their race composition
  /truncated_search   the same filters, the first 3 studies without race rows: a light preview
Filter values are canonicalized by validation.py; a bad value is a 400 that lists every problem.
"""
# import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request
load_dotenv()

import db
import validation

# print(os.getenv(""))

app = Flask(__name__)
try:
    from flask_cors import CORS
    CORS(app, resources={r"/*": {"origins": "*"}})
except ImportError:                      # the API still works, just not from a browser on another origin
    pass


def _filters() -> dict:
    """Only the query parameters we filter on, canonicalized. Raises validation.QueryError."""
    given = {key: request.args.getlist(key) for key in validation.QUERY_PARAMS if key in request.args}
    return validation.process_search_query(given)


def _search(limit: int, with_races: bool):
    try:
        params = _filters()
    except validation.QueryError as exc:
        return jsonify({"error": {"code": "bad_request", "message": str(exc), "details": exc.errors}}), 400
    con = db.connect()
    try:
        if not con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'studies'").fetchone():
            return jsonify({"error": {"code": "no_database",
                                      "message": "studies.db is empty; run: python ingest.py"}}), 503
        studies, total = db.search(con, **params, limit=limit)
        if not with_races:
            for study in studies:
                study.pop("race_composition", None)
        return jsonify({"studies": studies, "total": total, "filters": params})
    finally:
        con.close()


@app.route('/')
def hello():
    return 'Hello, World!'

# Dashboard
@app.route('/dashboard')
def dashboard():
    return 'Dashboard Page (homepage)'

# Report
@app.route('/report')
def report():
    return 'Report Page (Big circle)'

# Truncated search: a 3-study preview without race rows
@app.route('/truncated_search')
def truncated_search():
    return _search(limit=3, with_races=False)

# Search
@app.route('/search')
def search():
    return _search(limit=10, with_races=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
