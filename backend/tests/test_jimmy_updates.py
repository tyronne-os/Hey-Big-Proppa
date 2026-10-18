import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boo_curriculum as cur
import jimmy_updates as ju


@pytest.fixture(autouse=True)
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(ju, "DIR", tmp_path / "jimmy")
    monkeypatch.setattr(cur, "DIR", tmp_path / "cur")
    return tmp_path


def _props():
    return [dict(player_id=f"p{i}", team="KC", prop_type=t, confidence=c * 100, line=50)
            for i, (t, c) in enumerate([("rec_yds", .9), ("rush_yds", .8), ("pass_yds", .7), ("receptions", .6), ("rec_yds", .5)])]


def test_pick_respects_legs_and_exclusion():
    pol = {"legs": 2, "direction": {p: "over" for p in ju.PROPS}, "rank": "confidence"}
    got = ju.pick(_props(), pol, {"p0"})
    assert len(got) == 2 and all(g["player_id"] != "p0" for g in got)
    under = ju.pick(_props(), {**pol, "direction": {**pol["direction"], "rec_yds": "under"}, "legs": 1})
    assert under[0]["prop_type"] == "rush_yds" or not under[0]["is_over"]


def test_baseline_version_without_updates():
    assert ju.version() == "JU-0000" and ju.current()["policy"] == ju.BASE_POLICY


def test_live_record_and_summary():
    slips = [dict(result=True, legs=2, legs_hit=2, wager=5.0, payout=20.0), dict(result=False, legs=3, legs_hit=1, wager=5.0, payout=0.0)]
    ju.record_live(2025, slips, 110.0, "JU-0001", "s1")
    s = ju.live_summary()["JU-0001"]
    assert s["slips"] == 2 and s["wins"] == 1 and s["staked"] == 10.0 and s["returned"] == 20.0
