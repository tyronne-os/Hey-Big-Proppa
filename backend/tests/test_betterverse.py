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
    first = sim._edge_tables(2023, md.weeks(2023))
    assert first[1] == {}                                           # first season, first week: nothing learned yet
    assert len(first[2]) <= len(first[10])                          # evidence only grows as weeks are played
    assert sim._edge_tables(2024, md.weeks(2024))[1]                # 2024 starts with what 2023 taught

def test_leaderboard_ranks_real_winnings_unfiltered():
    ins = sim.simulate(2024, 60, 11)
    lb = ins["leaderboard"]
    assert len(lb) == 60                                            # nobody is hidden or re-weighted
    assert all(lb[i]["final_bankroll"] >= lb[i + 1]["final_bankroll"] for i in range(len(lb) - 1))
    assert "unit" in lb[0] and lb[0]["unit"] in (5, 10)


def test_table_limits_5_10_then_20_then_free():
    import betterverse_bettors as mb
    b = mb.roster(30, 3)[0]
    assert mb.stake_for(b, 100) in (5.0, 10.0)
    assert mb.stake_for(b, 499.99, 3.0) <= 10.0                     # chasing can't break the $10 cap
    assert mb.stake_for(b, 500) <= 20.0 and mb.stake_for(b, 999, 3.0) <= 20.0
    assert mb.stake_for(b, 5000) > 20.0                             # over $1,000 they bet freely
    _, _, _, slips, _ = sim._run(2024, 60, 11, None, keep_legs=False)
    low, mid = slips[slips["bankroll_before"] < 500], slips[(slips["bankroll_before"] >= 500) & (slips["bankroll_before"] < 1000)]
    assert low["stake"].max() <= 10.0 and (mid.empty or mid["stake"].max() <= 20.0)


def test_study_pools_universes_and_is_repeatable():
    import betterverse_study as st
    a, b = st.run_study(2, 40, 3), st.run_study(2, 40, 3)
    assert a["bettor_seasons"] == 2 * 3 * 40
    assert [r["roi"] for r in a["dims"]["tier"]] == [r["roi"] for r in b["dims"]["tier"]]
    row = a["dims"]["style_tier"][0]
    assert row["ci_lo"] <= row["roi"] <= row["ci_hi"] and set(row["by_season"]) == {"2023", "2024", "2025"}
    assert a["rookie_winners"] and all(w["tier_label"] in ("Casual", "Degen") for w in a["rookie_winners"])


def test_career_pools_two_seasons_with_same_betters():
    sim.simulate(2024, 40, 21)
    sim.simulate(2025, 40, 21)
    c = sim.career([sim.run_id(2024, 40, 21, None), sim.run_id(2025, 40, 21, None)])
    assert c and len(c["leaderboard"]) == 40 and c["leaderboard"][0]["unit"] in (5, 10)
    assert len(c["leaderboard"][0]["by_season"]) == 2


def test_obsidian_vault_links_resolve_and_graph_is_colored():
    import io
    import json
    import re
    import zipfile
    import betterverse_obsidian as ob
    import betterverse_study as st
    study = st.run_study(2, 40, 3)
    notes = ob.build(study)
    assert "00 Home.md" in notes and ".obsidian/graph.json" in notes
    have = {p[:-3] for p in notes if p.endswith(".md")}
    missing = []
    for path, text in notes.items():
        for target in re.findall(r"\[\[([^\]|\\]+)\\?(?:\|[^\]]*)?\]\]", text):
            if target not in have:
                missing.append((path, target))
    assert not missing, missing[:5]
    assert all(not re.search(r'[\\:*?"<>|#^\[\]]', p.split("/")[-1]) for p in notes)
    graph = json.loads(notes[".obsidian/graph.json"])
    assert {g["query"] for g in graph["colorGroups"]} >= {"tag:#tier/sharp", "tag:#proven", "tag:#loser"}
    assert "```mermaid" in notes["00 Home.md"] and "xychart-beta" in notes["00 Home.md"]
    assert any(p.startswith("Strategies/") for p in notes) and any(p.startswith("Betters/") for p in notes)
    assert "tag:#top5" in {g["query"] for g in graph["colorGroups"]}
    rank = notes["Rankings/Parlay Shape Ranking.md"]
    assert "quadrantChart" in rank and "every tested season" in rank and "Rankings/Top Parlays.md" in notes
    assert any("top5" in t.splitlines()[2] for p, t in notes.items() if p.startswith("Shapes/"))
    for path, text in notes.items():                                   # alias pipes inside table rows must be escaped
        for line in text.splitlines():
            if line.startswith("|"):
                assert not re.search(r"\[\[[^\]]*[^\\]\|[^\]]*\]\]", line), (path, line[:80])
    z = zipfile.ZipFile(io.BytesIO(ob.zip_bytes(study)))
    assert f"{ob.ROOT}/00 Home.md" in z.namelist()


def test_study_compare_two_vs_three_seasons():
    import betterverse_study as st
    two = st.run_study(2, 40, 3, None, (2024, 2025))
    three = st.run_study(2, 40, 3)
    assert two["study_id"].endswith("_y2024-2025") and three["study_id"].endswith("_y2023-2024-2025")
    st._write = lambda *a, **k: None                       # not persisting here; compare reads through load()
    import json
    st.load = lambda sid: two if sid == two["study_id"] else three
    c = st.compare(two["study_id"], three["study_id"])
    assert set(c["shape_tally"]) == {"held", "dropped", "rose", "never-promising"} and c["dims"]["shape"]
