-- Run rate and wickets per over in each phase, by season.
-- Params: $dataset ('ipl', 't20s', ... or 'all')
SELECT
    season,
    phase,
    round(6.0 * sum(total_runs) / nullif(sum(legal_ball::INT), 0), 2)  AS run_rate,
    round(6.0 * sum(is_wicket::INT) / nullif(sum(legal_ball::INT), 0), 2) AS wickets_per_over,
    round(100.0 * sum((is_four OR is_six)::INT) / nullif(sum(legal_ball::INT), 0), 1) AS boundary_pct,
    count(DISTINCT match_id) AS matches
FROM deliveries
WHERE ($dataset = 'all' OR dataset = $dataset)
  AND innings <= 2 AND phase IS NOT NULL
GROUP BY season, phase
ORDER BY season, CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END;
