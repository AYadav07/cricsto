"""Query helpers for the Cricsheet DuckDB database (cricsheet/data/cricsto.duckdb).

The database is built from Cricsheet JSON in cricsheet/data/raw/json/ by the v2 loader
(see cricsheet/SCHEMA.md). This module only opens it and runs queries.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent          # the cricsheet/ folder
RAW_DIR = ROOT / "data" / "raw" / "json"
DB_PATH = ROOT / "data" / "cricsto.duckdb"
QUERIES_DIR = ROOT / "queries"
REFERENCE_DIR = ROOT / "data" / "reference"


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise SystemExit("Database not built yet. Run: python cricsheet/scripts/build_db.py")
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    _attach_reference(con)
    return con


def _attach_reference(con: duckdb.DuckDBPyConnection) -> None:
    """Expose cricsheet/data/reference/*.csv (e.g. bowler_types.csv) as views of the same name."""
    if not REFERENCE_DIR.exists():
        return
    for path in REFERENCE_DIR.glob("*.csv"):
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {path.stem} AS "
            f"SELECT * FROM read_csv('{path.as_posix()}', header=true, all_varchar=true)"
        )


def run_query(name: str, **params) -> pd.DataFrame:
    """Run cricsheet/queries/<name>.sql. Use $param placeholders in the SQL; pass values as kwargs."""
    sql_text = (QUERIES_DIR / f"{name}.sql").read_text()
    con = connect()
    try:
        return con.execute(sql_text, params).df() if params else con.execute(sql_text).df()
    finally:
        con.close()


def sql(query: str, **params) -> pd.DataFrame:
    """Run an ad-hoc SQL string against the database."""
    con = connect()
    try:
        return con.execute(query, params).df() if params else con.execute(query).df()
    finally:
        con.close()
