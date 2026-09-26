"""
Build IB 2.0 (IRRITABLE BOWEL 2.0) for the current NFL slate.

What changed from IB 1.0, and why (evidence: scripts/ib_deep_dive.py, 2023-2025,
60.5k dropbacks, weights set on 2023-24 and checked on 2025 untouched):
  * true pressure rate replaces sack counts -- pressure is ~2x more stable week to week
  * pressure WITH FOUR rushers is its own ingredient -- those defenses held offenses
    19 yds under their own passing average in 2025; blitz-heavy defenses held them to 0
  * blitz rate is shown but NOT rewarded -- it is a coaching choice, not a result
  * INT-worthy throws forced (FTN) replace raw interceptions -- raw INTs barely repeat
  * it is a MATCHUP: the defense's pressure against this offense's protection

Outputs (lake/gold/nfl/):
  ib2_bucket_rates.csv      2023-2025 outcomes per IB 2.0 matchup score 1-5 (the calibration)
  ib2_matchups_current.csv  every side of every unplayed game this week, scored 1-5 with components

In-season caveat: nflverse publishes pressure/participation after the season, so the
current-season part uses a play-by-play proxy (sack | QB hit | scramble, rescaled to
pressure). The proxy tracks true team pressure at r=0.72 (2023-2025 team seasons).

Run from the repo root:
    backend/.venv/bin/python scripts/build_ib2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_deep_dive as dd  # noqa: E402

GOLD = dd.GOLD
CURRENT = 2026
HIST = (2023, 2024, 2025)


def weights_raw(g: pd.DataFrame, wk: pd.Series) -> pd.DataFrame:
    z = dd.zscore
    g["ib2_raw"] = (1.0 * z(g.pre_pressure_rate, wk) + 0.8 * z(g.pre_pressure4_rate, wk)
                    + 0.6 * z(g.pre_int_worthy_rate, wk) - 0.8 * z(g.pre_epa_per_db, wk))
    g["ib2_matchup_raw"] = g.ib2_raw + 1.2 * z(g.pre_off_pressure_allowed, wk) + 0.6 * z(g.pre_off_int_worthy, wk)
    return g


def main() -> None:
    hist = dd.load_dropbacks(HIST)
    _, games = dd.section_c(hist)
    cuts = np.quantile(games.ib2_matchup_raw, [0.2, 0.4, 0.6, 0.8]).tolist()

    # Calibration table: what actually happened at each score, all three seasons
    games["p_int"] = (games.interception >= 1).astype(int)
    games["sacks3"] = (games.sack >= 3).astype(int)
    cal = games.groupby("ib2_matchup").agg(
        games=("pass_yds", "size"),
        pass_yds_vs_lines=("pass_yds_vs_lines", "mean"),
        pass_under_lines_rate=("pass_yds_vs_lines", lambda x: (x < 0).mean()),
        pass_under_own_avg_rate=("pass_under", "mean"),
        sacks_per_game=("sack", "mean"), sacks_vs_lines=("sacks_vs_lines", "mean"),
        sacks_3plus_rate=("sacks3", "mean"),
        ints_per_game=("interception", "mean"), qb_int_1plus_rate=("p_int", "mean"),
        pressure_rate=("actual_pressure_rate", "mean"),
    ).round(4).reset_index().rename(columns={"ib2_matchup": "ib2_score"})
    cal.to_csv(GOLD / "ib2_bucket_rates.csv", index=False)

    # ── current season: pbp proxy, 2025 true-pressure prior ─────────────────
    cur = dd.load_dropbacks((CURRENT,))
    proxy = ((cur.sack == 1) | (cur.qb_hit == 1) | (cur.qb_scramble == 1)).astype(float)
    h25 = hist[hist.season == 2025]
    h25_proxy = ((h25.sack == 1) | (h25.qb_hit == 1) | (h25.qb_scramble == 1)).mean()
    scale = h25.pressure.mean() / h25_proxy
    p4_share = (h25.groupby("defteam").pressure4.sum() / h25.groupby("defteam").pressure.sum()).to_dict()
    league_p4 = h25.pressure4.sum() / h25.pressure.sum()
    iw_per_int = hist.int_worthy.sum() / hist.interception.sum()
    cur["pressure"] = proxy * scale
    cur["pressure4"] = cur.pressure * cur.defteam.map(p4_share).fillna(league_p4)
    cur["rushers"] = 4  # every current-season dropback counts toward the pressure-with-four denominator
    cur["int_worthy"] = cur.interception * iw_per_int
    cur["blitz"] = np.nan

    both = pd.concat([h25, cur], ignore_index=True)
    dg = dd.defense_games(both)

    # One placeholder row per upcoming game side so pregame() reports "everything played so far"
    sched = pd.read_csv(GOLD / "schedule.csv")
    up = sched[sched.home_score.isna() & (sched.season == CURRENT)]
    wk = int(up.week.min())
    up = up[up.week == wk]
    ph = []
    for _, r in up.iterrows():
        for off, de, home in [(r.away_team, r.home_team, r.home_team), (r.home_team, r.away_team, r.home_team)]:
            ph.append({"season": CURRENT, "week": wk, "game_id": r.game_id, "defteam": de, "posteam": off,
                       "home_team": home, "spread_line": r.spread_line, "total_line": r.total_line, "games": 0,
                       **{c: 0 for c in ["db", "att", "rush4_db", "pressure", "pressure4", "blitz", "sack",
                                         "hit_or_sack", "int_worthy", "interception", "epa", "pass_yds", "pass_td",
                                         "points"]}})
    dg = pd.concat([dg, pd.DataFrame(ph)], ignore_index=True).sort_values(["defteam", "season", "week"])
    pre = dd.pregame(dg, "defteam", dd.DEF_STATS)
    off = dd.pregame(dg.rename(columns={"defteam": "_d", "posteam": "offteam"}), "offteam",
                     {"off_pass_yds": ("pass_yds", "games"), "off_pressure_allowed": ("pressure", "db"),
                      "off_int_worthy": ("int_worthy", "att"), "off_sack_allowed": ("sack", "db")})
    pre = pre.merge(off[["game_id", "offteam", "pre_off_pass_yds", "pre_off_pressure_allowed", "pre_off_int_worthy",
                         "pre_off_sack_allowed"]].rename(columns={"offteam": "posteam"}), on=["game_id", "posteam"])
    slate = pre[(pre.season == CURRENT) & (pre.week == wk) & (pre.db == 0)].copy()
    slate = weights_raw(slate, pd.Series("x", index=slate.index))
    slate["ib2_score"] = np.digitize(slate.ib2_matchup_raw, cuts) + 1
    slate["defense_only_score"] = np.digitize(slate.ib2_raw, np.quantile(games.ib2_raw, [0.2, 0.4, 0.6, 0.8])) + 1
    blitz25 = h25.groupby("defteam").blitz.mean()
    slate["blitz_rate_2025"] = slate.defteam.map(blitz25)
    slate = slate.merge(cal, on="ib2_score", how="left")

    out = slate[["season", "week", "game_id", "defteam", "posteam", "ib2_score", "defense_only_score",
                 "ib2_matchup_raw", "ib2_raw", "pre_pressure_rate", "pre_pressure4_rate", "blitz_rate_2025",
                 "pre_int_worthy_rate", "pre_epa_per_db", "pre_off_pressure_allowed", "pre_off_int_worthy",
                 "pre_off_pass_yds", "pass_yds_vs_lines", "pass_under_lines_rate", "sacks_per_game",
                 "sacks_3plus_rate", "qb_int_1plus_rate"]].round(4)
    out.sort_values("ib2_matchup_raw", ascending=False).to_csv(GOLD / "ib2_matchups_current.csv", index=False)
    (GOLD / "ib2_meta.json").write_text(json.dumps({
        "cuts_matchup_raw": cuts, "proxy_scale": round(float(scale), 4), "week": wk,
        "calibration_seasons": list(HIST), "current_season_source": "play-by-play proxy (sack|hit|scramble)",
    }, indent=1))
    print(cal.to_string(index=False))
    print(out[["defteam", "posteam", "ib2_score", "ib2_matchup_raw", "pre_pressure_rate", "pre_off_pressure_allowed",
               "qb_int_1plus_rate"]].sort_values("ib2_matchup_raw", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
