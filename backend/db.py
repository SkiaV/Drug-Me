"""SQLite store for harmonized trials, the researcher table, and per-drug enrichment.

Two files:
  * registry.sqlite  trials, trial_drugs, drug_rows, meta. Rebuilt only by harvest.py / build_table.py.
  * extras.sqlite    drug_extras: the profile-independent, network-derived part of a report (RxClass, FDA label
                     sentences, FAERS split, approval date, CDC prevalence) keyed by drug name. A few KB per drug,
                     committed, filled by prewarm.py or by the first report for a drug. It is what lets every
                     dashboard report render with the Wi-Fi off.
Kept deliberately tiny (stdlib sqlite3) so a teammate can swap in Postgres by replacing connect() and the DDL.
"""
import json
import sqlite3
import time

from config import DB_PATH, EXTRAS_PATH

DDL = """
CREATE TABLE IF NOT EXISTS trials (nct TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trial_drugs (name TEXT NOT NULL, nct TEXT NOT NULL, PRIMARY KEY (name, nct));
CREATE INDEX IF NOT EXISTS ix_trial_drugs_name ON trial_drugs(name);
CREATE TABLE IF NOT EXISTS drug_rows (name TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
EXTRAS_DDL = """
CREATE TABLE IF NOT EXISTS drug_extras (name TEXT PRIMARY KEY, data TEXT NOT NULL, fetched_at REAL NOT NULL);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)
    return con


def connect_extras():
    con = sqlite3.connect(EXTRAS_PATH)
    con.executescript(EXTRAS_DDL)
    return con


def store_trials(records: list[dict]):
    con = connect()
    with con:
        con.executemany("INSERT OR REPLACE INTO trials(nct, data) VALUES (?, ?)",
                        [(r["nct"], json.dumps(r)) for r in records if r.get("nct")])
        rows = [(name, r["nct"]) for r in records if r.get("nct") for name in r.get("drug_names", [])]
        con.executemany("INSERT OR IGNORE INTO trial_drugs(name, nct) VALUES (?, ?)", rows)
    con.close()


def trials_with_name(name: str) -> list[dict]:
    """Trials whose drug names (MeSH terms, intervention names, other names) contain exactly `name`."""
    con = connect()
    out = [json.loads(d) for (d,) in con.execute(
        "SELECT t.data FROM trial_drugs d JOIN trials t ON t.nct = d.nct WHERE d.name = ?", (name.lower().strip(),))]
    con.close()
    return out


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


# ---- extras: the network-derived part of a report, one row per drug ----

def get_extras(name: str, max_age_days: float | None = None) -> dict | None:
    con = connect_extras()
    row = con.execute("SELECT data, fetched_at FROM drug_extras WHERE name = ?", (name.lower().strip(),)).fetchone()
    con.close()
    if not row:
        return None
    if max_age_days is not None and time.time() - row[1] > max_age_days * 86400:
        return None
    data = json.loads(row[0])
    data["_fetched_at"] = row[1]
    return data


def set_extras(name: str, data: dict):
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    con = connect_extras()
    with con:
        con.execute("INSERT OR REPLACE INTO drug_extras(name, data, fetched_at) VALUES (?, ?, ?)",
                    (name.lower().strip(), json.dumps(data), time.time()))
    con.close()


def extras_count() -> int:
    con = connect_extras()
    n = con.execute("SELECT COUNT(*) FROM drug_extras").fetchone()[0]
    con.close()
    return n
