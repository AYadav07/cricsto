"""Build or update data/cricsto.duckdb from the Cricsheet JSON in data/raw/json/.

Usage:
    python scripts/build_db.py          # incremental: new / changed / removed files only
    python scripts/build_db.py --full   # drop every table and reload everything

Close any other connection to the database (DBeaver, duckdb CLI) first:
DuckDB allows only one writer.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cricsto.load_json import LoadError, load  # noqa: E402
from cricsto.views import apply_views  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="drop every table and reload everything")
    ap.add_argument("--workers", type=int, default=None, help="parser processes (default: all CPUs)")
    args = ap.parse_args()
    try:
        load(full=args.full, workers=args.workers)
    except LoadError as e:
        sys.exit(f"LOAD FAILED. This run's inserts were rolled back; matches it was "
                 f"reloading are absent and will load on the next run.\n{e}")
    apply_views()


if __name__ == "__main__":
    main()
