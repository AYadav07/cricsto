"""Loader tests on small fixture matches (no real data needed)."""
from __future__ import annotations

import json

import pytest

from cricsto.load_json import LoadError, team_id
from conftest import basic_match


def test_basic_rows(env):
    env.write("900001", basic_match())
    r = env.load()
    rows = r["rows"]
    assert (r["new"], r["changed"], r["gone"]) == (1, 0, 0)
    assert rows["matches"] == 1 and rows["innings"] == 2 and rows["balls"] == 10
    assert rows["wickets"] == 3 and rows["fielding"] == 2 and rows["reviews"] == 1
    assert rows["replacements"] == 1 and rows["powerplays"] == 1
    assert rows["people"] == 9 and rows["teams"] == 2 and rows["venues"] == 1
    assert rows["match_players"] == 6 and rows["officials"] == 3 and rows["player_of_match"] == 1
    assert env.q("SELECT season, dataset, gender, event_group FROM matches") == [("2024", "tst", "male", "1")]


def test_legal_ball_numbering(env):
    env.write("900001", basic_match())
    env.load()
    got = env.q("""SELECT ball_seq, legal_ball_no, actual_delivery, wides, noballs FROM balls
                   WHERE innings_no = 1 ORDER BY ball_seq""")
    # wide and no-ball carry the number of the ball being attempted
    assert [g[1] for g in got] == [1, 2, 2, 3, 3, 4, 5, 6]
    assert all(g[2] == f"0.{g[1]}" for g in got)


def test_wicket_flags_and_fielders(env):
    env.write("900001", basic_match())
    env.load()
    w = dict((k, (c, d)) for k, c, d in env.q(
        "SELECT kind, bowler_credited, is_dismissal FROM wickets"))
    assert w["retired hurt"] == (False, False)
    assert w["run out"] == (False, True)
    assert w["caught"] == (True, True)
    f = env.q("SELECT fielder_id, is_substitute FROM fielding ORDER BY ball_seq")
    assert f == [(None, True), ("bbbb0002", False)]


def test_review_and_replacement(env):
    env.write("900001", basic_match())
    env.load()
    assert env.q("SELECT reviewing_team_id, batter_id, umpire_id, decision, umpires_call, review_type "
                 "FROM reviews") == [(team_id("Alpha"), "aaaa0003", "uuuu0001", "struck down", True, "wicket")]
    assert env.q("SELECT scope, team_id, player_in_id, player_out_id, reason FROM replacements") == [
        ("match", team_id("Beta"), "bbbb0003", "bbbb0002", "impact_player")]


def test_rerun_is_noop(env):
    env.write("900001", basic_match())
    first = env.load()
    second = env.load()
    assert (second["new"], second["changed"], second["gone"]) == (0, 0, 0)
    assert second["rows"] == first["rows"]


def test_changed_file_reloads(env):
    m = basic_match()
    env.write("900001", m)
    env.load()
    m["meta"]["revision"] = 2
    m["innings"][1]["overs"][0]["deliveries"][0]["runs"].update(batter=4, total=4)
    env.write("900001", m)
    r = env.load()
    assert r["changed"] == 1
    assert env.q("SELECT revision FROM matches") == [(2,)]
    assert env.q("SELECT runs_batter FROM balls WHERE innings_no = 2 AND ball_seq = 1") == [(4,)]
    assert r["rows"]["balls"] == 10


def test_gone_file_is_deleted(env):
    env.write("900001", basic_match())
    m2 = basic_match()
    m2["info"]["dates"] = ["2024-05-01"]
    p2 = env.write("900002", m2)
    env.load()
    p2.unlink()
    r = env.load()
    assert r["gone"] == 1
    assert env.q("SELECT match_id FROM matches") == [("900001",)]
    assert env.q("SELECT count(*) FROM balls WHERE match_id = '900002'") == [(0,)]


