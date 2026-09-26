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
TABLES = ("study_races", "study_drugs", "studies", "meta")          # children first, so drops never hit a foreign key
SOURCE_URL = "https://clinicaltrials.gov/study/{}"

STUDY_COLUMNS = ("nct_id", "drug", "drug_mesh", "condition", "sex", "age_lower", "age_upper",
                 "female_count", "male_count", "participants", "race_reported")

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


def schema_is_current(con: sqlite3.Connection) -> bool:
    """False when the file was built by an earlier schema.sql (no studies table at all is fine)."""
    columns = {row["name"] for row in con.execute("PRAGMA table_info(studies)")}
    return not columns or set(STUDY_COLUMNS) <= columns


def drop_all(con: sqlite3.Connection) -> None:
    with con:
        for table in TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")


# ----------------------------------------------------------------------------- writes


def upsert_studies(con: sqlite3.Connection, records: list[StudyRecord]) -> None:
    """Insert or update a batch in one transaction. Child rows are rebuilt, so re-running the ingest is idempotent."""
    with con:
        for r in records:
            con.execute(_UPSERT_STUDY, [getattr(r, column) for column in STUDY_COLUMNS])
            con.execute("DELETE FROM study_races WHERE nct_id = ?", (r.nct_id,))
            con.execute("DELETE FROM study_drugs WHERE nct_id = ?", (r.nct_id,))
            con.executemany(
                "INSERT OR IGNORE INTO study_races (nct_id, demographic, count, category, dimension, measure_title) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(r.nct_id, x.demographic, x.count, x.category, x.dimension, x.measure_title) for x in r.races])
            con.executemany(
                "INSERT OR IGNORE INTO study_drugs (nct_id, drug, drug_mesh) VALUES (?, ?, ?)",
                [(r.nct_id, x.drug, x.drug_mesh) for x in r.drugs])


def set_meta(con: sqlite3.Connection, key: str, value) -> None:
    with con:
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)))


def get_meta(con: sqlite3.Connection, key: str, default=None):
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


# ----------------------------------------------------------------------------- reads


def _public(row) -> dict:
    """A studies row as the API returns it: every column, plus the ClinicalTrials.gov link (derived, not stored)."""
    out = dict(row)
    out["source_url"] = SOURCE_URL.format(out["nct_id"])
    return out


def _where(drug=None, condition=None, sex=None, age=None, race=None) -> tuple[str, list]:
    """Shared filter clause. `s` is the studies alias in every query below. Values arrive canonical
    (validation.py): sex is M / F / MF, race is a study_races.category, age is a whole number of years."""
    clauses, params = [], []
    if drug:                                                    # reported name or MeSH name, substring
        like = f"%{drug}%"
        clauses.append("s.nct_id IN (SELECT nct_id FROM study_drugs WHERE drug LIKE ? OR drug_mesh LIKE ?)")
        params += [like, like]
    if condition:
        clauses.append("s.condition LIKE ?")
        params.append(f"%{condition}%")
    if sex == "MF":                                             # studies that enrolled both sexes
        clauses.append("s.sex = 'MF'")
    elif sex:                                                   # "F" matches female-only and mixed studies
        clauses.append("s.sex IN (?, 'MF')")
        params.append(sex)
    if age is not None:                                         # a NULL bound is no bound
        clauses.append("(s.age_lower IS NULL OR s.age_lower <= ?) AND (s.age_upper IS NULL OR s.age_upper >= ?)")
        params += [age, age]
    if race:
        clauses.append("s.nct_id IN (SELECT nct_id FROM study_races WHERE category = ? AND count > 0)")
        params.append(race)
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
    """One study with its race composition and drug rows, or None."""
    row = con.execute("SELECT * FROM studies WHERE nct_id = ?", (nct_id,)).fetchone()
    if not row:
        return None
    out = _public(row)
    out["race_composition"] = [dict(x) for x in con.execute(
        "SELECT demographic, count, category, dimension, measure_title FROM study_races "
        "WHERE nct_id = ? ORDER BY dimension DESC, count DESC", (nct_id,))]
    out["drugs"] = [dict(x) for x in con.execute(
        "SELECT drug, drug_mesh FROM study_drugs WHERE nct_id = ? ORDER BY drug_mesh", (nct_id,))]
    return out


def search(con: sqlite3.Connection, *, drug=None, condition=None, sex=None, age=None, race=None,
           limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """Matching studies (most recently registered first) with their race composition, plus the total match count."""
    where, params = _where(drug, condition, sex, age, race)
    total = con.execute(f"SELECT COUNT(*) FROM studies s{where}", params).fetchone()[0]
    rows = [_public(x) for x in con.execute(
        f"SELECT s.* FROM studies s{where} ORDER BY s.nct_id DESC LIMIT ? OFFSET ?", [*params, limit, offset])]
    return _attach_races(con, rows), total


def aggregate(con: sqlite3.Connection, *, drug=None, condition=None, sex=None, age=None, race=None) -> dict:
    """Pool every matching study: race head counts by harmonized category and by reported label, sex counts,
    the age envelope (a NULL upper bound means at least one study set none), and how many studies reported race."""
    where, params = _where(drug, condition, sex, age, race)
    totals = con.execute(
        f"SELECT COUNT(*) AS studies, COALESCE(SUM(participants), 0) AS participants, "
        f"SUM(female_count) AS female, SUM(male_count) AS male, "
        f"MIN(COALESCE(age_lower, 0)) AS age_lower, "
        f"CASE WHEN SUM(age_upper IS NULL) > 0 THEN NULL ELSE MAX(age_upper) END AS age_upper, "
        f"COALESCE(SUM(race_reported), 0) AS studies_reporting_race FROM studies s{where}", params).fetchone()
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
        "age_range": [totals["age_lower"], totals["age_upper"]],
        "race_composition": [dict(x) for x in by_category],
        "race_composition_as_reported": [dict(x) for x in by_label],
    }


def stats(con: sqlite3.Connection) -> dict:
    totals = con.execute("SELECT COUNT(*) AS studies, COALESCE(SUM(participants), 0) AS participants, "
                         "COALESCE(SUM(race_reported), 0) AS with_race FROM studies").fetchone()
    return {
        "studies": totals["studies"],
        "participants": totals["participants"],
        "with_race_composition": totals["with_race"],
        # MeSH terms arrive in the source's casing ("Bupivacaine" in one study, "bupivacaine" in another)
        "distinct_drugs": con.execute("SELECT COUNT(DISTINCT lower(drug_mesh)) FROM study_drugs").fetchone()[0],
        "ingest": get_meta(con, "ingest"),
    }
