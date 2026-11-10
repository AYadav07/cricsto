-- Batters against each bowling type. Needs data/reference/bowler_types.csv (bowler,bowler_type).
-- Params: $dataset, $season_from, $min_balls
WITH x AS (
    SELECT
        d.striker AS batter,
        t.bowler_type,
        sum(d.runs_off_bat)::BIGINT AS runs,
        sum(d.faced_ball::INT)::BIGINT AS balls,
        sum(COALESCE(d.player_dismissed = d.striker AND d.bowler_wicket, false)::INT)::BIGINT AS outs
    FROM deliveries d
    JOIN bowler_types t ON t.bowler = d.bowler
    WHERE ($dataset = 'all' OR d.dataset = $dataset)
      AND d.season >= $season_from
    GROUP BY 1, 2
)
SELECT
    batter, bowler_type, balls, runs, outs,
    round(100.0 * runs / balls, 1) AS strike_rate,
    round(runs::DOUBLE / nullif(outs, 0), 1) AS average
FROM x
WHERE balls >= $min_balls
ORDER BY batter, bowler_type;
