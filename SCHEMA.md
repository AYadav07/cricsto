# Cricsto database design (Cricsheet JSON → DuckDB)

Status: **design, not yet implemented.** Every rule below was checked against the real files on 2026-11-10: 11,340 matches in `data/raw/json/`, all Cricsheet JSON `data_version` 1.3.0.

Contents: 1 Overview · 2 Keys and lookup tables · 3 Table reference · 4 Views · 5 JSON coverage map · 6 Cricket rules · 7 Loading and validation · 8 Data notes · 9 Query cookbook

---

## 1. Overview

### Principles

1. **Raw JSON is the source of truth.** Files in `data/raw/json/` are never edited; the database can always be rebuilt from them.
2. **Normalized tables joined by keys.** One table per real-world thing. Lists inside the JSON (wickets on a ball, fielders on a wicket, players in a team) become their own tables, linked by primary and foreign keys.
3. **IDs, not names.** People, venues and teams are stored once, in lookup tables, with one row per ID and one name. Every other table holds only the ID. To get a name, join the lookup table.
4. **Store facts, derive the rest in views.** Tables hold what Cricsheet recorded. Flags like `is_four` or `phase` live in views, so the rules can change without reloading.
5. **Backward compatible.** The `deliveries`, `batter_innings` and `dismissals` views keep their v1 column names, so existing queries keep working.

### Relationships

```
                      ┌──────────── people (person_id) ─────────────┐
                      │   referenced by every *_id that is a person  │
                      └──────────────────────────────────────────────┘
venues (venue_id) ──< matches >── teams (team_id)
                         │
     ┌─────────┬─────────┼──────────────┬────────────────┐
match_players  officials  player_of_match  innings
                                             │
                    ┌───────────┬────────────┼──────────────┐
               powerplays  miscounted_overs  absent_hurt   balls
                                                             │
                                         ┌───────────┬───────┴──────┐
                                      wickets     reviews      replacements
                                         │
                                      fielding
```

`load_log` (one row per loaded file), `load_warnings` (data oddities found on load) and `bowler_types` (your own reference list) sit beside these.

### Raw data layout

```
data/raw/json/<code>_<gender>_json/<match_id>.json   (+ README.txt, LICENSE.txt: ignored)
```

Folders: `ipl_male_json`, `wpl_female_json`, `odis_male_json`, `odis_female_json`, `t20s_male_json`, `t20s_female_json`, `tests_male_json`, `tests_female_json`.

- `matches.dataset` is the code part of the folder name (`ipl_male_json` → `ipl`), so `dataset = 'ipl'` keeps working in existing queries.
- `odis`, `t20s` and `tests` hold **both genders**. Filter on `matches.gender` when it matters.

---

## 2. Keys and lookup tables

### Lookup tables (one row per ID, one name per ID)

| Table | Key | Where the key comes from | Stable across files? |
|---|---|---|---|
| `people` | `person_id` | `info.registry.people` (8-char hex) | Yes: one ID per person, reused in every match they appear in |
| `venues` | `venue_id` | `info.registry.venues` (8-char hex) | Yes |
| `teams` | `team_id` | **made by us**: first 8 hex chars of `md5(team name)` | Yes (same name → same ID on every rebuild) |

**Names are not unique; IDs are.** Across all files:

- **90 names belong to more than one person**, e.g. "Rashid Khan" is 4 different people. Never join or group on a name. Use the ID.
- **25 people and 20 venues appear under more than one name** (NR Sciver → NR Sciver-Brunt; Subrata Roy Sahara Stadium → Maharashtra Cricket Association Stadium, Pune). The lookup table keeps one name: **the one used in the most recent match** (latest `start_date`, then highest `match_id`). Older spellings stay only in the raw JSON.
- Teams have no Cricsheet IDs. Renamed franchises are separate teams (Delhi Daredevils ≠ Delhi Capitals). Men's and women's sides with the same name share one `team_id` ("India"); `matches.gender` separates them.

Every name in every file has a registry ID (checked: zero missing), so all person, venue and team ID columns are `NOT NULL` unless the JSON field itself is optional.

### Composite keys

| Thing | Key |
|---|---|
| Match | `match_id` (the JSON file name, e.g. `1359475`; unique across Cricsheet) |
| Innings | `(match_id, innings_no)`. `innings_no` is the 1-based position in `innings[]`, super overs included (up to 8 seen). |
| Ball | `(match_id, innings_no, over_num, ball_seq)`. `over_num` is 0-based, as in the JSON. `ball_seq` is the 1-based position within the over's `deliveries[]`, **counting wides and no-balls**. |
| Ball number in the over | `legal_ball_no` (not part of the key). Counts **legal balls only**: wides and no-balls never increase it. A wide or no-ball carries the number of the ball being attempted, Cricsheet's own convention. |

How the two counters work, in the 12th over (`over_num = 11`):

