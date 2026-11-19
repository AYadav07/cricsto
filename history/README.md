# history: scorecard database (Tests 1877–2023, ODIs 1971–2023)

A **separate** database for matches Cricsheet doesn't cover (before ~2002), at scorecard level.
It shares nothing with `cricsheet/data/cricsto.duckdb`: own raw files, own loader, own database file,
own IDs, own queries. Never join the two or add their numbers together without saying so.

**Full reference for querying: [SCHEMA.md](SCHEMA.md)** (every table and column, coverage by era, rules, example queries).

```
history/raw/test/, history/raw/odi/   source CSVs (git-ignored)
history/build.py                       builds history/history.duckdb (about 10 s, full rebuild each run)
history/schema.sql                     tables
history/views.sql                      batter_innings, bowler_innings, match_results
history/db.py                          run(), sql(), find_player()
history/queries/*.sql                  reusable queries with $params
```

## Set up

```bash
cd history/raw
git clone https://huggingface.co/datasets/bhuvaneshprasad/test-cricket-dataset-1877-2014 test
git clone https://huggingface.co/datasets/bhuvaneshprasad/odi-cricket-dataset-1971-2014 odi
cd ../..
python history/build.py
```

Despite the "2014" in the names, both datasets run to December 2023.

## What's in it

Men's Tests and ODIs: 2,520 Tests (1,581 before 2002) and 4,716 ODIs (1,782 before 2002).

| Table | One row per |
|---|---|
| `matches` | match: series, dates, teams, captains, venue, umpires, toss, result, player of the match, `balls_per_over` |
| `match_players` | player per match (playing XIs), with `is_debut` |
| `innings` | innings: batting/bowling team, total, wickets, extras |
| `batting` | batter per innings: runs, balls, 4s, 6s, how out, dismissing bowler, fielders |
| `bowling` | bowler per innings: overs, balls, maidens, runs, wickets, dots, 4s, 6s, wides, no-balls |
| `fall_of_wickets` | wicket: score and over at the fall |
| `partnerships` | partnership: both batters' runs and balls |
| `players` | player: name, date of birth, batting and bowling style |

There's no ball-by-ball data: no phases, no batter-vs-bowler matchups.

## Coverage: what was recorded when

Share of rows where the value is known (NULL = not recorded):

| | balls faced | dots | over at fall of wicket | dismissing bowler on batting card |
|---|---|---|---|---|
| Tests before 1970 | 1–38% | none | none | none |
| Tests 1970s | 69% | none | none | none |
| Tests 1980s | 90% | none | none | none |
| Tests 1990s | 100% | 5% | 26% | 5% |
| ODIs 1971–1989 | 100% | none | none | none |
| ODIs 1990s | 100% | 8% | 31% | 8% |
| 2000s onwards | 100% | 85–100% | 98–100% | 86–100% |

- **Strike rates before the 1980s** use only innings with balls recorded, so they're a sample. `career_batting` shows `balls_known` next to `innings`.
- **4s and 6s** are NULL where not recorded (many Tests before the 1970s). **Bowler wides and no-balls** are stored as 0 when not recorded: don't use them before the 1990s.
- **Bowler wickets are complete in every era** (from the bowling card), even when the batting card doesn't say who took the wicket.
- **8-ball overs.** The source counted every over as 6 balls. The build detects 8-ball matches from figures like `7.7`, extends that to the rest of the series, and recalculates `balls`. That gives 179 Tests and 13 ODIs: Australia 1924–79, South Africa 1938–58, New Zealand 1969–79, Pakistan 1975–78, England 1939. `economy` and strike rates are per 6 balls.
- **Appearances:** count matches from `match_players`, not from `batting`. A player who didn't bat has no batting row.
- **Names** are full names ("Donald Bradman", "Muthiah Muralidaran"). Use `find_player()`.

## Checks

The build records problems in `load_warnings` instead of failing:

- `innings_total_mismatch` (63 innings): the batting card plus extras doesn't add up to the total, usually because a batter's row is missing.
- `bowler_wickets_vs_card` (41 innings): bowling wickets don't match the dismissals on the batting card.
- `unknown_player` (68 IDs): IDs with no entry in `players`, so they have no name.
- `match_without_scorecard` (6): abandoned matches.

Spot-checked against published career records: Bradman 6,996 runs at 99.94 (HS 334), Tendulkar 15,921 Test and 18,426 ODI runs,
Lara 11,953, Gavaskar 10,122; Muralidaran 800 Test wickets, Warne 708, Kapil Dev 434, Hadlee 431,
Grimmett 216 wickets in 14,513 balls (8-ball fix), Wasim Akram 502 ODI wickets. Appearances from
`match_players`: Tendulkar 200 Tests / 463 ODIs, Lara 131 / 299, Richards 121 / 187.

## Rules

- Use this database for matches before Cricsheet's coverage, or for whole-career totals (it's complete for Tests and ODIs through 2023).
- Label charts: "Data: ESPNcricinfo scorecards via Hugging Face (bhuvaneshprasad)" and state the years.
- Say "scorecard data" whenever a stat depends on balls faced or boundaries before the 1990s, and give the sample.
- The source has no stated licence. Use it for analysis and post derived stats with credit; don't republish the raw files.

## Examples

```python
import sys; sys.path.insert(0, "history")
from db import run, sql, find_player

run("career_batting", format="test", from_date="1990-01-01", to_date="2001-12-31", min_innings=40)
run("career_bowling", format="odi", from_date="1971-01-01", to_date="2001-12-31", min_wickets=150)
find_player("murali")
sql("SELECT * FROM match_results WHERE format = 'odi' AND year = 1996 AND series_name ILIKE '%world cup%'")
```
