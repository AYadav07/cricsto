"""Refresh data/raw/json/ from Cricsheet (SCHEMA.md section 7a). Only changes files;
run the loader afterwards (scripts/refresh.py does both).

    weekly()      recently added matches (2 small zips), routed into our folders
    full_sync()   the 8 full zips; each folder is made identical to its zip
"""
from __future__ import annotations

import io
import json
import re
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .load_json import RAW_DIR

BASE_URL = "https://cricsheet.org/downloads/"
USER_AGENT = "cricsto-data/2.0"
FOLDERS = [
    "ipl_male_json", "wpl_female_json",
    "odis_male_json", "odis_female_json",
    "t20s_male_json", "t20s_female_json",
    "tests_male_json", "tests_female_json",
]
MATCH_FILE = re.compile(r"^\d+\.json$")
KEEP = {"README.txt", "LICENSE.txt"}
# A full zip with fewer matches than this share of the local folder is treated as broken.
MIN_SHARE = 0.9


def route(info: dict) -> str | None:
    """Folder for a match, from its info block, or None if we don't collect it."""
    event = info.get("event", {}).get("name")
    gender, team_type, match_type = info["gender"], info["team_type"], info["match_type"]
    if event == "Indian Premier League" and gender == "male" and team_type == "club":
        return "ipl_male_json"
    if event == "Women's Premier League" and gender == "female" and team_type == "club":
        return "wpl_female_json"
    if team_type == "international":
        code = {"T20": "t20s", "ODI": "odis", "Test": "tests"}.get(match_type)
        if code:
            return f"{code}_{gender}_json"
    return None


def fetch(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _matches_in_zip(data: bytes) -> dict[str, bytes]:
    """{file name: bytes} for every <digits>.json in the zip, each checked to parse."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.namelist():
            name = Path(member).name           # flatten; never trust paths inside the zip
            if MATCH_FILE.match(name):
                body = z.read(member)
                json.loads(body)               # broken JSON stops the refresh
                out[name] = body
    return out


def _write(path: Path, body: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(path)


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    skipped: int = 0          # weekly: matches from competitions we don't collect

    def __str__(self) -> str:
        return (f"added {len(self.added)}, updated {len(self.updated)}, removed {len(self.removed)}, "
                f"unchanged {self.unchanged}, skipped {self.skipped}")


def weekly(days: int = 7, raw_dir: Path = RAW_DIR, dry_run: bool = False) -> Report:
    """Add matches from Cricsheet's 'recently added' zips (both genders)."""
    rep = Report()
    local = {p.name: p for p in raw_dir.glob("*/*.json")}
    for gender in ("male", "female"):
        files = _matches_in_zip(fetch(f"{BASE_URL}recently_added_{days}_{gender}_json.zip"))
        for name, body in sorted(files.items()):
            folder = route(json.loads(body)["info"])
            if folder is None:
                rep.skipped += 1
                continue
            target = raw_dir / folder / name
            old = local.get(name)
            if old is not None and old.read_bytes() == body and old == target:
                rep.unchanged += 1
                continue
            (rep.updated if old is not None else rep.added).append(f"{folder}/{name}")
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                _write(target, body)
                if old is not None and old != target:   # moved folder: keep one copy only
                    old.unlink()
    return rep


def full_sync(folders: list[str] | None = None, raw_dir: Path = RAW_DIR,
              dry_run: bool = False) -> Report:
    """Make each folder identical to its full Cricsheet zip (adds, updates, removes)."""
    rep = Report()
    for folder in folders or FOLDERS:
        data = fetch(f"{BASE_URL}{folder}.zip")
        files = _matches_in_zip(data)
        target_dir = raw_dir / folder
        local = {p.name: p for p in target_dir.glob("*.json")} if target_dir.exists() else {}
        if local and len(files) < MIN_SHARE * len(local):
            raise RuntimeError(f"{folder}.zip has {len(files)} matches but the folder has "
                               f"{len(local)}; refusing to sync (download broken?)")
        for name, body in sorted(files.items()):
            old = local.get(name)
            if old is not None and old.read_bytes() == body:
                rep.unchanged += 1
                continue
            (rep.updated if old is not None else rep.added).append(f"{folder}/{name}")
            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
                _write(target_dir / name, body)
        for name in sorted(set(local) - set(files)):
            rep.removed.append(f"{folder}/{name}")
            if not dry_run:
                local[name].unlink()
        if not dry_run:  # keep Cricsheet's README / LICENSE current
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for member in z.namelist():
                    if Path(member).name in KEEP:
                        _write(target_dir / Path(member).name, z.read(member))
    return rep
