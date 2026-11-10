"""Ready-made insights. Each returns a pandas DataFrame you can inspect, then chart.

    from cricsto import insights as ins
    ins.phase_scoring("ipl")
    ins.batter_strike_rate("ipl", phase="death", season_from="2023", min_balls=60)
"""
from __future__ import annotations

from .db import run_query, sql  # noqa: F401  (sql re-exported for ad-hoc queries)


def phase_scoring(dataset: str = "ipl"):
    """Run rate, wickets/over and boundary % per phase, by season."""
    return run_query("phase_scoring_by_season", dataset=dataset)


def batter_strike_rate(dataset: str = "ipl", phase: str = "death",
                       season_from: str = "2023", min_balls: int = 60):
    """Fastest-scoring batters in a phase (with average, boundary % and dot %)."""
    return run_query("batter_phase_strike_rate", dataset=dataset, phase=phase,
                     season_from=season_from, min_balls=min_balls)


def bowler_economy(dataset: str = "ipl", phase: str = "death",
                   season_from: str = "2023", min_balls: int = 120):
    """Most economical bowlers in a phase."""
    return run_query("bowler_phase_economy", dataset=dataset, phase=phase,
                     season_from=season_from, min_balls=min_balls)


def venue_bat_first(dataset: str = "ipl", season_from: str = "2018", min_matches: int = 10):
    """Bat-first win % by venue (matches with a result)."""
    return run_query("venue_bat_first", dataset=dataset, season_from=season_from,
                     min_matches=min_matches)


def chase_success(dataset: str = "ipl", season_from: str = "2018"):
    """Chase win % by first-innings total (20-run bands)."""
    return run_query("chase_success_by_target", dataset=dataset, season_from=season_from)


def recent_form(batter: str, dataset: str = "all", last_n: int = 10):
    """A batter's last N innings. Pass the Cricsheet name (e.g. 'V Kohli') or a person_id
    from find_player(); use the ID when the name belongs to more than one person."""
    return run_query("batter_recent_form", dataset=dataset, batter=batter, last_n=last_n)


def vs_bowler_type(dataset: str = "ipl", season_from: str = "2022", min_balls: int = 30):
    """Batters vs bowling types. Fill data/reference/bowler_types.csv first
    (bowlers_to_classify() lists who is missing)."""
    return run_query("batter_vs_bowler_type", dataset=dataset, season_from=season_from,
                     min_balls=min_balls)


def find_player(text: str, dataset: str = "all"):
    """Find players by any name they have used. One row per person (person_id), so
    namesakes show up separately; first/last match dates help tell them apart."""
    return sql(
        """
        WITH hits AS (
            SELECT DISTINCT key_id AS person_id FROM name_sources
            WHERE kind = 'person' AND name ILIKE '%' || $text || '%'
        )
        SELECT p.person_id, p.name,
               string_agg(DISTINCT ns.name, ' / ' ORDER BY ns.name) AS all_names,
               count(DISTINCT ns.match_id) AS matches,      -- as player, sub or official
               string_agg(DISTINCT m.dataset, ', ' ORDER BY m.dataset) AS datasets,
               min(m.start_date) AS first_match, max(m.start_date) AS last_match
        FROM hits
        JOIN people p USING (person_id)
        JOIN name_sources ns ON ns.kind = 'person' AND ns.key_id = p.person_id
        JOIN matches m ON m.match_id = ns.match_id
        WHERE ($dataset = 'all' OR m.dataset = $dataset)
        GROUP BY p.person_id, p.name
        ORDER BY matches DESC, p.name
        LIMIT 15
        """,
        text=text, dataset=dataset,
    )


def bowlers_to_classify(dataset: str = "ipl", season_from: str = "2022", min_balls: int = 60):
    """Bowlers missing from data/reference/bowler_types.csv, most balls first.
    Add rows as: person_id,name,bowler_type (pace / spin)."""
    return sql(
        """
        SELECT d.bowler_id AS person_id, any_value(d.bowler) AS name, count(*) AS balls
        FROM deliveries d
        LEFT JOIN bowler_types t ON t.person_id = d.bowler_id
        WHERE t.person_id IS NULL AND ($dataset = 'all' OR d.dataset = $dataset)
          AND d.season >= $season_from AND d.legal_ball
        GROUP BY d.bowler_id
        HAVING count(*) >= $min_balls
        ORDER BY balls DESC, name
        """,
        dataset=dataset, season_from=season_from, min_balls=min_balls,
    )
