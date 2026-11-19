"""Post batch, 2026-11-10: the IPL scoring boom.

    python posts/batches/batch_2026_11_10.py   → posts/output/*.png, and prints the numbers used in the posts
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root

from posts import charts  # noqa: E402
from cricsheet import insights as ins  # noqa: E402

# Cricsheet season labels → the IPL year fans use
IPL_YEAR = {"2007/08": "2008", "2009/10": "2010", "2020/21": "2020"}


def year(s: str) -> str:
    return IPL_YEAR.get(s, s)


# 1. Phase run rates by season ---------------------------------------------------------
ps = ins.phase_scoring("ipl")
rr = ps.pivot(index="season", columns="phase", values="run_rate").sort_index()
print("\nRun rate by phase\n", rr)
x = [year(s) for s in rr.index]
fig = charts.line(x, {"Powerplay": rr["powerplay"], "Death": rr["death"], "Middle": rr["middle"]},
                  title="The powerplay just broke 10 an over",
                  subtitle="IPL run rate by phase, 2008–2026 (overs 1–6 / 7–15 / 16–20)",
                  ylabel="Runs per over")
print(charts.save(fig, "ipl_phase_run_rate_2026"))

# 2. 200+ first-innings totals, and how many were chased --------------------------------
big = ins.big_total_chases("ipl", threshold=200)
big["year"] = big["season"].map(year)
print("\n200+ first innings and chases\n", big)
fig = charts.line(big["year"], {"200+ totals": big["big_totals"],
                                "Chased": big["chased"]},
                  title="200 used to be a winning total",
                  subtitle="IPL first-innings totals of 200+, and how many were chased down "
                           "(D/L excluded)",
                  ylabel="Matches")
print(charts.save(fig, "ipl_200_chased"))

recent = big[big["season"] >= "2018"]
pct200 = (100 * recent["big_totals"] / recent["matches"]).round(0)
fig = charts.bar(recent["year"], pct200,
                 title="Half of IPL 2026 first innings hit 200",
                 subtitle="% of first innings reaching 200+, per season (completed matches, D/L excluded)",
                 highlight="2026", value_fmt="{:.0f}%", horizontal=False)
print(charts.save(fig, "ipl_pct_200"))

era = big.assign(era=big["season"].map(lambda s: "2023–26" if s >= "2023" else "2008–22")) \
         .groupby("era")[["matches", "big_totals", "chased"]].sum()
era["chased_pct"] = (100 * era["chased"] / era["big_totals"]).round(1)
print("\nBy era\n", era)

# 3. Death-over hitters: fast AND hard to dry up ---------------------------------------
d = ins.batter_strike_rate("ipl", phase="death", season_from="2024", min_balls=100).head(15)
print("\nDeath hitters since 2024 (min 100 balls)\n", d)
fig = charts.scatter(d["strike_rate"], d["dot_pct"], d["batter"],
                     title="Fast at the death, and almost never stuck",
                     subtitle="IPL overs 16–20, 2024–2026, top 15 by strike rate (min. 100 balls faced)",
                     xlabel="Strike rate", ylabel="Dot-ball %  (lower = better)",
                     highlight="T Stubbs", invert_y=True,
                     label_offsets={"V Kohli": (-8, 4), "Naman Dhir": (-8, 6), "SS Iyer": (7, -16)})
print(charts.save(fig, "ipl_death_sr_vs_dots"))
