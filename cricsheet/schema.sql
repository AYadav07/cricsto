-- Cricsto v2 tables (Cricsheet JSON -> DuckDB). Design and column sources: SCHEMA.md.
-- Created in dependency order: lookups, matches, match children, innings children, ball children.

-- ---------- lookup tables: one row per ID, one name ----------

CREATE TABLE IF NOT EXISTS people (
    person_id        VARCHAR PRIMARY KEY,
    name             VARCHAR NOT NULL            -- name from the most recent match
);

CREATE TABLE IF NOT EXISTS venues (
    venue_id         VARCHAR PRIMARY KEY,
    name             VARCHAR NOT NULL,           -- name from the most recent match
    city             VARCHAR                     -- most recent non-null city
);

CREATE TABLE IF NOT EXISTS teams (
    team_id          VARCHAR PRIMARY KEY,        -- md5(name)[:8], made by us
    name             VARCHAR NOT NULL UNIQUE,
    team_type        VARCHAR NOT NULL            -- international / club
);

-- ---------- matches ----------

CREATE TABLE IF NOT EXISTS matches (
    match_id            VARCHAR PRIMARY KEY,
    dataset             VARCHAR NOT NULL,
    gender              VARCHAR NOT NULL,
    team_type           VARCHAR NOT NULL,
    match_type          VARCHAR NOT NULL,
    match_type_number   INTEGER,
    season              VARCHAR NOT NULL,
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    num_days            INTEGER NOT NULL,
    venue_id            VARCHAR NOT NULL REFERENCES venues (venue_id),
    event_name          VARCHAR,
    event_match_number  INTEGER,
    event_group         VARCHAR,
    event_stage         VARCHAR,
    event_sub_name      VARCHAR,
    team1_id            VARCHAR NOT NULL REFERENCES teams (team_id),
    team2_id            VARCHAR NOT NULL REFERENCES teams (team_id),
    balls_per_over      INTEGER NOT NULL,
    overs               INTEGER,
    toss_winner_id      VARCHAR NOT NULL REFERENCES teams (team_id),
    toss_decision       VARCHAR NOT NULL,
    toss_uncontested    BOOLEAN NOT NULL,
    winner_id           VARCHAR REFERENCES teams (team_id),
    win_by_runs         INTEGER,
    win_by_wickets      INTEGER,
    win_by_innings      INTEGER,
    result              VARCHAR,
    method              VARCHAR,
    eliminator_id       VARCHAR REFERENCES teams (team_id),
    bowl_out_winner_id  VARCHAR REFERENCES teams (team_id),
    bowl_out            JSON,
    missing             JSON,
    data_version        VARCHAR NOT NULL,
    meta_created        DATE NOT NULL,
    revision            INTEGER NOT NULL
);

-- Where each lookup name came from: one row per (match, person / venue / team).
-- The lookup tables' names are recomputed from this after every load, so a
-- corrected or removed match also corrects the name. Not for analysis.
CREATE TABLE IF NOT EXISTS name_sources (
    match_id         VARCHAR NOT NULL REFERENCES matches (match_id),
    kind             VARCHAR NOT NULL,           -- person / venue / team
    key_id           VARCHAR NOT NULL,
    name             VARCHAR NOT NULL,
    city             VARCHAR,                    -- venue only
    team_type        VARCHAR,                    -- team only
    PRIMARY KEY (match_id, kind, key_id)
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id         VARCHAR NOT NULL REFERENCES matches (match_id),
    person_id        VARCHAR NOT NULL REFERENCES people (person_id),
    team_id          VARCHAR NOT NULL REFERENCES teams (team_id),
    list_order       INTEGER NOT NULL,
    is_supersub      BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, team_id, person_id)   -- one Cricsheet error lists a player for both teams
);

CREATE TABLE IF NOT EXISTS officials (
    match_id         VARCHAR NOT NULL REFERENCES matches (match_id),
    role             VARCHAR NOT NULL,           -- umpire / tv_umpire / match_referee / reserve_umpire
    person_id        VARCHAR NOT NULL REFERENCES people (person_id),
    list_order       INTEGER NOT NULL,
    PRIMARY KEY (match_id, role, person_id)
);

CREATE TABLE IF NOT EXISTS player_of_match (
    match_id         VARCHAR NOT NULL REFERENCES matches (match_id),
    person_id        VARCHAR NOT NULL REFERENCES people (person_id),
    PRIMARY KEY (match_id, person_id)
);

-- ---------- innings ----------

CREATE TABLE IF NOT EXISTS innings (
    match_id           VARCHAR NOT NULL REFERENCES matches (match_id),
    innings_no         INTEGER NOT NULL,
    batting_team_id    VARCHAR NOT NULL REFERENCES teams (team_id),
    bowling_team_id    VARCHAR NOT NULL REFERENCES teams (team_id),
    is_super_over      BOOLEAN NOT NULL,
    declared           BOOLEAN NOT NULL,
    forfeited          BOOLEAN NOT NULL,
    target_runs        INTEGER,
    target_overs       DOUBLE,
    penalty_runs_pre   INTEGER NOT NULL,
    penalty_runs_post  INTEGER NOT NULL,
    PRIMARY KEY (match_id, innings_no)
);

CREATE TABLE IF NOT EXISTS absent_hurt (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    person_id        VARCHAR NOT NULL REFERENCES people (person_id),
    PRIMARY KEY (match_id, innings_no, person_id),
    FOREIGN KEY (match_id, innings_no) REFERENCES innings (match_id, innings_no)
);

