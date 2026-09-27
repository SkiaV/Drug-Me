"""SQLite store for harmonized trials and the researcher table.

Kept deliberately tiny (stdlib sqlite3, three tables) so a teammate can swap in Postgres/Tiger Data by
replacing connect() and the two DDL statements.
"""
import json
import sqlite3

from config import DB_PATH

DDL = """
CREATE TABLE IF NOT EXISTS trials (nct TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trial_drugs (name TEXT NOT NULL, nct TEXT NOT NULL, PRIMARY KEY (name, nct));
CREATE INDEX IF NOT EXISTS ix_trial_drugs_name ON trial_drugs(name);
CREATE TABLE IF NOT EXISTS drug_rows (name TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)
    return con


def store_trials(records: list[dict]):
    con = connect()
    with con:
        con.executemany("INSERT OR REPLACE INTO trials(nct, data) VALUES (?, ?)",
                        [(r["nct"], json.dumps(r)) for r in records if r.get("nct")])
        rows = [(name, r["nct"]) for r in records if r.get("nct") for name in r.get("drug_names", [])]
        con.executemany("INSERT OR IGNORE INTO trial_drugs(name, nct) VALUES (?, ?)", rows)
    con.close()


def trials_for_names(names: list[str]) -> list[dict]:
    """Candidate trials whose intervention names contain any of the drug names (word match done later)."""
    if not names:
        return []
    con = connect()
    seen, out = set(), []
    for n in names:
        n = n.lower().strip()
        if not n:
            continue
        for (nct, data) in con.execute(
                "SELECT t.nct, t.data FROM trial_drugs d JOIN trials t ON t.nct = d.nct WHERE d.name = ? OR d.name LIKE ?",
                (n, f"%{n}%")):
            if nct not in seen:
                seen.add(nct)
                out.append(json.loads(data))
    con.close()
    return out


def all_trials():
    con = connect()
    for (data,) in con.execute("SELECT data FROM trials"):
        yield json.loads(data)
    con.close()


def trial_count() -> int:
    con = connect()
    n = con.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
    con.close()
    return n


def store_drug_rows(rows: list[dict]):
    con = connect()
    with con:
        con.execute("DELETE FROM drug_rows")
        con.executemany("INSERT INTO drug_rows(name, data) VALUES (?, ?)", [(r["drug"], json.dumps(r)) for r in rows])
    con.close()


def drug_rows() -> list[dict]:
    con = connect()
    rows = [json.loads(d) for (d,) in con.execute("SELECT data FROM drug_rows")]
    con.close()
    return rows


def set_meta(key, value):
    con = connect()
    with con:
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, json.dumps(value)))
    con.close()


def get_meta(key, default=None):
    con = connect()
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    con.close()
    return json.loads(row[0]) if row else default
