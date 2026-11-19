"""India in New Zealand, ODIs, Nov 2026: numbers and charts for the series posts.

    python posts/batches/series_ind_nz_2026.py   → posts/output/*.png, and prints every number used

Note: the database ends before this series (Cricsheet lags a few days), so these are
"before this series" numbers. NZ = matches at grounds in New Zealand cities (NZ_CITIES).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root

import pandas as pd  # noqa: E402

from posts import charts  # noqa: E402
from cricsheet import insights as ins  # noqa: E402

pd.set_option("display.width", 200)
NZ_CITIES = ("Auckland", "Wellington", "Hamilton", "Christchurch", "Dunedin", "Napier", "Nelson",
             "Mount Maunganui", "Queenstown", "Whangarei", "Lincoln", "New Plymouth",
             "Invercargill", "Palmerston North")
NZ = "(" + ",".join(f"'{c}'" for c in NZ_CITIES) + ")"

# 1. India's ODI tours of NZ: results by year (men's ODIs) ----------------------------------
tours = ins.sql(f"""
    SELECT year(m.start_date) AS yr, count(*) AS played,
           count(*) FILTER (WHERE w.name = 'India') AS india, count(*) FILTER (WHERE w.name = 'New Zealand') AS nz,
           count(*) FILTER (WHERE m.winner_id IS NULL) AS no_result_or_tie
    FROM matches m JOIN venues v USING (venue_id)
    JOIN teams a ON a.team_id = m.team1_id JOIN teams b ON b.team_id = m.team2_id
    LEFT JOIN teams w ON w.team_id = m.winner_id
    WHERE m.dataset = 'odis' AND m.gender = 'male' AND v.city IN {NZ}
      AND list_sort([a.name, b.name]) = ['India', 'New Zealand']
    GROUP BY 1 ORDER BY 1""")
print("\nIndia ODIs in NZ by year\n", tours)

# 2. Kohli's ODI hundreds vs NZ ------------------------------------------------------------
k = ins.sql("""
    SELECT b.start_date, v.city, b.runs, b.balls
    FROM batter_innings b JOIN matches m USING (match_id) JOIN venues v ON v.venue_id = m.venue_id
    WHERE b.dataset = 'odis' AND b.batter_id = 'ba607b88' AND b.bowling_team = 'New Zealand' AND b.runs >= 100
    ORDER BY b.start_date""")
print("\nKohli ODI hundreds vs NZ\n", k)
kt = ins.sql("""
    SELECT count(*) inns, sum(runs) runs, round(sum(runs) / sum(is_out::INT), 1) avg,
           round(100.0 * sum(runs) / sum(balls), 1) sr
    FROM batter_innings WHERE dataset = 'odis' AND batter_id = 'ba607b88' AND bowling_team = 'New Zealand'""")
print(kt)
labels = [f"{r.city.replace('Chandigarh', 'Mohali')} {r.start_date.year}" for r in k.itertuples()]
in_nz = [lab for lab, c in zip(labels, k["city"]) if c in NZ_CITIES]
fig = charts.bar(labels, k["runs"], title="Kohli's 7 ODI hundreds vs New Zealand",
                 subtitle=f"{int(kt.runs[0])} runs in {int(kt.inns[0])} innings, average {kt.avg[0]}. "
                          f"Red = the only one in New Zealand (ODIs to Oct 2026)",
                 highlight=in_nz, value_fmt="{:.0f}")  # red = scored in New Zealand
print(charts.save(fig, "kohli_100s_vs_nz"))

# 3. Rain: share of men's ODIs with a no result or a D/L result, since 2010 ----------------
rain = ins.sql(f"""
    SELECT CASE WHEN v.city IN {NZ} THEN 'in NZ' ELSE 'elsewhere' END AS loc, count(*) AS matches,
           count(*) FILTER (WHERE m.result = 'no result') AS no_result,
           count(*) FILTER (WHERE m.method IS NOT NULL) AS dl,
           round(100.0 * count(*) FILTER (WHERE m.result = 'no result' OR m.method IS NOT NULL) / count(*), 1) AS pct
    FROM matches m JOIN venues v USING (venue_id)
    WHERE m.dataset = 'odis' AND m.gender = 'male' AND m.start_date >= '2010-01-01'
    GROUP BY 1 ORDER BY 1""")
print("\nRain-hit ODIs since 2010\n", rain)
