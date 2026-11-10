-- Chasing success rate by first-innings total, in 20-run bands (limited-overs).
-- Params: $dataset, $season_from
WITH totals AS (
    SELECT dataset, match_id, any_value(season) AS season, any_value(winner) AS winner,
           sum(total_runs) FILTER (WHERE innings = 1) AS first_total,
           any_value(batting_team) FILTER (WHERE innings = 2) AS chasing_team
    FROM deliveries
    WHERE innings <= 2
    GROUP BY dataset, match_id
)
SELECT
    (floor(first_total / 20) * 20)::INT AS band_from,
    (floor(first_total / 20) * 20 + 19)::INT AS band_to,
    count(*) AS matches,
    round(100.0 * sum((winner = chasing_team)::INT) / count(*), 1) AS chase_win_pct
FROM totals
WHERE ($dataset = 'all' OR dataset = $dataset)
  AND season >= $season_from AND winner IS NOT NULL AND chasing_team IS NOT NULL
GROUP BY 1, 2
HAVING count(*) >= 5
ORDER BY band_from;
