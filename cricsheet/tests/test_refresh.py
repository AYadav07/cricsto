"""Refresh tests with fake zips (no network)."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from cricsheet import refresh
from conftest import basic_match


def info(**kw):
    i = {"gender": "male", "team_type": "international", "match_type": "T20", "event": {"name": "X"}}
    i.update(kw)
    return i


@pytest.mark.parametrize("kw, folder", [
    ({}, "t20s_male_json"),
    ({"gender": "female", "match_type": "ODI"}, "odis_female_json"),
    ({"match_type": "Test"}, "tests_male_json"),
    ({"match_type": "ODM"}, None),                                     # non-official one-dayers
    ({"team_type": "club"}, None),                                     # other leagues
    ({"team_type": "club", "event": {"name": "Indian Premier League"}}, "ipl_male_json"),
    ({"team_type": "club", "gender": "female", "event": {"name": "Women's Premier League"}},
     "wpl_female_json"),
    ({"team_type": "club", "gender": "female", "event": {"name": "Indian Premier League"}}, None),
])
def test_route(kw, folder):
    assert refresh.route(info(**kw)) == folder


def make_zip(files: dict[str, dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("README.txt", "readme")
        for name, data in files.items():
            z.writestr(name, json.dumps(data))
        z.writestr("../evil.json", "{}")          # must be ignored (not <digits>.json)
    return buf.getvalue()


def match(**info_kw):
    m = basic_match()
    m["info"].update(info_kw)
    return m


def test_weekly_routes_and_skips(env, monkeypatch):
    zips = {
        "recently_added_7_male_json.zip": make_zip({
            "1.json": match(),                                           # T20I -> t20s_male
            "2.json": match(team_type="club", event={"name": "Some League"}),  # skipped
        }),
        "recently_added_7_female_json.zip": make_zip({"3.json": match(gender="female", match_type="ODI")}),
    }
    monkeypatch.setattr(refresh, "fetch", lambda url: zips[url.rsplit("/", 1)[1]])
    rep = refresh.weekly(raw_dir=env.raw)
    assert sorted(rep.added) == ["odis_female_json/3.json", "t20s_male_json/1.json"]
    assert rep.skipped == 1
    assert not (env.raw.parent / "evil.json").exists()
    again = refresh.weekly(raw_dir=env.raw)
    assert again.added == [] and again.unchanged == 2


def test_weekly_dry_run_changes_nothing(env, monkeypatch):
    z = make_zip({"1.json": match()})
    monkeypatch.setattr(refresh, "fetch", lambda url: z)
    rep = refresh.weekly(raw_dir=env.raw, dry_run=True)
    assert rep.added and not list(env.raw.glob("*/*.json"))


def test_full_sync_adds_updates_removes(env, monkeypatch):
    env.write("1", match(), folder="t20s_male_json")
    env.write("2", match(), folder="t20s_male_json")
    m1 = match()
    m1["meta"]["revision"] = 2
    z = make_zip({"1.json": m1, "3.json": match()})
    monkeypatch.setattr(refresh, "fetch", lambda url: z)
    monkeypatch.setattr(refresh, "MIN_SHARE", 0.5)
    rep = refresh.full_sync(folders=["t20s_male_json"], raw_dir=env.raw)
    assert rep.updated == ["t20s_male_json/1.json"]
    assert rep.added == ["t20s_male_json/3.json"]
    assert rep.removed == ["t20s_male_json/2.json"]
    names = sorted(p.name for p in (env.raw / "t20s_male_json").iterdir())
    assert names == ["1.json", "3.json", "README.txt"]


def test_full_sync_refuses_a_suspiciously_small_zip(env, monkeypatch):
    for i in range(10):
        env.write(str(i), match(), folder="t20s_male_json")
    monkeypatch.setattr(refresh, "fetch", lambda url: make_zip({"1.json": match()}))
    with pytest.raises(RuntimeError, match="refusing"):
        refresh.full_sync(folders=["t20s_male_json"], raw_dir=env.raw)
    assert len(list((env.raw / "t20s_male_json").glob("*.json"))) == 10


def test_refresh_then_load(env, monkeypatch):
    z = make_zip({"900001.json": match()})
    monkeypatch.setattr(refresh, "fetch", lambda url: z)
    refresh.weekly(raw_dir=env.raw)
    r = env.load()
    assert r["new"] == 1 and r["rows"]["balls"] == 10


class _Resp:
    def __init__(self, body, ctype):
        self.body, self.headers = body, {"Content-Type": ctype}
    def read(self):
        return self.body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_fetch_retries_a_web_page_then_returns_the_zip(monkeypatch):
    answers = [_Resp(b"<!DOCTYPE html><title>Too many requests</title>", "text/html"),
               _Resp(make_zip({"1.json": match()}), "application/zip")]
    monkeypatch.setattr(refresh.urllib.request, "urlopen", lambda req, timeout: answers.pop(0))
    monkeypatch.setattr(refresh.time, "sleep", lambda s: None)
    assert refresh.fetch("https://cricsheet.org/downloads/x.zip").startswith(b"PK")


def test_fetch_gives_up_with_a_clear_error(monkeypatch):
    monkeypatch.setattr(refresh.urllib.request, "urlopen",
                        lambda req, timeout: _Resp(b"<html>blocked</html>", "text/html"))
    monkeypatch.setattr(refresh.time, "sleep", lambda s: None)
    import pytest
    with pytest.raises(refresh.DownloadError, match="not a zip"):
        refresh.fetch("https://cricsheet.org/downloads/x.zip")
