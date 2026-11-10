# CLAUDE.md: cricsto-data

Claude Code reads this file automatically. It holds the context, decisions and next steps for this repo, so a new session can continue without re-explaining. Keep it up to date when decisions change.

## What this project is

**@cricsto ("Cricket by Numbers")** is a data-first cricket account on X, run by me as a long-term side project. Posts are short, evidence-first stats and charts that settle cricket debates with numbers.

This repo is the **data engine** behind it:

```
Cricsheet ball-by-ball data → local DuckDB database → SQL insights → on-brand chart PNGs → posts on X
```

Typical loop: a question people are debating ("Who scores fastest at the death since 2024?") → a SQL query → a result table → a chart → a post.

## Current state (2026-11-10: v1 removed, v2 being built)

The v1 CSV pipeline was removed on 2026-11-10. That covered the CSV data in `data/raw/ipl|odis|t20s`, the old `data/cricsto.duckdb`, `scripts/build_db.py`, `download.py`, `refresh.py` and the CSV loader in `cricsto/db.py`. The v1 code is in git commit `85bda72`. **There is no database until the v2 loader exists**, so `insights.py` won't run yet.

What's still here:
- `data/raw/json/`: the Cricsheet JSON (source for v2, see "Raw data (v2)").
- `cricsto/db.py`: query helpers only (`connect()`, `run_query()`, `sql()`).
- `cricsto/views.sql`: **still v1** (reads `balls_raw`); rewritten in step 2.
- `cricsto/insights.py`: one-line insight functions backed by `queries/*.sql` (`$param` placeholders).
- `cricsto/charts.py`: branded `bar()`, `line()`, `save()` → `output/<name>.png` (1600×900).
- `examples/first_post.py`: end-to-end example.
- `data/reference/bowler_types.csv`: manual bowler → pace/spin mapping (Cricsheet has no bowling style). Currently empty.
- `tests/baseline_v1/`: v1 query results saved before removal, for comparing v2 against (see its README).

## Decisions made (and why)

