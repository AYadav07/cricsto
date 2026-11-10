"""Build and query the Cricsto DuckDB database from Cricsheet "Ashwin" CSV files.

Expected layout (one folder per dataset you download from cricsheet.org/downloads,
choosing the CSV "Ashwin" format):

    data/raw/ipl/        1082591.csv, 1082591_info.csv, ...
    data/raw/t20s/       ...
"""
from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "cricsto.duckdb"
QUERIES_DIR = ROOT / "queries"
REFERENCE_DIR = ROOT / "data" / "reference"

# Columns we use from the ball-by-ball files. Others in the file are ignored.
BALL_COLUMNS = [
    "match_id", "season", "start_date", "venue", "innings", "ball",
    "batting_team", "bowling_team", "striker", "non_striker", "bowler",
    "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes", "penalty",
    "non_boundary", "wicket_type", "player_dismissed", "other_wicket_type", "other_player_dismissed",
]


INFO_COLUMNS = [
    "match_id", "dataset", "date", "team1", "team2", "event", "match_number", "city",
    "venue", "gender", "match_type", "toss_winner", "toss_decision", "winner",
    "winner_runs", "winner_wickets", "outcome", "method", "player_of_match",
    "balls_per_over",
]


def _ball_files(folder: Path) -> list[Path]:
    """Per-match ball files; falls back to a combined all_matches.csv if that's all there is."""
    per_match = [
        p for p in folder.glob("*.csv")
        if not p.name.endswith("_info.csv") and not p.name.startswith("all_matches")
    ]
    if per_match:
        return per_match
    return list(folder.glob("all_matches*.csv"))


def _read_info(folder: Path, dataset: str) -> pd.DataFrame:
    """Parse <id>_info.csv files into one row per match with the useful fields."""
    rows = []
    for path in folder.glob("*_info.csv"):
        match_id = path.name.removesuffix("_info.csv")
        rec = {"match_id": match_id, "dataset": dataset, "teams": []}
        with path.open(newline="", encoding="utf-8") as f:
            for line in csv.reader(f):
                if len(line) < 3 or line[0] != "info":
                    continue
                key, value = line[1], line[2]
                if key == "team":
                    rec["teams"].append(value)
                elif key in ("date",):
                    rec.setdefault("date", value)  # first day of the match
                elif key in (
                    "event", "match_number", "city", "venue", "gender", "match_type",
                    "toss_winner", "toss_decision", "winner", "winner_runs",
                    "winner_wickets", "outcome", "method", "player_of_match",
                    "balls_per_over",
                ):
                    rec.setdefault(key, value)
        teams = rec.pop("teams")
        rec["team1"] = teams[0] if teams else None
        rec["team2"] = teams[1] if len(teams) > 1 else None
        rows.append(rec)
    return pd.DataFrame(rows)


def build(datasets: list[str] | None = None) -> None:
    """(Re)build data/cricsto.duckdb from every dataset folder under data/raw/."""
    folders = sorted(p for p in RAW_DIR.iterdir() if p.is_dir()) if RAW_DIR.exists() else []
    if datasets:
        folders = [f for f in folders if f.name in datasets]
    if not folders:
        raise SystemExit(f"No dataset folders found in {RAW_DIR}. See README: Get the data.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("DROP TABLE IF EXISTS balls_raw")
    con.execute("DROP TABLE IF EXISTS matches")

    info_frames = []
    first = True
    for folder in folders:
        files = _ball_files(folder)
        if not files:
            print(f"  skip {folder.name}: no ball-by-ball CSVs")
            continue
        file_list = [str(p) for p in files]
        cols = ", ".join(BALL_COLUMNS)
        select = (
            f"SELECT {cols}, '{folder.name}' AS dataset "
            f"FROM read_csv(?, union_by_name=true, all_varchar=true, header=true)"
        )
        if first:
            con.execute(f"CREATE TABLE balls_raw AS {select}", [file_list])
            first = False
        else:
            con.execute(f"INSERT INTO balls_raw {select}", [file_list])
        info = _read_info(folder, folder.name)
        if not info.empty:
            info_frames.append(info)
        print(f"  loaded {folder.name}: {len(files)} files")

    if first:
        raise SystemExit("Nothing loaded.")

    info_df = pd.concat(info_frames, ignore_index=True) if info_frames else pd.DataFrame()
    for col in INFO_COLUMNS:  # views.sql relies on these existing
        if col not in info_df.columns:
            info_df[col] = None
    info_df = info_df.astype(object).where(info_df.notna(), None)
    con.register("info_df", info_df)
    casts = ", ".join(f'CAST("{c}" AS VARCHAR) AS "{c}"' for c in INFO_COLUMNS)
    con.execute(f"CREATE TABLE matches AS SELECT {casts} FROM info_df")
    con.unregister("info_df")

    con.execute((Path(__file__).parent / "views.sql").read_text())
    n_balls = con.execute("SELECT count(*) FROM deliveries").fetchone()[0]
    n_matches = con.execute("SELECT count(DISTINCT match_id) FROM deliveries").fetchone()[0]
    con.close()
    print(f"Built {DB_PATH.name}: {n_matches:,} matches, {n_balls:,} deliveries")


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise SystemExit("Database not built yet. Run: python scripts/build_db.py")
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    _attach_reference(con)
    return con


def _attach_reference(con: duckdb.DuckDBPyConnection) -> None:
    """Expose data/reference/*.csv (e.g. bowler_types.csv) as views of the same name."""
    if not REFERENCE_DIR.exists():
        return
    for path in REFERENCE_DIR.glob("*.csv"):
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {path.stem} AS "
            f"SELECT * FROM read_csv('{path.as_posix()}', header=true, all_varchar=true)"
        )


def run_query(name: str, **params) -> pd.DataFrame:
    """Run queries/<name>.sql. Use $param placeholders in the SQL; pass values as kwargs."""
    sql = (QUERIES_DIR / f"{name}.sql").read_text()
    con = connect()
    try:
        return con.execute(sql, params).df() if params else con.execute(sql).df()
    finally:
        con.close()


def sql(query: str, **params) -> pd.DataFrame:
    """Run an ad-hoc SQL string against the database."""
    con = connect()
    try:
        return con.execute(query, params).df() if params else con.execute(query).df()
    finally:
        con.close()
