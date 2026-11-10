"""Weekly refresh: re-download your datasets and rebuild the database.

Edit DATASETS to the competitions you follow, then run:
    python scripts/refresh.py
"""
import subprocess
import sys
from pathlib import Path

DATASETS = ["ipl", "t20s", "odis"]

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    py = sys.executable
    subprocess.run([py, str(ROOT / "scripts" / "download.py"), *DATASETS], check=True)
    subprocess.run([py, str(ROOT / "scripts" / "build_db.py")], check=True)
