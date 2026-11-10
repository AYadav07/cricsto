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
    """A batter's last N innings. Use the Cricsheet spelling, e.g. 'V Kohli'."""
    return run_query("batter_recent_form", dataset=dataset, batter=batter, last_n=last_n)


def vs_bowler_type(dataset: str = "ipl", season_from: str = "2022", min_balls: int = 30):
    """Batters vs bowling types. Fill data/reference/bowler_types.csv first."""
    return run_query("batter_vs_bowler_type", dataset=dataset, season_from=season_from,
                     min_balls=min_balls)


def find_player(text: str, dataset: str = "all"):
    """Find the exact Cricsheet spelling of a player's name."""
    return sql(
        """
        SELECT name, count(*) AS deliveries FROM (
            SELECT striker AS name, dataset FROM deliveries
            UNION ALL SELECT bowler, dataset FROM deliveries
        )
        WHERE name ILIKE '%' || $text || '%' AND ($dataset = 'all' OR dataset = $dataset)
        GROUP BY name ORDER BY deliveries DESC LIMIT 15
        """,
        text=text, dataset=dataset,
    )
