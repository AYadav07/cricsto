-- Cricsto v2 views over the normalized tables (SCHEMA.md section 4).
-- They do the joins and add names, keeping the v1 column names so old queries still run.
-- Group by the *_id columns when namesakes matter: names are not unique.

-- One row per ball, flat. Every stats query can start here.
CREATE OR REPLACE VIEW deliveries AS
WITH w AS (
    SELECT match_id, innings_no, over_num, ball_seq,
           max(player_out_id) FILTER (WHERE wicket_seq = 1) AS out1_id,
           max(kind)          FILTER (WHERE wicket_seq = 1) AS kind1,
           max(player_out_id) FILTER (WHERE wicket_seq = 2) AS out2_id,
           max(kind)          FILTER (WHERE wicket_seq = 2) AS kind2,
           bool_or(is_dismissal)    AS any_dismissal,
           bool_or(bowler_credited) AS any_bowler_credited
    FROM wickets
    GROUP BY ALL
),
b AS (
    SELECT
        m.dataset, b.match_id, m.season, m.start_date, m.match_type, m.gender,
        m.event_name                            AS event,
        v.name                                  AS venue,
        v.city,
        tw.name                                 AS winner,
        tt.name                                 AS toss_winner,
        m.toss_decision,
        b.innings_no                            AS innings,
        b.over_num, b.ball_seq, b.legal_ball_no,
        b.over_num + b.legal_ball_no / 10.0     AS ball,         -- e.g. 3.4, same as actual_delivery
        b.actual_delivery,
        bt.name                                 AS batting_team,
        bw.name                                 AS bowling_team,
        ps.name                                 AS striker,
        pn.name                                 AS non_striker,
        pb.name                                 AS bowler,
        b.batter_id, b.non_striker_id, b.bowler_id,
        b.runs_batter                           AS runs_off_bat,
        b.runs_extras                           AS extras,
        b.runs_total                            AS total_runs,
        b.wides, b.noballs, b.byes, b.legbyes, b.penalty, b.non_boundary,
        p1.name                                 AS player_dismissed,
        w.out1_id                               AS player_dismissed_id,
        w.kind1                                 AS wicket_type,
        p2.name                                 AS other_player_dismissed,
        w.out2_id                               AS other_player_dismissed_id,
        w.kind2                                 AS other_wicket_type,
        COALESCE(w.any_dismissal, false)        AS is_wicket,       -- a batter was out (retired hurt / not out excluded)
        COALESCE(w.any_bowler_credited, false)  AS bowler_wicket,
        i.is_super_over,
        i.batting_team_id, i.bowling_team_id, m.venue_id
    FROM balls b
    JOIN innings i  ON i.match_id = b.match_id AND i.innings_no = b.innings_no
    JOIN matches m  ON m.match_id = b.match_id
    JOIN venues v   ON v.venue_id = m.venue_id
    JOIN teams bt   ON bt.team_id = i.batting_team_id
    JOIN teams bw   ON bw.team_id = i.bowling_team_id
    LEFT JOIN teams tw ON tw.team_id = m.winner_id
    JOIN teams tt   ON tt.team_id = m.toss_winner_id
    JOIN people ps  ON ps.person_id = b.batter_id
    JOIN people pn  ON pn.person_id = b.non_striker_id
    JOIN people pb  ON pb.person_id = b.bowler_id
    LEFT JOIN w     ON w.match_id = b.match_id AND w.innings_no = b.innings_no
                   AND w.over_num = b.over_num AND w.ball_seq = b.ball_seq
    LEFT JOIN people p1 ON p1.person_id = w.out1_id
    LEFT JOIN people p2 ON p2.person_id = w.out2_id
),
x AS (
    SELECT
        *,
        runs_off_bat + wides + noballs                      AS bowler_runs,   -- byes, leg byes, penalties not charged
        (wides = 0 AND noballs = 0)                         AS legal_ball,    -- counts toward the over
        (wides = 0)                                         AS faced_ball,    -- a ball faced by the batter
        (runs_off_bat = 4 AND NOT non_boundary)             AS is_four,
        (runs_off_bat = 6 AND NOT non_boundary)             AS is_six,
        (total_runs = 0)                                    AS is_dot,
        CASE
            WHEN match_type IN ('ODI', 'ODM') THEN
                CASE WHEN over_num < 10 THEN 'powerplay'
                     WHEN over_num < 40 THEN 'middle' ELSE 'death' END
            WHEN match_type IN ('Test', 'MDM') THEN NULL
            ELSE  -- T20, IT20 and T20 leagues
                CASE WHEN over_num < 6 THEN 'powerplay'
                     WHEN over_num < 15 THEN 'middle' ELSE 'death' END
        END                                                 AS phase
    FROM b
)
SELECT
    x.*,
    CASE
        WHEN EXISTS (SELECT 1 FROM powerplays pp
                     WHERE pp.match_id = x.match_id AND pp.innings_no = x.innings) THEN
            EXISTS (SELECT 1 FROM powerplays pp    -- compare as over*10 + ball (5.6 -> 56), no float equality
                    WHERE pp.match_id = x.match_id AND pp.innings_no = x.innings
                      AND x.over_num * 10 + x.legal_ball_no
                          BETWEEN round(pp.from_ball * 10)::INT AND round(pp.to_ball * 10)::INT)
        ELSE COALESCE(x.phase = 'powerplay', false)          -- no powerplay data: phase rule
    END                                                     AS in_powerplay