| Delivery | ball_seq | legal_ball_no | Cricsheet `actual_delivery` |
|---|---|---|---|
| dot | 1 | 1 | 11.1 |
| four | 2 | 2 | 11.2 |
| wide | 3 | 3 | 11.3 |
| single | 4 | 3 | 11.3 |
| no-ball | 5 | 4 | 11.4 |
| dot | 6 | 4 | 11.4 |
| two | 7 | 5 | 11.5 |
| six | 8 | 6 | 11.6 |

"The 5th ball of the 12th over" = `over_num = 11 AND legal_ball_no = 5 AND wides = 0 AND noballs = 0` (one row). Leave out the extras filter to also get any wides or no-balls bowled while attempting that ball. A normal over ends at `legal_ball_no = 6`; only umpire miscounts go higher (see §7, §8).
| Wicket | ball key + `wicket_seq` (1-based position in `wickets[]`) |
| Fielder | wicket key + `fielder_seq` (1-based position in `fielders[]`) |

### Conventions

- Column names ending in `_id` are foreign keys to `people`, `venues` or `teams`.
- `Null = yes` means the JSON field can be absent. Missing counts become `0` and missing flags become `false`, never NULL (stated per column).
- Booleans are `BOOLEAN`; lists that hold references become child tables, never arrays.
- DuckDB has no `ON DELETE CASCADE`, so the loader deletes a match's rows child-first (see §7).

---

## 3. Table reference

Path shorthand: `info.` = `info`, `inn.` = `innings[i]`, `ov.` = `inn.overs[o]`, `d.` = `ov.deliveries[k]`, `w.` = `d.wickets[n]`, `reg()` = look the name up in that match's `info.registry.people`.

### `people`
One row per person (players and officials).
**PK** `person_id`

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| person_id | VARCHAR | no | `info.registry.people` value | |
| name | VARCHAR | no | `info.registry.people` key | name from their most recent match |

### `venues`
One row per ground.
**PK** `venue_id`

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| venue_id | VARCHAR | no | `info.registry.venues` value | |
| name | VARCHAR | no | `info.venue` | name from the most recent match there |
| city | VARCHAR | yes | `info.city` | most recent non-null city (29 venues have two spellings, e.g. Bangalore / Bengaluru) |

### `teams`
One row per team name.
**PK** `team_id`

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| team_id | VARCHAR | no | `md5(name)[:8]` | made by us; the loader fails on a collision |
| name | VARCHAR | no | `info.teams[]` | |
| team_type | VARCHAR | no | `info.team_type` | `international` / `club` (never varies per team) |

### `name_sources`
Bookkeeping: which name each person, venue and team had in each match. The lookup tables' names are recomputed from it after every load (latest match wins), so a corrected or removed match also corrects the name. Not meant for analysis, though it does let you search old spellings.
**PK** `(match_id, kind, key_id)` · **FK** `match_id` → matches

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id | VARCHAR | no | file name | |
| kind | VARCHAR | no | | `person` / `venue` / `team` |
| key_id | VARCHAR | no | registry ID, or `team_id` | |
| name | VARCHAR | no | `registry.people` key / `info.venue` / `info.teams[]` | |
| city | VARCHAR | yes | `info.city` | venues only |
| team_type | VARCHAR | yes | `info.team_type` | teams only |

### `matches`
One row per match.
**PK** `match_id` · **FK** `venue_id` → venues; `team1_id`, `team2_id`, `toss_winner_id`, `winner_id`, `eliminator_id`, `bowl_out_winner_id` → teams

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id | VARCHAR | no | file name | |
| dataset | VARCHAR | no | folder code | `ipl`, `wpl`, `odis`, `t20s`, `tests` |
| gender | VARCHAR | no | `info.gender` | `male` / `female`; must match the folder |
| team_type | VARCHAR | no | `info.team_type` | |
| match_type | VARCHAR | no | `info.match_type` | `T20`, `ODI`, `Test` |
| match_type_number | INT | yes | `info.match_type_number` | e.g. ODI no. 4321 |
| season | VARCHAR | no | `info.season` | always text (JSON has both `2024` and `"2020/21"`) |
| start_date | DATE | no | `info.dates[0]` | |
| end_date | DATE | no | `info.dates[-1]` | |
| num_days | INT | no | `len(info.dates)` | |
| venue_id | VARCHAR | no | `reg(info.venue)` in `registry.venues` | |
| event_name | VARCHAR | yes | `info.event.name` | |
| event_match_number | INT | yes | `info.event.match_number` | |
| event_group | VARCHAR | yes | `info.event.group` | text (JSON has both `"A"` and `1`) |
| event_stage | VARCHAR | yes | `info.event.stage` | e.g. Final |
| event_sub_name | VARCHAR | yes | `info.event.sub_name` | |
| team1_id, team2_id | VARCHAR | no | `info.teams[0]`, `[1]` | |
| balls_per_over | INT | no | `info.balls_per_over` | |
| overs | INT | yes | `info.overs` | missing for Tests |
| toss_winner_id | VARCHAR | no | `info.toss.winner` | |
| toss_decision | VARCHAR | no | `info.toss.decision` | `bat` / `field` |
| toss_uncontested | BOOLEAN | no | `info.toss.uncontested` | default false |
| winner_id | VARCHAR | yes | `info.outcome.winner` | NULL for tie / draw / no result |
| win_by_runs | INT | yes | `info.outcome.by.runs` | |
| win_by_wickets | INT | yes | `info.outcome.by.wickets` | |
| win_by_innings | INT | yes | `info.outcome.by.innings` | Tests |
| result | VARCHAR | yes | `info.outcome.result` | `tie`, `draw`, `no result` |
| method | VARCHAR | yes | `info.outcome.method` | `D/L`, `VJD`… |
| eliminator_id | VARCHAR | yes | `info.outcome.eliminator` | super-over winner |
| bowl_out_winner_id | VARCHAR | yes | `info.outcome.bowl_out` | |
| bowl_out | JSON | yes | `info.bowl_out` | list of bowler attempts, kept as-is (2 matches) |
| missing | JSON | yes | `info.missing` | what Cricsheet says is unrecorded, kept as-is |
| data_version | VARCHAR | no | `meta.data_version` | |
| meta_created | DATE | no | `meta.created` | |
| revision | INT | no | `meta.revision` | |

