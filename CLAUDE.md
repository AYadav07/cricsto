# CLAUDE.md: cricsto-data

Claude Code reads this file automatically. It holds the context, decisions and next steps for this repo, so a new session can continue without re-explaining. Keep it up to date when decisions change.

## What this project is

**@cricsto ("Cricket by Numbers")** is a data-first cricket account on X, run by me as a long-term side project. Posts are short, evidence-first stats and charts that settle cricket debates with numbers.

This repo is the **data engine** behind it:

```
Cricsheet ball-by-ball data → local DuckDB database → SQL insights → on-brand chart PNGs → posts on X
```

Typical loop: a question people are debating ("Who scores fastest at the death since 2024?") → a SQL query → a result table → a chart → a post.

## Repo layout (2026-11-19: split into three modules)

Run every command from the repo root. Each module has its own README.

```
cricsheet/   ball-by-ball database (Python package `cricsheet`)
             *.py (load_json, refresh, db, insights, views), schema.sql, views.sql,
             queries/*.sql, scripts/ (refresh, build_db, get_db.sh, manifest),
             data/ (raw/json, cricsto.duckdb, reference/bowler_types.csv), tests/, README.md, SCHEMA.md
history/     pre-2002 scorecard database, fully separate (build.py, db.py, queries/, raw/, history.duckdb, README.md, SCHEMA.md)
posts/       @cricsto output side (Python package `posts`): charts.py, fonts/, batches/ (one script per post batch), output/ (PNGs), README.md (brand, voice, checklist)
.github/workflows/refresh-data.yml   weekly Cricsheet refresh → release `data-latest`
README.md    overview of the three modules
```

Imports: `from cricsheet import insights as ins`, `from cricsheet.db import run_query, sql`, `from posts import charts`; for history, `sys.path.insert(0, "history"); from db import run, sql, find_player`. Before 2026-11-19 the Cricsheet code was the `cricsto/` package, with `data/`, `queries/`, `scripts/`, `tests/`, `examples/`, `fonts/` and `output/` at the top level. Older notes may use those paths.

## Current state (2026-11-10: v2 complete, on `main`; 2026-11-19: cloud data refresh + separate history DB)

