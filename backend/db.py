"""SQLite layer: create the schema, load StudyRecords, and answer the queries the Flask API needs.

stdlib sqlite3 only. To move to Postgres later, replace connect() and the "?" placeholders; nothing above
this file needs to change.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3

from config import BASE_DIR, DB_PATH
from parse_study import StudyRecord

SCHEMA_PATH = BASE_DIR / "schema.sql"

STUDY_COLUMNS = ("nct_id", "title", "drug", "drug_mesh", "condition", "sex", "age_min", "age_max",
                 "eligible_sex", "age_min_raw", "age_max_raw", "female_count", "male_count", "participants",
                 "phase", "status", "start_date", "has_results", "race_reported", "source_url", "fetched_at")

_UPSERT_STUDY = (
    f"INSERT INTO studies ({', '.join(STUDY_COLUMNS)}) VALUES ({', '.join('?' for _ in STUDY_COLUMNS)}) "
    "ON CONFLICT(nct_id) DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in STUDY_COLUMNS if c != "nct_id")
)


def connect(path: pathlib.Path | str = DB_PATH) -> sqlite3.Connection:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- writes


def upsert_studies(con: sqlite3.Connection, records: list[StudyRecord]) -> None:
    """Insert or update a batch in one transaction. Child rows are rebuilt, so re-running the ingest is idempotent."""
    with con:
        for r in records:
            con.execute(_UPSERT_STUDY, [getattr(r, column) for column in STUDY_COLUMNS])
            for table in ("study_races", "study_drugs", "study_conditions"):
                con.execute(f"DELETE FROM {table} WHERE nct_id = ?", (r.nct_id,))
            con.executemany(
                "INSERT OR IGNORE INTO study_races (nct_id, demographic, count, category, dimension, measure_title) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(r.nct_id, x.demographic, x.count, x.category, x.dimension, x.measure_title) for x in r.races])
            con.executemany(
                "INSERT OR IGNORE INTO study_drugs (nct_id, drug, role, intervention_type) VALUES (?, ?, ?, ?)",
                [(r.nct_id, x.drug, x.role, x.intervention_type) for x in r.drugs])
            con.executemany(
                "INSERT OR IGNORE INTO study_conditions (nct_id, condition, source) VALUES (?, ?, ?)",
                [(r.nct_id, name, source) for name, source in r.conditions])


def set_meta(con: sqlite3.Connection, key: str, value) -> None:
    with con:
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)))


def get_meta(con: sqlite3.Connection, key: str, default=None):
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


# ----------------------------------------------------------------------------- reads


def _where(drug=None, condition=None, sex=None, age=None, race=None, has_results=None) -> tuple[str, list]:
    """Shared filter clause. `s` is the studies alias in every query below."""
    clauses, params = [], []
    if drug:
        clauses.append("s.nct_id IN (SELECT nct_id FROM study_drugs WHERE drug = ? OR drug LIKE ?)")
        params += [drug.lower(), f"%{drug.lower()}%"]
    if condition:
        clauses.append("s.nct_id IN (SELECT nct_id FROM study_conditions WHERE condition LIKE ?)")
        params.append(f"%{condition.lower()}%")
    if sex:                                                     # "Female" matches female-only and mixed studies
        clauses.append("(s.sex = ? OR s.sex = 'Male and Female')")
        params.append(sex)
    if age is not None:
        clauses.append("s.age_min <= ? AND s.age_max >= ?")
        params += [age, age]
    if race:
        clauses.append("s.nct_id IN (SELECT nct_id FROM study_races WHERE category = ? AND count > 0)")
        params.append(race)
    if has_results is not None:
        clauses.append("s.has_results = ?")
        params.append(int(has_results))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _attach_races(con: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    """Add the race composition list to every study dict in `rows` (one query for the whole page)."""
    for row in rows:
        row["race_composition"] = []
    if rows:
        by_id = {row["nct_id"]: row for row in rows}
        placeholders = ", ".join("?" for _ in by_id)
        for x in con.execute(
                f"SELECT nct_id, demographic, count, category, dimension FROM study_races "
                f"WHERE nct_id IN ({placeholders}) ORDER BY dimension DESC, count DESC", list(by_id)):
            by_id[x["nct_id"]]["race_composition"].append(
                {"demographic": x["demographic"], "count": x["count"], "category": x["category"], "dimension": x["dimension"]})
    return rows


def study(con: sqlite3.Connection, nct_id: str) -> dict | None:
    """One study with its race composition, drugs and conditions, or None."""
    row = con.execute("SELECT * FROM studies WHERE nct_id = ?", (nct_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["race_composition"] = [dict(x) for x in con.execute(
        "SELECT demographic, count, category, dimension, measure_title FROM study_races "
        "WHERE nct_id = ? ORDER BY dimension DESC, count DESC", (nct_id,))]
    out["drugs"] = [dict(x) for x in con.execute(
        "SELECT drug, role, intervention_type FROM study_drugs WHERE nct_id = ? ORDER BY role, drug", (nct_id,))]
    out["conditions"] = [dict(x) for x in con.execute(
        "SELECT condition, source FROM study_conditions WHERE nct_id = ? ORDER BY source, condition", (nct_id,))]
    return out


def search(con: sqlite3.Connection, *, drug=None, condition=None, sex=None, age=None, race=None, has_results=None,
           limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """Matching studies (newest first) with their race composition, plus the total match count."""
    where, params = _where(drug, condition, sex, age, race, has_results)
    total = con.execute(f"SELECT COUNT(*) FROM studies s{where}", params).fetchone()[0]
    rows = [dict(x) for x in con.execute(
        f"SELECT s.* FROM studies s{where} ORDER BY s.start_date DESC, s.nct_id LIMIT ? OFFSET ?",
        [*params, limit, offset])]
    return _attach_races(con, rows), total


def aggregate(con: sqlite3.Connection, *, drug=None, condition=None, sex=None, age=None, race=None,
              has_results=None) -> dict:
    """Pool every matching study: race head counts by harmonized category and by reported label, sex counts,
    the age envelope, and how many studies reported race at all."""
    where, params = _where(drug, condition, sex, age, race, has_results)
    totals = con.execute(
        f"SELECT COUNT(*) AS studies, SUM(participants) AS participants, SUM(female_count) AS female, "
        f"SUM(male_count) AS male, MIN(age_min) AS age_min, MAX(age_max) AS age_max, "
        f"SUM(race_reported) AS studies_reporting_race FROM studies s{where}", params).fetchone()
    by_category = con.execute(
        f"SELECT r.dimension, r.category, SUM(r.count) AS count, COUNT(DISTINCT r.nct_id) AS studies "
        f"FROM study_races r JOIN studies s ON s.nct_id = r.nct_id{where} "
        f"GROUP BY r.dimension, r.category ORDER BY r.dimension DESC, count DESC", params)
    by_label = con.execute(
        f"SELECT r.dimension, r.demographic, SUM(r.count) AS count, COUNT(DISTINCT r.nct_id) AS studies "
        f"FROM study_races r JOIN studies s ON s.nct_id = r.nct_id{where} "
        f"GROUP BY r.dimension, r.demographic ORDER BY r.dimension DESC, count DESC", params)
    return {
        "studies": totals["studies"],
        "participants": totals["participants"],
        "studies_reporting_race": totals["studies_reporting_race"],
        "sex": {"female": totals["female"], "male": totals["male"]},
        "age_range": [totals["age_min"], totals["age_max"]],
        "race_composition": [dict(x) for x in by_category],
        "race_composition_as_reported": [dict(x) for x in by_label],
    }


def stats(con: sqlite3.Connection) -> dict:
    totals = con.execute("SELECT COUNT(*) AS studies, COALESCE(SUM(has_results), 0) AS with_results, "
                         "COALESCE(SUM(race_reported), 0) AS with_race FROM studies").fetchone()
    return {
        "studies": totals["studies"],
        "with_results": totals["with_results"],
        "with_race_composition": totals["with_race"],
        "distinct_drugs": con.execute("SELECT COUNT(DISTINCT drug) FROM study_drugs").fetchone()[0],
        "distinct_conditions": con.execute("SELECT COUNT(DISTINCT condition) FROM study_conditions").fetchone()[0],
        "ingest": get_meta(con, "ingest"),
    }