FROM x;


-- One row per batter per innings (super overs excluded). Includes batters who
-- were at the crease without facing a ball (e.g. run out as non-striker).
CREATE OR REPLACE VIEW batter_innings AS
WITH appear AS (   -- every time a batter is at the crease, in order
    SELECT match_id, innings, over_num, ball_seq, 0 AS role, batter_id AS person_id FROM deliveries WHERE NOT is_super_over
    UNION ALL
    SELECT match_id, innings, over_num, ball_seq, 1 AS role, non_striker_id FROM deliveries WHERE NOT is_super_over
),
pos AS (
    SELECT match_id, innings, person_id,
           row_number() OVER (PARTITION BY match_id, innings
                              ORDER BY min(over_num * 100000 + ball_seq * 10 + role)) AS batting_position
    FROM appear GROUP BY match_id, innings, person_id
),
stats AS (
    SELECT match_id, innings, batter_id AS person_id,
           sum(runs_off_bat)::BIGINT                          AS runs,
           sum(faced_ball::INT)::BIGINT                       AS balls,
           sum(is_four::INT)::BIGINT                          AS fours,
           sum(is_six::INT)::BIGINT                           AS sixes,
           sum((faced_ball AND runs_off_bat = 0)::INT)::BIGINT AS dots
    FROM deliveries WHERE NOT is_super_over
    GROUP BY ALL
),
outs AS (
    SELECT match_id, innings_no AS innings, player_out_id AS person_id, max(kind) AS how_out
    FROM wickets WHERE is_dismissal
    GROUP BY ALL
)
SELECT
    m.dataset, m.match_id, m.season, m.start_date, m.match_type, m.gender,
    m.event_name AS event, v.name AS venue,
    pos.innings, bt.name AS batting_team, bw.name AS bowling_team,
    p.name AS batter, pos.person_id AS batter_id, pos.batting_position,
    COALESCE(s.runs, 0)  AS runs,
    COALESCE(s.balls, 0) AS balls,
    COALESCE(s.fours, 0) AS fours,
    COALESCE(s.sixes, 0) AS sixes,
    COALESCE(s.dots, 0)  AS dots,
    (o.person_id IS NOT NULL) AS is_out,
    o.how_out
