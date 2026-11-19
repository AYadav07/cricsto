-- Career batting by player within a format and date range.
-- Params: $format ('test' / 'odi'), $from_date, $to_date, $min_innings
-- Strike rate uses only innings where balls faced were recorded (balls_known shows how many).
SELECT
    any_value(player ORDER BY start_date DESC)        AS player,
    player_id,
    count(DISTINCT match_id)                           AS matches_batted,
    count(*) FILTER (WHERE did_bat)                    AS innings,
    count(*) FILTER (WHERE did_bat AND NOT is_out)     AS not_outs,
    sum(runs)                                          AS runs,
    max(runs)                                          AS highest,
    round(sum(runs) / nullif(count(*) FILTER (WHERE is_out), 0), 2) AS average,
    count(*) FILTER (WHERE runs >= 100)                AS hundreds,
    count(*) FILTER (WHERE runs >= 50 AND runs < 100)  AS fifties,
    count(*) FILTER (WHERE did_bat AND balls IS NOT NULL) AS balls_known,
    round(100.0 * sum(runs) FILTER (WHERE balls > 0) / nullif(sum(balls) FILTER (WHERE balls > 0), 0), 2) AS strike_rate
FROM batter_innings
WHERE format = $format
  AND start_date BETWEEN $from_date AND $to_date
GROUP BY player_id
HAVING count(*) FILTER (WHERE did_bat) >= $min_innings
ORDER BY runs DESC, player_id
