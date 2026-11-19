"""NZ vs IND Test series batch (2026-11-18): charts for the X drafts.

Numbers come from Cricsheet Test JSON (data/raw/json/tests_male_json), read directly
because this batch was run where the DuckDB file could not be opened. WTC figures are
from the 10 Nov 2026 table (Outlook India) with our own points arithmetic.
"""
import collections, glob, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cricsto import charts

RAW = Path(__file__).resolve().parent.parent / "data/raw/json/tests_male_json"
NB = {"run out", "retired hurt", "retired out", "obstructing the field", "retired not out"}

matches = []
for f in glob.glob(str(RAW / "*.json")):
    d = json.load(open(f))
    if d["info"].get("gender") == "male":
        matches.append(d)

def total(inn):
    return sum(dl["runs"]["total"] for o in inn.get("overs", []) for dl in o["deliveries"])

# Basin Reserve since 2015: bat-first vs bowl-first results, wicket-takers
basin = [d for d in matches if "Basin" in d["info"].get("venue", "") and d["info"]["dates"][0] >= "2015"]
res = collections.Counter(); wk = collections.Counter()
for d in basin:
    first = d["innings"][0]["team"]; w = d["info"]["outcome"].get("winner")
    res["Draw" if not w else ("Batting first" if w == first else "Bowling first")] += 1
    for inn in d["innings"]:
        for o in inn.get("overs", []):
            for dl in o["deliveries"]:
                wk[dl["bowler"]] += sum(1 for x in dl.get("wickets", []) if x["kind"] not in NB)
print("Basin since 2015:", len(basin), dict(res)); print(wk.most_common(8))

# Bowler averages: overall and vs an opponent
def bowl(name, opp=None):
    r = w = 0
    for d in matches:
        for inn in d["innings"]:
            if opp and inn["team"] != opp: continue
            for o in inn.get("overs", []):
                for dl in o["deliveries"]:
                    if dl["bowler"] != name: continue
                    ex = dl.get("extras", {})
                    r += dl["runs"]["batter"] + ex.get("wides", 0) + ex.get("noballs", 0)
                    w += sum(1 for x in dl.get("wickets", []) if x["kind"] not in NB)
    return w, r / w
b_all, b_nz = bowl("JJ Bumrah"), bowl("JJ Bumrah", "New Zealand")
print("Bumrah all", b_all, "vs NZ", b_nz)

# India's innings in NZ, 2020
ind20 = []
for d in sorted(matches, key=lambda d: d["info"]["dates"][0]):
    i = d["info"]
    if set(i["teams"]) == {"India", "New Zealand"} and i["dates"][0].startswith("2020-0") and i.get("city") in ("Wellington", "Christchurch"):
        for n, inn in enumerate(d["innings"]):
            if inn["team"] == "India":
                ind20.append((i.get("city"), total(inn)))
print("India 2020 in NZ:", ind20)

# --- charts ---
charts.save(charts.bar(["Bowling first", "Batting first", "Draw"],
    [res["Bowling first"], res["Batting first"], res["Draw"]],
    "At Basin Reserve, bowl first", f"Results of the {len(basin)} Tests at Basin Reserve, Wellington, since 2015",
    highlight="Bowling first", value_fmt="{:.0f}"), "nzvind_basin_toss")

top = wk.most_common(4); lyon = ("NM Lyon", wk["NM Lyon"])
names = {"TG Southee": "Southee", "N Wagner": "Wagner", "TA Boult": "Boult", "MJ Henry": "Henry", "NM Lyon": "Lyon (best spinner)"}
rows = top + [lyon]
charts.save(charts.bar([names[n] for n, _ in rows], [v for _, v in rows],
    "Basin Reserve is a seamers' ground", "Most Test wickets at Basin Reserve since 2015 (14 Tests)",
    highlight=[names[n] for n, _ in top], value_fmt="{:.0f}", xlabel="Wickets"), "nzvind_basin_wickets")

charts.save(charts.bar(["vs New Zealand", "All Tests"], [b_nz[1], b_all[1]],
    "Bumrah's one odd number", f"Test bowling average (lower is better). vs NZ: {b_nz[0]} wkts in 5 Tests. All: {b_all[0]} wkts",
    highlight="vs New Zealand", value_fmt="{:.2f}"), "nzvind_bumrah_nz")

charts.save(charts.bar([f"{c}, {k} inns" for k, (c, _) in zip(["1st", "2nd", "1st", "2nd"], ind20)], [v for _, v in ind20],
    "India never crossed 250 in NZ in 2020", "India's 4 innings on the 2020 Test tour (Wellington, Christchurch)",
    value_fmt="{:.0f}"), "nzvind_india_2020")

# WTC: India 68 pts from 11 Tests (5W 4L 2D) = 51.52%; win 12 pts, draw 4
sc = {"Win 2-0": 92, "1 win, 1 draw": 84, "1-1": 80, "Draw both": 76, "Lose 0-2": 68}
pct = {k: v / 156 * 100 for k, v in sc.items()}
print("WTC scenarios:", {k: round(v, 2) for k, v in pct.items()})
charts.save(charts.bar(list(pct), list(pct.values()),
    "What this series does to India's WTC %", "India's points % after the 2 Tests in NZ (now 51.52%). Win = 12 pts, draw = 4",
    source="WTC table: ICC standings as of 10 Nov 2026. Calculation: Cricsto", highlight="1-1",
    value_fmt="{:.2f}%"), "nzvind_wtc_scenarios")
