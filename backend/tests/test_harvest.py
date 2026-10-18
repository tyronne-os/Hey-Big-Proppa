import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import betterverse_sim as sim
import betterverse_study as study
import boo_curriculum as cur
import boo_harvest as h
import boo_jev_trainer as tr


@pytest.fixture(autouse=True)
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "OUT", tmp_path / "bv")
    monkeypatch.setattr(study, "OUT", tmp_path / "studies")
    monkeypatch.setattr(cur, "DIR", tmp_path / "cur")
    monkeypatch.setattr(h, "DIR", tmp_path / "harvest")
    monkeypatch.setattr(tr, "DIR", tmp_path / "models")
    monkeypatch.setattr(h, "_mirror", lambda kind, ident, path, remote: False)       # no network in tests
    monkeypatch.setattr(h, "_mirror_state", lambda: None)
    return tmp_path


def _row(key, label, roi, p_all, by_season, slips=5000, ci=(0.01, 0.1), hit=0.3, imp=0.27, rank=1):
    return dict(key=key, label=label, slips=slips, staked=slips * 7.0, roi=roi, ci_lo=ci[0], ci_hi=ci[1], p_profit=min(1, p_all + 0.2),
                p_all_seasons=p_all, p_profit_by_season={y: 0.9 for y in by_season}, hit_rate=hit, implied=imp, edge_pts=hit - imp,
                by_season=by_season, profitable_95=ci[0] > 0, profitable_all_seasons=all(v > 0 for v in by_season.values()), rank_p=rank,
                beats_field_all_seasons=True, beats_field_95=True, units=100, avg_legs=2)


def _study(seasons, shape_by_season, p_all):
    return {"study_id": f"st_u20_n150_s100_y{'-'.join(map(str, seasons))}", "universes": 20, "bettors_per_universe": 150, "bettor_seasons": 9000,
            "slips": 100000, "seed": 100, "seasons": list(seasons), "field": {"roi": -0.16, "by_season": {str(y): -0.16 for y in seasons}},
            "dims": {"shape": [_row("total:over x2", "Game Total over x2", 0.05, p_all, shape_by_season),
                               _row("total:over x6", "Game Total over x6", -0.6, 0.0, {str(y): -0.6 for y in seasons}, ci=(-0.7, -0.5), hit=0.01, imp=0.02)],
                     "style_tier": [], "n_legs": [_row("2", "2-leg slip", -0.08, 0.0, {str(y): -0.08 for y in seasons}, ci=(-0.1, -0.06))],
                     "sgp": [], "tier": []},
            "rookie_winners": []}


def test_grading_rules():
    base = dict(label="x", studies=1, slips=5000, staked=1.0, roi=0.05, ci_lo=0.01, ci_hi=0.1, p_all=0.7, p_all_min=0.7, p_profit=0.9, hit_rate=0.3,
                implied=0.27, edge_pts=0.03, by_season={"2024": 0.05, "2025": 0.05}, profitable_95_all=True, replications={"passed": 1, "total": 1})
    assert cur.grade(base, "shape") == "teach"
    assert cur.grade(dict(base, by_season={"2023": -0.2, "2024": 0.1, "2025": 0.1}, p_all=0.0, p_all_min=0.0), "shape") == "fragile"
    assert cur.grade(dict(base, roi=-0.3, ci_lo=-0.4, ci_hi=-0.2, p_all=0.0, p_all_min=0.0, p_profit=0.0), "shape") == "avoid"
    assert cur.grade(dict(base, ci_lo=-0.02, p_all=0.4, p_all_min=0.4, by_season={"2024": 0.1, "2025": -0.01}), "shape") == "watch"
    assert cur.grade(dict(base, ci_lo=-0.02, p_all=0.1, p_all_min=0.1, by_season={"2024": 0.1, "2025": -0.01}), "shape") is None
    assert cur.grade(base, "n_legs") == "benchmark"


