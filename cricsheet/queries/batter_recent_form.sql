-- A batter's last N innings, newest first.
-- Params: $dataset, $batter (Cricsheet name, e.g. 'V Kohli', or a person_id), $last_n
-- Use find_player() first if the name might belong to more than one person.
SELECT
    bi.start_date, bi.event, bi.bowling_team AS opponent, bi.venue,
    bi.runs, bi.balls,
    round(100.0 * bi.runs / nullif(bi.balls, 0), 1) AS strike_rate,
    bi.is_out AS out,
    bi.how_out
FROM batter_innings bi
WHERE ($dataset = 'all' OR bi.dataset = $dataset)
  AND (bi.batter = $batter OR bi.batter_id = $batter)
ORDER BY bi.start_date DESC, bi.match_id DESC, bi.innings DESC
LIMIT $last_n;
