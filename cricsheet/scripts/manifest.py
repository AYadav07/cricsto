"""Print a JSON summary of cricsheet/data/cricsto.duckdb: when it was built and the latest match per dataset.

Published next to the database in the data-latest release, so you can see how fresh it is
without downloading it.

Usage:
    python cricsheet/scripts/manifest.py [path/to/cricsto.duckdb]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent   # the cricsheet/ folder
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "cricsto.duckdb"


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    rows = con.execute("""
        SELECT dataset, gender, count(*) AS matches, max(start_date) AS latest_match
        FROM matches
        GROUP BY dataset, gender
        ORDER BY dataset, gender
    """).fetchall()
    balls = con.execute("SELECT count(*) FROM balls").fetchone()[0]
    con.close()
    print(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_matches": sum(r[2] for r in rows),
        "total_balls": balls,
        "datasets": [
            {"dataset": d, "gender": g, "matches": n, "latest_match": str(latest)}
            for d, g, n, latest in rows
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