### `match_players`
One row per player listed for a team in a match. Supersubs are already in the list.
**PK** `(match_id, team_id, person_id)` (one Cricsheet error lists a player for both teams; see §8) · **FK** `match_id` → matches, `person_id` → people, `team_id` → teams

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id | VARCHAR | no | file name | |
| team_id | VARCHAR | no | `info.players` key | |
| person_id | VARCHAR | no | `reg(info.players[team][j])` | |
| list_order | INT | no | `j + 1` | order as listed (not batting order) |
| is_supersub | BOOLEAN | no | `info.supersubs[team] == player` | default false |

### `officials`
One row per official per match.
**PK** `(match_id, role, person_id)` · **FK** `match_id` → matches, `person_id` → people

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id | VARCHAR | no | file name | |
| role | VARCHAR | no | `info.officials` key, made singular | `umpire`, `tv_umpire`, `match_referee`, `reserve_umpire` |
| person_id | VARCHAR | no | `reg(name)` | |
| list_order | INT | no | position in the list | |

`info.officials` is missing in some matches (no rows then).

### `player_of_match`
**PK** `(match_id, person_id)` · **FK** `match_id` → matches, `person_id` → people

| Column | Type | Null | Source |
|---|---|---|---|
| match_id | VARCHAR | no | file name |
| person_id | VARCHAR | no | `reg(info.player_of_match[])` |

### `innings`
One row per innings, super overs included.
**PK** `(match_id, innings_no)` · **FK** `match_id` → matches, `batting_team_id`, `bowling_team_id` → teams

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id | VARCHAR | no | file name | |
| innings_no | INT | no | `i + 1` | |
| batting_team_id | VARCHAR | no | `inn.team` | |
| bowling_team_id | VARCHAR | no | the other of `info.teams` | |
| is_super_over | BOOLEAN | no | `inn.super_over` | default false |
| declared | BOOLEAN | no | `inn.declared` | default false |
| forfeited | BOOLEAN | no | `inn.forfeited` | default false |
| target_runs | INT | yes | `inn.target.runs` | includes DLS revisions |
| target_overs | DOUBLE | yes | `inn.target.overs` | can be fractional |
| penalty_runs_pre | INT | no | `inn.penalty_runs.pre` | default 0 |
| penalty_runs_post | INT | no | `inn.penalty_runs.post` | default 0 |

### `absent_hurt`
Batters who didn't bat through injury.
**PK** `(match_id, innings_no, person_id)` · **FK** `(match_id, innings_no)` → innings, `person_id` → people

| Column | Type | Null | Source |
|---|---|---|---|
| match_id, innings_no | VARCHAR, INT | no | innings key |
| person_id | VARCHAR | no | `reg(inn.absent_hurt[])` |

### `powerplays`
**PK** `(match_id, innings_no, pp_seq)` · **FK** `(match_id, innings_no)` → innings

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id, innings_no | VARCHAR, INT | no | innings key | |
| pp_seq | INT | no | position in `inn.powerplays[]` | |
| from_ball | DOUBLE | no | `.from` | e.g. `0.1` = over 0, ball 1 |
| to_ball | DOUBLE | no | `.to` | e.g. `5.6` |
| type | VARCHAR | no | `.type` | `mandatory`, `batting`, `fielding` |

Never recorded for Tests; missing for 496 ODI and 135 T20 innings.

### `miscounted_overs`
Overs where the umpire gave the wrong number of balls.
**PK** `(match_id, innings_no, over_num)` · **FK** `(match_id, innings_no)` → innings

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id, innings_no | VARCHAR, INT | no | innings key | |
| over_num | INT | no | `inn.miscounted_overs` key | 0-based (verified on all 381) |
| balls | INT | no | `.balls` | legal balls actually bowled; sometimes text in JSON |
| umpire_id | VARCHAR | yes | `reg(.umpire)` | FK → people. If the name isn't in the registry (2 cases, e.g. "Bowden"), it's matched by surname to that match's umpires and a warning is recorded |

