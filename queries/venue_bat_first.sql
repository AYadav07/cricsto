-- How often the team batting first wins at each venue (matches with a result only).
-- Params: $dataset, $season_from, $min_matches
-- Grouped by venue ID, so a renamed ground counts as one venue (shown by its latest name).
WITH first_inns AS (
    SELECT dataset, match_id, any_value(venue_id) AS venue_id, any_value(venue) AS venue,
           any_value(batting_team) AS bat_first, any_value(winner) AS winner, any_value(season) AS season
    FROM deliveries
    WHERE innings = 1
    GROUP BY dataset, match_id
)
SELECT
    any_value(venue) AS venue,
    count(*) AS matches,
    sum((winner = bat_first)::INT)::BIGINT AS bat_first_wins,
    round(100.0 * sum((winner = bat_first)::INT) / count(*), 1) AS bat_first_win_pct
FROM first_inns
WHERE ($dataset = 'all' OR dataset = $dataset)
  AND season >= $season_from AND winner IS NOT NULL
GROUP BY venue_id
HAVING count(*) >= $min_matches
ORDER BY bat_first_win_pct DESC, matches DESC, venue;
