-- history.duckdb: scorecard-level Tests (1877-) and ODIs (1971-), men's.
-- Separate from cricsheet/data/cricsto.duckdb (Cricsheet ball-by-ball). Nothing here references it.
--
-- NULL always means "not recorded", never zero. Coverage by era is in history/README.md.
-- IDs are the source dataset's player/match IDs (ESPNcricinfo-based), not Cricsheet IDs.

CREATE TABLE players (
    player_id        BIGINT PRIMARY KEY,
    object_id        BIGINT,          -- ESPNcricinfo profile object id
    name             VARCHAR,
    dob              DATE,
    dod              DATE,
    gender           VARCHAR,         -- M / F
    batting_style    VARCHAR,         -- e.g. right-hand bat
    bowling_style    VARCHAR,         -- e.g. right-arm fast-medium, legbreak googly
    country_id       INTEGER
);

CREATE TABLE matches (
    match_id         BIGINT PRIMARY KEY,
    format           VARCHAR NOT NULL,   -- test / odi
    match_no         INTEGER,            -- Test # / ODI #
    match_name       VARCHAR,
    series_id        BIGINT,
    series_name      VARCHAR,
    start_date       DATE,
    end_date         DATE,               -- Tests only
    team1            VARCHAR,
    team1_id         BIGINT,
    team1_captain_id BIGINT,
    team2            VARCHAR,
    team2_id         BIGINT,
    team2_captain_id BIGINT,
    venue            VARCHAR,
    city             VARCHAR,
    country          VARCHAR,
    umpire1          VARCHAR,
    umpire2          VARCHAR,
    referee          VARCHAR,
    toss_winner      VARCHAR,
    toss_decision    VARCHAR,            -- bat / bowl
    winner           VARCHAR,            -- NULL for draw / tie / no result
    result_text      VARCHAR,
    player_of_match_id BIGINT,
    balls_per_over   INTEGER NOT NULL,   -- 6 or 8
    bpo_source       VARCHAR NOT NULL    -- 'detected' (an over ended .6/.7), 'series' (another match in the series did), 'default'
);

CREATE TABLE match_players (
    match_id         BIGINT NOT NULL REFERENCES matches (match_id),
    team             VARCHAR NOT NULL,
    player_id        BIGINT NOT NULL,
    list_order       INTEGER NOT NULL,
    is_debut         BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, team, player_id)
);

CREATE TABLE innings (
    match_id         BIGINT NOT NULL REFERENCES matches (match_id),
    innings_no       INTEGER NOT NULL,   -- order in the match (1-4)
    batting_team     VARCHAR NOT NULL,
    bowling_team     VARCHAR,
    team_innings_no  INTEGER NOT NULL,   -- 1st or 2nd innings of that team
    runs             INTEGER,            -- total from the match record
    wickets          INTEGER,
    extras           INTEGER,
    PRIMARY KEY (match_id, innings_no)
);

CREATE TABLE batting (
    match_id         BIGINT NOT NULL REFERENCES matches (match_id),
    innings_no       INTEGER NOT NULL,
    team             VARCHAR NOT NULL,
    position         INTEGER NOT NULL,   -- batting order as listed on the card
    player_id        BIGINT,             -- NULL on a handful of malformed rows
    did_bat          BOOLEAN NOT NULL,   -- false = did not bat
    runs             INTEGER,
    balls            INTEGER,
    fours            INTEGER,
    sixes            INTEGER,
    is_out           BOOLEAN,
    dismissal        VARCHAR,            -- caught, bowled, lbw, run out, stumped, hit wicket, not out, retired not out, ...
    bowler_id        BIGINT,             -- dismissing bowler; mostly NULL before ~2000
    fielder_ids      BIGINT[],           -- catcher / run-out fielders when recorded
    PRIMARY KEY (match_id, innings_no, position)
);

CREATE TABLE bowling (
    match_id         BIGINT NOT NULL REFERENCES matches (match_id),
    innings_no       INTEGER NOT NULL,
    team             VARCHAR NOT NULL,   -- bowling team
    opposition       VARCHAR,            -- batting team
    player_id        BIGINT NOT NULL,
    overs            DOUBLE,             -- as written (8-ball overs where balls_per_over = 8)
    balls            INTEGER,            -- corrected for 8-ball overs
    maidens          INTEGER,
    runs             INTEGER,
    wickets          INTEGER,
    dots             INTEGER,            -- mostly NULL before ~2000
    fours            INTEGER,
    sixes            INTEGER,
    wides            INTEGER,
    noballs          INTEGER,
    PRIMARY KEY (match_id, innings_no, player_id)
);

CREATE TABLE fall_of_wickets (
    match_id         BIGINT NOT NULL REFERENCES matches (match_id),
    innings_no       INTEGER NOT NULL,
    team             VARCHAR NOT NULL,
    wicket_no        INTEGER NOT NULL,
    player_id        BIGINT,             -- batter out
    score            INTEGER,            -- team score at the fall
    over_at          DOUBLE              -- mostly NULL before ~2000
);

CREATE TABLE partnerships (
    match_id         BIGINT NOT NULL REFERENCES matches (match_id),
    innings_no       INTEGER NOT NULL,
    wicket_no        INTEGER NOT NULL,   -- for the nth wicket
    team             VARCHAR NOT NULL,
    opposition       VARCHAR,
    player1_id       BIGINT,
    player2_id       BIGINT,
    player1_runs     INTEGER,
    player2_runs     INTEGER,
    player1_balls    INTEGER,            -- 0/NULL when not recorded (before ~2000)
    player2_balls    INTEGER,
    runs             INTEGER,
    balls            INTEGER
);

CREATE TABLE load_warnings (
    check_name       VARCHAR NOT NULL,
    match_id         BIGINT,
    detail           VARCHAR
);

CREATE TABLE load_info (
    key              VARCHAR PRIMARY KEY,
    value            VARCHAR
);
