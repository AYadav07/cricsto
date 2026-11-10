"""Shared helpers: build a small raw_dir from fixture JSON, load it, query it."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cricsto.load_json import load  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def basic_match() -> dict:
    """A fresh copy of tests/fixtures/match_basic.json."""
    return copy.deepcopy(json.loads((FIXTURES / "match_basic.json").read_text()))


class Env:
    """A raw_dir + database in a temp folder."""

    def __init__(self, tmp: Path):
        self.raw = tmp / "raw"
        self.db = tmp / "test.duckdb"
        self.raw.mkdir()

    def write(self, match_id: str, data: dict, folder: str = "tst_male_json") -> Path:
        d = self.raw / folder
        d.mkdir(exist_ok=True)
        path = d / f"{match_id}.json"
        path.write_text(json.dumps(data))
        return path

    def load(self, **kw) -> dict:
        return load(raw_dir=self.raw, db_path=self.db, workers=2, verbose=False, **kw)

    def q(self, sql: str, *params):
        con = duckdb.connect(str(self.db), read_only=True)
        try:
            return con.execute(sql, list(params)).fetchall()
        finally:
            con.close()

    def views(self) -> None:
        from cricsto.views import apply_views
        apply_views(self.db)


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)
