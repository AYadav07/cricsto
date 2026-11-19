-- Flat views for querying. Rebuilt on every build.

-- One row per batter per innings, with names and match context.
CREATE OR REPLACE VIEW batter_innings AS
SELECT
    m.format, m.match_id, m.match_no, m.start_date, year(m.start_date) AS year,
    m.series_name, m.venue, m.city, m.country,
    b.innings_no, i.team_innings_no, b.team, i.bowling_team AS opposition,
    b.position, b.player_id, p.name AS player,
    b.did_bat, b.runs, b.balls, b.fours, b.sixes,
    b.is_out, b.dismissal,
    b.bowler_id, pb.name AS bowler,
    -- strike rate only where balls faced were recorded
    CASE WHEN b.balls > 0 THEN round(100.0 * b.runs / b.balls, 2) END AS strike_rate
FROM batting b
JOIN matches m USING (match_id)
JOIN innings i USING (match_id, innings_no)
LEFT JOIN players p ON p.player_id = b.player_id
LEFT JOIN players pb ON pb.player_id = b.bowler_id;

-- One row per bowler per innings. economy and strike rate per 6 balls, using corrected balls.
CREATE OR REPLACE VIEW bowler_innings AS
SELECT
    m.format, m.match_id, m.match_no, m.start_date, year(m.start_date) AS year,
    m.series_name, m.venue, m.city, m.country, m.balls_per_over,
    w.innings_no, w.team, w.opposition,
    w.player_id, p.name AS player, p.bowling_style,
    w.overs, w.balls, w.maidens, w.runs, w.wickets,
    w.dots, w.fours, w.sixes, w.wides, w.noballs,
    CASE WHEN w.balls > 0 THEN round(6.0 * w.runs / w.balls, 2) END AS economy,
    CASE WHEN w.wickets > 0 THEN round(1.0 * w.balls / w.wickets, 1) END AS balls_per_wicket
FROM bowling w
JOIN matches m USING (match_id)
LEFT JOIN players p ON p.player_id = w.player_id;

-- Match results with each team's totals side by side.
CREATE OR REPLACE VIEW match_results AS
SELECT
    m.format, m.match_id, m.match_no, m.start_date, year(m.start_date) AS year,
    m.series_name, m.team1, m.team2, m.venue, m.city, m.country,
    m.toss_winner, m.toss_decision, m.winner, m.result_text,
    CASE WHEN m.winner IS NULL THEN 'no winner'
         WHEN m.winner = m.toss_winner THEN 'toss winner won' ELSE 'toss loser won' END AS toss_outcome,
    pm.name AS player_of_match
FROM matches m
LEFT JOIN players pm ON pm.player_id = m.player_of_match_id;