### `balls`
One row per delivery. The big table.
**PK** `(match_id, innings_no, over_num, ball_seq)` · **FK** `(match_id, innings_no)` → innings; `batter_id`, `non_striker_id`, `bowler_id` → people

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| match_id, innings_no | VARCHAR, INT | no | innings key | |
| over_num | INT | no | `ov.over` | 0-based |
| ball_seq | INT | no | `k + 1` | counts wides and no-balls |
| legal_ball_no | INT | no | computed | legal ball: legal balls so far in the over, this one included. Wide / no-ball: that count + 1 (the ball being attempted). Equals the part after the dot in `actual_delivery` (verified on all deliveries). |
| actual_delivery | VARCHAR | no | `d.actual_delivery` | e.g. `"0.1"`, stored as written |
| batter_id | VARCHAR | no | `reg(d.batter)` | |
| non_striker_id | VARCHAR | no | `reg(d.non_striker)` | |
| bowler_id | VARCHAR | no | `reg(d.bowler)` | |
| runs_batter | INT | no | `d.runs.batter` | |
| runs_extras | INT | no | `d.runs.extras` | |
| runs_total | INT | no | `d.runs.total` | |
| non_boundary | BOOLEAN | no | `d.runs.non_boundary` | default false |
| wides | INT | no | `d.extras.wides` | default 0 |
| noballs | INT | no | `d.extras.noballs` | default 0 |
| byes | INT | no | `d.extras.byes` | default 0 |
| legbyes | INT | no | `d.extras.legbyes` | default 0 |
| penalty | INT | no | `d.extras.penalty` | default 0 |

To find balls with a wicket, review or replacement, join those tables (or use the `deliveries` view).

### `wickets`
One row per wicket entry. A ball can have two (10 in the data).
**PK** `(match_id, innings_no, over_num, ball_seq, wicket_seq)` · **FK** ball key → balls, `player_out_id` → people

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| ball key (4 cols) | | no | | |
| wicket_seq | INT | no | `n + 1` | |
| player_out_id | VARCHAR | no | `reg(w.player_out)` | always in the match's player list |
| kind | VARCHAR | no | `w.kind` | 14 values, see §8 |
| bowler_credited | BOOLEAN | no | derived from `kind` | see §6 |
| is_dismissal | BOOLEAN | no | derived from `kind` | false for `retired hurt` and `retired not out` |

The bowler is the ball's `bowler_id`; join `balls`.

### `fielding`
One row per fielder named in a wicket.
**PK** wicket key + `fielder_seq` · **FK** wicket key → wickets, `fielder_id` → people

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| wicket key (5 cols) | | no | | |
| fielder_seq | INT | no | position in `w.fielders[]` | |
| fielder_id | VARCHAR | yes | `reg(w.fielders[].name)` | NULL on 32 of 112,841 entries (only "substitute" recorded) |
| is_substitute | BOOLEAN | no | `w.fielders[].substitute` | default false |

### `reviews`
One row per DRS review.
**PK** ball key · **FK** ball key → balls, `reviewing_team_id` → teams, `batter_id`, `umpire_id` → people

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| ball key (4 cols) | | no | | |
| reviewing_team_id | VARCHAR | no | `d.review.by` | |
| batter_id | VARCHAR | no | `reg(d.review.batter)` | the batter the review was about |
| umpire_id | VARCHAR | yes | `reg(d.review.umpire)` | missing on 155 reviews |
| decision | VARCHAR | no | `d.review.decision` | `upheld`, `struck down`, `technical failure` |
| umpires_call | BOOLEAN | no | `d.review.umpires_call` | default false |
| review_type | VARCHAR | yes | `d.review.type` | only value seen: `wicket` (on 3,980 of 12,317) |

### `replacements`
One row per substitution (Impact Player, concussion, injury…).
**PK** ball key + `scope` + `repl_seq` · **FK** ball key → balls, `team_id` → teams, `player_in_id`, `player_out_id` → people

| Column | Type | Null | Source | Notes |
|---|---|---|---|---|
| ball key (4 cols) | | no | | the ball it was recorded on |
| scope | VARCHAR | no | `d.replacements` key | `match` (player swapped for the match) / `role` (batter or bowler swapped mid-play) |
| repl_seq | INT | no | position in that list | |
| team_id | VARCHAR | yes | `.team` | only for scope `match` |
| player_in_id | VARCHAR | no | `reg(.in)` | |
| player_out_id | VARCHAR | yes | `reg(.out)` | can be missing for scope `role` |
| reason | VARCHAR | no | `.reason` | as written; values in §8 (`impact_player` = IPL Impact Player) |
| role | VARCHAR | yes | `.role` | `batter` / `bowler`, only for scope `role` |

### `load_log`
One row per loaded file.
**PK** `match_id` · **FK** `match_id` → matches

| Column | Type | Null | Notes |
|---|---|---|---|
| match_id | VARCHAR | no | |
| folder | VARCHAR | no | e.g. `ipl_male_json` |
| revision | INT | no | `meta.revision` |
| file_hash | VARCHAR | no | sha256 of the file bytes |
| loaded_at | TIMESTAMP | no | |

