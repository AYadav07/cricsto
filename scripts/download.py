"""Download Cricsheet ball-by-ball data (CSV "Ashwin" format) into data/raw/<dataset>/.

Usage:
    python scripts/download.py ipl                 # IPL, men's
    python scripts/download.py t20s odis           # several at once
    python scripts/download.py wpl --gender female
    python scripts/download.py --list              # show common codes

Re-running replaces the folder with the latest data. If a download fails, open
https://cricsheet.org/downloads/ , copy the "CSV (Ashwin)" link for the competition
and pass it with --url.
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

COMMON = {
    "ipl": "Indian Premier League",
    "t20s": "T20 internationals",
    "odis": "One-day internationals",
    "tests": "Test matches",
    "bbl": "Big Bash League",
    "psl": "Pakistan Super League",
    "cpl": "Caribbean Premier League",
    "sat": "SA20",
    "hnd": "The Hundred",
    "wpl": "Women's Premier League (use --gender female)",
}


def url_for(code: str, gender: str) -> str:
    return f"https://cricsheet.org/downloads/{code}_{gender}_csv2.zip"


def download(code: str, url: str) -> None:
    dest = RAW_DIR / code
    print(f"Downloading {code} from {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "cricsto-data/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.namelist():
            name = Path(member).name
            if name.endswith(".csv"):  # flatten, skip readme etc.
                (dest / name).write_bytes(z.read(member))
    n = sum(1 for p in dest.glob("*.csv") if not p.name.endswith("_info.csv"))
    print(f"  saved {n} match files to {dest.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("codes", nargs="*", help="competition codes, e.g. ipl t20s odis")
    ap.add_argument("--gender", default="male", choices=["male", "female"])
    ap.add_argument("--url", help="explicit zip URL (only with a single code)")
    ap.add_argument("--list", action="store_true", help="show common competition codes")
    args = ap.parse_args()

    if args.list or not args.codes:
        for k, v in COMMON.items():
            print(f"  {k:6} {v}")
        print("\nFull list: https://cricsheet.org/downloads/")
        return
    if args.url and len(args.codes) != 1:
        sys.exit("--url works with exactly one code")

    for code in args.codes:
        try:
            download(code, args.url or url_for(code, args.gender))
        except Exception as e:  # noqa: BLE001
            print(f"  failed: {e}\n  Copy the 'CSV (Ashwin)' link from https://cricsheet.org/downloads/ "
                  f"and run: python scripts/download.py {code} --url <link>")


if __name__ == "__main__":
    main()