Latest session (2026-11-19, Claude in the claude.ai app, working on this folder through the desktop app):
- Weekly GitHub Action that refreshes Cricsheet data and publishes the database as a release (PR #1, merged). See "Data from anywhere".
- A second, fully separate database of pre-2002 scorecards in `history/`. See "History database".
- Repo split into three modules: `cricsheet/`, `history/`, `posts/`. See "Repo layout".


v2 builds `cricsheet/data/cricsto.duckdb` from Cricsheet JSON only. The v1 CSV pipeline was removed; its code is in commit `85bda72`. `cricsheet/README.md` is the user guide; `cricsheet/SCHEMA.md` is the full reference (every table and column with its JSON source, keys, views, a JSON coverage map, cricket rules, loading, validation, refresh, data notes and example queries).

- `python cricsheet/scripts/build_db.py`: incremental load from `cricsheet/data/raw/json/` (about 1 s when nothing changed), then the views. `--full` drops and reloads everything (about 40 s for 11,340 matches, 5.1M balls).
- `cricsheet/schema.sql`: 19 tables with primary and foreign keys (cricsheet/SCHEMA.md §3).
- `cricsheet/load_json.py`: the loader: scan, hash, new/changed/unchanged/gone, parallel parse, chunked insert, lookup names from `name_sources`, validation and `load_warnings`.
- `cricsheet/views.sql` + `cricsheet/views.py`: `deliveries`, `batter_innings`, `bowler_innings`, `dismissals` with v1 column names plus IDs. Men's IPL/T20I/ODI totals match v1 on all 114 seasons (cricsheet/SCHEMA.md §4).
- `python cricsheet/scripts/refresh.py`: weekly refresh from Cricsheet's recently-added zips (`--full` monthly: re-download the 8 full zips; `--dry-run` to preview), then the incremental load. Code in `cricsheet/refresh.py` (cricsheet/SCHEMA.md §7a).
- `cricsheet/db.py`: query helpers (`connect()`, `run_query()`, `sql()`).
- `cricsheet/insights.py`: one-line insight functions backed by `cricsheet/queries/*.sql` (`$param` placeholders). All run on v2.
- `posts/charts.py`: branded `bar()`, `line()`, `scatter()`, `save()` → `posts/output/<name>.png` (1600×900). Horizontal bars widen the left margin to fit the longest name; `scatter()` takes `label_offsets` to move colliding labels. Brand fonts are static instances in `posts/fonts/` (Space Grotesk Medium/Bold, Inter Regular/SemiBold/Bold, cut from the Google Fonts variable files because matplotlib can't pick weights from a variable font).
- `posts/batches/first_post.py`: end-to-end example; runs on v2.
- `posts/batches/batch_2026_11_10.py`: first post batch (IPL phase run rates, 200+ totals and chases, death hitters strike rate vs dot %); rerun to regenerate the charts and print every number used.
- `cricsheet/queries/big_total_chases.sql` / `insights.big_total_chases()`: per season, first-innings totals ≥ `$threshold` and how many were chased (completed matches with a winner, D/L excluded).
- `cricsheet/data/reference/bowler_types.csv`: manual bowler → pace/spin mapping, columns `person_id,name,bowler_type` (Cricsheet has no bowling style). Currently empty; `insights.bowlers_to_classify()` lists bowlers to add.
- `cricsheet/tests/`: `python -m pytest cricsheet/tests`, 46 tests. Fixture-based loader/view tests, plus checks on the real database against `cricsheet/tests/baseline_v1/` (skipped if the database isn't built).

## Decisions made (and why)

1. **Relational, not MongoDB.** The work is analytical (group-bys, joins over millions of balls). SQL is far simpler and faster for that than Mongo aggregation pipelines. Raw JSON stays on disk as the source of truth.
2. **DuckDB, not Postgres.** This is OLAP for one user on a laptop: columnar, very fast aggregations, one file, no server, reads CSV/JSON directly. Postgres only if Cricsto becomes a multi-user web app/API; migration is easy (DuckDB's postgres extension).
3. **Move to Cricsheet JSON.** JSON is the official, most complete format and a superset of the CSV. JSON-only extras: DRS reviews, player replacements (Impact Player, concussion subs), powerplay periods.
4. **Parse JSON in Python, query in DuckDB.** Several JSON parts use names as object keys (`players`, `registry.people`, `supersubs`), which flatten more clearly in code than with `read_json`.
5. **Backward compatibility.** The `deliveries`, `batter_innings`, `dismissals` views keep their current column names so existing queries and `insights.py` keep working.
6. **Normalized tables, IDs not names (2026-11-10).** Names aren't unique: 90 names belong to more than one person (e.g. 4 "Rashid Khan"s), and 25 people / 20 venues changed names. So `people`, `venues` and `teams` are lookup tables with one row per ID and one name (from the most recent match). Every other table stores only IDs, with foreign keys. `team_id` is our own key (`md5(name)[:8]`); Cricsheet has no team IDs.
7. **Ball numbering follows Cricsheet (2026-11-10).** `legal_ball_no` counts legal balls only; a wide or no-ball carries the number of the ball being attempted, so it always matches `actual_delivery` (verified on all 5.1M deliveries).
8. **Validation: errors vs warnings.** Errors stop the load (orphan IDs, numbering mismatch, gender/folder mismatch); data oddities such as an unrecorded 7-ball over go to `load_warnings` and the load continues. A full load gives exactly 4 warnings, all genuine Cricsheet oddities (cricsheet/SCHEMA.md §8).
9. **Loader and refresh are separate.** The loader only reads `cricsheet/data/raw/json/` and is incremental (new / changed / unchanged / gone, via `load_log`). The refresh job only puts files there: a weekly diff from Cricsheet's `recently_added_7_*_json.zip`, plus a monthly full sync of the 8 zips to catch corrections and withdrawals.
10. **Foreign keys kept; deletes child-first (2026-11-10).** DuckDB 2.0 allows updating referenced rows but not deleting a parent in the same transaction as its children. So reloads delete level by level in committed transactions, then insert in one transaction. A match is always fully loaded or absent, and a failed run heals on the next run.
11. **`is_wicket` excludes retirements (2026-11-10).** In `deliveries`, retired hurt / retired not out are not wickets (v1 counted them). `player_dismissed` / `wicket_type` still show every wicket entry.
12. **Queries group by ID (2026-11-10).** `cricsheet/queries/*.sql` group players by `batter_id` / `bowler_id` and venues by `venue_id`, and show the latest name. Outs come from `striker_out` (retirements don't count). Every `ORDER BY` has a tie-break, and super overs are excluded with `NOT is_super_over`. `bowler_types.csv` is keyed by `person_id` (`insights.bowlers_to_classify()` lists who's missing). `find_player()` searches every name a person has used and returns `person_id`.
13. **Database shipped as a release asset, not committed (2026-11-19).** The DuckDB file is a few hundred MB: over GitHub's 100 MB file limit, and a weekly commit would bloat history. A GitHub Action rebuilds it and replaces the `data-latest` release file instead.
14. **Pre-2002 data is a separate database (2026-11-19).** No open ball-by-ball exists before Cricsheet's coverage, so scorecards go into `history/history.duckdb` with their own IDs and code. Kept separate at the user's request: never merged, joined or summed with the Cricsheet database.

## Raw data (v2)

`cricsheet/data/raw/json/<code>_<gender>_json/` (git-ignored; on a fresh clone, `python cricsheet/scripts/refresh.py --full` downloads it and builds the database). There are 8 folders (`ipl_male`, `wpl_female`, `odis_male`, `odis_female`, `t20s_male`, `t20s_female`, `tests_male`, `tests_female`) holding 11,340 matches in Cricsheet JSON 1.3.0. It is the only raw data; the v1 CSV is gone.

## Data from anywhere (phone / cloud sessions)

Added 2026-11-19 (PR #1, merged to `main`). Lets Claude query the data from the phone or any cloud session without this laptop.

- `.github/workflows/refresh-data.yml`: runs every Monday 03:00 IST (`--days 30` recently-added refresh), a full sync on the 1st of each month 04:00 IST, or by hand from **Actions → Refresh data → Run workflow** (tick "Full sync"). It caches `cricsheet/data/raw` + the database between runs, runs `python -m pytest cricsheet/tests`, and only if they pass publishes `cricsto.duckdb.gz` and `manifest.json` to the release **`data-latest`** (replacing the previous files). The database is never committed (too big for git, and `.gitignore` excludes it).
- `cricsheet/scripts/get_db.sh`: downloads and unzips the release to `cricsheet/data/cricsto.duckdb` and `cricsheet/data/manifest.json`. Uses `gh release download` if the GitHub CLI is signed in (needed if the repo is ever made private), otherwise the public link.
- `cricsheet/scripts/manifest.py`: prints build time, total matches/balls and the latest match per dataset/gender. Check it before posting; for matches newer than `latest_match`, use the live scorecard.
- First run 2026-11-19 succeeded: 11,340 matches, 5,127,683 balls, latest match 2026-11-02. Download + open verified from a cloud session with DuckDB 2.0.
- Phone workflow: "Cricsto: <question>" → Claude runs `bash cricsheet/scripts/get_db.sh`, queries, charts with `posts/charts.py`, sends the PNG + post text → the user posts from the X app. No automated posting.
- Network: Claude cloud sessions and the desktop app's Linux shell can reach GitHub (and package registries) but **not** cricsheet.org, Hugging Face, Kaggle or ESPNcricinfo. That's why the refresh runs on GitHub's machines.
- Repo is public (`AYadav07/cricsto`), so the release is public. Cricsheet data may be shared with credit; the release notes credit Cricsheet.

## History database (separate, pre-2002 scorecards)

Added 2026-11-19. **A second, fully separate database. Never merge it with `cricsheet/data/cricsto.duckdb`**: different source, different player/match IDs, scorecard-level not ball-by-ball. Never join the two databases or add their numbers together; if a post uses both, say which numbers come from which.

- Why: Cricsheet ball-by-ball starts Dec 2001 (Tests) / Jun 2002 (ODIs); no open ball-by-ball exists for older matches. This gives full scorecards back to 1877.
- Source: Hugging Face `bhuvaneshprasad/test-cricket-dataset-1877-2014` and `bhuvaneshprasad/odi-cricket-dataset-1971-2014` (ESPNcricinfo-derived CSVs; despite the names both run to Dec 2023). Cloned into `history/raw/test/` and `history/raw/odi/` (git-ignored). No stated licence: analyse and post derived stats with credit, don't republish the raw files.
- Contents: men's Tests 2,520 (1,581 before 2002) and ODIs 4,717 (1,782 before 2002). Tables `matches`, `match_players`, `innings`, `batting`, `bowling`, `fall_of_wickets`, `partnerships`, `players`, `load_warnings`, `load_info`; views `batter_innings`, `bowler_innings`, `match_results`.
- Files, all in `history/`: `build.py` (full rebuild from `raw/` into `history.duckdb`, about 10 s), `schema.sql`, `views.sql`, `db.py` (`run()`, `sql()`, `find_player()`), `queries/career_batting.sql`, `queries/career_bowling.sql`, `README.md` (overview), **`SCHEMA.md` (full reference: every table and column, coverage by decade, rules, tested example queries; read this before querying)**.
- It's a fixed snapshot: no refresh needed. Rebuild only if `build.py` changes.
- Data rules (details in `history/SCHEMA.md` §7): NULL = not recorded. Balls faced are patchy before 1980; dots, fall-of-wicket overs and the dismissing bowler on the batting card only from ~2000; bowler `wides`/`noballs` are 0 when not recorded (don't use them before the 1990s). 8-ball overs (179 Tests, 13 ODIs) are detected from figures ending .6/.7 and `bowling.balls` is corrected; economy and strike rates are per 6 balls. Count appearances from `match_players`. Names are full names (`Donald Bradman`); group by `player_id`.
- Checks: `load_warnings` has 63 innings whose card doesn't add up, 41 bowler-wicket mismatches, 68 IDs with no player row, and 6 abandoned matches. Career totals were spot-checked against published records (Bradman 6,996 at 99.94; Tendulkar 15,921 / 18,426 runs and 200 / 463 matches; Muralidaran 800; Warne 708; Grimmett 14,513 balls after the 8-ball fix).
- Status 2026-11-19: built on this laptop with DuckDB 1.5.6 (Claude's Linux shell; readable by 2.0). **Not committed yet** and **not in the `data-latest` release yet**.

## Next ideas

v2 was built in steps 1–6 on branch `v2-json` (2026-11-10) and merged into `main`.

Open items:
- Commit `history/` (code and docs only; `history/raw/` and `history/*.duckdb` are git-ignored) and the `.gitignore` / `CLAUDE.md` changes.
- Upload `history/history.duckdb` to the `data-latest` release once by hand (Edit release → attach), then add it to `cricsheet/scripts/get_db.sh` so phone sessions can query it too. It doesn't change, so it doesn't need the Action.
- Optional for history: more queries (venue / toss results, chases by target, batting position, partnership records, pace vs spin via `players.bowling_style`), pytest checks for the career spot-checks and the 8-ball fix.
- `players.bowling_style` in the history DB could help fill `cricsheet/data/reference/bowler_types.csv`, but the IDs differ: match by name + dates, and check by hand.
- Fill `cricsheet/data/reference/bowler_types.csv` (`insights.bowlers_to_classify()` lists who's missing).
- Unknown: whether corrected matches reappear in Cricsheet's "recently added" zips. Monthly `refresh.py --full` covers it either way.

Later ideas: `player_in_country` query (player × format × country, e.g. Rohit's ODIs in New Zealand, via a city/venue → country mapping), fielding leaderboards, DRS success rates, Impact Player analysis.

## Rules for this repo

- **Never state a stat that didn't come from a query run against this database.** No invented or remembered numbers.
- Check the result table before charting; flag small samples or odd values.
- Chart subtitles always state sample size and filters (min balls, seasons, phase).
- Credit "Data: Cricsheet" (the chart template does this).
- New reusable questions go in `cricsheet/queries/<name>.sql` with `$params`, wrapped in `cricsheet/insights.py`. Group by IDs (`batter_id`, `bowler_id`, `venue_id`), never by names, and give `ORDER BY` a tie-break.
- After changing the loader, views or queries, run `python -m pytest cricsheet/tests`.
- Don't commit `cricsheet/data/raw/`, `history/raw/`, `*.duckdb` or `posts/output/` (already in `.gitignore`).
- Close any open DuckDB connection (DBeaver, CLI) before rebuilding: DuckDB allows one writer.

## Cricket definitions used

- T20 phases: powerplay overs 1–6, middle 7–15, death 16–20. ODI: 1–10, 11–40, 41–50. Tests: no phase.
- Legal ball: not a wide or no-ball. Ball faced by the batter: not a wide.
- Bowler's runs: runs off the bat + wides + no-balls (byes and leg byes aren't charged).
- Bowler-credited wickets: bowled, caught, caught and bowled, lbw, stumped, hit wicket.
- Boundary: 4 or 6 off the bat, unless `non_boundary` is set.
- Dismissal (batter is out): any wicket kind except retired hurt and retired not out.
- Super overs are excluded from most stats.

## Brand (for charts)

- Navy `#0E1A2B` background, cricket-ball red `#D94B3D` accent, cream `#F2E8D5` text, muted `#C9C2B3`, amber `#E8A33D` second series.
- Fonts: Space Grotesk (headings), Inter (body). Handle mark `@cricsto` bottom-right.

## Voice (for post drafts)

Sharp, evidence-first, curious. Hook = a question; answer = one clear chart plus 1–2 lines. No hot takes without numbers; never mock players or fans.

## Environment

- Windows 11 laptop, VS Code with the Claude Code extension; Python 3 venv in `.venv/`.
- Install: `pip install -r requirements.txt` (duckdb, pandas, matplotlib, jupyterlab, pytest). Tested with DuckDB 2.0.0.
- Tests: `python -m pytest cricsheet/tests` (the real-data tests need the database built).
- Run SQL directly: `duckdb cricsheet/data/cricsto.duckdb`, or DBeaver → DuckDB connection. History: `duckdb history/history.duckdb`.
- DuckDB 2.0 note: relations no longer have `fetchone()`. Use `con.execute(sql).fetchall()` / `.fetchone()` or `.df()`.
- GitHub CLI (`gh`) isn't installed on Windows yet (`winget install --id GitHub.cli`, then `gh auth login`). Only needed if the repo goes private.
- Claude in the claude.ai app can edit this folder through the desktop app's folder connection, **except `.github/workflows/`** (blocked: workflow files are added by hand). Its Linux shell has Python 3.10 with DuckDB 1.5.x only, so it can't open `cricsheet/data/cricsto.duckdb` (DuckDB 2.0 format). Its git also sees CRLF line-ending noise, so commit from Windows git or VS Code.
