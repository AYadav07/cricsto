# Cricsto database design (Cricsheet JSON → DuckDB)

Status: design, not yet implemented. Source format: Cricsheet JSON (data_version 1.x).

## Principles

1. **Raw JSON is the source of truth.** Files in `data/raw/<dataset>/` are never edited; the database can always be rebuilt from them.
2. **One table per real-world thing** (match, innings, ball, wicket, review…), not one giant table. Lists inside the JSON (wickets on a ball, fielders on a wicket, players in a team) become their own tables.
3. **Store facts, derive the rest in views.** Tables hold what Cricsheet recorded; flags like `is_four` or `phase` live in views so the rules can change without reloading.
4. **Backward compatible.** The `deliveries`, `batter_innings` and `dismissals` views keep their current column names, so existing queries keep working.
5. **Player IDs everywhere.** Every name column has a matching `_id` from Cricsheet's registry, so name spellings never split a player's stats.

## Keys

- `match_id`: the JSON file name (e.g. `1359475`). Unique across all of Cricsheet.
- A ball is identified by `(match_id, innings_no, over_num, ball_seq)`.
  - `over_num`: 0-based over, as in the JSON (`0` = first over).
  - `ball_seq`: 1-based position of the delivery within the over's list, **counting wides and no-balls**.
  - `legal_ball_no`: the legal-ball count in the over after this delivery (a wide repeats the previous number).
- A wicket is `(ball key, wicket_seq)`; a fielder is `(wicket key, fielder_seq)`.

## Tables

### `matches`: one row per match
| Column | Type | From JSON |
|---|---|---|
| match_id | VARCHAR PK | file name |
| dataset | VARCHAR | download folder (ipl, t20s…) |
| data_version, revision, created | VARCHAR, INT, DATE | meta.* |
| match_type, match_type_number | VARCHAR, INT | info.match_type, info.match_type_number |
| gender, team_type | VARCHAR | info.gender, info.team_type |
| season | VARCHAR | info.season ("2024", "2011/12") |
| start_date, end_date, num_days | DATE, DATE, INT | info.dates[] (first, last, count) |
| city, venue, venue_id | VARCHAR | info.city, info.venue, registry.venues |
| event_name, event_match_number, event_group, event_stage | VARCHAR, INT, VARCHAR, VARCHAR | info.event.* |
| team1, team2 | VARCHAR | info.teams[0], [1] |
| balls_per_over, overs | INT | info.balls_per_over, info.overs |
| toss_winner, toss_decision, toss_uncontested | VARCHAR, VARCHAR, BOOLEAN | info.toss.* |
| winner | VARCHAR | info.outcome.winner |
| win_by_runs, win_by_wickets, win_by_innings | INT | info.outcome.by.* |
| result | VARCHAR | info.outcome.result (tie / draw / no result) |
| method | VARCHAR | info.outcome.method (D/L, VJD…) |
| eliminator, bowl_out_winner | VARCHAR | info.outcome.eliminator / bowl_out (tie-breakers) |
| player_of_match | VARCHAR[] | info.player_of_match |
| missing | JSON | info.missing (what Cricsheet says is unrecorded) |

### `people`: one row per person (players and officials)
| Column | Type | From JSON |
|---|---|---|
| person_id | VARCHAR PK | registry.people values (8-char ID) |
| name | VARCHAR | most recent name used with that ID |

### `match_players`: one row per player per match (playing XIs)
| Column | Type | From JSON |
|---|---|---|
| match_id, team | VARCHAR | info.players key |
| player, player_id | VARCHAR | info.players[team][], registry |
| list_order | INT | position in the list |
| is_supersub | BOOLEAN | info.supersubs |

### `officials`: one row per official per match
| match_id | role (umpire / tv_umpire / match_referee / reserve_umpire) | name | person_id |
|---|---|---|---|

### `innings`: one row per innings
| Column | Type | From JSON |
|---|---|---|
| match_id, innings_no | VARCHAR, INT | position in innings[] (1-based) |
| batting_team, bowling_team | VARCHAR | innings[].team; bowling = the other team |
| is_super_over, declared, forfeited | BOOLEAN | innings[].super_over / declared / forfeited |
| target_runs, target_overs | INT, DOUBLE | innings[].target.* (incl. DLS-revised) |
| penalty_runs_pre, penalty_runs_post | INT | innings[].penalty_runs.* |
| absent_hurt | VARCHAR[] | innings[].absent_hurt |

### `balls`: one row per delivery (the big table)
| Column | Type | From JSON |
|---|---|---|
| match_id, innings_no, over_num, ball_seq | key | see Keys |
| legal_ball_no | INT | computed while loading |
| actual_delivery | VARCHAR | delivery.actual_delivery (if present) |
| batter, batter_id | VARCHAR | delivery.batter + registry |
| non_striker, non_striker_id | VARCHAR | delivery.non_striker + registry |
| bowler, bowler_id | VARCHAR | delivery.bowler + registry |
| runs_batter, runs_extras, runs_total | INT | delivery.runs.* |
| non_boundary | BOOLEAN | delivery.runs.non_boundary |
| wides, noballs, byes, legbyes, penalty | INT (0 if absent) | delivery.extras.* |
| has_wicket, has_review, has_replacement | BOOLEAN | presence of wickets / review / replacements |

