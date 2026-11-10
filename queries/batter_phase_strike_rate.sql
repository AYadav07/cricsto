-- Batters ranked by strike rate in one phase.
-- Params: $dataset, $phase ('powerplay' | 'middle' | 'death'), $season_from (e.g. '2023'), $min_balls
-- Grouped by player ID (names aren't unique). Outs = dismissals while on strike; retirements don't count.
WITH x AS (
    SELECT
        batter_id,
        any_value(striker) AS batter,
        sum(runs_off_bat)::BIGINT AS runs,
        sum(faced_ball::INT)::BIGINT AS balls,
        sum(striker_out::INT)::BIGINT AS outs,
        sum((is_four OR is_six)::INT)::BIGINT AS boundaries,
        sum((faced_ball AND runs_off_bat = 0)::INT)::BIGINT AS dots
    FROM deliveries
    WHERE ($dataset = 'all' OR dataset = $dataset)
      AND phase = $phase AND season >= $season_from AND NOT is_super_over
    GROUP BY batter_id
)
SELECT
    batter, runs, balls, outs,
    round(100.0 * runs / balls, 1) AS strike_rate,
    round(runs::DOUBLE / nullif(outs, 0), 1) AS average,
    round(100.0 * boundaries / balls, 1) AS boundary_pct,
    round(100.0 * dots / balls, 1) AS dot_pct,
    batter_id
FROM x
WHERE balls >= $min_balls
ORDER BY strike_rate DESC, balls DESC, batter
LIMIT 25;
