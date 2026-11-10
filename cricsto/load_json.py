"""Incremental loader: Cricsheet JSON in data/raw/json/ -> DuckDB tables (SCHEMA.md).

    from cricsto.load_json import load
    load()            # new / changed / gone files only
    load(full=True)   # drop every table and reload everything

Per run:
  1. scan folders, hash files, compare with load_log -> new / changed / unchanged / gone
  2. delete rows of changed and gone matches, child-first (one committed transaction
     per level: DuckDB won't delete a parent in the same transaction as its children)
  3. parse new and changed files in parallel, insert per table in one transaction
  4. recompute lookup names (people / venues / teams) from name_sources
  5. validate: errors roll back step 3-4; warnings go to load_warnings
A match is therefore always either fully loaded or absent. If a run fails after
step 2, the affected matches are absent and the next run loads them as new.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "json"
DB_PATH = ROOT / "data" / "cricsto.duckdb"
SCHEMA_SQL = Path(__file__).with_name("schema.sql")

FOLDER_RE = re.compile(r"^([a-z0-9]+)_(male|female)_json$")

BOWLER_CREDITED = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
NOT_A_DISMISSAL = {"retired hurt", "retired not out"}
OFFICIAL_ROLES = {"umpires": "umpire", "tv_umpires": "tv_umpire",
                  "match_referees": "match_referee", "reserve_umpires": "reserve_umpire"}

# Insert order (parents first) and the columns written for each table.
COLUMNS: dict[str, list[str]] = {
    "matches": [
        "match_id", "dataset", "gender", "team_type", "match_type", "match_type_number", "season",
        "start_date", "end_date", "num_days", "venue_id", "event_name", "event_match_number",
        "event_group", "event_stage", "event_sub_name", "team1_id", "team2_id", "balls_per_over",
        "overs", "toss_winner_id", "toss_decision", "toss_uncontested", "winner_id", "win_by_runs",
        "win_by_wickets", "win_by_innings", "result", "method", "eliminator_id",
        "bowl_out_winner_id", "bowl_out", "missing", "data_version", "meta_created", "revision"],
    "name_sources": ["match_id", "kind", "key_id", "name", "city", "team_type"],
    "match_players": ["match_id", "person_id", "team_id", "list_order", "is_supersub"],
    "officials": ["match_id", "role", "person_id", "list_order"],
    "player_of_match": ["match_id", "person_id"],
    "innings": [
        "match_id", "innings_no", "batting_team_id", "bowling_team_id", "is_super_over", "declared",
        "forfeited", "target_runs", "target_overs", "penalty_runs_pre", "penalty_runs_post"],
    "absent_hurt": ["match_id", "innings_no", "person_id"],
    "powerplays": ["match_id", "innings_no", "pp_seq", "from_ball", "to_ball", "type"],
    "miscounted_overs": ["match_id", "innings_no", "over_num", "balls", "umpire_id"],
    "balls": [
        "match_id", "innings_no", "over_num", "ball_seq", "legal_ball_no", "actual_delivery",
        "batter_id", "non_striker_id", "bowler_id", "runs_batter", "runs_extras", "runs_total",
        "non_boundary", "wides", "noballs", "byes", "legbyes", "penalty"],
    "wickets": [
        "match_id", "innings_no", "over_num", "ball_seq", "wicket_seq", "player_out_id", "kind",
        "bowler_credited", "is_dismissal"],
    "fielding": [
        "match_id", "innings_no", "over_num", "ball_seq", "wicket_seq", "fielder_seq",
        "fielder_id", "is_substitute"],
    "reviews": [
        "match_id", "innings_no", "over_num", "ball_seq", "reviewing_team_id", "batter_id",
        "umpire_id", "decision", "umpires_call", "review_type"],
    "replacements": [
        "match_id", "innings_no", "over_num", "ball_seq", "scope", "repl_seq", "team_id",
        "player_in_id", "player_out_id", "reason", "role"],
    "load_log": ["match_id", "folder", "revision", "file_hash", "loaded_at"],
}

# Child-first delete levels. Tables in one level don't reference each other.
DELETE_LEVELS: list[list[str]] = [
    ["fielding"],
    ["wickets", "reviews", "replacements"],
    ["balls"],
    ["absent_hurt", "powerplays", "miscounted_overs"],
    ["innings", "match_players", "officials", "player_of_match", "name_sources",
     "load_warnings", "load_log"],
    ["matches"],
]
LOOKUPS = ["people", "venues", "teams"]


class LoadError(Exception):
    """A validation error: the load is rolled back."""


def team_id(name: str) -> str:
    return hashlib.md5(name.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Parsing one file
# ---------------------------------------------------------------------------

def _int(v):
    return None if v is None else int(v)


def _str(v):
    return None if v is None else str(v)


def parse_match(path: Path, dataset: str, gender: str) -> dict[str, list[tuple]]:
    """Turn one Cricsheet JSON file into rows per table (see COLUMNS)."""
    j = json.loads(path.read_bytes())
    meta, info = j["meta"], j["info"]
    mid = path.stem
    reg = info["registry"]["people"]
    rows: dict[str, list[tuple]] = {t: [] for t in COLUMNS if t != "load_log"}
    rows["_warnings"] = []  # (match_id, check_name, innings_no, over_num, detail)

    def pid(name):
        return None if name is None else reg[name]  # KeyError = name without an ID

    def umpire_pid(name, innings_no, over_num):
        """miscounted_overs.umpire is sometimes informal ('Bowden' for 'BF Bowden')."""
        if name is None or name in reg:
            return pid(name)
        umpires = info.get("officials", {}).get("umpires", [])
        surname = name.split()[-1]
        hits = [u for u in umpires if u.split()[-1] == surname]
        resolved = reg[hits[0]] if len(hits) == 1 else None
        rows["_warnings"].append((mid, "umpire_name_not_in_registry", innings_no, over_num,
                                  f"{name!r} -> {hits[0] if resolved else 'unresolved'}"))
        return resolved

    if info["gender"] != gender:
        raise LoadError(f"{path.name}: info.gender {info['gender']!r} but folder says {gender!r}")

    teams = info["teams"]
    tid = {t: team_id(t) for t in teams}

    def team(name):
        if name is None:
            return None
        if name not in tid:
            raise LoadError(f"{path.name}: team {name!r} is not one of info.teams")
        return tid[name]

    dates = info["dates"]
    event = info.get("event", {})
    outcome = info.get("outcome", {})
    by = outcome.get("by", {})
    toss = info["toss"]
    venue_id = info["registry"]["venues"][info["venue"]]

    rows["matches"].append((
        mid, dataset, info["gender"], info["team_type"], info["match_type"],
        _int(info.get("match_type_number")), str(info["season"]),
        dates[0], dates[-1], len(dates), venue_id,
        event.get("name"), _int(event.get("match_number")), _str(event.get("group")),
        event.get("stage"), event.get("sub_name"),
        tid[teams[0]], tid[teams[1]], int(info["balls_per_over"]), _int(info.get("overs")),
        team(toss["winner"]), toss["decision"], bool(toss.get("uncontested", False)),
        team(outcome.get("winner")), _int(by.get("runs")), _int(by.get("wickets")),
        _int(by.get("innings")), outcome.get("result"), outcome.get("method"),
        team(outcome.get("eliminator")), team(outcome.get("bowl_out")),
        json.dumps(info["bowl_out"]) if "bowl_out" in info else None,
        json.dumps(info["missing"]) if "missing" in info else None,
        str(meta["data_version"]), meta["created"], int(meta["revision"]),
    ))

    # name sources -> lookup tables
    for name, person in reg.items():
        rows["name_sources"].append((mid, "person", person, name, None, None))
    rows["name_sources"].append((mid, "venue", venue_id, info["venue"], info.get("city"), None))
    for t in teams:
        rows["name_sources"].append((mid, "team", tid[t], t, None, info["team_type"]))

    supersubs = info.get("supersubs", {})
    player_team: dict[str, str] = {}
    for t, players in info["players"].items():
        for k, p in enumerate(players, 1):
            if pid(p) in player_team and player_team[pid(p)] != t:
                rows["_warnings"].append((mid, "player_in_both_teams", None, None,
                                          f"{p} listed for {player_team[pid(p)]} and {t}"))
            player_team[pid(p)] = t
            rows["match_players"].append((mid, pid(p), team(t), k, supersubs.get(t) == p))
    for key, people in info.get("officials", {}).items():
        for k, p in enumerate(people, 1):
            rows["officials"].append((mid, OFFICIAL_ROLES[key], pid(p), k))
    for p in dict.fromkeys(info.get("player_of_match", [])):
        rows["player_of_match"].append((mid, pid(p)))

    for i, inn in enumerate(j["innings"], 1):
        bat = inn["team"]
        bowl = teams[1] if bat == teams[0] else teams[0]
        target = inn.get("target", {})
        pen = inn.get("penalty_runs", {})
        rows["innings"].append((
            mid, i, team(bat), team(bowl), bool(inn.get("super_over", False)),
            bool(inn.get("declared", False)), bool(inn.get("forfeited", False)),
            _int(target.get("runs")), target.get("overs"),
            int(pen.get("pre", 0)), int(pen.get("post", 0)),
        ))
        for p in dict.fromkeys(inn.get("absent_hurt", [])):
            rows["absent_hurt"].append((mid, i, pid(p)))
        for k, pp in enumerate(inn.get("powerplays", []), 1):
            rows["powerplays"].append((mid, i, k, float(pp["from"]), float(pp["to"]), pp["type"]))
        for over, mo in inn.get("miscounted_overs", {}).items():
            rows["miscounted_overs"].append(
                (mid, i, int(over), int(mo["balls"]), umpire_pid(mo.get("umpire"), i, int(over))))

        for ov in inn["overs"]:
            o = int(ov["over"])
            legal = 0
            for seq, d in enumerate(ov["deliveries"], 1):
                ex = d.get("extras", {})
                is_legal = not ex.get("wides") and not ex.get("noballs")
                if is_legal:
                    legal += 1
                lbn = legal if is_legal else legal + 1
                r = d["runs"]
                key = (mid, i, o, seq)
                rows["balls"].append(key + (
                    lbn, str(d["actual_delivery"]), pid(d["batter"]), pid(d["non_striker"]),
                    pid(d["bowler"]), int(r["batter"]), int(r["extras"]), int(r["total"]),
                    bool(r.get("non_boundary", False)),
                    int(ex.get("wides", 0)), int(ex.get("noballs", 0)), int(ex.get("byes", 0)),
                    int(ex.get("legbyes", 0)), int(ex.get("penalty", 0)),
                ))
                for w_seq, w in enumerate(d.get("wickets", []), 1):
                    kind = w["kind"]
                    rows["wickets"].append(key + (
                        w_seq, pid(w["player_out"]), kind,
                        kind in BOWLER_CREDITED, kind not in NOT_A_DISMISSAL))
                    for f_seq, f in enumerate(w.get("fielders", []), 1):
                        rows["fielding"].append(key + (
                            w_seq, f_seq, pid(f.get("name")), bool(f.get("substitute", False))))
                rv = d.get("review")
                if rv:
                    rows["reviews"].append(key + (
                        team(rv["by"]), pid(rv["batter"]), pid(rv.get("umpire")), rv["decision"],
                        bool(rv.get("umpires_call", False)), rv.get("type")))
                for scope, items in d.get("replacements", {}).items():
                    for r_seq, x in enumerate(items, 1):
                        rows["replacements"].append(key + (
                            scope, r_seq, team(x.get("team")), pid(x["in"]), pid(x.get("out")),
                            x["reason"], x.get("role")))
    return rows


def _parse_job(args):
    path, dataset, gender = args
    try:
        return path, parse_match(Path(path), dataset, gender), None
    except Exception as e:  # noqa: BLE001  reported by the caller
        return path, None, f"{Path(path).name}: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Scanning folders
# ---------------------------------------------------------------------------

@dataclass
class SourceFile:
    match_id: str
    path: Path
    folder: str
    dataset: str
    gender: str
    file_hash: str


def scan(raw_dir: Path = RAW_DIR) -> list[SourceFile]:
    """Every <match_id>.json under raw_dir/<code>_<gender>_json/, with its hash."""
    files: list[SourceFile] = []
    seen: dict[str, str] = {}
    for folder in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        m = FOLDER_RE.match(folder.name)
        if not m:
            print(f"  skip folder {folder.name}: name is not <code>_<gender>_json")
            continue
        for path in sorted(folder.glob("*.json")):
            mid = path.stem
            if mid in seen:
                raise LoadError(f"match {mid} is in both {seen[mid]} and {folder.name}")
            seen[mid] = folder.name
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append(SourceFile(mid, path, folder.name, m.group(1), m.group(2), digest))
    return files


# ---------------------------------------------------------------------------
# Database steps
# ---------------------------------------------------------------------------

def _create_schema(con: duckdb.DuckDBPyConnection, full: bool) -> None:
    if full:
        for level in DELETE_LEVELS:
            for t in level:
                con.execute(f"DROP TABLE IF EXISTS {t}")
        for t in LOOKUPS:
            con.execute(f"DROP TABLE IF EXISTS {t}")
    con.execute(SCHEMA_SQL.read_text())


def _delete_matches(con: duckdb.DuckDBPyConnection, match_ids: list[str]) -> None:
    if not match_ids:
        return
    con.execute("CREATE OR REPLACE TEMP TABLE _del AS SELECT unnest(?::VARCHAR[]) AS match_id",
                [match_ids])
    for level in DELETE_LEVELS:
        con.begin()
        for t in level:
            con.execute(f"DELETE FROM {t} WHERE match_id IN (SELECT match_id FROM _del)")
        con.commit()


def _insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple],
            cols: list[str] | None = None, conflict: str = "") -> None:
    if not rows:
        return
    cols = cols or COLUMNS[table]
    df = pd.DataFrame(rows, columns=cols)
    con.register("_df", df)
    col_list = ", ".join(cols)
    con.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM _df {conflict}")
    con.unregister("_df")


def _insert_chunk(con: duckdb.DuckDBPyConnection, rows: dict[str, list[tuple]]) -> None:
    # Lookups first (new IDs only; names are fixed up after the whole run).
    ns = rows["name_sources"]
    people = {r[2]: (r[2], r[3]) for r in ns if r[1] == "person"}
    venues = {r[2]: (r[2], r[3], r[4]) for r in ns if r[1] == "venue"}
    teams = {r[2]: (r[2], r[3], r[5]) for r in ns if r[1] == "team"}
    _insert(con, "people", list(people.values()), ["person_id", "name"], "ON CONFLICT DO NOTHING")
    _insert(con, "venues", list(venues.values()), ["venue_id", "name", "city"], "ON CONFLICT DO NOTHING")
    _insert(con, "teams", list(teams.values()), ["team_id", "name", "team_type"], "ON CONFLICT DO NOTHING")
    for table in COLUMNS:
        if table in rows:
            _insert(con, table, rows[table])
    now = datetime.now()
    _insert(con, "load_warnings", [w + (now,) for w in rows.get("_warnings", [])],
            ["match_id", "check_name", "innings_no", "over_num", "detail", "found_at"])


def _refresh_lookup_names(con: duckdb.DuckDBPyConnection) -> None:
    """Set each lookup name to the one used in the most recent match (date, then match_id)."""
    latest = """
        SELECT s.key_id,
               arg_max(s.name, (m.start_date, TRY_CAST(m.match_id AS BIGINT), m.match_id)) AS name,
               arg_max(s.city, (m.start_date, TRY_CAST(m.match_id AS BIGINT), m.match_id))
                   FILTER (WHERE s.city IS NOT NULL) AS city,
               arg_max(s.team_type, (m.start_date, TRY_CAST(m.match_id AS BIGINT), m.match_id)) AS team_type
        FROM name_sources s JOIN matches m USING (match_id)
        WHERE s.kind = '{kind}' GROUP BY s.key_id"""
    con.execute(f"""UPDATE people SET name = x.name FROM ({latest.format(kind='person')}) x
                    WHERE people.person_id = x.key_id AND people.name IS DISTINCT FROM x.name""")
    con.execute(f"""UPDATE venues SET name = x.name, city = x.city FROM ({latest.format(kind='venue')}) x
                    WHERE venues.venue_id = x.key_id
                      AND (venues.name IS DISTINCT FROM x.name OR venues.city IS DISTINCT FROM x.city)""")
    con.execute(f"""UPDATE teams SET team_type = x.team_type FROM ({latest.format(kind='team')}) x
                    WHERE teams.team_id = x.key_id AND teams.team_type IS DISTINCT FROM x.team_type""")


def _check_team_ids(con: duckdb.DuckDBPyConnection) -> None:
    clash = con.execute("""
        SELECT key_id, list(DISTINCT name) FROM name_sources WHERE kind = 'team'
        GROUP BY key_id HAVING count(DISTINCT name) > 1""").fetchall()
    if clash:
        raise LoadError(f"team_id hash collision: {clash}")


# ---------------------------------------------------------------------------
# Validation (SCHEMA.md section 7)
# ---------------------------------------------------------------------------

ERROR_CHECKS = {
    "player_out not in match_players": """
        SELECT w.match_id, w.innings_no, w.over_num, w.player_out_id
        FROM wickets w JOIN _new USING (match_id)
        LEFT JOIN match_players mp ON mp.match_id = w.match_id AND mp.person_id = w.player_out_id
        WHERE mp.person_id IS NULL""",
    "legal_ball_no does not match actual_delivery": """
        SELECT b.match_id, b.innings_no, b.over_num, b.ball_seq, b.actual_delivery, b.legal_ball_no
        FROM balls b JOIN _new USING (match_id)
        WHERE b.actual_delivery <> b.over_num || '.' || b.legal_ball_no""",
    "matches per folder differ from files": """
        SELECT f.folder, f.files, coalesce(l.loaded, 0) AS loaded
        FROM _files f FULL JOIN (SELECT folder, count(*) AS loaded FROM load_log GROUP BY folder) l
          USING (folder)
        WHERE f.files IS DISTINCT FROM l.loaded""",
}

WARNING_CHECKS = {
    # (match_id, innings_no, over_num, detail)
    "over_too_long": """
        SELECT b.match_id, b.innings_no, b.over_num,
               count(*) FILTER (WHERE b.wides = 0 AND b.noballs = 0) || ' legal balls, balls_per_over '
                   || any_value(m.balls_per_over)
        FROM balls b JOIN _new USING (match_id) JOIN matches m USING (match_id)
        LEFT JOIN miscounted_overs mo
          ON mo.match_id = b.match_id AND mo.innings_no = b.innings_no AND mo.over_num = b.over_num
        WHERE mo.over_num IS NULL
        GROUP BY b.match_id, b.innings_no, b.over_num
        HAVING count(*) FILTER (WHERE b.wides = 0 AND b.noballs = 0) > any_value(m.balls_per_over)""",
    "miscount_mismatch": """
        SELECT mo.match_id, mo.innings_no, mo.over_num,
               coalesce(x.legal, 0) || ' legal balls, miscounted_overs says ' || mo.balls
        FROM miscounted_overs mo JOIN _new USING (match_id)
        LEFT JOIN (SELECT match_id, innings_no, over_num,
                          count(*) FILTER (WHERE wides = 0 AND noballs = 0) AS legal
                   FROM balls GROUP BY ALL) x USING (match_id, innings_no, over_num)
        WHERE coalesce(x.legal, 0) <> mo.balls""",
}


def _validate(con: duckdb.DuckDBPyConnection) -> int:
    errors = []
    for name, q in ERROR_CHECKS.items():
        bad = con.execute(q).fetchall()
        if bad:
            errors.append(f"{name}: {len(bad)} rows, e.g. {bad[:3]}")
    if errors:
        raise LoadError("validation failed:\n  " + "\n  ".join(errors))
    now = datetime.now()
    n = 0
    for name, q in WARNING_CHECKS.items():
        found = con.execute(q).fetchall()
        _insert(con, "load_warnings", [(m, name, i, o, d, now) for m, i, o, d in found],
                ["match_id", "check_name", "innings_no", "over_num", "detail", "found_at"])
        n += len(found)
    return n


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load(full: bool = False, raw_dir: Path = RAW_DIR, db_path: Path = DB_PATH,
         workers: int | None = None, chunk_size: int = 500, verbose: bool = True) -> dict:
    """Load data/raw/json into the database. Returns counts of what happened."""
    t0 = time.time()
    say = print if verbose else (lambda *a, **k: None)

    files = scan(raw_dir)
    say(f"Scanned {len(files):,} files in {time.time() - t0:.1f}s")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        _create_schema(con, full)
        logged = dict(con.execute("SELECT match_id, file_hash FROM load_log").fetchall())
        # Matches with rows but no load_log entry (left by a failed run) are reloaded.
        stray = {r[0] for r in con.execute(
            "SELECT match_id FROM matches WHERE match_id NOT IN (SELECT match_id FROM load_log)").fetchall()}

        by_id = {f.match_id: f for f in files}
        new = [f for f in files if f.match_id not in logged]
        changed = [f for f in files if f.match_id in logged and logged[f.match_id] != f.file_hash]
        gone = [m for m in logged if m not in by_id]
        todo = new + changed
        say(f"  new {len(new):,}, changed {len(changed):,}, "
            f"unchanged {len(files) - len(todo):,}, gone {len(gone):,}")

        _delete_matches(con, [f.match_id for f in changed] + gone + sorted(stray))

        con.execute("CREATE OR REPLACE TEMP TABLE _new AS SELECT unnest(?::VARCHAR[]) AS match_id",
                    [[f.match_id for f in todo]])
        folder_counts: dict[str, int] = {}
        for f in files:
            folder_counts[f.folder] = folder_counts.get(f.folder, 0) + 1
        con.execute("CREATE OR REPLACE TEMP TABLE _files AS SELECT * FROM (VALUES "
                    + ", ".join(f"('{k}', {v})" for k, v in folder_counts.items())
                    + ") t(folder, files)" if folder_counts else
                    "CREATE OR REPLACE TEMP TABLE _files (folder VARCHAR, files BIGINT)")

        con.begin()
        try:
            n_warn = 0
            if todo:
                now = datetime.now()
                jobs = [(str(f.path), f.dataset, f.gender) for f in todo]
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    for start in range(0, len(jobs), chunk_size):
                        chunk = jobs[start:start + chunk_size]
                        merged: dict[str, list[tuple]] = {t: [] for t in COLUMNS}
                        merged["_warnings"] = []
                        failures = []
                        for path, rows, err in pool.map(_parse_job, chunk, chunksize=16):
                            if err:
                                failures.append(err)
                                continue
                            for t, r in rows.items():
                                merged[t].extend(r)
                            f = by_id[Path(path).stem]
                            merged["load_log"].append(
                                (f.match_id, f.folder, rows["matches"][0][-1], f.file_hash, now))
                        if failures:
                            raise LoadError(f"{len(failures)} files failed to parse, e.g.\n  "
                                            + "\n  ".join(failures[:5]))
                        _insert_chunk(con, merged)
                        say(f"  loaded {min(start + chunk_size, len(jobs)):,}/{len(jobs):,} "
                            f"({time.time() - t0:.0f}s)")
            _check_team_ids(con)
            _refresh_lookup_names(con)
            n_warn = _validate(con)
            con.commit()
        except Exception:
            con.rollback()
            raise

        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in LOOKUPS + list(COLUMNS) + ["load_warnings"]}
        result = {"new": len(new), "changed": len(changed), "gone": len(gone),
                  "warnings": n_warn, "seconds": round(time.time() - t0, 1), "rows": counts}
        say(f"Done in {result['seconds']}s, {n_warn} new warnings, "
            f"{counts['matches']:,} matches, {counts['balls']:,} balls")
        return result
    finally:
        con.close()
