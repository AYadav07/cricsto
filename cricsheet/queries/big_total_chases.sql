-- How often a big first-innings total is chased down, by season (limited-overs).
-- Params: $dataset, $gender ('male' / 'female' / 'all'), $threshold (first-innings runs, e.g. 200)
-- Only completed matches with a winner and no D/L method (a revised target isn't a chase of
-- the first-innings total). Ties and no-results are left out. Super overs excluded.
WITH totals AS (
    SELECT match_id,
           any_value(season) AS season,
           any_value(winner) AS winner,
           sum(total_runs) FILTER (WHERE innings = 1) AS first_total,
           any_value(batting_team) FILTER (WHERE innings = 2) AS chasing_team
    FROM deliveries
    WHERE ($dataset = 'all' OR dataset = $dataset)
      AND ($gender = 'all' OR gender = $gender)
      AND innings <= 2 AND NOT is_super_over
    GROUP BY match_id
)
SELECT
    t.season,
    count(*) AS matches,
    count(*) FILTER (WHERE t.first_total >= $threshold) AS big_totals,
    count(*) FILTER (WHERE t.first_total >= $threshold AND t.winner = t.chasing_team) AS chased,
    round(100.0 * count(*) FILTER (WHERE t.first_total >= $threshold AND t.winner = t.chasing_team)
          / nullif(count(*) FILTER (WHERE t.first_total >= $threshold), 0), 1) AS chased_pct
FROM totals t
JOIN matches m USING (match_id)
WHERE t.winner IS NOT NULL AND t.chasing_team IS NOT NULL AND m.method IS NULL
GROUP BY t.season
ORDER BY t.season;
