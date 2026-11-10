-- A batter's last N innings, newest first.
-- Params: $dataset, $batter (exact Cricsheet name, e.g. 'V Kohli'), $last_n
SELECT
    bi.start_date, bi.event, bi.bowling_team AS opponent, bi.venue,
    bi.runs, bi.balls,
    round(100.0 * bi.runs / nullif(bi.balls, 0), 1) AS strike_rate,
    EXISTS (
        SELECT 1 FROM dismissals d
        WHERE d.dataset = bi.dataset AND d.match_id = bi.match_id
          AND d.innings = bi.innings AND d.batter = bi.batter
    ) AS out
FROM batter_innings bi
WHERE ($dataset = 'all' OR bi.dataset = $dataset)
  AND bi.batter = $batter
ORDER BY bi.start_date DESC, bi.innings DESC
LIMIT $last_n;
