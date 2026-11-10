# cricsto-data

The data engine behind **@cricsto — Cricket by Numbers**.
Cricsheet ball-by-ball data → DuckDB → ready-made insights → on-brand charts for X.

```
scripts/download.py   get Cricsheet data into data/raw/<competition>/
scripts/build_db.py   build data/cricsto.duckdb (tables + clean views)
scripts/refresh.py    weekly: re-download + rebuild in one go
cricsto/db.py         loader, run_query(), sql()
cricsto/views.sql     clean views: deliveries, batter_innings, dismissals
cricsto/insights.py   ready-made insights (one function per question)
cricsto/charts.py     Cricsto chart template (1600×900, navy/red/cream, @cricsto mark)
queries/*.sql         the SQL behind each insight; add your own here
examples/first_post.py  question → table → chart, end to end
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
python scripts/download.py ipl t20s odis      # men's IPL, T20Is, ODIs
python scripts/download.py --list             # other competition codes
python scripts/build_db.py
```

If a download fails, open https://cricsheet.org/downloads/, copy the **CSV (Ashwin)**
link for that competition, and run `python scripts/download.py ipl --url <link>`.
New matches usually appear on Cricsheet a few days after they're played; use the live
scorecard for in-match posts.

## 3. Find an insight

```python
from cricsto import insights as ins

ins.phase_scoring("ipl")                                   # run rate per phase, by season
ins.batter_strike_rate("ipl", phase="death", season_from="2024", min_balls=60)
ins.bowler_economy("ipl", phase="powerplay", season_from="2024")
ins.venue_bat_first("ipl", season_from="2018")             # bat-first win % by venue
ins.chase_success("t20s")                                  # chase win % by target band
ins.find_player("kohli")                                   # exact Cricsheet spelling
ins.recent_form("V Kohli", last_n=10)
ins.vs_bowler_type("ipl")                                  # needs bowler_types.csv (below)
ins.sql("SELECT count(*) FROM deliveries WHERE is_six")    # anything ad hoc
```

Tip: `jupyter lab` and keep a scratch notebook for exploring.

Useful columns on `deliveries`: `phase` (powerplay / middle / death), `over_num` (0-based),
`legal_ball`, `faced_ball`, `total_runs`, `bowler_runs`, `is_four`, `is_six`, `is_dot`,
`is_wicket`, `bowler_wicket`, `season`, `match_type`, `venue`, `winner`.

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

1. Write `queries/<name>.sql` using `$params` (copy an existing file).
2. Call it: `from cricsto.db import run_query; run_query("<name>", dataset="ipl", ...)`.
3. If you'll reuse it, add a small wrapper to `cricsto/insights.py`.

## Bowler types (pace / spin)

Cricsheet doesn't record bowling style. Fill `data/reference/bowler_types.csv`
with the bowlers you care about, using their exact Cricsheet names:

```
bowler,bowler_type
JJ Bumrah,right-arm pace
Rashid Khan,leg-spin
```

## Weekly routine

```bash
python scripts/refresh.py      # edit DATASETS inside it to your competitions
```

## Before posting: checklist

- [ ] The number comes from a query in this repo (rerunnable), not memory.
- [ ] Sample size is stated in the subtitle (min. balls, matches, seasons).
- [ ] Phases and filters are stated (e.g. "overs 16–20, since 2024").
- [ ] Spot-check one figure against ESPNcricinfo or the scorecard.
- [ ] Cricsheet is credited (the chart template adds "Data: Cricsheet").

## Notes

- `phase` uses T20 overs 1–6 / 7–15 / 16–20 and ODI overs 1–10 / 11–40 / 41–50; it's empty for Tests.
- Super overs (innings 3+ in limited-overs games) are excluded from most queries.
- `data/raw/`, the database and `output/` are git-ignored; rebuild them anytime.