### `load_warnings`
Data oddities found during validation that don't stop the load (§7).
**No PK** (`innings_no` / `over_num` can be NULL) · **FK** `match_id` → matches

| Column | Type | Null | Notes |
|---|---|---|---|
| match_id | VARCHAR | no | |
| check_name | VARCHAR | no | `over_too_long`, `miscount_mismatch`, `umpire_name_not_in_registry`, `player_in_both_teams` |
| innings_no | INT | yes | |
| over_num | INT | yes | |
| detail | VARCHAR | no | e.g. `7 legal balls, balls_per_over 6` |
| found_at | TIMESTAMP | no | |

Rows for a match are cleared and re-checked whenever that match reloads.

### `bowler_types` (your reference list)
From `data/reference/bowler_types.csv` (currently empty).
**PK** `person_id` · **FK** `person_id` → people

| Column | Type | Null | Notes |
|---|---|---|---|
| person_id | VARCHAR | no | keyed by ID, so namesakes don't clash |
| name | VARCHAR | yes | for readability only; ignored by joins |
| bowler_type | VARCHAR | no | `pace` / `spin` |

---

## 4. Views

Views do the joins and add name columns, so most stats can be queried without writing joins. They're rebuilt from `cricsto/views.sql` after every load.

### `deliveries`
One row per ball. A flat, v1-compatible view: `balls` + `innings` + `matches` + names + wickets folded in.

| Column | Definition |
|---|---|
| dataset, season, start_date, match_type, gender, event | `matches` (`event` = `event_name`) |
| winner, toss_winner, toss_decision | team names via `teams` |
| venue, city | `venues.name`, `venues.city` |
| match_id, innings, over_num, ball_seq, legal_ball_no | `innings` = `innings_no` |
| ball | `over_num + legal_ball_no / 10.0` (e.g. `3.4`), v1 style; same as `actual_delivery` |
| batting_team, bowling_team | team names |
| striker, non_striker, bowler | names via `people` |
| batter_id, non_striker_id, bowler_id | IDs (new) |
| runs_off_bat, extras, total_runs | `runs_batter`, `runs_extras`, `runs_total` |
| wides, noballs, byes, legbyes, penalty, non_boundary | from `balls` |
| player_dismissed, player_dismissed_id, wicket_type | the wicket with `wicket_seq = 1` (any kind, retirements included, as in v1) |
| other_player_dismissed, other_player_dismissed_id, other_wicket_type | the wicket with `wicket_seq = 2` |
| is_wicket | a wicket on this ball with `is_dismissal` (**changed from v1:** retired hurt / retired not out no longer count) |
| bowler_wicket | a `bowler_credited` wicket on this ball |
| actual_delivery, batting_team_id, bowling_team_id, venue_id | IDs and Cricsheet label (new) |
| is_super_over | from `innings` (new) |
| in_powerplay | ball falls in a `powerplays` row; if the innings has none, the phase rule (new) |
| legal_ball, faced_ball, bowler_runs, is_four, is_six, is_dot, phase | §6 rules |

Changes from v1: `city` and `venue` come from the venue's latest name, so all names of a ground group together ("M Chinnaswamy Stadium, Bengaluru" for every match there). `is_wicket` excludes retirements.

**Checked against v1** (`tests/baseline_v1/`, 2026-11-10). Men's IPL, T20I and ODI totals per dataset and season are identical on all 114 seasons: matches, deliveries, runs, bat runs, extras, legal balls, wicket balls, fours and sixes. The insight queries return the same values, except for these intended changes:
- `wickets_per_over` drops in seasons with a retired-hurt ball;
- `venue_bat_first` merges renamed grounds;
- `recent_form` shows the venue's latest name;
- `t20s` / `odis` include women's matches unless filtered on `gender`.

Rows with equal values may come back in a different order, because the queries have no tie-break.

### `batter_innings`
One row per batter per innings. Excludes super overs.

| Column | Definition |
|---|---|
| dataset, match_id, season, start_date, match_type, gender, event, venue | from the match |
| innings, batting_team, bowling_team | from the innings |
| batter, batter_id | name and ID |
| batting_position | order of first appearance at the crease (as striker or non-striker) |
| runs, balls, fours, sixes, dots | sums over `deliveries` (balls = `faced_ball`) |
| is_out | a `wickets` row with this `player_out_id` and `is_dismissal` |
| how_out | that wicket's `kind` (NULL if not out) |

Batters who were at the crease but faced no ball (e.g. run out as non-striker) are included.

### `bowler_innings`
One row per bowler per innings. Excludes super overs.

| Column | Definition |
|---|---|
| match keys, innings, bowling_team, batting_team | as above |
| bowler, bowler_id | name and ID |
| legal_balls, overs | `overs` = `legal_balls // bpo + (legal_balls % bpo) / 10.0` (e.g. `3.4`) |
| runs | sum of `bowler_runs` |
| wickets | count of `bowler_credited` wickets |
| dots, fours, sixes, wides, noballs | sums |

