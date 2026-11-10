-- Bowlers ranked by economy in one phase (lower is better).
-- Params: $dataset, $phase, $season_from, $min_balls
-- Grouped by player ID (names aren't unique).
WITH x AS (
    SELECT
        bowler_id,
        any_value(bowler) AS bowler,
        sum(bowler_runs)::BIGINT AS runs,
        sum(legal_ball::INT)::BIGINT AS balls,
        sum(bowler_wicket::INT)::BIGINT AS wickets,
        sum((legal_ball AND is_dot)::INT)::BIGINT AS dots
    FROM deliveries
    WHERE ($dataset = 'all' OR dataset = $dataset)
      AND phase = $phase AND season >= $season_from AND NOT is_super_over
    GROUP BY bowler_id
)
SELECT
    bowler, balls, runs, wickets,
    round(6.0 * runs / balls, 2) AS economy,
    round(100.0 * dots / balls, 1) AS dot_pct,
    round(balls::DOUBLE / nullif(wickets, 0), 1) AS balls_per_wicket,
    bowler_id
FROM x
WHERE balls >= $min_balls
ORDER BY economy ASC, balls DESC, bowler
LIMIT 25;
