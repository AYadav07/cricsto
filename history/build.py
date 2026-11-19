"""Build history/history.duckdb from the scorecard CSVs in history/raw/.

Separate from the Cricsheet database (data/cricsto.duckdb): this script reads only
history/raw/ and writes only history/history.duckdb.

Usage (from the repo root):
    python history/build.py

Expects:
    history/raw/test/  test_Matches_Data.csv, test_Batting_Card.csv, test_Bowling_Card.csv,
                       test_Fow_Card.csv, test_Partnership_Card.csv, players_info.csv
    history/raw/odi/   the same with odi_ prefixes
(git clone of the two bhuvaneshprasad datasets on Hugging Face, see history/README.md)

The database is rebuilt from scratch every run (about 10 s). Data problems that don't break
the structure are written to load_warnings and summarised at the end; structural problems
(duplicate keys, unknown matches) stop the build.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DB = HERE / "history.duckdb"
FORMATS = ("test", "odi")


def csv(fmt: str, name: str) -> str:
    path = RAW / fmt / (name if name == "players_info.csv" else f"{fmt}_{name}.csv")
    if not path.exists():
        sys.exit(f"Missing {path}. See history/README.md for how to download the data.")
    return f"read_csv('{path.as_posix()}', sample_size=-1, header=true)"


def ids(expr: str) -> str:
    """"['12', '-', '34']" -> [12, 34] (NULL if none)."""
    return f"nullif(list_transform(regexp_extract_all({expr}, '\\d+'), lambda x: x::BIGINT), [])"


def build(con: duckdb.DuckDBPyConnection) -> None:
    con.execute((HERE / "schema.sql").read_text(encoding="utf-8"))

    # players: identical file in both folders; take the Test copy
    con.execute(f"""
        INSERT INTO players
        SELECT player_id, player_object_id, player_name, dob, dod, gender,
               batting_style, bowling_style, country_id::INTEGER
        FROM {csv('test', 'players_info.csv')}
    """)

    for fmt in FORMATS:
        m = csv(fmt, "Matches_Data")
        no_col = "TEST Match No" if fmt == "test" else "ODI Match No"
        start = '"Match Start Date"' if fmt == "test" else '"Match Date"'
        end = '"Match End Date"' if fmt == "test" else "NULL"
        con.execute(f"""
            CREATE TEMP TABLE raw_m_{fmt} AS SELECT * FROM {m} WHERE "Match ID" IS NOT NULL;
            INSERT INTO matches
            SELECT "Match ID", '{fmt}', "{no_col}", "Match Name", "Series ID"::BIGINT, "Series Name",
                   {start}, {end},
                   "Team1 Name", "Team1 ID"::BIGINT, "Team1 Captain"::BIGINT,
                   "Team2 Name", "Team2 ID"::BIGINT, "Team2 Captain"::BIGINT,
                   "Match Venue (Stadium)", "Match Venue (City)", "Match Venue (Country)",
                   "Umpire 1", "Umpire 2", "Match Referee",
                   "Toss Winner", "Toss Winner Choice", "Match Winner", "Match Result Text",
                   "MOM Player"::BIGINT,
                   6, 'default'
            FROM raw_m_{fmt};
        """)

        # playing XIs (+ debut flag)
        con.execute(f"""
            INSERT INTO match_players
            WITH xi AS (
                SELECT "Match ID" AS match_id, "Team1 Name" AS team, {ids('"Team1 Playing 11"')} AS l,
                       {ids('"Debut Players"')} AS deb FROM raw_m_{fmt}
                UNION ALL
                SELECT "Match ID", "Team2 Name", {ids('"Team2 Playing 11"')},
                       {ids('"Debut Players"')} FROM raw_m_{fmt}
            ), u AS (
                SELECT match_id, team, unnest(l) AS player_id,
                       generate_subscripts(l, 1) AS list_order, deb
                FROM xi WHERE l IS NOT NULL
            )
            SELECT match_id, team, player_id, min(list_order),
                   coalesce(bool_or(list_contains(deb, player_id)), false)
            FROM u GROUP BY match_id, team, player_id
        """)

        # batting card; file order = batting order within each innings
        con.execute(f"""
            INSERT INTO batting
            WITH b AS (SELECT *, row_number() OVER () AS rn FROM {csv(fmt, 'Batting_Card')})
            SELECT "Match ID", innings, team,
                   row_number() OVER (PARTITION BY "Match ID", innings ORDER BY rn),
                   batsman::BIGINT,
                   coalesce(wicketType, '') <> 'DNB',
                   runs::INTEGER, balls::INTEGER, fours::INTEGER, sixes::INTEGER,
                   CASE WHEN wicketType = 'DNB' THEN NULL ELSE isOut END,
                   CASE wicketType WHEN 'DNB' THEN NULL WHEN 'stumping' THEN 'stumped'
                                   WHEN 'hitwicket' THEN 'hit wicket' ELSE wicketType END,
                   bowler::BIGINT,
                   {ids('fielders')}
            FROM b WHERE team IS NOT NULL   -- empty placeholder rows for abandoned matches
        """)

        # bowling card; balls recomputed later for 8-ball overs
        con.execute(f"""
            INSERT INTO bowling
            SELECT "Match ID", innings, team, opposition, "bowler id", overs, balls, maidens,
                   conceded, wickets, dots::INTEGER, fours::INTEGER, sixes::INTEGER, wides, noballs
            FROM {csv(fmt, 'Bowling_Card')} WHERE team IS NOT NULL
        """)

        con.execute(f"""
            INSERT INTO fall_of_wickets
            SELECT "Match ID", innings, team, wicket::INTEGER, player::BIGINT, runs::INTEGER, "over"
            FROM {csv(fmt, 'Fow_Card')}
            WHERE wicket IS NOT NULL AND team IS NOT NULL
        """)

        con.execute(f"""
            INSERT INTO partnerships
            SELECT "Match ID", innings, "for wicket", team, opposition, player1, player2,
                   "player1 runs", "player2 runs", nullif("player1 balls", 0), nullif("player2 balls", 0),
                   "partnership runs", nullif("partnership balls", 0)
            FROM {csv(fmt, 'Partnership_Card')} WHERE team IS NOT NULL
        """)

        # innings: one row per (match, innings) seen on the batting card, totals from the match record
        if fmt == "test":
            totals = " UNION ALL ".join(
                f"""SELECT "Match ID" AS match_id, "Team{t} Name" AS team, {i} AS team_innings_no,
                           "Innings{i} Team{t} Runs Scored" AS runs, "Innings{i} Team{t} Wickets Fell" AS wkts,
                           "Innings{i} Team{t} Extras Rec" AS extras FROM raw_m_test"""
                for t in (1, 2) for i in (1, 2))
        else:
            totals = " UNION ALL ".join(
                f"""SELECT "Match ID" AS match_id, "Team{t} Name" AS team, 1 AS team_innings_no,
                           "Team{t} Runs Scored" AS runs, "Team{t} Wickets Fell" AS wkts,
                           "Team{t} Extras Rec" AS extras FROM raw_m_odi"""
                for t in (1, 2))
        con.execute(f"""
            INSERT INTO innings
            WITH seen AS (
                SELECT DISTINCT b.match_id, b.innings_no, b.team
                FROM batting b JOIN matches m USING (match_id) WHERE m.format = '{fmt}'
            ), numbered AS (
                SELECT *, row_number() OVER (PARTITION BY match_id, team ORDER BY innings_no) AS tin
                FROM seen
            )
            SELECT n.match_id, n.innings_no, n.team,
                   CASE n.team WHEN m.team1 THEN m.team2 WHEN m.team2 THEN m.team1 END,
                   n.tin, t.runs::INTEGER, t.wkts::INTEGER, t.extras::INTEGER
            FROM numbered n
            JOIN matches m USING (match_id)
            LEFT JOIN ({totals}) t ON t.match_id = n.match_id AND t.team = n.team AND t.team_innings_no = n.tin
        """)

    fix_eight_ball_overs(con)
    validate(con)
    con.execute((HERE / "views.sql").read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("INSERT INTO load_info VALUES ('built_at', ?), ('duckdb_version', ?), ('source', ?)",
                [now, duckdb.__version__,
                 "Hugging Face: bhuvaneshprasad/test-cricket-dataset-1877-2014 and "
                 "odi-cricket-dataset-1971-2014 (ESPNcricinfo-derived scorecards)"])


def fix_eight_ball_overs(con: duckdb.DuckDBPyConnection) -> None:
    """The source counts every over as 6 balls. A bowling figure like 7.7 can only come from an
    8-ball over: flag that match, then every match in the same series (same host, same season),
    and recompute balls = full overs * 8 + part balls."""
    con.execute("""
        UPDATE matches SET balls_per_over = 8, bpo_source = 'detected'
        WHERE match_id IN (
            SELECT DISTINCT match_id FROM bowling
            WHERE round((overs - floor(overs)) * 10) IN (6, 7)
        );
        UPDATE matches SET balls_per_over = 8, bpo_source = 'series'
        WHERE balls_per_over = 6 AND series_id IN (
            SELECT series_id FROM matches WHERE bpo_source = 'detected' AND series_id IS NOT NULL
        );
        UPDATE bowling b SET balls = (floor(b.overs) * 8 + round((b.overs - floor(b.overs)) * 10))::INTEGER
        FROM matches m
        WHERE m.match_id = b.match_id AND m.balls_per_over = 8 AND b.overs IS NOT NULL;
    """)


def validate(con: duckdb.DuckDBPyConnection) -> None:
    # Structural: every card row belongs to a known match (FKs already enforce this on insert).
    checks = {
        "innings_total_mismatch": """
            SELECT i.match_id, format('inns {} {}: card {} + extras {} vs total {}',
                   i.innings_no, i.batting_team, s.r, i.extras, i.runs)
            FROM innings i JOIN (
                SELECT match_id, innings_no, sum(runs) AS r FROM batting GROUP BY ALL) s USING (match_id, innings_no)
            WHERE i.runs IS NOT NULL AND s.r + coalesce(i.extras, 0) <> i.runs""",
        "innings_total_missing": """
            SELECT match_id, format('inns {} {}', innings_no, batting_team) FROM innings WHERE runs IS NULL""",
        "team_not_in_match": """
            SELECT DISTINCT b.match_id, b.team FROM batting b JOIN matches m USING (match_id)
            WHERE b.team NOT IN (m.team1, m.team2)""",
        "unknown_player": """
            SELECT NULL, format('player_id {} ({} card rows)', player_id, count(*)) FROM (
                SELECT player_id FROM batting UNION ALL SELECT player_id FROM bowling
                UNION ALL SELECT player_id FROM match_players)
            WHERE player_id IS NOT NULL AND player_id NOT IN (SELECT player_id FROM players)
            GROUP BY player_id""",
        "batting_row_without_player": """
            SELECT match_id, format('inns {} pos {}', innings_no, position) FROM batting WHERE player_id IS NULL""",
        "bowler_wickets_vs_card": """
            SELECT o.match_id, format('inns {}: bowlers {} vs card {}', o.innings_no, w.w, o.o)
            FROM (SELECT match_id, innings_no, count(*) FILTER (WHERE dismissal IN
                    ('caught','bowled','lbw','stumped','hit wicket')) AS o FROM batting GROUP BY ALL) o
            JOIN (SELECT match_id, innings_no, sum(wickets) AS w FROM bowling GROUP BY ALL) w USING (match_id, innings_no)
            WHERE o.o <> w.w""",
        "match_without_scorecard": """
            SELECT match_id, coalesce(result_text, '') FROM matches
            WHERE match_id NOT IN (SELECT match_id FROM batting)""",
    }
    for name, q in checks.items():
        con.execute(f"INSERT INTO load_warnings SELECT '{name}', * FROM ({q})")


def main() -> None:
    t0 = time.time()
    tmp = DB.with_name(DB.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    con = duckdb.connect(str(tmp))
    try:
        build(con)
        summary = con.execute("""
            SELECT format, count(*) AS matches, min(start_date), max(start_date),
                   count(*) FILTER (WHERE start_date < DATE '2002-01-01') AS before_2002,
                   count(*) FILTER (WHERE balls_per_over = 8) AS eight_ball
            FROM matches GROUP BY format ORDER BY format""").fetchall()
        warns = con.execute("SELECT check_name, count(*) FROM load_warnings GROUP BY 1 ORDER BY 1").fetchall()
    finally:
        con.close()
    os.replace(tmp, DB)

    print(f"Built {DB.relative_to(HERE.parent)} in {time.time() - t0:.1f}s")
    for f, n, a, b, pre, eight in summary:
        print(f"  {f:5} {n:5} matches  {a} -> {b}  ({pre} before 2002, {eight} with 8-ball overs)")
    print("Warnings (details: SELECT * FROM load_warnings):")
    for name, n in warns:
        print(f"  {name:28} {n}")


if __name__ == "__main__":
    main()
