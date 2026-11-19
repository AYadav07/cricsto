# history.duckdb: schema reference

Everything you need to query `history/history.duckdb` by hand: every table and column, how they
join, which values are recorded in which era, and tested example queries.

**This database is separate from `data/cricsto.duckdb` (Cricsheet).** It has different IDs and
different sources, and it's scorecard-level, not ball-by-ball. Don't join the two databases or add
their numbers together.

Open it with:

```bash
duckdb history/history.duckdb          # CLI
```
```python
import duckdb
con = duckdb.connect("history/history.duckdb", read_only=True)
```
Or in DBeaver, add a DuckDB connection to `history/history.duckdb`.

---

## Contents

1. [At a glance](#1-at-a-glance)
2. [How the tables join](#2-how-the-tables-join)
3. [Tables](#3-tables)
4. [Views (start here for most queries)](#4-views)
5. [Value lists](#5-value-lists)
6. [What was recorded when](#6-what-was-recorded-when)
7. [Rules and gotchas](#7-rules-and-gotchas)
8. [Example queries](#8-example-queries)

---

## 1. At a glance

| | |
|---|---|
| Formats | Men's Tests (`format = 'test'`) and ODIs (`format = 'odi'`) |
| Tests | 2,520 matches, 1877-03-15 → 2023-12-26 (1,581 before 2002) |
| ODIs | 4,717 matches, 1971-01-05 → 2023-12-23 (1,782 before 2002) |
| Teams | 29, including ICC World XI and associate ODI teams |
| Players | 6,707 |
| Source | ESPNcricinfo-derived scorecard CSVs on Hugging Face (`bhuvaneshprasad/test-cricket-dataset-1877-2014`, `odi-cricket-dataset-1971-2014`; both actually run to Dec 2023) |
| Built by | `python history/build.py` (full rebuild from `history/raw/`, about 10 s) |
| Changes? | No. A fixed snapshot: rebuilding from the same files gives the same database |

Row counts:

| Table | Rows |
|---|---|
| `matches` | 7,237 |
| `match_players` | 159,192 |
| `innings` | 18,494 |
| `batting` | 203,434 |
| `bowling` | 104,934 |
| `fall_of_wickets` | 145,657 |
| `partnerships` | 153,994 |
| `players` | 6,707 |
| `load_warnings` | 178 |
| `load_info` | 3 |

---

## 2. How the tables join

```
players ──< match_players >── matches ──< innings ──< batting
   │                             │            ├──< bowling
   │                             │            ├──< fall_of_wickets
   │                             │            └──< partnerships
   └── player_id is used in batting.player_id / bowler_id, bowling.player_id,
       fall_of_wickets.player_id, partnerships.player1_id / player2_id,
       matches.team1_captain_id / team2_captain_id / player_of_match_id
```

| Join | On |
|---|---|
| any card → `matches` | `match_id` |
| `batting` / `bowling` / `fall_of_wickets` / `partnerships` → `innings` | `(match_id, innings_no)` |
| anything with a player → `players` | `player_id` (or `bowler_id`, `player1_id`…) = `players.player_id` |

Keys:
- A match is `match_id` (ESPNcricinfo match ID, unique across both formats).
- An innings is `(match_id, innings_no)`. `innings_no` is the order in the match, 1–4.
- A batting row is `(match_id, innings_no, position)`. A bowling row is `(match_id, innings_no, player_id)`.

Team names are plain text (`'India'`, `'West Indies'`) and match across all tables.

---

## 3. Tables

"Known" = share of rows where the value isn't NULL, for all years / before 2002. NULL always means
*not recorded*. Section 6 has the coverage by decade.

### `matches`: one row per match

| Column | Type | Meaning | Known (all / pre-2002) |
|---|---|---|---|
| `match_id` | BIGINT, PK | ESPNcricinfo match ID | 100 / 100 |
| `format` | VARCHAR | `test` or `odi` | 100 / 100 |
| `match_no` | INTEGER | Official Test # / ODI # | 100 / 100 |
| `match_name` | VARCHAR | e.g. `Australia Vs England 1St Test` | 100 / 100 |
| `series_id` | BIGINT | Series ID | 100 / 100 |
| `series_name` | VARCHAR | e.g. `Benson & Hedges World Cup` | 100 / 100 |
| `start_date` | DATE | First day | 100 / 100 |
| `end_date` | DATE | Last day (**Tests only**; NULL for ODIs) | 35 / 47 |
| `team1`, `team2` | VARCHAR | Team names | 100 / 100 |
| `team1_id`, `team2_id` | BIGINT | Team IDs | 100 / 100 |
| `team1_captain_id`, `team2_captain_id` | BIGINT | Captain → `players.player_id` | 100 / 100 |
| `venue` | VARCHAR | Ground, e.g. `Melbourne Cricket Ground` | 100 / 100 |
| `city` | VARCHAR | City | 100 / 100 |
| `country` | VARCHAR | Country of the ground | 100 / 100 |
| `umpire1`, `umpire2` | VARCHAR | Umpire names | 100 / 100 |
| `referee` | VARCHAR | Match referee (role started in the 1990s) | 73 / 43 |
| `toss_winner` | VARCHAR | Team name | 100 / 100 |
| `toss_decision` | VARCHAR | `bat` / `bowl` | 100 / 100 |
| `winner` | VARCHAR | Team name. **NULL = draw, tie or no result** | 86 / 80 |
| `result_text` | VARCHAR | e.g. `Australia won by 45 runs`, `Match drawn`, `No result (abandoned with a toss)` | 100 / 100 |
| `player_of_match_id` | BIGINT | → `players.player_id` (award didn't exist in early years) | 83 / 71 |
| `balls_per_over` | INTEGER | `6` or `8` (see section 7) | 100 / 100 |
| `bpo_source` | VARCHAR | How `balls_per_over` was set: `detected`, `series` or `default` | 100 / 100 |

### `match_players`: one row per player per match (playing XIs)

| Column | Type | Meaning |
|---|---|---|
| `match_id` | BIGINT | → `matches` |
| `team` | VARCHAR | Team name |
| `player_id` | BIGINT | → `players` |
| `list_order` | INTEGER | Position in the team list (1 = first listed; not the batting order) |
| `is_debut` | BOOLEAN | First match in this format |

PK `(match_id, team, player_id)`. **Use this table to count appearances**, not `batting`: a player who didn't bat has no batting row.

### `innings`: one row per innings

| Column | Type | Meaning |
|---|---|---|
| `match_id` | BIGINT | → `matches` |
| `innings_no` | INTEGER | Order in the match: 1–2 for ODIs, 1–4 for Tests |
| `batting_team` | VARCHAR | Team batting |
| `bowling_team` | VARCHAR | Team bowling |
| `team_innings_no` | INTEGER | That team's 1st or 2nd innings (Tests: tells you about follow-ons) |
| `runs` | INTEGER | Innings total |
| `wickets` | INTEGER | Wickets fallen |
| `extras` | INTEGER | Extras |

PK `(match_id, innings_no)`. There's no overs or declared flag for the innings. All columns 100% known.

### `batting`: one row per batter per innings (including "did not bat")

| Column | Type | Meaning | Known (all / pre-2002) |
|---|---|---|---|
| `match_id` | BIGINT | → `matches` | 100 / 100 |
| `innings_no` | INTEGER | → `innings` | 100 / 100 |
| `team` | VARCHAR | Batting team | 100 / 100 |
| `position` | INTEGER | Batting order (1 = opener) | 100 / 100 |
| `player_id` | BIGINT | → `players` | 100 / 100 |
| `did_bat` | BOOLEAN | `false` = did not bat (the rest of the row is NULL) | 100 / 100 |
| `runs` | INTEGER | Runs scored | 85 / 85 (= rows where `did_bat`) |
| `balls` | INTEGER | Balls faced. **Patchy before 1980** | 74 / 63 |
| `fours`, `sixes` | INTEGER | Boundaries. NULL when not recorded | 79 / 75, 84 / 85 |
| `is_out` | BOOLEAN | Dismissed in this innings | 85 / 85 |
| `dismissal` | VARCHAR | How out (section 5). NULL when `did_bat` is false | 85 / 85 |
| `bowler_id` | BIGINT | Bowler credited with the dismissal. **Almost never recorded before 2000** | 35 / 4 |
| `fielder_ids` | BIGINT[] | Catcher / run-out fielder(s), a list | 46 / 44 |

PK `(match_id, innings_no, position)`. The known share of `fours` and `sixes` counts only rows where `did_bat`.

### `bowling`: one row per bowler per innings

| Column | Type | Meaning | Known (all / pre-2002) |
|---|---|---|---|
| `match_id` | BIGINT | → `matches` | 100 / 100 |
| `innings_no` | INTEGER | → `innings` (the innings being bowled at) | 100 / 100 |
| `team` | VARCHAR | **Bowling** team | 100 / 100 |
| `opposition` | VARCHAR | Batting team | 100 / 100 |
| `player_id` | BIGINT | → `players` | 100 / 100 |
| `overs` | DOUBLE | As written: `7.4` = 7 overs and 4 balls (8-ball overs where `matches.balls_per_over = 8`) | 100 / 100 |
| `balls` | INTEGER | Balls bowled, **corrected for 8-ball overs** | 100 / 100 |
| `maidens` | INTEGER | Maidens | 100 / 100 |
| `runs` | INTEGER | Runs conceded | 100 / 100 |
| `wickets` | INTEGER | Wickets | 100 / 100 |
| `dots` | INTEGER | Dot balls. **Only from ~2000** | 54 / 7 |
| `fours`, `sixes` | INTEGER | Boundaries conceded. **Only from ~2000** | 54 / 7 |
| `wides` | INTEGER | Wides. **0 before the 1990s means not recorded** | 100 / 100 |
| `noballs` | INTEGER | No-balls. **0 before the 1990s means not recorded** | 100 / 100 |

PK `(match_id, innings_no, player_id)`. Wickets are complete in every era.

### `fall_of_wickets`: one row per wicket

| Column | Type | Meaning | Known (all / pre-2002) |
|---|---|---|---|
| `match_id`, `innings_no` | | → `innings` | 100 / 100 |
| `team` | VARCHAR | Batting team | 100 / 100 |
| `wicket_no` | INTEGER | 1st, 2nd … wicket | 100 / 100 |
| `player_id` | BIGINT | Batter out → `players` | 100 / 100 |
| `score` | INTEGER | Team score when it fell | 100 / 100 |
| `over_at` | DOUBLE | Over when it fell, e.g. `23.4`. **Mostly from 2000** | 59 / 19 |

### `partnerships`: one row per partnership

| Column | Type | Meaning | Known (all / pre-2002) |
|---|---|---|---|
| `match_id`, `innings_no` | | → `innings` | 100 / 100 |
| `wicket_no` | INTEGER | Partnership for the nth wicket (the last one may be unbroken) | 100 / 100 |
| `team` / `opposition` | VARCHAR | Batting / bowling team | 100 / 100 |
| `player1_id`, `player2_id` | BIGINT | The two batters → `players` | 100 / 100 |
| `player1_runs`, `player2_runs` | INTEGER | Each batter's runs in the stand | 100 / 100 |
| `player1_balls`, `player2_balls` | INTEGER | Each batter's balls. **Mostly from 2000** | 50 / 6 |
| `runs` | INTEGER | Partnership runs | 100 / 100 |
| `balls` | INTEGER | Partnership balls. **Mostly from 2000** | 59 / 19 |

### `players`: one row per player

| Column | Type | Meaning | Known |
|---|---|---|---|
| `player_id` | BIGINT, PK | Player ID used in every other table | 100 |
| `object_id` | BIGINT | ESPNcricinfo profile ID | 100 |
| `name` | VARCHAR | Full name, e.g. `Donald Bradman`, `Muthiah Muralidaran` | 100 |
| `dob` / `dod` | DATE | Date of birth / death | 100 / 19 |
| `gender` | VARCHAR | `M` (one `F`) | 100 |
| `batting_style` | VARCHAR | `right-hand bat` / `left-hand bat` | 99 |
| `bowling_style` | VARCHAR | e.g. `right-arm fast`, `legbreak googly` (section 5) | 83 |
| `country_id` | INTEGER | Country ID (no names table) | 100 |

68 player IDs used in the cards have no row here (listed in `load_warnings`), so a LEFT JOIN gives a NULL name.

### `load_warnings`: data problems found during the build

| Column | Meaning |
|---|---|
| `check_name` | `innings_total_mismatch` (63), `bowler_wickets_vs_card` (41), `unknown_player` (68), `match_without_scorecard` (6) |
| `match_id` | The match, when there is one |
| `detail` | e.g. `inns 1 Sri Lanka: card 97 + extras 10 vs total 122` |

### `load_info`

`key` / `value` pairs: `built_at`, `duckdb_version`, `source`.

---

## 4. Views

These already join the tables and add names. Most queries start here.

### `batter_innings`: `batting` + match + innings + names

`format, match_id, match_no, start_date, year, series_name, venue, city, country, innings_no,
team_innings_no, team, opposition, position, player_id, player, did_bat, runs, balls, fours, sixes,
is_out, dismissal, bowler_id, bowler, strike_rate`

- `opposition` = the bowling team.
- `strike_rate` = 100 × runs / balls, NULL when balls weren't recorded.

### `bowler_innings`: `bowling` + match + names

`format, match_id, match_no, start_date, year, series_name, venue, city, country, balls_per_over,
innings_no, team, opposition, player_id, player, bowling_style, overs, balls, maidens, runs, wickets,
dots, fours, sixes, wides, noballs, economy, balls_per_wicket`

- `economy` = runs per **6** balls (from corrected balls). `balls_per_wicket` = bowling strike rate.

### `match_results`: one row per match

`format, match_id, match_no, start_date, year, series_name, team1, team2, venue, city, country,
toss_winner, toss_decision, winner, result_text, toss_outcome, player_of_match`

- `toss_outcome` = `toss winner won` / `toss loser won` / `no winner`.

---

## 5. Value lists

**`batting.dismissal`** (count): `caught` 84,910 · `bowled` 29,399 · `not out` 26,472 · `lbw` 18,406 ·
`run out` 9,007 · `stumped` 3,379 · `retired not out` 245 · `hit wicket` 239 · `handled the ball` 10 ·
`obstructing the field` 10 · `retired out` 2 · `timed out` 1 · NULL (did not bat) 31,354

- Out = `is_out`: true for every dismissal except `not out` and `retired not out` (`retired out` counts as out).
- Credited to the bowler: `caught`, `bowled`, `lbw`, `stumped`, `hit wicket`.

**`matches.toss_decision`**: `bat` 4,210 · `bowl` 3,023 · NULL 4

**`matches.bpo_source`**: `default` 7,045 · `detected` 127 · `series` 65

**`players.bowling_style`**:
- Pace: `right-arm fast`, `right-arm fast-medium`, `right-arm medium-fast`, `right-arm medium`, `right-arm slow-medium`,
  `left-arm fast`, `left-arm fast-medium`, `left-arm medium-fast`, `left-arm medium`, `left-arm slow-medium`
- Spin: `right-arm offbreak`, `legbreak`, `legbreak googly`, `slow left-arm orthodox`, `left-arm wrist-spin`, `left-arm slow`, `right-arm slow`, `(unknown arm) slow`
- Unspecified: `right-arm bowler`, `left-arm bowler`
- NULL for 17% of players (mostly people who didn't bowl)

**Test teams**: Australia, Afghanistan, Bangladesh, England, ICC World XI, India, Ireland, New Zealand,
Pakistan, South Africa, Sri Lanka, West Indies, Zimbabwe. ODIs also include associate teams (29 teams in all).

---

## 6. What was recorded when

Share of rows with the value recorded (batting columns over innings where the player batted):

| Format | Decade | Matches | Balls faced | 4s | Dots (bowling) | Over at fall of wicket | Dismissing bowler on batting card |
|---|---|---|---|---|---|---|---|
| Test | 1870s | 3 | 31% | 56% | – | – | – |
| Test | 1880s | 29 | 21% | 83% | – | – | – |
| Test | 1890s | 32 | 1% | 50% | – | – | – |
| Test | 1900s | 41 | 3% | 63% | – | – | – |
| Test | 1910s | 29 | 38% | 57% | – | – | – |
| Test | 1920s | 51 | 32% | 65% | – | – | – |
| Test | 1930s | 89 | 31% | 57% | – | – | – |
| Test | 1940s | 45 | 30% | 54% | – | 5% | – |
| Test | 1950s | 164 | 7% | 60% | – | – | – |
| Test | 1960s | 186 | 29% | 75% | – | – | – |
| Test | 1970s | 198 | 69% | 88% | – | – | – |
| Test | 1980s | 266 | 90% | 93% | – | 1% | – |
| Test | 1990s | 347 | 100% | 100% | 5% | 26% | 5% |
| Test | 2000s | 464 | 100% | 100% | 90% | 100% | 90% |
| Test | 2010s–2023 | 576 | 100% | 100% | 100% | 100% | 100% |
| ODI | 1970s | 82 | 100% | 94% | – | – | – |
| ODI | 1980s | 516 | 100% | 96% | – | – | – |
| ODI | 1990s | 933 | 100% | 100% | 8% | 31% | 8% |
| ODI | 2000s | 1,403 | 100% | 100% | 85% | 98% | 86% |
| ODI | 2010s–2023 | 1,777 | 100% | 100% | 100% | 100% | 100% |

Always complete: runs, how out, bowler wickets, overs, maidens, runs conceded, innings totals,
fall-of-wicket scores, partnership runs, playing XIs.

---

## 7. Rules and gotchas

1. **NULL = not recorded.** Never treat it as 0. Exception: `bowling.wides` and `noballs` were
   stored as 0 when not recorded, so don't use them before the 1990s.
2. **Strike rates with patchy balls.** Use only innings where `balls IS NOT NULL` for both runs and
   balls, and report how many innings that covers (`career_batting.sql` does this).
3. **8-ball overs.** `bowling.overs` is as written; `bowling.balls` is corrected. Use `balls` for
   economy and strike rate. 179 Tests and 13 ODIs have `balls_per_over = 8`: Australia 1924–79,
   South Africa 1938–58, New Zealand 1969–79, Pakistan 1975–78, England 1939.
   `bpo_source = 'detected'` means a bowler's figure ended `.6` or `.7`. `series` means another
   match in the same series did. In a series where no figure ever reached `.6`, an 8-ball match
   could still be marked 6.
4. **Appearances come from `match_players`.** Matches-batted counts from `batting` are lower.
5. **Averages:** `sum(runs) / count(*) FILTER (WHERE is_out)`. Batting average excludes not outs and
   `retired not out`. Bowling average = `sum(runs) / sum(wickets)` from `bowling`.
6. **Group by `player_id`, not name.** Show the name with `any_value(player)`. Find IDs with
   `history/db.py`'s `find_player('text')` or `SELECT * FROM players WHERE name ILIKE '%text%'`.
7. **Abandoned matches** have a `matches` row but no cards.
8. **Before 2002 only:** add `start_date < DATE '2002-01-01'`. The database also covers 2002–2023,
   which makes it good for whole careers, but use Cricsheet for anything ball-by-ball.
9. **Small source errors:** 63 innings don't add up (a batter's row missing) and 41 innings' bowler
   wickets don't match the batting card (`load_warnings`). Fine for aggregates; check a single
   match against its scorecard before posting a stat about it.
10. **Credit on charts:** "Data: ESPNcricinfo scorecards (via bhuvaneshprasad, Hugging Face)", and
    say "scorecard data" plus the sample for any stat that uses balls faced or boundaries before the 1990s.

---

## 8. Example queries

All tested against the database.

**Highest successful ODI chases before 2002**
```sql
SELECT m.start_date, i.batting_team, i.bowling_team, i.runs, i.wickets, m.venue
FROM innings i JOIN matches m USING (match_id)
WHERE m.format = 'odi' AND m.start_date < DATE '2002-01-01'
  AND i.innings_no = 2 AND m.winner = i.batting_team
ORDER BY i.runs DESC, m.start_date
LIMIT 10;
```

**Most Test hundreds in the 1990s**
```sql
SELECT any_value(player) AS player, count(*) AS hundreds
FROM batter_innings
WHERE format = 'test' AND year BETWEEN 1990 AND 1999 AND runs >= 100
GROUP BY player_id
ORDER BY hundreds DESC, player
LIMIT 10;
```

**Highest partnerships before 2002**
```sql
SELECT m.format, m.start_date, pt.team, p1.name AS batter1, p2.name AS batter2, pt.wicket_no, pt.runs
FROM partnerships pt
JOIN matches m USING (match_id)
LEFT JOIN players p1 ON p1.player_id = pt.player1_id
LEFT JOIN players p2 ON p2.player_id = pt.player2_id
WHERE m.start_date < DATE '2002-01-01'
ORDER BY pt.runs DESC, m.start_date
LIMIT 10;
```

**Does winning the toss win Tests? By decade**
```sql
SELECT (year // 10) * 10 AS decade,
       count(*) FILTER (WHERE toss_outcome = 'toss winner won') AS toss_winner_won,
       count(*) FILTER (WHERE toss_outcome = 'toss loser won')  AS toss_loser_won,
       count(*) FILTER (WHERE toss_outcome = 'no winner')       AS no_winner
FROM match_results
WHERE format = 'test' AND year < 2002
GROUP BY decade ORDER BY decade;
```

**Pace vs spin wickets in 1990s Tests**
```sql
SELECT CASE WHEN bowling_style IS NULL
                 OR bowling_style IN ('right-arm bowler', 'left-arm bowler') THEN 'unspecified'
            WHEN bowling_style ILIKE '%fast%' OR bowling_style ILIKE '%medium%' THEN 'pace'
            ELSE 'spin' END AS type,
       sum(wickets) AS wickets,
       round(sum(runs) / sum(wickets), 2) AS average
FROM bowler_innings
WHERE format = 'test' AND year BETWEEN 1990 AND 1999
GROUP BY type ORDER BY wickets DESC;
```

**A player's debut and appearances**
```sql
SELECT m.format, min(m.start_date) FILTER (WHERE mp.is_debut) AS debut, count(*) AS matches
FROM match_players mp JOIN matches m USING (match_id)
WHERE mp.player_id = (SELECT player_id FROM players WHERE name = 'Sachin Tendulkar')
GROUP BY m.format;
```

**Career batting with strike rate where balls were recorded**: see `history/queries/career_batting.sql`
(params `$format`, `$from_date`, `$to_date`, `$min_innings`). Career bowling: `history/queries/career_bowling.sql`.

**One match's full scorecard** (example: India v Australia, 2nd Test, Kolkata, March 2001)
```sql
-- find the match
SELECT match_id, start_date, match_name, series_name FROM matches
WHERE format = 'test' AND start_date BETWEEN DATE '2001-03-01' AND DATE '2001-03-31';

-- batting card
SELECT innings_no, team, position, player, dismissal, bowler, runs, balls, fours, sixes
FROM batter_innings WHERE match_id = 63920 ORDER BY innings_no, position;

-- bowling card
SELECT innings_no, team, player, overs, maidens, runs, wickets
FROM bowler_innings WHERE match_id = 63920 ORDER BY innings_no, wickets DESC;
```
