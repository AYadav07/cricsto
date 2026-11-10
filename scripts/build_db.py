"""Build data/cricsto.duckdb from everything in data/raw/.

Usage:
    python scripts/build_db.py            # all downloaded datasets
    python scripts/build_db.py ipl t20s   # only these
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cricsto.db import build  # noqa: E402

if __name__ == "__main__":
    build(sys.argv[1:] or None)
