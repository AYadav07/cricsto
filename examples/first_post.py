"""Example: from question to post-ready chart in one script.

Question: How has powerplay scoring changed season by season in the IPL?

    python examples/first_post.py
Chart lands in output/. Check the printed table before you post anything.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cricsto import charts, insights as ins  # noqa: E402

DATASET = "ipl"

df = ins.phase_scoring(DATASET)
pp = df[df["phase"] == "powerplay"]
death = df[df["phase"] == "death"]
print(df.to_string(index=False))

fig = charts.line(
    pp["season"],
    {"Powerplay": pp["run_rate"], "Death": death.set_index("season").reindex(pp["season"])["run_rate"]},
    title="IPL scoring rate by season",
    subtitle="Runs per over, powerplay (overs 1–6) vs death (overs 16–20)",
    ylabel="Runs per over",
)
print("Saved:", charts.save(fig, "ipl_phase_run_rate"))

top = ins.batter_strike_rate(DATASET, phase="death", season_from="2024", min_balls=60).head(10)
print(top.to_string(index=False))
if top.empty:
    sys.exit("No batters met the minimum balls. Lower min_balls or season_from.")
fig = charts.bar(
    top["batter"], top["strike_rate"],
    title="Fastest death-over hitters in the IPL",
    subtitle="Strike rate in overs 16–20 since 2024 (min. 60 balls)",
    highlight=top["batter"].iloc[0],
    value_fmt="{:.0f}",
)
print("Saved:", charts.save(fig, "ipl_death_strike_rate"))
