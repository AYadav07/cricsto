# cricsto-data

The data engine behind **@cricsto: Cricket by Numbers**.
Cricsheet ball-by-ball JSON → DuckDB → ready-made insights → on-brand charts for X.

```
scripts/refresh.py      get new Cricsheet data into data/raw/json/, then update the database
scripts/build_db.py     build / update data/cricsto.duckdb from data/raw/json/
cricsto/schema.sql      the tables (one per real-world thing, joined by IDs)
cricsto/load_json.py    incremental JSON loader with validation
cricsto/refresh.py      Cricsheet downloads and routing into folders
cricsto/views.sql       flat views: deliveries, batter_innings, bowler_innings, dismissals
cricsto/insights.py     ready-made insights (one function per question)
cricsto/charts.py       Cricsto chart template (1600×900, navy/red/cream, @cricsto mark)
queries/*.sql           the SQL behind each insight; add your own here
examples/first_post.py  question → table → chart, end to end
SCHEMA.md               full reference: every table, column, key, view and rule
tests/                  python -m pytest tests
```

## 1. Set up (once)

```bash
git clone <your repo url> cricsto-data && cd cricsto-data
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Fonts (optional, for the exact brand look): install **Space Grotesk** and **Inter** from
Google Fonts, or drop their `.ttf` files into a `fonts/` folder here. Without them, charts
fall back to a default font.

## 2. Get the data

```bash
python scripts/refresh.py --full     # first time: downloads the 8 Cricsheet zips and builds the database
```

That fills `data/raw/json/` with one folder per competition and gender:

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
python scripts/refresh.py            # weekly: matches added in the last 7 days (--days 30 after a gap)
python scripts/refresh.py --full     # monthly: picks up Cricsheet corrections and removed matches
python scripts/refresh.py --dry-run  # preview what would change
python scripts/build_db.py --full    # rebuild the database from the files (after a schema change)
```

Both refreshes only touch new or changed matches, so updating takes seconds. A full rebuild
takes about 40 s. Close DBeaver or any `duckdb` session first, because DuckDB allows one writer.
New matches usually appear on Cricsheet a few days after they're played; use the live scorecard
for in-match posts.

## 3. Find an insight

```python
from cricsto import insights as ins

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
concussion subs), fielding, powerplays, officials and playing XIs. See `SCHEMA.md` §9 for
example queries that join them.

## 4. Make the chart

```python
from cricsto import charts

top = ins.batter_strike_rate("ipl", phase="death", season_from="2024", min_balls=60).head(10)
fig = charts.bar(top["batter"], top["strike_rate"],
                 title="Fastest death-over hitters",
                 subtitle="IPL, overs 16–20, since 2024 (min. 60 balls)",
                 highlight=top["batter"].iloc[0], value_fmt="{:.0f}")
charts.save(fig, "death_hitters")       # → output/death_hitters.png
```

`charts.line(x, {"Series A": ys, "Series B": ys2}, title=...)` for trends.
Run `python examples/first_post.py` for a full worked example.

## 5. Add your own question

1. Write `queries/<name>.sql` using `$params` (copy an existing file). Group by IDs, and add a
   tie-break to `ORDER BY`.
2. Call it: `from cricsto.db import run_query; run_query("<name>", dataset="ipl", ...)`.
3. If you'll reuse it, add a small wrapper to `cricsto/insights.py`.

## Bowler types (pace / spin)

Cricsheet doesn't record bowling style. Fill `data/reference/bowler_types.csv` with the
bowlers you care about, keyed by `person_id` (`name` is only there for readability).
`ins.bowlers_to_classify("ipl")` lists the bowlers still missing, most balls first:

```
person_id,name,bowler_type
<id from bowlers_to_classify()>,JJ Bumrah,pace
<id from bowlers_to_classify()>,Rashid Khan,spin
```

## Before posting: checklist

- [ ] The number comes from a query in this repo (rerunnable), not memory.
- [ ] Sample size is stated in the subtitle (min. balls, matches, seasons).
- [ ] Phases and filters are stated (e.g. "overs 16–20, since 2024").
- [ ] Spot-check one figure against ESPNcricinfo or the scorecard.
- [ ] Cricsheet is credited (the chart template adds "Data: Cricsheet").

## Notes

- `phase` uses T20 overs 1–6 / 7–15 / 16–20 and ODI overs 1–10 / 11–40 / 41–50; it's empty for Tests.
- Super overs are excluded from most queries (`NOT is_super_over`).
- Retired hurt / retired not out are not wickets or outs (`is_wicket`, `striker_out`, `batter_innings.is_out`).
- IPL season labels follow Cricsheet: `2007/08` is IPL 2008, `2009/10` is 2010, `2020/21` is 2020.
- `load_warnings` lists data oddities found on load (e.g. an unrecorded 7-ball over); see `SCHEMA.md` §8.
- `data/raw/`, the database and `output/` are git-ignored; rebuild them anytime.