### `dismissals`
One row per wicket entry.

| Column | Definition |
|---|---|
| dataset, match_id, innings, ball, over_num, ball_seq | from the ball |
| batter, batter_id | the player out |
| wicket_type | `kind` |
| bowler, bowler_id | the ball's bowler |
| bowler_credited, is_dismissal | from `wickets` |
| fielders | comma-joined fielder names (`sub` where unnamed) |
| fielder_ids | list of fielder IDs |

---

## 5. JSON coverage map

Every key in the JSON and where it lands. ✗ = deliberately not stored.

| JSON path | Lands in |
|---|---|
| `meta.data_version` / `created` / `revision` | `matches.data_version` / `meta_created` / `revision` |
| `info.balls_per_over` | `matches.balls_per_over` |
| `info.bowl_out` | `matches.bowl_out` (JSON) |
| `info.city` | `venues.city` (latest) |
| `info.dates` | `matches.start_date`, `end_date`, `num_days` |
| `info.event.name` / `match_number` / `group` / `stage` / `sub_name` | `matches.event_*` |
| `info.gender` / `team_type` / `match_type` / `match_type_number` / `season` / `overs` | `matches.*` |
| `info.missing` | `matches.missing` (JSON) |
| `info.officials.*` | `officials` |
| `info.outcome.winner` / `by.*` / `result` / `method` / `eliminator` / `bowl_out` | `matches.winner_id`, `win_by_*`, `result`, `method`, `eliminator_id`, `bowl_out_winner_id` |
| `info.player_of_match` | `player_of_match` |
| `info.players` | `match_players` |
| `info.registry.people` | `people` (and every `*_id` lookup) |
| `info.registry.venues` | `venues` |
| `info.supersubs` | `match_players.is_supersub` |
| `info.teams` | `teams`, `matches.team1_id`, `team2_id` |
| `info.toss.*` | `matches.toss_*` |
| `info.venue` | `venues.name`, `matches.venue_id` |
| `innings[].team` | `innings.batting_team_id` (bowling team derived) |
| `innings[].super_over` / `declared` / `forfeited` | `innings.*` |
| `innings[].target.*` / `penalty_runs.*` | `innings.target_*`, `penalty_runs_*` |
| `innings[].absent_hurt` | `absent_hurt` |
| `innings[].powerplays` | `powerplays` |
| `innings[].miscounted_overs` | `miscounted_overs` |
| `overs[].over` | `balls.over_num` |
| `deliveries[]` batter / non_striker / bowler / actual_delivery | `balls.*` |
| `deliveries[].runs.*` / `extras.*` | `balls.*` |
| `deliveries[].wickets[]` (player_out, kind) | `wickets` |
| `deliveries[].wickets[].fielders[]` (name, substitute) | `fielding` |
| `deliveries[].review.*` | `reviews` |
| `deliveries[].replacements.match[]` / `.role[]` | `replacements` |
| Names a person used in older matches | ✗ (lookup tables keep the latest name only) |
| Venue names / cities from older matches | ✗ (same) |
| `README.txt`, `LICENSE.txt` | ✗ |

---

## 6. Cricket rules (used by the views)

| Term | Rule |
|---|---|
| Legal ball | `wides = 0 AND noballs = 0` (counts toward the over) |
| Ball faced by the batter | `wides = 0` |
| Bowler's runs | `runs_batter + wides + noballs` (byes, leg byes and penalties aren't charged) |
| Dot ball | `runs_total = 0` |
| Four / six | `runs_batter = 4` / `6` and not `non_boundary` |
| Bowler-credited wicket | `kind` in (bowled, caught, caught and bowled, lbw, stumped, hit wicket) |
| Dismissal (batter is out) | any `kind` except `retired hurt` and `retired not out` |
| T20 phases | powerplay overs 1–6, middle 7–15, death 16–20 (`over_num` 0–5, 6–14, 15–19) |
| ODI phases | 1–10, 11–40, 41–50 (`over_num` 0–9, 10–39, 40–49) |
| Tests | no phase |
| Super overs | excluded from `batter_innings`, `bowler_innings` and most stats |

---

## 7. Loading and validation

The loader only reads what is in `data/raw/json/`; it never downloads. Getting new files there is the refresh job (§7a).

1. **Scan folders.** List every `<match_id>.json` under `data/raw/json/<code>_<gender>_json/`. Files are never modified.
2. **Detect changes** against `load_log`:
   - **new** file (not in `load_log`) → load;
   - **changed** file (different hash or `meta.revision`) → delete the match's rows, then load (corrected matches reload automatically);
   - **unchanged** → skip;
   - **gone** (in `load_log` but no file any more, e.g. a withdrawn match) → delete the match's rows.

   `--full` drops every table and reloads everything (for schema changes).