1. **Relational, not MongoDB.** The work is analytical (group-bys, joins over millions of balls). SQL is far simpler and faster for that than Mongo aggregation pipelines. Raw JSON stays on disk as the source of truth.
2. **DuckDB, not Postgres.** This is OLAP for one user on a laptop: columnar, very fast aggregations, one file, no server, reads CSV/JSON directly. Postgres only if Cricsto becomes a multi-user web app/API; migration is easy (DuckDB's postgres extension).
3. **Move to Cricsheet JSON.** JSON is the official, most complete format and a superset of the CSV. JSON-only extras: DRS reviews, player replacements (Impact Player, concussion subs), powerplay periods.
4. **Parse JSON in Python, query in DuckDB.** Several JSON parts use names as object keys (`players`, `registry.people`, `supersubs`), which flatten more clearly in code than with `read_json`.
5. **Backward compatibility.** The `deliveries`, `batter_innings`, `dismissals` views keep their current column names so existing queries and `insights.py` keep working.
6. **Normalized tables, IDs not names (2026-11-10).** Names aren't unique: 90 names belong to more than one person (e.g. 4 "Rashid Khan"s), and 25 people / 20 venues changed names. So `people`, `venues` and `teams` are lookup tables with one row per ID and one name (from the most recent match). Every other table stores only IDs, with foreign keys. `team_id` is our own key (`md5(name)[:8]`); Cricsheet has no team IDs.
7. **Ball numbering follows Cricsheet (2026-11-10).** `legal_ball_no` counts legal balls only; a wide or no-ball carries the number of the ball being attempted, so it always matches `actual_delivery` (verified on all 5.1M deliveries).
8. **Validation: errors vs warnings.** Errors stop the load (orphan IDs, numbering mismatch, gender/folder mismatch); data oddities such as an unrecorded 7-ball over go to `load_warnings` and the load continues.
9. **Loader and refresh are separate.** The loader only reads `data/raw/json/` and is incremental (new / changed / unchanged / gone, via `load_log`). The refresh job only puts files there: a weekly diff from Cricsheet's `recently_added_7_*_json.zip`, plus a monthly full sync of the 8 zips to catch corrections and withdrawals.

## Raw data (v2)

The JSON is already downloaded: `data/raw/json/<code>_<gender>_json/`. There are 8 folders (`ipl_male`, `wpl_female`, `odis_male`, `odis_female`, `t20s_male`, `t20s_female`, `tests_male`, `tests_female`) holding 11,340 matches in Cricsheet JSON 1.3.0. It is the only raw data; the v1 CSV is gone.

## Next task: implement the JSON pipeline (v2)

The full design is in **`SCHEMA.md`** (repo root). Read it before starting. It has every table and column with its JSON source, keys, views, a JSON coverage map, cricket rules, loading and validation, refresh, data notes and example queries. Every open question in it has been answered from the real files.

Order (design done 2026-11-10; next is step 1):
1. Write `cricsto/schema.sql` (CREATE TABLE with PK/FK), `cricsto/load_json.py` (incremental loader: parser → per-table DataFrames → bulk insert in one transaction per batch) and `scripts/build_db.py` (runs the loader; `--full` for a rebuild). Build a fresh `data/cricsto.duckdb` from `data/raw/json/` only. First test whether DuckDB lets the loader update `people.name` while other rows reference it; if not, keep the PKs, drop the FKs and rely on the orphan check (SCHEMA §7).
2. Rewrite `cricsto/views.sql` on the new tables, keeping v1 column names; compare v1 and v2 results for the same IPL matches.
3. Add validation (errors + `load_warnings`) and tests with fixture JSON in `tests/fixtures/`.
4. Write the refresh job: weekly diff + monthly full sync + routing rules (SCHEMA §7a), with the routing tested on the existing files.
5. Confirm every function in `cricsto/insights.py` and `examples/first_post.py` still runs; switch `batter_vs_bowler_type` / `bowler_types.csv` to `person_id`.
6. Update `README.md` and this file.

Later ideas: `player_in_country` query (player × format × country, e.g. Rohit's ODIs in New Zealand, via a city/venue → country mapping), fielding leaderboards, DRS success rates, Impact Player analysis.

## Rules for this repo

- **Never state a stat that didn't come from a query run against this database.** No invented or remembered numbers.
- Check the result table before charting; flag small samples or odd values.
- Chart subtitles always state sample size and filters (min balls, seasons, phase).
- Credit "Data: Cricsheet" (the chart template does this).
- New reusable questions go in `queries/<name>.sql` with `$params`, wrapped in `cricsto/insights.py`.
- Don't commit `data/raw/`, `*.duckdb` or `output/` (already in `.gitignore`).
- Close any open DuckDB connection (DBeaver, CLI) before rebuilding: DuckDB allows one writer.

## Cricket definitions used

- T20 phases: powerplay overs 1–6, middle 7–15, death 16–20. ODI: 1–10, 11–40, 41–50. Tests: no phase.
- Legal ball: not a wide or no-ball. Ball faced by the batter: not a wide.
- Bowler's runs: runs off the bat + wides + no-balls (byes and leg byes aren't charged).
- Bowler-credited wickets: bowled, caught, caught and bowled, lbw, stumped, hit wicket.
- Boundary: 4 or 6 off the bat, unless `non_boundary` is set.
- Super overs are excluded from most stats.

## Brand (for charts)

- Navy `#0E1A2B` background, cricket-ball red `#D94B3D` accent, cream `#F2E8D5` text, muted `#C9C2B3`, amber `#E8A33D` second series.
- Fonts: Space Grotesk (headings), Inter (body). Handle mark `@cricsto` bottom-right.

## Voice (for post drafts)

Sharp, evidence-first, curious. Hook = a question; answer = one clear chart plus 1–2 lines. No hot takes without numbers; never mock players or fans.

## Environment

- Windows 11 laptop, VS Code with the Claude Code extension; Python 3 venv in `.venv/`.
- Install: `pip install -r requirements.txt` (duckdb, pandas, matplotlib, jupyterlab).
- Run SQL directly: `duckdb data/cricsto.duckdb`, or DBeaver → DuckDB connection.
