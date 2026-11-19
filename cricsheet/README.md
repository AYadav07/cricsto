# cricsheet: ball-by-ball database

Cricsheet ball-by-ball JSON → DuckDB (`cricsheet/data/cricsto.duckdb`) → ready-made insights.
One of three modules in this repo (see the top-level `README.md`). Separate from `history/`:
never join or sum the two databases. Charts and posts live in `posts/`.

```
cricsheet/scripts/refresh.py    get new Cricsheet data into cricsheet/data/raw/json/, then update the database
cricsheet/scripts/build_db.py   build / update cricsheet/data/cricsto.duckdb from cricsheet/data/raw/json/
cricsheet/scripts/get_db.sh     download the database the GitHub Action built (no laptop needed)
cricsheet/scripts/manifest.py   how fresh the database is (latest match per dataset)
cricsheet/schema.sql            the tables (one per real-world thing, joined by IDs)
cricsheet/load_json.py          incremental JSON loader with validation
cricsheet/refresh.py            Cricsheet downloads and routing into folders
cricsheet/views.sql             flat views: deliveries, batter_innings, bowler_innings, dismissals
cricsheet/db.py                 connect(), run_query(), sql()
cricsheet/insights.py           ready-made insights (one function per question)
cricsheet/queries/*.sql         the SQL behind each insight; add your own here
cricsheet/data/reference/       bowler_types.csv (your pace/spin list)
cricsheet/SCHEMA.md             full reference: every table, column, key, view and rule
cricsheet/tests/                python -m pytest cricsheet/tests
```

Run every command from the repo root.

## 1. Set up (once)

See the top-level `README.md` (virtual env + `pip install -r requirements.txt`).

## 2. Get the data

```bash
python cricsheet/scripts/refresh.py --full     # first time: downloads the 8 Cricsheet zips and builds the database
```

That fills `cricsheet/data/raw/json/` with one folder per competition and gender:

| Folder | What |
|---|---|
| `ipl_male_json` | Indian Premier League |
| `wpl_female_json` | Women's Premier League |
| `t20s_male_json`, `t20s_female_json` | T20 internationals |
| `odis_male_json`, `odis_female_json` | ODIs |
| `tests_male_json`, `tests_female_json` | Tests |

In queries, `dataset` is the code (`ipl`, `wpl`, `t20s`, `odis`, `tests`). `t20s`, `odis` and
`tests` contain **both genders**, so add `gender = 'male'` / `'female'` when it matters.

### Keeping it fresh

```bash
python cricsheet/scripts/refresh.py            # weekly: matches added in the last 7 days (--days 30 after a gap)
python cricsheet/scripts/refresh.py --full     # monthly: picks up Cricsheet corrections and removed matches
python cricsheet/scripts/refresh.py --dry-run  # preview what would change
python cricsheet/scripts/build_db.py --full    # rebuild the database from the files (after a schema change)
```

Both refreshes only touch new or changed matches, so updating takes seconds. A full rebuild
takes about 40 s. Close DBeaver or any `duckdb` session first, because DuckDB allows one writer.
New matches usually appear on Cricsheet a few days after they're played; use the live scorecard
for in-match posts.

### Without your laptop

The **Refresh data** GitHub Action does the weekly refresh in the cloud and publishes the
database to the `data-latest` release. On any machine, get it with:

```bash
bash cricsheet/scripts/get_db.sh       # → cricsheet/data/cricsto.duckdb, plus cricsheet/data/manifest.json (latest match per dataset)
```

It uses the GitHub CLI if you're signed in (`gh auth login`), so it works for a private repo too.
Run the Action by hand from the repo's **Actions** tab (works in the GitHub phone app); tick
"Full sync" to re-download everything.

## 3. Find an insight

```python
from cricsheet import insights as ins

ins.phase_scoring("ipl")                                   # run rate per phase, by season
ins.batter_strike_rate("ipl", phase="death", season_from="2024", min_balls=60)
ins.bowler_economy("ipl", phase="powerplay", season_from="2024")
ins.venue_bat_first("ipl", season_from="2018")             # bat-first win % by venue
ins.chase_success("t20s")                                  # chase win % by target band
ins.find_player("kohli")                                   # person_id, every name used, first/last match
ins.recent_form("V Kohli", last_n=10)                      # a name or a person_id
ins.vs_bowler_type("ipl")                                  # needs bowler_types.csv (below)
ins.sql("SELECT count(*) FROM deliveries WHERE is_six")    # anything ad hoc
```

Tip: `jupyter lab` and keep a scratch notebook for exploring.

**Names aren't unique, IDs are.** There are four different "Rashid Khan"s in the data, and
players and grounds change names (NR Sciver → NR Sciver-Brunt). Every person, venue and team has
an ID, and tables store only IDs. Group by `batter_id` / `bowler_id` / `venue_id`, and use
`find_player()` to get the right ID. Names shown are the most recent ones.

Useful columns on `deliveries`: `phase` (powerplay / middle / death), `over_num` (0-based),
`legal_ball_no` (1–6; a wide or no-ball carries the number of the ball being attempted, so
`ball` 11.5 = the 5th ball of the 12th over), `legal_ball`, `faced_ball`, `total_runs`,
`bowler_runs`, `is_four`, `is_six`, `is_dot`, `is_wicket`, `bowler_wicket`, `striker_out`,
`in_powerplay`, `is_super_over`, `season`, `match_type`, `gender`, `venue`, `winner`, plus
`batter_id`, `bowler_id`.

Going beyond the views: the tables also hold reviews (DRS), replacements (Impact Player,
concussion subs), fielding, powerplays, officials and playing XIs. See `cricsheet/SCHEMA.md` §9 for
example queries that join them.

## 4. Add your own question

1. Write `cricsheet/queries/<name>.sql` using `$params` (copy an existing file). Group by IDs, and add a
   tie-break to `ORDER BY`.
2. Call it: `from cricsheet.db import run_query; run_query("<name>", dataset="ipl", ...)`.
3. If you'll reuse it, add a small wrapper to `cricsheet/insights.py`.

## Bowler types (pace / spin)

Cricsheet doesn't record bowling style. Fill `cricsheet/data/reference/bowler_types.csv` with the
bowlers you care about, keyed by `person_id` (`name` is only there for readability).
`ins.bowlers_to_classify("ipl")` lists the bowlers still missing, most balls first:

```
person_id,name,bowler_type
<id from bowlers_to_classify()>,JJ Bumrah,pace
<id from bowlers_to_classify()>,Rashid Khan,spin
```

## Notes

- `phase` uses T20 overs 1–6 / 7–15 / 16–20 and ODI overs 1–10 / 11–40 / 41–50; it's empty for Tests.
- Super overs are excluded from most queries (`NOT is_super_over`).
- Retired hurt / retired not out are not wickets or outs (`is_wicket`, `striker_out`, `batter_innings.is_out`).
- IPL season labels follow Cricsheet: `2007/08` is IPL 2008, `2009/10` is 2010, `2020/21` is 2020.
- `load_warnings` lists data oddities found on load (e.g. an unrecorded 7-ball over); see `cricsheet/SCHEMA.md` §8.
- `cricsheet/data/raw/` and the database are git-ignored; rebuild them anytime.