CREATE TABLE IF NOT EXISTS powerplays (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    pp_seq           INTEGER NOT NULL,
    from_ball        DOUBLE NOT NULL,
    to_ball          DOUBLE NOT NULL,
    type             VARCHAR NOT NULL,           -- mandatory / batting / fielding
    PRIMARY KEY (match_id, innings_no, pp_seq),
    FOREIGN KEY (match_id, innings_no) REFERENCES innings (match_id, innings_no)
);

CREATE TABLE IF NOT EXISTS miscounted_overs (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    over_num         INTEGER NOT NULL,           -- 0-based
    balls            INTEGER NOT NULL,           -- legal balls actually bowled
    umpire_id        VARCHAR REFERENCES people (person_id),
    PRIMARY KEY (match_id, innings_no, over_num),
    FOREIGN KEY (match_id, innings_no) REFERENCES innings (match_id, innings_no)
);

-- ---------- balls ----------

CREATE TABLE IF NOT EXISTS balls (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    over_num         INTEGER NOT NULL,           -- 0-based
    ball_seq         INTEGER NOT NULL,           -- 1-based, counts wides and no-balls
    legal_ball_no    INTEGER NOT NULL,           -- legal balls only; extras carry the ball being attempted
    actual_delivery  VARCHAR NOT NULL,
    batter_id        VARCHAR NOT NULL REFERENCES people (person_id),
    non_striker_id   VARCHAR NOT NULL REFERENCES people (person_id),
    bowler_id        VARCHAR NOT NULL REFERENCES people (person_id),
    runs_batter      INTEGER NOT NULL,
    runs_extras      INTEGER NOT NULL,
    runs_total       INTEGER NOT NULL,
    non_boundary     BOOLEAN NOT NULL,
    wides            INTEGER NOT NULL,
    noballs          INTEGER NOT NULL,
    byes             INTEGER NOT NULL,
    legbyes          INTEGER NOT NULL,
    penalty          INTEGER NOT NULL,
    PRIMARY KEY (match_id, innings_no, over_num, ball_seq),
    FOREIGN KEY (match_id, innings_no) REFERENCES innings (match_id, innings_no)
);

CREATE TABLE IF NOT EXISTS wickets (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    over_num         INTEGER NOT NULL,
    ball_seq         INTEGER NOT NULL,
    wicket_seq       INTEGER NOT NULL,
    player_out_id    VARCHAR NOT NULL REFERENCES people (person_id),
    kind             VARCHAR NOT NULL,
    bowler_credited  BOOLEAN NOT NULL,
    is_dismissal     BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, innings_no, over_num, ball_seq, wicket_seq),
    FOREIGN KEY (match_id, innings_no, over_num, ball_seq)
        REFERENCES balls (match_id, innings_no, over_num, ball_seq)
);

CREATE TABLE IF NOT EXISTS fielding (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    over_num         INTEGER NOT NULL,
    ball_seq         INTEGER NOT NULL,
    wicket_seq       INTEGER NOT NULL,
    fielder_seq      INTEGER NOT NULL,
    fielder_id       VARCHAR REFERENCES people (person_id),   -- NULL when only "substitute" is recorded
    is_substitute    BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, innings_no, over_num, ball_seq, wicket_seq, fielder_seq),
    FOREIGN KEY (match_id, innings_no, over_num, ball_seq, wicket_seq)
        REFERENCES wickets (match_id, innings_no, over_num, ball_seq, wicket_seq)
);

CREATE TABLE IF NOT EXISTS reviews (
    match_id           VARCHAR NOT NULL,
    innings_no         INTEGER NOT NULL,
    over_num           INTEGER NOT NULL,
    ball_seq           INTEGER NOT NULL,
    reviewing_team_id  VARCHAR NOT NULL REFERENCES teams (team_id),
    batter_id          VARCHAR NOT NULL REFERENCES people (person_id),
    umpire_id          VARCHAR REFERENCES people (person_id),
    decision           VARCHAR NOT NULL,         -- upheld / struck down / technical failure
    umpires_call       BOOLEAN NOT NULL,
    review_type        VARCHAR,
    PRIMARY KEY (match_id, innings_no, over_num, ball_seq),
    FOREIGN KEY (match_id, innings_no, over_num, ball_seq)
        REFERENCES balls (match_id, innings_no, over_num, ball_seq)
);

CREATE TABLE IF NOT EXISTS replacements (
    match_id         VARCHAR NOT NULL,
    innings_no       INTEGER NOT NULL,
    over_num         INTEGER NOT NULL,
    ball_seq         INTEGER NOT NULL,
    scope            VARCHAR NOT NULL,           -- match / role
    repl_seq         INTEGER NOT NULL,
    team_id          VARCHAR REFERENCES teams (team_id),
    player_in_id     VARCHAR NOT NULL REFERENCES people (person_id),
    player_out_id    VARCHAR REFERENCES people (person_id),
    reason           VARCHAR NOT NULL,
    role             VARCHAR,
    PRIMARY KEY (match_id, innings_no, over_num, ball_seq, scope, repl_seq),
    FOREIGN KEY (match_id, innings_no, over_num, ball_seq)
        REFERENCES balls (match_id, innings_no, over_num, ball_seq)
);

-- ---------- bookkeeping ----------

CREATE TABLE IF NOT EXISTS load_log (
    match_id         VARCHAR PRIMARY KEY REFERENCES matches (match_id),
    folder           VARCHAR NOT NULL,
    revision         INTEGER NOT NULL,
    file_hash        VARCHAR NOT NULL,
    loaded_at        TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS load_warnings (
    match_id         VARCHAR NOT NULL REFERENCES matches (match_id),
    check_name       VARCHAR NOT NULL,
    innings_no       INTEGER,
    over_num         INTEGER,
    detail           VARCHAR NOT NULL,
    found_at         TIMESTAMP NOT NULL
);
