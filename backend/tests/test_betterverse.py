import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import betterverse_data as md
import betterverse_rules as rules
import betterverse_sim as sim


def _leg(market, side="over", game="G1", team="KC", player_id="", dec=1.87):
    return dict(market=market, side=side, game_id=game, team=team, player_id=player_id, player=player_id,
                line=1.5, dec=dec, hit=1, actual=2, pop=0.5, mid=f"{market}{side}{player_id}{game}{team}")


def test_rules_block_illegal_combos():
    assert not rules.validate([_leg("spread", "fav"), _leg("ml", "fav")])[0]
    assert not rules.validate([_leg("total", "over"), _leg("total", "under")])[0]
    assert not rules.validate([_leg("rec_yds", "over", player_id="p1"), _leg("rec_yds", "under", player_id="p1")])[0]
    assert not rules.validate([_leg("rush_yds", player_id="p1"), _leg("rush_rec_yds", player_id="p1")])[0]
    assert not rules.validate([_leg("spread", game=f"G{i}") for i in range(11)])[0]
    assert rules.validate([_leg("spread", game="G1"), _leg("spread", game="G2"), _leg("rec_yds", player_id="p1")])[0]


def test_sgp_haircut_applies_to_correlated_legs():
    cross, sgp = rules.price([_leg("pass_yds", player_id="qb", game="G1"), _leg("rec_yds", player_id="wr", game="G2")])
    assert not sgp
    stack, sgp = rules.price([_leg("pass_yds", player_id="qb"), _leg("rec_yds", player_id="wr")])
    assert sgp and stack < cross


def test_no_lookahead_in_prop_lines():
    for item in [i for i in md.menu(2024, 6) if i["player_id"]][:200]:
        rows = md._prior_rows(2024, item["player_id"], 6, 8)
        later = [g for (p, w), g in md.stats(2024)["games"].items() if p == item["player_id"] and w >= 6]
        assert not any(r is g for r in rows for g in later)


def test_deterministic_and_vig_sane():
    a = sim.simulate(2024, 60, 11)
    b = sim.simulate(2024, 60, 11)
    assert a["archetypes"] == b["archetypes"] and a["totals"] == b["totals"]
    assert 0.0 < a["totals"]["house_hold"] < 0.5        # the book wins overall, like real life


def test_roster_has_usernames_tiers_and_rules():
    import betterverse_bettors as mb
    r = mb.roster(150, 7)
    assert len({b.username for b in r}) == 150
    assert {b.tier for b in r} == {"sharp", "grinder", "casual", "degen"}
    assert all(b.rules and b.bio for b in r)
    sharp = [b for b in r if b.tier == "sharp"]
    assert all(b.chase == 1.0 and b.learns and b.legs_hi <= 3 for b in sharp)
    assert mb.roster(150, 7)[5].username == r[5].username          # same people every time


def test_sharps_never_use_the_week_they_bet():
    tables = sim._edge_tables(2024, md.weeks(2024))
    assert tables[1] == {}                                          # week 1 of the first season: nothing learned yet
    assert len(tables[2]) <= len(tables[10])


def test_leaderboard_ranks_by_proof_and_flags_provisional():
    ins = sim.simulate(2024, 60, 11)
    ranked = [r for r in ins["leaderboard"] if r["proof"] is not None]
    assert ranked and all(ranked[i]["proof"] >= ranked[i + 1]["proof"] for i in range(len(ranked) - 1))
    assert all(r["slips"] >= sim.MIN_PROOF_SLIPS for r in ranked)
