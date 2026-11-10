"""Checks on the real database (data/cricsto.duckdb). Skipped if it isn't built.

Compares v2 with the v1 baseline in tests/baseline_v1/ and checks known facts
about the full Cricsheet load (SCHEMA.md section 8).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cricsto.duckdb"
BASELINE = Path(__file__).parent / "baseline_v1"

pytestmark = pytest.mark.skipif(not DB.exists(), reason="data/cricsto.duckdb not built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def test_v1_totals_match(con):
    """Men's IPL / T20I / ODI totals per season equal v1's (deliberate changes excluded)."""
    v1 = pd.read_csv(BASELINE / "totals_by_dataset_season.csv", dtype={"season": str})
    v2 = con.execute("""
        SELECT dataset, season, count(DISTINCT match_id) AS matches, count(*) AS deliveries,
               sum(total_runs) AS runs, sum(runs_off_bat) AS bat_runs, sum(extras) AS extras,
               sum(legal_ball::INT) AS legal_balls, sum((player_dismissed IS NOT NULL)::INT) AS wicket_balls,
               sum(is_four::INT) AS fours, sum(is_six::INT) AS sixes
        FROM deliveries WHERE gender = 'male' AND dataset IN ('ipl', 't20s', 'odis')
        GROUP BY ALL""").df()
    m = v1.merge(v2, on=["dataset", "season"], how="outer", suffixes=("_v1", "_v2"), indicator=True)
    assert (m["_merge"] == "both").all()
    for c in ["matches", "deliveries", "runs", "bat_runs", "extras", "legal_balls",
              "wicket_balls", "fours", "sixes"]:
        assert (m[c + "_v1"] == m[c + "_v2"]).all(), c


def test_every_ball_numbered_like_cricsheet(con):
    assert con.execute("""SELECT count(*) FROM balls
                          WHERE actual_delivery <> over_num || '.' || legal_ball_no""").fetchone() == (0,)


def test_known_warnings(con):
    got = set(con.execute("SELECT match_id, check_name FROM load_warnings").fetchall())
    assert got >= {  # new data may add more; these four are known (SCHEMA.md section 8)
        ("1229824", "player_in_both_teams"),
        ("1298152", "over_too_long"),
        ("325580", "umpire_name_not_in_registry"),
        ("936133", "umpire_name_not_in_registry"),
    }


def test_namesakes_stay_apart(con):
    assert con.execute("SELECT count(*) FROM people WHERE name = 'Rashid Khan'").fetchone() == (4,)


def test_latest_names(con):
    assert con.execute("SELECT name FROM people WHERE person_id = 'f3a18a0c'").fetchone() == ("NR Sciver-Brunt",)
    assert con.execute("SELECT name FROM venues WHERE venue_id = '6f9052c3'").fetchone() == (
        "Maharashtra Cricket Association Stadium, Pune",)


def test_every_raw_file_routes_to_its_folder():
    import json
    from cricsto.refresh import route
    raw = ROOT / "data" / "raw" / "json"
    wrong = [p for p in raw.glob("*/*.json") if route(json.loads(p.read_bytes())["info"]) != p.parent.name]
    assert wrong == []


def test_impact_players(con):
    n = con.execute("""SELECT count(*) FROM replacements r JOIN matches m USING (match_id)
                       WHERE m.dataset = 'ipl' AND r.reason = 'impact_player'""").fetchone()[0]
    assert n >= 557  # count on 2026-11-10; grows with new IPL seasons