FROM pos
JOIN matches m ON m.match_id = pos.match_id
JOIN venues v  ON v.venue_id = m.venue_id
JOIN innings i ON i.match_id = pos.match_id AND i.innings_no = pos.innings
JOIN teams bt  ON bt.team_id = i.batting_team_id
JOIN teams bw  ON bw.team_id = i.bowling_team_id
JOIN people p  ON p.person_id = pos.person_id
LEFT JOIN stats s ON s.match_id = pos.match_id AND s.innings = pos.innings AND s.person_id = pos.person_id
LEFT JOIN outs o  ON o.match_id = pos.match_id AND o.innings = pos.innings AND o.person_id = pos.person_id;


-- One row per bowler per innings (super overs excluded).
CREATE OR REPLACE VIEW bowler_innings AS
WITH s AS (
    SELECT d.dataset, d.match_id, d.season, d.start_date, d.match_type, d.gender, d.event, d.venue,
           d.innings, d.bowling_team, d.batting_team, d.bowler_id,
           sum(d.legal_ball::INT)::BIGINT                         AS legal_balls,
           sum(d.bowler_runs)::BIGINT                             AS runs,
           sum((d.legal_ball AND d.is_dot)::INT)::BIGINT          AS dots,
           sum(d.is_four::INT)::BIGINT                            AS fours,
           sum(d.is_six::INT)::BIGINT                             AS sixes,
           sum((d.wides > 0)::INT)::BIGINT                        AS wides,
           sum((d.noballs > 0)::INT)::BIGINT                      AS noballs
    FROM deliveries d WHERE NOT d.is_super_over
    GROUP BY ALL
),
wk AS (
    SELECT b.match_id, b.innings_no AS innings, b.bowler_id, count(*) AS wickets
    FROM wickets w JOIN balls b USING (match_id, innings_no, over_num, ball_seq)
    WHERE w.bowler_credited
    GROUP BY ALL
)
SELECT s.dataset, s.match_id, s.season, s.start_date, s.match_type, s.gender, s.event, s.venue,
       s.innings, s.bowling_team, s.batting_team,
       p.name AS bowler, s.bowler_id,
       s.legal_balls,
       (s.legal_balls // m.balls_per_over) + (s.legal_balls % m.balls_per_over) / 10.0 AS overs,
       s.runs, COALESCE(wk.wickets, 0) AS wickets,
       s.dots, s.fours, s.sixes, s.wides, s.noballs
FROM s
JOIN matches m ON m.match_id = s.match_id
JOIN people p  ON p.person_id = s.bowler_id
LEFT JOIN wk ON wk.match_id = s.match_id AND wk.innings = s.innings AND wk.bowler_id = s.bowler_id;


-- One row per wicket entry, with fielders. Includes retirements (see is_dismissal).
CREATE OR REPLACE VIEW dismissals AS
WITH f AS (
    SELECT f.match_id, f.innings_no, f.over_num, f.ball_seq, f.wicket_seq,
           string_agg(COALESCE(p.name, 'sub'), ', ' ORDER BY f.fielder_seq) AS fielders,
           list(f.fielder_id ORDER BY f.fielder_seq)                         AS fielder_ids
    FROM fielding f LEFT JOIN people p ON p.person_id = f.fielder_id
    GROUP BY ALL
)
SELECT m.dataset, w.match_id, w.innings_no AS innings,
       b.over_num + b.legal_ball_no / 10.0 AS ball, w.over_num, w.ball_seq, w.wicket_seq,
       po.name AS batter, w.player_out_id AS batter_id,
       w.kind AS wicket_type,
       pb.name AS bowler, b.bowler_id,
       w.bowler_credited, w.is_dismissal,
       f.fielders, f.fielder_ids
FROM wickets w
JOIN balls b   USING (match_id, innings_no, over_num, ball_seq)
JOIN matches m ON m.match_id = w.match_id
JOIN people po ON po.person_id = w.player_out_id
JOIN people pb ON pb.person_id = b.bowler_id
LEFT JOIN f ON f.match_id = w.match_id AND f.innings_no = w.innings_no AND f.over_num = w.over_num
           AND f.ball_seq = w.ball_seq AND f.wicket_seq = w.wicket_seq;
