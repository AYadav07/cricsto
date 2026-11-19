# posts: the @cricsto side

Everything that turns query results into posts: the brand chart template, the fonts, one script
per batch of posts, and the generated PNGs. It reads from the databases (`cricsheet/`, `history/`)
and never writes to them.

```
posts/charts.py      brand chart template: bar(), line(), scatter(), save()
posts/fonts/         Space Grotesk (headings) and Inter (body), static .ttf files
posts/batches/       one script per post batch; rerun it to regenerate the charts and print every number used
posts/output/        generated PNGs (git-ignored)
```

Run every command from the repo root.

## Brand

- Navy `#0E1A2B` background, cricket-ball red `#D94B3D` accent, cream `#F2E8D5` text,
  muted `#C9C2B3`, amber `#E8A33D` second series.
- Space Grotesk headings, Inter body. `@cricsto` mark bottom-right, source line bottom-left.
- 1600×900 px (16:9 shows in full in the X timeline).
- Voice: sharp, evidence-first, curious. Hook = a question; answer = one clear chart plus 1–2 lines.
  No hot takes without numbers; never mock players or fans.

## Make a chart

```python
from cricsheet import insights as ins
from posts import charts

top = ins.batter_strike_rate("ipl", phase="death", season_from="2024", min_balls=60).head(10)
fig = charts.bar(top["batter"], top["strike_rate"],
                 title="Fastest death-over hitters",
                 subtitle="IPL, overs 16–20, since 2024 (min. 60 balls)",
                 highlight=top["batter"].iloc[0], value_fmt="{:.0f}")
charts.save(fig, "death_hitters")       # → posts/output/death_hitters.png
```

- `charts.line(x, {"Series A": ys, "Series B": ys2}, title=...)` for trends.
- `charts.scatter(x, y, labels, title=..., label_offsets=...)` for two measures at once.
- Every chart takes `source=`. The default is `"Data: Cricsheet"`. For the history database use
  e.g. `source="Data: ESPNcricinfo scorecards (via bhuvaneshprasad), 1877–2001"`.
- If the fonts aren't found, charts fall back to a default font. They're loaded from
  `posts/fonts/` automatically.

## Batches

One script per batch of posts, named by date or series, e.g. `posts/batches/batch_2026_11_10.py`
or `series_ind_nz_2026.py`. Each one builds its charts and prints every number it uses, so any
posted stat can be rerun and checked. `first_post.py` is a worked example to copy:

```bash
python posts/batches/first_post.py
```

## Before posting: checklist

- [ ] The number comes from a query in this repo (rerunnable), not memory.
- [ ] Sample size is stated in the subtitle (min. balls, matches, seasons).
- [ ] Phases and filters are stated (e.g. "overs 16–20, since 2024").
- [ ] Spot-check one figure against ESPNcricinfo or the scorecard.
- [ ] The source is credited. The template adds "Data: Cricsheet"; change `source=` for history-database charts.
- [ ] Numbers from `cricsheet/` and `history/` aren't added together. If a post uses both, it says which is which.
