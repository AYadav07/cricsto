"""(Re)create the views in cricsto/views.sql."""
from __future__ import annotations

from pathlib import Path

import duckdb

from .load_json import DB_PATH

VIEWS_SQL = Path(__file__).with_name("views.sql")


def apply_views(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(VIEWS_SQL.read_text())
    finally:
        con.close()
