-- Career bowling by player within a format and date range.
-- Params: $format ('test' / 'odi'), $from_date, $to_date, $min_wickets
-- Balls are corrected for 8-ball overs, so economy and strike rate are per 6 balls.
SELECT
    any_value(player ORDER BY start_date DESC)    AS player,
    player_id,
    any_value(bowling_style)                      AS bowling_style,
    count(DISTINCT match_id)                      AS matches_bowled,
    sum(balls)                                    AS balls,
    sum(runs)                                     AS runs,
    sum(wickets)                                  AS wickets,
    round(sum(runs) / nullif(sum(wickets), 0), 2) AS average,
    round(6.0 * sum(runs) / nullif(sum(balls), 0), 2) AS economy,
    round(1.0 * sum(balls) / nullif(sum(wickets), 0), 1) AS strike_rate,
    count(*) FILTER (WHERE wickets >= 5)          AS five_wkt_innings
FROM bowler_innings
WHERE format = $format
  AND start_date BETWEEN $from_date AND $to_date
GROUP BY player_id
HAVING sum(wickets) >= $min_wickets
ORDER BY wickets DESC, player_id
