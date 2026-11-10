-- Clean, typed view over the raw ball-by-ball rows. Every query builds on `deliveries`.
CREATE OR REPLACE VIEW deliveries AS
WITH b AS (
    SELECT
        r.dataset,
        r.match_id,
        r.season,
        TRY_CAST(replace(r.start_date, '/', '-') AS DATE)      AS start_date,
        r.venue,
        CAST(r.innings AS INTEGER)                              AS innings,
        CAST(r.ball AS DOUBLE)                                  AS ball,
        CAST(floor(CAST(r.ball AS DOUBLE)) AS INTEGER)          AS over_num,      -- 0-based
        r.batting_team,
        r.bowling_team,
        r.striker,
        r.non_striker,
        r.bowler,
        COALESCE(TRY_CAST(r.runs_off_bat AS INTEGER), 0)        AS runs_off_bat,
        COALESCE(TRY_CAST(r.extras AS INTEGER), 0)              AS extras,
        COALESCE(TRY_CAST(r.wides AS INTEGER), 0)               AS wides,
        COALESCE(TRY_CAST(r.noballs AS INTEGER), 0)             AS noballs,
        COALESCE(TRY_CAST(r.byes AS INTEGER), 0)                AS byes,
        COALESCE(TRY_CAST(r.legbyes AS INTEGER), 0)             AS legbyes,
        COALESCE(TRY_CAST(r.penalty AS INTEGER), 0)             AS penalty,
        COALESCE(r.non_boundary, '') NOT IN ('', '0')           AS non_boundary,
        NULLIF(r.wicket_type, '')                               AS wicket_type,
        NULLIF(r.player_dismissed, '')                          AS player_dismissed,
        NULLIF(r.other_wicket_type, '')                         AS other_wicket_type,
        NULLIF(r.other_player_dismissed, '')                    AS other_player_dismissed,
        m.match_type,
        m.event,
        m.gender,
        m.winner,
        m.toss_winner,
        m.toss_decision,
        m.city
    FROM balls_raw r
    LEFT JOIN matches m ON m.match_id = r.match_id AND m.dataset = r.dataset
)
SELECT
    *,
    runs_off_bat + extras                                       AS total_runs,
    runs_off_bat + wides + noballs                              AS bowler_runs,   -- runs charged to bowler
    (wides = 0 AND noballs = 0)                                 AS legal_ball,    -- counts toward the over
    (wides = 0)                                                 AS faced_ball,    -- counts as a ball faced by the batter
    (player_dismissed IS NOT NULL)                              AS is_wicket,
    COALESCE(wicket_type IN ('bowled', 'caught', 'lbw', 'stumped',
                     'caught and bowled', 'hit wicket'), false) AS bowler_wicket,
    (runs_off_bat = 4 AND NOT non_boundary)                     AS is_four,
    (runs_off_bat = 6 AND NOT non_boundary)                     AS is_six,
    (runs_off_bat = 0 AND extras = 0)                           AS is_dot,
    CASE
        WHEN match_type IN ('ODI', 'ODM') THEN
            CASE WHEN over_num < 10 THEN 'powerplay'
                 WHEN over_num < 40 THEN 'middle' ELSE 'death' END
        WHEN match_type IN ('Test', 'MDM') THEN NULL
        ELSE  -- T20, IT20 and T20 leagues
            CASE WHEN over_num < 6 THEN 'powerplay'
                 WHEN over_num < 15 THEN 'middle' ELSE 'death' END
    END                                                         AS phase
FROM b;

-- One row per batter per innings: the base for form and consistency stats.
CREATE OR REPLACE VIEW batter_innings AS
SELECT
    dataset, match_id, season, start_date, match_type, event, venue,
    innings, batting_team, bowling_team,
    striker                                         AS batter,
    sum(runs_off_bat)::BIGINT                               AS runs,
    sum(CASE WHEN faced_ball THEN 1 ELSE 0 END)::BIGINT     AS balls,
    sum(CASE WHEN is_four THEN 1 ELSE 0 END)::BIGINT        AS fours,
    sum(CASE WHEN is_six THEN 1 ELSE 0 END)::BIGINT         AS sixes
FROM deliveries
GROUP BY ALL;

-- Dismissals (who got out, how, when). Includes run-outs of the non-striker.
CREATE OR REPLACE VIEW dismissals AS
SELECT dataset, match_id, innings, ball, player_dismissed AS batter, wicket_type, bowler
FROM deliveries WHERE player_dismissed IS NOT NULL
UNION ALL
SELECT dataset, match_id, innings, ball, other_player_dismissed, other_wicket_type, bowler
FROM deliveries WHERE other_player_dismissed IS NOT NULL;