### `wickets`: one row per dismissal (a ball can have two)
| match_id, innings_no, over_num, ball_seq, wicket_seq | player_out, player_out_id | kind | bowler, bowler_id | bowler_credited (BOOLEAN) |
|---|---|---|---|---|

`bowler_credited` = kind in (bowled, caught, caught and bowled, lbw, stumped, hit wicket).

### `fielding`: one row per fielder involved in a wicket
| wicket key + fielder_seq | fielder, fielder_id | is_substitute (if recorded) |
|---|---|---|

### `reviews`: one row per DRS review
| ball key | reviewing_team | batter, batter_id | umpire | decision (upheld / struck down) | umpires_call | review_type (if recorded) |
|---|---|---|---|---|---|---|

### `replacements`: one row per substitution
| ball key | scope (match / role) | team | player_in, player_in_id | player_out, player_out_id | reason | role (batter / bowler, for scope = role) |
|---|---|---|---|---|---|---|

Covers concussion, injury and tactical substitutes, and Impact Players where Cricsheet records them. `reason` is stored exactly as Cricsheet writes it.

### `powerplays`: one row per powerplay period
| match_id, innings_no | from_ball, to_ball (DOUBLE, e.g. 0.1 → 5.6) | type (mandatory / batting / fielding) |
|---|---|---|

### `load_log`: what has been loaded
| match_id | dataset | file_name | revision | file_hash | loaded_at |
|---|---|---|---|---|---|

### `bowler_types`: your reference list (CSV, unchanged)
| bowler | bowler_type |
|---|---|

## Relationships

```
matches 1──* innings 1──* balls 1──* wickets 1──* fielding
   │                       ├──0..1 reviews
   │                       └──* replacements
   ├──* match_players *──1 people
   ├──* officials     *──1 people
   └──* powerplays (per innings)
```

## Views (derived, rebuilt on every load)

- **`deliveries`**: `balls` joined to `innings` and `matches`, with the same columns as today (`striker`, `runs_off_bat`, `extras`, `player_dismissed`, `wicket_type`, `other_player_dismissed`…, `over_num`, `phase`, `legal_ball`, `faced_ball`, `total_runs`, `bowler_runs`, `is_four`, `is_six`, `is_dot`, `is_wicket`, `bowler_wicket`) plus new ones: `batter_id`, `bowler_id`, `in_powerplay` (from the real `powerplays` table where recorded), `is_super_over`.
- **`batter_innings`**: one row per batter per innings (runs, balls, 4s, 6s, out, how out, batting position).
- **`bowler_innings`**: one row per bowler per innings (overs, runs, wickets, dots, wides, no-balls).
- **`dismissals`**: wickets with fielders attached.
- Super overs are excluded from `batter_innings` and `bowler_innings` by default.

## Conversion: how a JSON file becomes rows

1. **Download** `<code>_json.zip` from Cricsheet into `data/raw/<dataset>/` (one `.json` per match, kept untouched).
2. **Detect changes.** For each file, compare `meta.revision` and a file hash with `load_log`; skip unchanged files. Corrected matches get reloaded automatically.
3. **Parse in Python** (`json` module), one file at a time, walking the tree once:
   - `info` → 1 `matches` row, `match_players`, `officials`, and every `registry.people` pair into `people`.
   - each `innings[i]` → 1 `innings` row (`innings_no = i + 1`) and its `powerplays`.
   - each `overs[o].deliveries[d]` → 1 `balls` row (`over_num = overs[o].over`, `ball_seq = d + 1`, `legal_ball_no` counted as you go, skipping wides and no-balls).
   - each `wickets[w]` → 1 `wickets` row; each `fielders[f]` → 1 `fielding` row.
   - `review` → 1 `reviews` row; `replacements.match[]` and `.role[]` → `replacements` rows.
   - Names are mapped to IDs with that match's `registry.people`.
4. **Bulk write.** Rows are collected into DataFrames per table and inserted in batches. For a changed match, its old rows are deleted from every table first (delete + insert inside one transaction), so the database is never half-updated.
5. **Validate** after each load (fail loudly, never silently):
   - sum of `runs_total` per innings + penalty runs = innings total implied by the data;
   - legal balls per over ≤ `balls_per_over` (except overs listed in `miscounted_overs`);
   - every `player_out` is in that match's `match_players`;
   - every name has an ID; match counts per dataset match the number of files.
6. **Rebuild views** from `views.sql`.

Why Python rather than DuckDB's `read_json` for parsing: several JSON parts use team or player names as keys (`players`, `registry.people`, `supersubs`), which flatten more clearly and testably in code. DuckDB still does all the querying.

## Scale

All of Cricsheet is roughly 20k matches and a few million deliveries. The database stays well under 1 GB and a full rebuild takes minutes; weekly refreshes only load new or changed files.

## Open questions

- Confirm Cricsheet's exact `reason` value for IPL Impact Players by inspecting a 2023+ IPL file.
- Confirm whether `fielders[].substitute` and `review.type` appear in real files (not in the format page).