3. **Parse in Python** (`json` module), one file at a time, walking the tree once. Names become IDs through that match's `registry.people`. Types are normalised: `season` → text, `event.group` → text, `miscounted_overs.balls` → int, missing flags → false, missing extras → 0.
4. **Delete** the rows of changed and gone matches, child-first, **one committed transaction per level**: fielding → wickets, reviews, replacements → balls → absent_hurt, powerplays, miscounted_overs → innings, match_players, officials, player_of_match, name_sources, load_warnings, load_log → matches. DuckDB won't delete a parent row in the same transaction as its children (tested on DuckDB 2.0.0), so this can't share one transaction with the inserts.
5. **Insert in one transaction.** Files are parsed in parallel and inserted in chunks of 500 (DataFrames per table): new IDs go into `people` / `venues` / `teams` first, then matches and their children, then `load_log`. At the end, lookup names are recomputed from `name_sources` (latest match wins), and validation runs. An error rolls back the whole transaction.

   **Guarantee:** a match is always fully loaded or absent, never half-loaded. If a run fails after step 4, the matches it was reloading are absent. Their `load_log` rows are gone too, so the next run loads them as new.
6. **Validate.** Errors stop the load and roll back; warnings are printed and saved, and the load continues.
   - **Errors:**
     - every foreign key resolves (enforced by the constraints themselves);
     - every `player_out_id` is in that match's `match_players`;
     - `legal_ball_no` matches `actual_delivery` on every ball;
     - `info.gender` matches the folder; no `match_id` appears in two folders; rows per folder = files per folder;
     - no `team_id` hash collisions.
   - **Warnings** (in table `load_warnings`: match_id, innings_no, over_num, check, detail):
     - an over has more legal balls than `balls_per_over` and isn't listed in `miscounted_overs`. Known case: match `1298152`, `over_num` 8 (7 balls);
     - an over in `miscounted_overs` whose legal-ball count differs from the recorded `balls`;
     - a `miscounted_overs.umpire` name not in the registry (resolved by surname where possible);
     - a player listed for both teams.
7. **Rebuild views** from `views.sql`.

### 7a. Refresh (getting new files into the folders)

Separate from the loader (`scripts/refresh.py`). Both modes only change files in `data/raw/json/`, then run the incremental loader.

| | Weekly diff | Monthly full sync |
|---|---|---|
| Downloads | `recently_added_7_male_json.zip`, `recently_added_7_female_json.zip` (all competitions, small) | the 8 full zips, `https://cricsheet.org/downloads/<code>_<gender>_json.zip` |
| Files | routed into our folders by their `info`; other competitions skipped; existing files overwritten | each folder's `.json` files replaced by the zip's contents |
| Catches | new matches | corrections, withdrawn matches, anything the diff missed |

Cricsheet doesn't say whether corrected matches reappear in the "recently added" zips, which is why the monthly full sync exists.

Routing rules (a file goes to the first rule it matches; no match = skipped):

| Rule | Folder |
|---|---|
| `event.name = "Indian Premier League"` | `ipl_male_json` |
| `event.name = "Women's Premier League"` | `wpl_female_json` |
| `team_type = international`, `match_type = T20` | `t20s_<gender>_json` |
| `team_type = international`, `match_type = ODI` | `odis_<gender>_json` |
| `team_type = international`, `match_type = Test` | `tests_<gender>_json` |

Before use, the rules are tested on the existing files: every file must route to the folder it already sits in.

**Foreign keys (tested on DuckDB 2.0.0):** updating or upserting a referenced row (e.g. `people.name`) works, so all foreign keys are declared and enforced. The only limitation is the delete order in step 4.

**Performance:** a full load of all 11,340 files takes about 40 seconds (16 CPUs).

---

## 8. Data notes (from scanning every file, 2026-11-10)

| Folder | Matches |
|---|---|
| ipl_male_json | 1,243 (seasons 2007/08 → 2026) |
| wpl_female_json | 88 (2022/23 → 2025/26) |
| odis_male_json / odis_female_json | 2,617 / 620 |
| t20s_male_json / t20s_female_json | 3,649 / 2,200 |
| tests_male_json / tests_female_json | 899 / 24 |

- **Value lists:**
  - wicket `kind`: caught, bowled, lbw, run out, caught and bowled, stumped, retired hurt, hit wicket, retired out, obstructing the field, retired not out, timed out, hit the ball twice, handled the ball
  - review `decision`: upheld, struck down, technical failure
  - replacement `reason`, scope `match`: impact_player, supersub, concussion_substitute, covid_replacement, unknown
  - replacement `reason`, scope `role`: injury, unknown, excluded - high full pitched balls, excluded - running on the pitch, too many overs
  - powerplay `type`: mandatory, batting, fielding
- **Impact Player:** match-level replacement with `reason = "impact_player"` (557 in IPL; e.g. match `1359475`, TU Deshpande in for AT Rayudu).
- **Season labels:** IPL `2007/08` is IPL 2008, `2009/10` is 2010, `2020/21` is 2020; WPL uses `2022/23` etc. Text comparisons like `season >= '2018'` still work.
- **Type quirks:** `season`, `event.group` and `miscounted_overs.balls` mix numbers and text; `target.overs` is sometimes fractional.
- **Balls per over:** every match has `balls_per_over = 6`. Legal balls per over:

  | Legal balls | Overs | Why |
  |---|---|---|
  | 6 | 824,650 | normal |
  | 0–5 | 11,031 | innings ended mid-over, or a short miscount (184 listed in `miscounted_overs`) |
  | 7 | 197 | umpire miscount (196 listed) |
  | 8 | 1 | umpire miscount (listed) |

  The one unlisted 7-ball over is match `1298152`, `over_num` 8; it becomes a load warning.
