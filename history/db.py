"""Query helpers for history/history.duckdb (scorecard-level Tests and ODIs).

Separate from cricsto/db.py, which serves the Cricsheet database.

    import sys; sys.path.insert(0, "history")    # from the repo root
    from db import run, sql, find_player

    run("career_batting", format="test", from_date="1990-01-01", to_date="2001-12-31", min_innings=20)
    find_player("murali")
    sql("SELECT * FROM match_results WHERE year = 1999 AND format = 'odi'")
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

HERE = Path(__file__).resolve().parent
DB = HERE / "history.duckdb"
QUERIES = HERE / "queries"


def connect() -> duckdb.DuckDBPyConnection:
    if not DB.exists():
        raise FileNotFoundError(f"{DB} not found: run python history/build.py first")
    return duckdb.connect(str(DB), read_only=True)


def sql(query: str, **params) -> pd.DataFrame:
    with connect() as con:
        return con.execute(query, params or None).df()


def run(name: str, **params) -> pd.DataFrame:
    """Run history/queries/<name>.sql with $params."""
    return sql((QUERIES / f"{name}.sql").read_text(encoding="utf-8"), **params)


def find_player(text: str) -> pd.DataFrame:
    """Players whose name contains text (names are full names, e.g. 'Donald Bradman')."""
    return sql("""
        SELECT p.player_id, p.name, p.dob, p.batting_style, p.bowling_style,
               string_agg(DISTINCT m.format, ', ') AS formats,
               min(m.start_date) AS first_match, max(m.start_date) AS last_match
        FROM players p
        LEFT JOIN match_players mp USING (player_id)
        LEFT JOIN matches m USING (match_id)
        WHERE p.name ILIKE '%' || $t || '%'
        GROUP BY ALL ORDER BY first_match NULLS LAST
    """, t=text)