def test_latest_name_wins_and_follows_deletes(env):
    old = basic_match()
    new = basic_match()
    new["info"]["dates"] = ["2024-06-01"]

    def rename(obj, a, b):  # same IDs, new name everywhere in the file
        return json.loads(json.dumps(obj).replace(f'"{a}"', f'"{b}"'))
    new = rename(new, "A One", "A One-Renamed")
    new = rename(new, "Test Ground", "Test Ground, New Name")
    new["info"]["city"] = "Newtown"
    env.write("900001", old)
    p_new = env.write("900002", new)
    env.load()
    assert env.q("SELECT name FROM people WHERE person_id = 'aaaa0001'") == [("A One-Renamed",)]
    assert env.q("SELECT name, city FROM venues") == [("Test Ground, New Name", "Newtown")]
    p_new.unlink()
    env.load()
    assert env.q("SELECT name FROM people WHERE person_id = 'aaaa0001'") == [("A One",)]
    assert env.q("SELECT name, city FROM venues") == [("Test Ground", "Testville")]


def test_gender_mismatch_is_an_error(env):
    env.write("900001", basic_match(), folder="tst_female_json")
    with pytest.raises(LoadError, match="gender"):
        env.load()


def test_same_match_in_two_folders_is_an_error(env):
    env.write("900001", basic_match(), folder="tst_male_json")
    env.write("900001", basic_match(), folder="xyz_male_json")
    with pytest.raises(LoadError, match="in both"):
        env.load()


def test_name_without_id_is_an_error(env):
    m = basic_match()
    del m["info"]["registry"]["people"]["B One"]
    env.write("900001", m)
    with pytest.raises(LoadError, match="failed to parse"):
        env.load()


def test_bad_actual_delivery_is_an_error(env):
    m = basic_match()
    m["innings"][0]["overs"][0]["deliveries"][1]["actual_delivery"] = "0.1"  # the wide
    env.write("900001", m)
    with pytest.raises(LoadError, match="actual_delivery"):
        env.load()


def test_failed_run_leaves_db_consistent_and_heals(env):
    good = basic_match()
    env.write("900001", good)
    env.load()
    bad = basic_match()
    bad["meta"]["revision"] = 2
    del bad["info"]["registry"]["people"]["B One"]
    env.write("900001", bad)
    with pytest.raises(LoadError):
        env.load()
    # the match being reloaded is absent, with no half-loaded rows
    assert env.q("SELECT count(*) FROM matches") == [(0,)]
    assert env.q("SELECT count(*) FROM balls") == [(0,)]
    env.write("900001", good)
    r = env.load()
    assert r["new"] == 1 and r["rows"]["balls"] == 10


def test_long_over_warning(env):
    m = basic_match()
    d = m["innings"][0]["overs"][0]["deliveries"]
    d.append({"actual_delivery": "0.7", "batter": "A Two", "bowler": "B One", "non_striker": "A One",
              "runs": {"batter": 1, "extras": 0, "total": 1}})
    env.write("900001", m)
    env.load()
    assert env.q("SELECT check_name, innings_no, over_num FROM load_warnings") == [("over_too_long", 1, 0)]
    # listed in miscounted_overs -> no warning
    m["innings"][0]["miscounted_overs"] = {"0": {"balls": "7", "umpire": "U One"}}
    m["meta"]["revision"] = 2
    env.write("900001", m)
    env.load()
    assert env.q("SELECT count(*) FROM load_warnings") == [(0,)]
    assert env.q("SELECT over_num, balls, umpire_id FROM miscounted_overs") == [(0, 7, "uuuu0001")]


def test_informal_umpire_name_resolved_with_warning(env):
    m = basic_match()
    m["innings"][0]["miscounted_overs"] = {"0": {"balls": 6, "umpire": "Two"}}  # 'U Two' by surname
    env.write("900001", m)
    env.load()
    assert env.q("SELECT umpire_id FROM miscounted_overs") == [("uuuu0002",)]
    assert env.q("SELECT check_name FROM load_warnings") == [("umpire_name_not_in_registry",)]


def test_player_in_both_teams_warning(env):
    m = basic_match()
    m["info"]["players"]["Beta"].append("A One")
    env.write("900001", m)
    env.load()
    assert env.q("SELECT check_name FROM load_warnings") == [("player_in_both_teams",)]
    assert env.q("SELECT count(*) FROM match_players WHERE person_id = 'aaaa0001'") == [(2,)]


def test_full_reload(env):
    env.write("900001", basic_match())
    env.load()
    r = env.load(full=True)
    assert r["new"] == 1 and r["rows"]["matches"] == 1
