-- Batters against each bowling type.
-- Needs data/reference/bowler_types.csv (person_id, name, bowler_type); see insights.bowlers_to_classify().
-- Params: $dataset, $season_from, $min_balls
WITH x AS (
    SELECT
        d.batter_id,
        any_value(d.striker) AS batter,
        t.bowler_type,
        sum(d.runs_off_bat)::BIGINT AS runs,
        sum(d.faced_ball::INT)::BIGINT AS balls,
        sum((d.striker_out AND d.bowler_wicket)::INT)::BIGINT AS outs
    FROM deliveries d
    JOIN bowler_types t ON t.person_id = d.bowler_id
    WHERE ($dataset = 'all' OR d.dataset = $dataset)
      AND d.season >= $season_from AND NOT d.is_super_over
    GROUP BY d.batter_id, t.bowler_type
)
SELECT
    batter, bowler_type, balls, runs, outs,
    round(100.0 * runs / balls, 1) AS strike_rate,
    round(runs::DOUBLE / nullif(outs, 0), 1) AS average,
    batter_id
FROM x
WHERE balls >= $min_balls
ORDER BY batter, bowler_type, batter_id;
