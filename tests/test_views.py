"""View tests on the fixture match."""
from __future__ import annotations

import pytest

from conftest import basic_match


@pytest.fixture
def loaded(env):
    env.write("900001", basic_match())
    env.load()
    env.views()
    return env


def test_deliveries_columns(loaded):
    rows = loaded.q("""SELECT ball, striker, legal_ball, faced_ball, bowler_runs, is_four, is_wicket,
                              bowler_wicket, phase, in_powerplay, player_dismissed, wicket_type
                       FROM deliveries WHERE innings = 1 ORDER BY ball_seq""")
    assert [float(r[0]) for r in rows] == [0.1, 0.2, 0.2, 0.3, 0.3, 0.4, 0.5, 0.6]
    assert rows[1][2:5] == (False, False, 1)          # wide: not legal, not faced, 1 run to bowler
    assert rows[3][2:5] == (False, True, 3)           # no-ball + 2 off the bat
    assert rows[2][5] is True                         # four
    assert rows[5][6:8] == (False, False)             # retired hurt: not a wicket
    assert rows[6][6:8] == (True, False)              # run out: wicket, not the bowler's
    assert rows[7][6:8] == (True, True)               # caught
    assert all(r[8] == "powerplay" and r[9] for r in rows)
    assert rows[7][10:] == ("A Three", "caught")


def test_non_boundary_four_is_not_a_four(loaded):
    assert loaded.q("SELECT is_four FROM deliveries WHERE innings = 2 AND ball_seq = 2") == [(False,)]


def test_batter_innings(loaded):
    rows = loaded.q("""SELECT batter, batting_position, runs, balls, fours, is_out, how_out
                       FROM batter_innings WHERE innings = 1 ORDER BY batting_position""")
    assert rows == [
        ("A One", 1, 7, 4, 1, True, "run out"),      # out as non-striker
        ("A Two", 2, 0, 1, 0, False, None),          # retired hurt = not out
        ("A Three", 3, 0, 2, 0, True, "caught"),
    ]


def test_bowler_innings(loaded):
    assert loaded.q("""SELECT bowler, legal_balls, overs, runs, wickets, wides, noballs
                       FROM bowler_innings WHERE innings = 1""") == [
        ("B One", 6, 1.0, 9, 1, 1, 1)]


def test_dismissals_with_fielders(loaded):
    rows = loaded.q("""SELECT batter, wicket_type, fielders, is_dismissal FROM dismissals
                       ORDER BY ball_seq""")
    assert rows == [("A Two", "retired hurt", None, False),
                    ("A One", "run out", "sub", True),
                    ("A Three", "caught", "B Two", True)]


def test_striker_and_non_striker_out(loaded):
    rows = loaded.q("""SELECT ball_seq, striker_out, non_striker_out FROM deliveries
                       WHERE innings = 1 AND (striker_out OR non_striker_out OR wicket_type IS NOT NULL)
                       ORDER BY ball_seq""")
    assert rows == [(6, False, False),   # retired hurt: nobody out
                    (7, False, True),    # non-striker run out
                    (8, True, False)]    # caught


def test_find_player_by_old_name(env, monkeypatch):
    import json
    from cricsto import db, insights
    old = basic_match()
    new = json.loads(json.dumps(basic_match()).replace('"A One"', '"A One-Renamed"'))
    new["info"]["dates"] = ["2024-06-01"]
    env.write("900001", old)
    env.write("900002", new)
    env.load()
    env.views()
    monkeypatch.setattr(db, "DB_PATH", env.db)
    df = insights.find_player("A One")
    row = df[df.person_id == "aaaa0001"].iloc[0]
    assert row["name"] == "A One-Renamed" and row["matches"] == 2
    assert set(row["all_names"].split(" / ")) == {"A One", "A One-Renamed"}
