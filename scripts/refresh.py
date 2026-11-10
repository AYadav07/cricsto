"""Get new Cricsheet data into data/raw/json/, then update the database.

Usage:
    python scripts/refresh.py              # weekly: matches added in the last 7 days
    python scripts/refresh.py --days 30    # catch up after a longer gap (2, 7 or 30)
    python scripts/refresh.py --full       # monthly: re-download the 8 full zips
                                           #   (also picks up corrections and removed matches)
    python scripts/refresh.py --dry-run    # show what would change; change nothing

Close any other connection to the database (DBeaver, duckdb CLI) first.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cricsto.load_json import LoadError, load  # noqa: E402
from cricsto.refresh import full_sync, weekly  # noqa: E402
from cricsto.views import apply_views  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--days", type=int, choices=[2, 7, 30], default=7,
                      help="recently-added window (default 7)")
    mode.add_argument("--full", action="store_true", help="re-download the 8 full zips")
    ap.add_argument("--dry-run", action="store_true", help="show changes without making them")
    ap.add_argument("--no-load", action="store_true", help="update files only, not the database")
    args = ap.parse_args()

    if args.full:
        print("Full sync of the 8 Cricsheet zips ...")
        rep = full_sync(dry_run=args.dry_run)
    else:
        print(f"Recently added (last {args.days} days) ...")
        rep = weekly(days=args.days, dry_run=args.dry_run)
    print(f"Files: {rep}")
    for label, items in (("added", rep.added), ("updated", rep.updated), ("removed", rep.removed)):
        for item in items[:20]:
            print(f"  {label:8} {item}")
        if len(items) > 20:
            print(f"  ... and {len(items) - 20} more {label}")

    if args.dry_run or args.no_load:
        return
    try:
        load()
    except LoadError as e:
        sys.exit(f"LOAD FAILED. This run's inserts were rolled back; matches it was "
                 f"reloading are absent and will load on the next run.\n{e}")
    apply_views()


if __name__ == "__main__":
    main()