- **Ball numbering:** `actual_delivery` labels wides and no-balls with the next legal ball's number; this held on all 5.1M deliveries, and `legal_ball_no` follows it.
- **Source errors handled as warnings** (in `load_warnings` after a full load):
  - match `1229824` (Isle of Man v Guernsey T20I): "J Butler" is listed for both teams with the same ID;
  - matches `325580`, `936133`: `miscounted_overs.umpire` is "Bowden" / "Nigel Llong", not the registry names "BF Bowden" / "NJ Llong"; resolved by surname.
- **Edge cases:** 10 balls with two wickets; match `1485939` (Netherlands v Nepal T20I) has 6 super-over innings; `toss.uncontested` appears once; `bowl_out` twice.
- **Optional fields:** `city`, `event`, `officials`, `player_of_match`, `overs`, `event.match_number`, `review.umpire`, `fielders[].name`.
- **Integrity (all hold):**
  - every name has a registry ID;
  - every team reference is one of `info.teams`;
  - every `player_out` is in the player list;
  - supersubs are in the player list.

---

## 9. Query cookbook

Top IPL run-scorers in 2025, from the raw tables:
```sql
SELECT p.name, sum(b.runs_batter) AS runs
FROM balls b
JOIN innings i ON i.match_id = b.match_id AND i.innings_no = b.innings_no
JOIN matches m ON m.match_id = b.match_id
JOIN people  p ON p.person_id = b.batter_id
WHERE m.dataset = 'ipl' AND m.season = '2025' AND NOT i.is_super_over
GROUP BY p.person_id, p.name
ORDER BY runs DESC LIMIT 10;
```

A specific ball: the 5th ball of the 12th over, 2nd innings of a match:
```sql
SELECT b.ball_seq, b.legal_ball_no, b.actual_delivery, p.name AS batter, b.runs_total, b.wides, b.noballs
FROM balls b JOIN people p ON p.person_id = b.batter_id
WHERE b.match_id = '1359475' AND b.innings_no = 2
  AND b.over_num = 11 AND b.legal_ball_no = 5   -- add: AND b.wides = 0 AND b.noballs = 0  for the legal ball only
ORDER BY b.ball_seq;
```

Find a player's ID (handles namesakes):
```sql
SELECT p.person_id, p.name, count(DISTINCT mp.match_id) AS matches,
       min(m.start_date) AS first, max(m.start_date) AS last
FROM people p
JOIN match_players mp ON mp.person_id = p.person_id
JOIN matches m ON m.match_id = mp.match_id
WHERE p.name ILIKE '%rashid khan%'
GROUP BY ALL;
```

Wickets by dismissal kind for one bowler:
```sql
SELECT w.kind, count(*) AS n
FROM wickets w
JOIN balls b USING (match_id, innings_no, over_num, ball_seq)
WHERE b.bowler_id = $bowler_id AND w.bowler_credited
GROUP BY w.kind ORDER BY n DESC;
```

Impact Player substitutions per IPL team:
```sql
SELECT t.name AS team, count(*) AS impact_subs
FROM replacements r
JOIN teams t ON t.team_id = r.team_id
WHERE r.reason = 'impact_player'
GROUP BY t.name ORDER BY impact_subs DESC;
```

DRS success rate by team:
```sql
SELECT t.name, count(*) AS reviews,
       round(100.0 * avg((r.decision = 'upheld')::INT), 1) AS success_pct
FROM reviews r JOIN teams t ON t.team_id = r.reviewing_team_id
GROUP BY t.name HAVING count(*) >= 50 ORDER BY success_pct DESC;
```

Results at a venue (all its names collapse to one ID):
```sql
SELECT v.name, m.season, tw.name AS winner, m.win_by_runs, m.win_by_wickets
FROM matches m
JOIN venues v ON v.venue_id = m.venue_id
LEFT JOIN teams tw ON tw.team_id = m.winner_id
WHERE v.name ILIKE '%Wankhede%' ORDER BY m.start_date;
```

Top catchers (fielding):
```sql
SELECT p.name, count(*) AS catches
FROM fielding f
JOIN wickets w USING (match_id, innings_no, over_num, ball_seq, wicket_seq)
JOIN people p ON p.person_id = f.fielder_id
WHERE w.kind = 'caught'
GROUP BY p.person_id, p.name ORDER BY catches DESC LIMIT 10;
```

The same questions via views (no joins): `SELECT striker, sum(runs_off_bat) FROM deliveries WHERE dataset = 'ipl' AND season = '2025' AND NOT is_super_over GROUP BY striker`, which groups by name. Use the ID columns when namesakes matter.
