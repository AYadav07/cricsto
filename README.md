# cricsto-data

The data engine behind **@cricsto: Cricket by Numbers**.
Question → query → chart → post on X.

The repo has three independent modules. Each has its own README:

| Module | What it is | Start here |
|---|---|---|
| [`cricsheet/`](cricsheet/README.md) | Ball-by-ball database from Cricsheet (2002 →, refreshed weekly): phases, matchups, every delivery | `cricsheet/README.md`, `cricsheet/SCHEMA.md` |
| [`history/`](history/README.md) | Scorecard database for Tests (1877–2023) and ODIs (1971–2023): the pre-2002 era. Fixed snapshot | `history/README.md`, `history/SCHEMA.md` |
| [`posts/`](posts/README.md) | The @cricsto side: brand chart template, fonts, post batches, generated charts | `posts/README.md` |

**The two databases are separate.** They have different sources, different player IDs and
different levels of detail. Never join them or add their numbers together.

```
cricsto-data/
├─ cricsheet/        ball-by-ball: code, queries, scripts, data/, tests/, SCHEMA.md
├─ history/          scorecards: build.py, queries, raw/, history.duckdb, SCHEMA.md
├─ posts/            charts.py, fonts/, batches/, output/
├─ .github/workflows/refresh-data.yml   weekly Cricsheet refresh → release "data-latest"
├─ requirements.txt
├─ CLAUDE.md         context and decisions for Claude sessions
└─ README.md
```

## Set up (once)

```bash
git clone https://github.com/AYadav07/cricsto cricsto-data && cd cricsto-data
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Then build the databases you need. Run everything from the repo root:

```bash
python cricsheet/scripts/refresh.py --full   # Cricsheet: download + build (first time)
bash cricsheet/scripts/get_db.sh             # ...or download the copy the GitHub Action built
python history/build.py                      # history: see history/README.md for the raw files
```

## Typical loop

1. Pick a question people are debating.
2. Query: `cricsheet/insights.py` and `cricsheet/queries/`, or `history/db.py` and `history/queries/`.
3. Chart: `posts/charts.py`, in a new script in `posts/batches/`.
4. Check: the checklist in `posts/README.md`.
5. Post the PNG from `posts/output/`.

## Tests

```bash
python -m pytest cricsheet/tests
```