def test_release_series_records_the_correction():
    cur.ingest_study_dict(_study((2024, 2025), {"2024": 0.08, "2025": 0.02}, 0.7))
    r1 = cur.cut_release(trigger="t")
    assert r1["released"] and r1["release"] == "R001" and r1["summary"]["teach"] == 1
    assert cur.cut_release()["released"] is False                       # nothing changed, no new release
    cur.ingest_study_dict(_study((2023, 2024, 2025), {"2023": -0.2, "2024": 0.08, "2025": 0.02}, 0.0))
    assert [r["study_id"] for r in cur.current_rows()] == ["st_u20_n150_s100_y2023-2024-2025"]      # the 3-season study replaces the 2-season one
    r2 = cur.cut_release(trigger="t")
    assert r2["release"] == "R002" and r2["summary"]["teach"] == 0 and r2["summary"]["fragile"] == 1 and r2["changes"]["demoted"] == 1
    rel = cur.get("R002")
    assert rel["previous"] == "R001" and rel["superseded"]
    assert cur.notes("R002").startswith("# MY BOO training curriculum")
    rows = [json.loads(l) for l in cur.training_rows("R002").splitlines()]
    assert rows and all(r["schema"] == cur.LESSON_SCHEMA and r["release"] == "R002" for r in rows)
    sft = [json.loads(l) for l in tr.curriculum_sft("R002").splitlines()]
    assert sft and sft[0]["messages"][0]["role"] == "system"
    assert cur.prior_for_shape("total:over x2")["action"] == "distrust"


def test_harvest_collects_everything_once_and_queues_unsent_mirrors():
    sim.simulate(2024, 30, 5)
    rid = sim.run_id(2024, 30, 5, None)
    a = h.harvest_run(rid)
    assert a["ok"] and a["legs"] > 0 and a["bettors"] == 30 and a["crowd_keys"] > 0
    assert h.harvest_run(rid).get("skipped") is True                     # idempotent
    st = h.status()
    assert st["collected"]["runs"] == 1 and st["collected"]["betters"] == 30 and st["pending_mirror"] == 1
    sim.simulate(2025, 30, 5)                                            # written but not yet in the ledger
    got = h.backfill()
    assert got["runs"] == 1 and h.status()["collected"]["runs"] == 2
    ok = []
    h._mirror = lambda kind, ident, path, remote: ok.append(ident) or True
    assert h.retry_pending() == 2 and len(ok) == 2


def test_cycle_collects_runs_study_and_blocks_overlap():
    r = h.cycle("test", universes=1, bettors=30, study_universes=2)
    assert r["ok"] and r["study"] and r["collected"]["runs"] >= 1
    s = h.status()
    assert s["cycles"] == 1 and s["collected"]["studies"] == 1 and s["collected"]["runs"] == 3 and s["crowd_keys"] > 0
    assert cur.latest() is not None                                      # the study fed the curriculum automatically
    assert h.state()["next_seed"] == h.FIRST_SEED + 1
    assert h._CYCLE_LOCK.acquire(blocking=False)
    try:
        assert h.cycle("again")["ok"] is False
    finally:
        h._CYCLE_LOCK.release()


def test_trainer_is_honest_about_promotion():
    df = tr.build_dataset(seasons=(2024, 2025), max_week=6)
    assert len(df) > 2000 and df["hit"].isin([0, 1]).all() and df["p_novig"].between(0, 1).all()
    out = tr.train(df, cycle=1)
    assert out["trained"] and len(out["folds"]) == 2 and isinstance(out["promoted"], bool)
    assert {"held_out_season", "brier_gain", "top_edge_roi"} <= set(out["folds"][0])
    assert tr.registry()["latest"] == "v001" and tr.status()["caveat"]
    assert tr.maybe_train(2) is None                                      # not due again for several cycles
    one = df[df["season"] == 2024]
    assert tr.train(one)["trained"] is False                              # one season cannot be evaluated out of sample
