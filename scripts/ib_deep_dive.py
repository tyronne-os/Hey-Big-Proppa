"""
IB 2.0 deep dive -- what actually rattles a QB, 2023-2025, play by play.

Joins nflverse play_by_play + pbp_participation (was_pressure, pass rushers,
time_to_throw, coverage) + FTN charting (blitzers, interception-worthy throws,
QB out of pocket). Raw files live in lake/bronze/nflverse/ (gitignored).

Sections
  A  play level: which conditions produce interceptions / INT-worthy throws
  B  rattle carryover: does being hit earlier make a QB worse later, with the
     current play's pressure held fixed
  C  defense level: pre-game IB 1.0 (sacks/INTs/points, the original formula)
     vs IB 2.0 (true pressure, 4-man pressure, blitz, INT-worthy forced) --
     which one predicts the opponent's passing game, trained 2023-24,
     scored on 2025 untouched
  D  in-game: first-half pressure as a live signal for the second half
  E  receivers: where the targets go when the pocket collapses

Run from the repo root:
    backend/.venv/bin/python scripts/ib_deep_dive.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parent.parent
BRONZE = REPO / "lake" / "bronze" / "nflverse"
GOLD = REPO / "lake" / "gold" / "nfl"
SEASONS = (2023, 2024, 2025)
TRAIN, TEST = (2023, 2024), 2025
PRIOR_DB = 150  # dropbacks of prior-season weight before a defense's own games take over

PBP_COLS = [
    "game_id", "play_id", "season", "week", "season_type", "posteam", "defteam", "home_team",
    "passer_player_id", "passer_player_name", "receiver_player_id", "receiver_player_name",
    "qb_dropback", "pass_attempt", "sack", "qb_hit", "qb_scramble", "qb_spike", "qb_kneel", "interception",
    "complete_pass", "passing_yards", "receiving_yards", "air_yards", "down", "ydstogo", "yardline_100", "qtr",
    "game_half", "score_differential", "half_seconds_remaining", "wp", "shotgun", "no_huddle",
    "epa", "cpoe", "two_point_attempt", "spread_line", "total_line", "fumble_lost", "pass_touchdown",
]


# ── load ─────────────────────────────────────────────────────────────────────

PART_COLS = ["was_pressure", "number_of_pass_rushers", "time_to_throw", "defense_coverage_type",
             "defense_man_zone_type", "defenders_in_box"]
FTN_COLS = ["n_blitzers", "ftn_rushers", "is_interception_worthy", "is_qb_out_of_pocket", "is_play_action",
            "is_screen_pass", "is_throw_away", "is_qb_fault_sack"]


def load_dropbacks(seasons=SEASONS) -> pd.DataFrame:
    """Participation / FTN files are optional per season (in-season years may only have play-by-play)."""
    frames = []
    for s in seasons:
        pbp = pd.read_csv(BRONZE / f"play_by_play_{s}.csv.gz", usecols=PBP_COLS, low_memory=False)
        pbp = pbp[(pbp.season_type == "REG") & (pbp.qb_dropback == 1) & (pbp.two_point_attempt.fillna(0) == 0)
                  & (pbp.qb_spike.fillna(0) == 0) & (pbp.qb_kneel.fillna(0) == 0)]
        df = pbp
        if (BRONZE / f"pbp_participation_{s}.csv").exists():
            part = pd.read_csv(BRONZE / f"pbp_participation_{s}.csv", low_memory=False,
                               usecols=["nflverse_game_id", "play_id"] + PART_COLS)
            df = df.merge(part.rename(columns={"nflverse_game_id": "game_id"}), on=["game_id", "play_id"], how="left")
        if (BRONZE / f"ftn_charting_{s}.csv").exists():
            ftn = pd.read_csv(BRONZE / f"ftn_charting_{s}.csv", low_memory=False,
                              usecols=["nflverse_game_id", "nflverse_play_id", "n_blitzers", "n_pass_rushers",
                                       "is_interception_worthy", "is_qb_out_of_pocket", "is_play_action",
                                       "is_screen_pass", "is_throw_away", "is_qb_fault_sack"])
            ftn = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id",
                                      "n_pass_rushers": "ftn_rushers"})
            df = df.merge(ftn, on=["game_id", "play_id"], how="left")
        frames.append(df.reindex(columns=list(df.columns) + [c for c in PART_COLS + FTN_COLS if c not in df.columns]))
    df = pd.concat(frames, ignore_index=True)

    for c in ["was_pressure", "is_interception_worthy", "is_qb_out_of_pocket", "is_play_action",
              "is_screen_pass", "is_throw_away", "is_qb_fault_sack"]:
        df[c] = df[c].map({True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0}).astype("float")
    df["rushers"] = df["number_of_pass_rushers"].fillna(df["ftn_rushers"])
    df["blitz"] = (df["n_blitzers"].fillna(0) > 0).astype(int)
    df["pressure"] = df["was_pressure"].fillna(((df.sack == 1) | (df.qb_hit == 1)).astype(float))
    df["pressure4"] = ((df.pressure == 1) & (df.rushers <= 4)).astype(int)  # pressure without sending extra men
    df["hit_or_sack"] = ((df.sack == 1) | (df.qb_hit == 1)).astype(int)
    df["int_worthy"] = df["is_interception_worthy"].fillna(df["interception"])
    df["pass_yds"] = df["passing_yards"].fillna(0)
    return df


# ── A: conditions behind interceptions ───────────────────────────────────────

def rate_table(df: pd.DataFrame, col: str, label: str) -> list[dict]:
    g = df.groupby(col, observed=True).agg(dropbacks=("interception", "size"), ints=("interception", "sum"),
                                           int_worthy=("int_worthy", "sum"), sacks=("sack", "sum"),
                                           epa=("epa", "mean"))
    base = df.interception.mean()
    out = []
    for k, r in g.iterrows():
        if r.dropbacks < 300:
            continue
        out.append({"factor": label, "bucket": str(k), "dropbacks": int(r.dropbacks),
                    "int_rate": round(r.ints / r.dropbacks, 4), "int_worthy_rate": round(r.int_worthy / r.dropbacks, 4),
                    "sack_rate": round(r.sacks / r.dropbacks, 4), "epa_per_db": round(r.epa, 3),
                    "int_lift": round((r.ints / r.dropbacks) / base, 2)})
    return out


def section_a(df: pd.DataFrame) -> dict:
    d = df.copy()
    d["pressure_b"] = d.pressure.map({1.0: "PRESSURED", 0.0: "CLEAN"})
    d["blitzers_b"] = pd.cut(d.n_blitzers, [-1, 0, 1, 2, 20], labels=["0", "1", "2", "3+"])
    d["ttt_b"] = pd.cut(d.time_to_throw, [0, 2.0, 2.5, 3.0, 3.5, 20], labels=["<2.0s", "2.0-2.5s", "2.5-3.0s", "3.0-3.5s", "3.5s+"])
    d["down_dist"] = np.select(
        [d.down == 3, d.down == 4, d.ydstogo >= 10],
        [np.where(d.ydstogo >= 7, "3rd & 7+", "3rd & <7"), "4th down", "1st/2nd & 10+"], "1st/2nd & <10")
    d["game_state"] = np.select(
        [(d.qtr >= 4) & (d.score_differential <= -8), (d.qtr >= 4) & (d.score_differential < 0),
         d.score_differential >= 8, d.score_differential <= -8],
        ["4Q trailing 9+", "4Q trailing 1-8", "leading 8+", "trailing 8+ (Q1-3)"], "within one score")
    d["coverage"] = d.defense_coverage_type.where(d.defense_coverage_type.isin(
        ["COVER_0", "COVER_1", "COVER_2", "COVER_3", "COVER_4", "COVER_6", "2_MAN", "COVER_9"]))
    d["pocket"] = d.is_qb_out_of_pocket.map({1.0: "OUT OF POCKET", 0.0: "IN POCKET"})
    d["pa"] = d.is_play_action.map({1.0: "PLAY ACTION", 0.0: "STRAIGHT DROPBACK"})

    table = []
    for col, label in [("pressure_b", "pressure"), ("blitzers_b", "blitzers"), ("ttt_b", "time_to_throw"),
                       ("down_dist", "down_distance"), ("game_state", "game_state"), ("coverage", "coverage"),
                       ("pocket", "pocket"), ("pa", "play_action")]:
        table += rate_table(d, col, label)

    # Pressure x game state: the "desperate and hunted" combination
    combo = d.assign(combo=d.pressure_b + " · " + d.game_state)
    table += rate_table(combo, "combo", "pressure_x_state")

    # Logistic model on INT-worthy throws (less noisy than INTs: drops and lucky picks wash out)
    att = d[d.pass_attempt == 1].copy()
    feats = pd.DataFrame({
        "pressure": att.pressure.fillna(0),
        "blitzers": att.n_blitzers.fillna(0).clip(0, 4),
        "rushers5plus": (att.rushers >= 5).astype(int),
        "out_of_pocket": att.is_qb_out_of_pocket.fillna(0),
        "play_action": att.is_play_action.fillna(0),
        "third_long": ((att.down == 3) & (att.ydstogo >= 7)).astype(int),
        "trailing_4q": ((att.qtr >= 4) & (att.score_differential < 0)).astype(int),
        "wp_low": (att.wp < 0.2).astype(int),
        "air_yards_15plus": (att.air_yards >= 15).astype(int),
        "cover_0_1": att.defense_coverage_type.isin(["COVER_0", "COVER_1"]).astype(int),
        "cover_2_4_6": att.defense_coverage_type.isin(["COVER_2", "COVER_4", "COVER_6", "2_MAN"]).astype(int),
    })
    y = att.int_worthy.fillna(0).astype(int)
    tr, te = att.season.isin(TRAIN), att.season == TEST
    m = LogisticRegression(max_iter=2000).fit(feats[tr], y[tr])
    p = m.predict_proba(feats[te])[:, 1]
    q = pd.qcut(p, 10, labels=False, duplicates="drop")
    top, bot = y[te].values[q == q.max()].mean(), y[te].values[q == q.min()].mean()
    return {
        "table": table,
        "odds_ratios": {f: round(float(np.exp(c)), 2) for f, c in zip(feats.columns, m.coef_[0])},
        "auc_2025": round(float(roc_auc_score(y[te], p)), 3),
        "top_decile_rate": round(float(top), 4), "bottom_decile_rate": round(float(bot), 4),
        "base_rate": round(float(y[te].mean()), 4),
    }


# ── B: rattle carryover ──────────────────────────────────────────────────────

def section_b(df: pd.DataFrame) -> dict:
    d = df.sort_values(["game_id", "play_id"]).copy()
    grp = d.groupby(["game_id", "passer_player_id"], sort=False)
    d["prior_hits"] = grp.hit_or_sack.cumsum() - d.hit_or_sack
    d["prior_db"] = grp.cumcount()
    d["hit_last_db"] = grp.hit_or_sack.shift(1).fillna(0)
    d["prior_hit_rate"] = d.prior_hits / d.prior_db.replace(0, np.nan)
    att = d[(d.pass_attempt == 1) & (d.prior_db >= 8)].copy()
    att["rattled"] = pd.cut(att.prior_hit_rate, [-0.01, 0.08, 0.16, 0.25, 1.0],
                            labels=["0-8% hit so far", "8-16%", "16-25%", "25%+ hit so far"])

    def summarize(frame):
        return {"attempts": int(len(frame)), "int_worthy_rate": round(float(frame.int_worthy.mean()), 4),
                "int_rate": round(float(frame.interception.mean()), 4),
                "ttt": round(float(frame.time_to_throw.mean()), 2), "epa": round(float(frame.epa.mean()), 3),
                "cpoe": round(float(frame.cpoe.mean()), 2)}

    # Only CLEAN pockets: if the QB still misfires with nobody on him, that is the rattle
    clean = att[att.pressure == 0]
    by_rattle = {str(k): summarize(g) for k, g in clean.groupby("rattled", observed=True)}
    after_hit = {"clean pocket, hit on previous dropback": summarize(clean[clean.hit_last_db == 1]),
                 "clean pocket, not hit on previous dropback": summarize(clean[clean.hit_last_db == 0])}

    X = pd.DataFrame({"prior_hit_rate": att.prior_hit_rate.fillna(0), "pressure_now": att.pressure.fillna(0),
                      "third_long": ((att.down == 3) & (att.ydstogo >= 7)).astype(int),
                      "trailing": (att.score_differential < 0).astype(int), "qtr": att.qtr})
    m = LogisticRegression(max_iter=2000).fit(X, att.int_worthy.fillna(0).astype(int))

    # Within-game test: same QB, same game, same defense -- clean-pocket throws right after a hit vs the rest.
    # Demeaning by QB-game removes defense quality, weather, game plan and QB talent.
    c = clean.assign(qg=clean.game_id + clean.passer_player_id)
    c = c[c.groupby("qg").hit_last_db.transform("nunique") == 2]
    fe = {}
    for col in ["int_worthy", "epa", "cpoe"]:
        y = c[col] - c.groupby("qg")[col].transform("mean")
        x = c.hit_last_db - c.groupby("qg").hit_last_db.transform("mean")
        ok = y.notna()
        beta = float((x[ok] * y[ok]).sum() / (x[ok] ** 2).sum())
        resid = y[ok] - beta * x[ok]
        se = float(np.sqrt((resid ** 2).sum() / (ok.sum() - 1) / (x[ok] ** 2).sum()))
        fe[col] = {"effect_after_hit": round(beta, 4), "se": round(se, 4), "t": round(beta / se, 2)}
    return {"within_game_after_hit_clean_pocket": fe, "within_game_n": int(len(c)),
            "clean_pocket_by_prior_hit_rate": by_rattle, "clean_pocket_after_hit": after_hit,
            "odds_ratio_per_+10pct_prior_hit_rate": round(float(np.exp(m.coef_[0][0] * 0.10)), 3),
            "odds_ratio_pressure_now": round(float(np.exp(m.coef_[0][1])), 2)}


# ── C: defense IB 1.0 vs IB 2.0, pre-game, predicting the opponent's passing game ──

DEF_STATS = {  # name -> (numerator column, denominator column)
    "pressure_rate": ("pressure", "db"),
    "pressure4_rate": ("pressure4", "rush4_db"),
    "blitz_rate": ("blitz", "db"),
    "sack_rate": ("sack", "db"),
    "hit_rate": ("hit_or_sack", "db"),
    "int_worthy_rate": ("int_worthy", "att"),
    "int_rate": ("interception", "att"),
    "epa_per_db": ("epa", "db"),
    "pass_yds_per_game": ("pass_yds", "games"),
    "points_allowed": ("points", "games"),
}


def defense_games(df: pd.DataFrame) -> pd.DataFrame:
    d = df.assign(att=df.pass_attempt, db=1, rush4_db=(df.rushers <= 4).astype(int))
    g = d.groupby(["season", "week", "game_id", "defteam", "posteam"]).agg(
        db=("db", "sum"), att=("att", "sum"), rush4_db=("rush4_db", "sum"), pressure=("pressure", "sum"),
        pressure4=("pressure4", "sum"), blitz=("blitz", "sum"), sack=("sack", "sum"), hit_or_sack=("hit_or_sack", "sum"),
        int_worthy=("int_worthy", "sum"), interception=("interception", "sum"), epa=("epa", "sum"),
        pass_yds=("pass_yds", "sum"), pass_td=("pass_touchdown", "sum"), spread_line=("spread_line", "first"),
        total_line=("total_line", "first"), home_team=("home_team", "first"),
    ).reset_index()
    g["games"] = 1
    # points allowed from team_game_stats (already in the lake)
    tgs = pd.read_csv(GOLD / "team_game_stats.csv")[["game_id", "team", "points_against"]]
    g = g.merge(tgs.rename(columns={"team": "defteam", "points_against": "points"}), on=["game_id", "defteam"], how="left")
    g["points"] = g.points.fillna(g.points.mean())
    return g.sort_values(["defteam", "season", "week"]).reset_index(drop=True)


def pregame(g: pd.DataFrame, key: str, stats: dict) -> pd.DataFrame:
    """Each row gets the team's rate from games BEFORE this one, shrunk toward last season (or league mean)."""
    out = g.copy()
    cols = {c for pair in stats.values() for c in pair}
    season_tot = g.groupby([key, "season"])[list(cols)].sum()
    league = {name: g[n].sum() / g[dn].sum() for name, (n, dn) in stats.items()}
    grp = out.groupby([key, "season"], sort=False)
    for name, (n, dn) in stats.items():
        cum_n = grp[n].cumsum() - out[n]
        cum_d = grp[dn].cumsum() - out[dn]
        prev = [season_tot.loc[(t, s - 1)] if (t, s - 1) in season_tot.index else None
                for t, s in zip(out[key], out.season)]
        prior = np.array([p[n] / p[dn] if p is not None and p[dn] else league[name] for p in prev])
        prior = 0.67 * prior + 0.33 * league[name]  # regress last season a third of the way to the mean
        w = PRIOR_DB if dn in ("db", "att", "rush4_db") else 4  # 4 games of prior weight for per-game stats
        out[f"pre_{name}"] = (cum_n + prior * w) / (cum_d + w)
    return out


def zscore(s: pd.Series, by: pd.Series) -> pd.Series:
    return s.groupby(by).transform(lambda x: (x - x.mean()) / (x.std() or 1))


def section_c(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    g = pregame(defense_games(df), "defteam", DEF_STATS)
    # offense side: this offense's own pre-game passing level and pressure allowed
    off = g.rename(columns={"defteam": "_d", "posteam": "offteam"})
    off = pregame(off, "offteam", {"off_pass_yds": ("pass_yds", "games"), "off_pressure_allowed": ("pressure", "db"),
                                   "off_int_worthy": ("int_worthy", "att"), "off_sack_allowed": ("sack", "db")})
    g = g.merge(off[["game_id", "offteam", "pre_off_pass_yds", "pre_off_pressure_allowed", "pre_off_int_worthy",
                     "pre_off_sack_allowed"]].rename(columns={"offteam": "posteam"}), on=["game_id", "posteam"])
    wk = g.season.astype(str) + "-" + g.week.astype(str)

    # IB 1.0 -- the original lake formula's ingredients: sacks, interceptions, points allowed
    g["ib1_raw"] = zscore(g.pre_sack_rate, wk) + zscore(g.pre_int_rate, wk) - zscore(g.pre_points_allowed, wk)
    # IB 2.0 -- true pressure, pressure with four, INT-worthy forced, EPA allowed; blitz is NOT rewarded on its own
    g["ib2_raw"] = (1.0 * zscore(g.pre_pressure_rate, wk) + 0.8 * zscore(g.pre_pressure4_rate, wk)
                    + 0.6 * zscore(g.pre_int_worthy_rate, wk) - 0.8 * zscore(g.pre_epa_per_db, wk))
    # MATCHUP -- the defense's pressure against this offense's protection
    g["exp_pressure"] = g.pre_pressure_rate * g.pre_off_pressure_allowed / (g.pressure.sum() / g.db.sum())
    g["ib2_matchup_raw"] = g.ib2_raw + 1.2 * zscore(g.pre_off_pressure_allowed, wk) + 0.6 * zscore(g.pre_off_int_worthy, wk)
    for c in ["ib1", "ib2", "ib2_matchup"]:
        g[c] = pd.qcut(g[f"{c}_raw"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

    g["team_spread"] = np.where(g.posteam == g.home_team, g.spread_line, -g.spread_line)  # + = offense favored
    g["pass_under"] = (g.pass_yds < g.pre_off_pass_yds).astype(int)
    g["actual_pressure_rate"] = g.pressure / g.db

    test = g[g.season == TEST]
    buckets = {}
    for c in ["ib1", "ib2", "ib2_matchup"]:
        t = test.groupby(c).agg(games=("pass_yds", "size"), pass_yds=("pass_yds", "mean"),
                                vs_own_avg=("pass_yds", lambda x: 0), under_rate=("pass_under", "mean"),
                                ints=("interception", "mean"), sacks=("sack", "mean"),
                                pressure=("actual_pressure_rate", "mean"))
        t["vs_own_avg"] = test.groupby(c).apply(lambda x: (x.pass_yds - x.pre_off_pass_yds).mean(), include_groups=False)
        buckets[c] = [{"score": int(k), **{kk: round(float(v), 3) for kk, v in r.items()}} for k, r in t.iterrows()]

    # Incremental value beyond the offense's own level and the Vegas lines
    base = ["pre_off_pass_yds", "team_spread", "total_line"]
    tr, te = g.season.isin(TRAIN), g.season == TEST
    def r2(cols, target):
        mdl = LinearRegression().fit(g.loc[tr, cols].fillna(0), g.loc[tr, target])
        pred = mdl.predict(g.loc[te, cols].fillna(0))
        resid = g.loc[te, target] - pred
        return round(float(1 - (resid ** 2).sum() / ((g.loc[te, target] - g.loc[te, target].mean()) ** 2).sum()), 4), mdl
    incr = {}
    for target in ["pass_yds", "interception", "sack", "int_worthy"]:
        b, _ = r2(base, target)
        v1, _ = r2(base + ["ib1_raw"], target)
        v2, _ = r2(base + ["ib2_raw"], target)
        vm, m = r2(base + ["ib2_matchup_raw"], target)
        incr[target] = {"lines_only": b, "plus_ib1": v1, "plus_ib2": v2, "plus_ib2_matchup": vm,
                        "yds_per_1sd_ib2_matchup": round(float(m.coef_[-1]), 2) if target == "pass_yds" else None}

    # Does the pre-game rate predict the in-game pressure? (stability of each ingredient)
    stab = {n: round(float(test[f"pre_{n}"].corr(test[a] / test[b])), 3)
            for n, (a, b) in DEF_STATS.items() if b in ("db", "att", "rush4_db")}
    stab["exp_pressure(matchup)"] = round(float(test.exp_pressure.corr(test.actual_pressure_rate)), 3)

    # Blitz-heavy vs pressure-with-four defenses: two different animals
    test = test.assign(style=np.select([(test.pre_blitz_rate > test.pre_blitz_rate.quantile(0.67)),
                                        (test.pre_pressure4_rate > test.pre_pressure4_rate.quantile(0.67))],
                                       ["BLITZ-HEAVY", "PRESSURE WITH FOUR"], "OTHER"))
    style = test.groupby("style").agg(games=("pass_yds", "size"), pass_yds_vs_own=("pass_yds", "mean"),
                                      ints=("interception", "mean"), pass_td=("pass_td", "mean"),
                                      epa=("epa", "sum")).reset_index()
    style["pass_yds_vs_own"] = test.groupby("style").apply(lambda x: (x.pass_yds - x.pre_off_pass_yds).mean(),
                                                          include_groups=False).values
    style["epa"] = test.groupby("style").apply(lambda x: x.epa.sum() / x.db.sum(), include_groups=False).values

    # Is it already in the lines? Residual after the lines-only model, by IB 2.0 matchup quintile.
    _, lm = r2(base, "pass_yds")
    # Residuals are centered within each season so a league-wide scoring shift doesn't read as an IB effect.
    g["pass_yds_vs_lines"] = g.pass_yds - lm.predict(g[base].fillna(0))
    g["pass_yds_vs_lines"] -= g.groupby("season").pass_yds_vs_lines.transform("median")
    _, sm = r2(base, "sack")
    g["sacks_vs_lines"] = g.sack - sm.predict(g[base].fillna(0))
    g["sacks_vs_lines"] -= g.groupby("season").sacks_vs_lines.transform("mean")
    vs_lines = {}
    for season_set, label in [((TEST,), "2025_holdout"), (SEASONS, "2023_2025_all")]:
        sub = g[g.season.isin(season_set)]
        vs_lines[label] = sub.groupby("ib2_matchup").agg(
            games=("pass_yds", "size"), pass_yds_vs_lines=("pass_yds_vs_lines", "mean"),
            under_lines_rate=("pass_yds_vs_lines", lambda x: (x < 0).mean()),
            sacks_vs_lines=("sacks_vs_lines", "mean"), sacks=("sack", "mean"), ints=("interception", "mean"),
            dropbacks=("db", "mean")).round(3).reset_index().to_dict("records")
    return {"buckets_2025": buckets, "incremental_r2_2025": incr, "pregame_to_ingame_corr_2025": stab,
            "style_2025": style.round(3).to_dict("records"), "vs_lines": vs_lines}, g


# ── D: first-half pressure as a live second-half signal ──────────────────────

def section_d(df: pd.DataFrame) -> dict:
    d = df[df.qtr <= 4]
    h = d.groupby(["game_id", "posteam", "game_half"]).agg(db=("pressure", "size"), score=("score_differential", "last"),
                                                          pressure=("pressure", "mean"),
                                                          hits=("hit_or_sack", "mean"), iw=("int_worthy", "sum"),
                                                          ints=("interception", "sum"), yds=("pass_yds", "sum"),
                                                          epa=("epa", "mean")).reset_index()
    h1 = h[h.game_half == "Half1"].set_index(["game_id", "posteam"])
    h2 = h[h.game_half == "Half2"].set_index(["game_id", "posteam"])
    j = h1.join(h2, lsuffix="_1h", rsuffix="_2h", how="inner")
    j = j[(j.db_1h >= 12) & (j.db_2h >= 8)]
    j["bucket"] = pd.qcut(j.hits_1h, 4, labels=["low 1H hits", "mid-low", "mid-high", "high 1H hits"])
    t = j.groupby("bucket", observed=True).agg(games=("db_2h", "size"), hit_rate_1h=("hits_1h", "mean"),
                                               pressure_2h=("pressure_2h", "mean"), iw_per_100_2h=("iw_2h", "sum"),
                                               ints_2h=("ints_2h", "mean"), epa_2h=("epa_2h", "mean"))
    t["iw_per_100_2h"] = j.groupby("bucket", observed=True).apply(lambda x: 100 * x.iw_2h.sum() / x.db_2h.sum()).values
    t["pass_yds_2h"] = j.groupby("bucket", observed=True).yds_2h.mean().values
    t["dropbacks_2h"] = j.groupby("bucket", observed=True).db_2h.mean().values
    t["halftime_score_diff"] = j.groupby("bucket", observed=True).score_1h.mean().values
    # Same comparison among games within one score at the half -- strips out "trailing teams throw more"
    close = j[j.score_1h.abs() <= 8]
    tc = close.groupby("bucket", observed=True).agg(games=("db_2h", "size"), epa_2h=("epa_2h", "mean"),
                                                    pass_yds_2h=("yds_2h", "mean"), ints_2h=("ints_2h", "mean"))
    return {"by_first_half_hits": [{"bucket": str(k), **{kk: round(float(v), 3) for kk, v in r.items()}}
                                   for k, r in t.iterrows()],
            "close_at_half": [{"bucket": str(k), **{kk: round(float(v), 3) for kk, v in r.items()}}
                              for k, r in tc.iterrows()],
            "corr_1h_hits_2h_epa": round(float(j.hits_1h.corr(j.epa_2h)), 3),
            "corr_1h_pressure_2h_pressure": round(float(j.pressure_1h.corr(j.pressure_2h)), 3)}


# ── E: receivers under a collapsing pocket ───────────────────────────────────

def section_e(df: pd.DataFrame, games: pd.DataFrame) -> dict:
    att = df[(df.pass_attempt == 1) & df.receiver_player_id.notna()].copy()
    att = att.merge(games[["game_id", "posteam", "ib2_matchup"]], on=["game_id", "posteam"], how="left")
    att["depth"] = pd.cut(att.air_yards, [-99, 0, 9, 19, 99], labels=["behind LOS", "short 1-9", "intermediate 10-19", "deep 20+"])
    mix = att.groupby(["ib2_matchup", "depth"], observed=True).size().unstack(fill_value=0)
    mix = mix.div(mix.sum(axis=1), axis=0).round(3)
    adot = att.groupby("ib2_matchup").air_yards.mean().round(2)

    # Receiver game lines vs each receiver's own pre-game average (prior games that season)
    rg = att.groupby(["season", "week", "game_id", "posteam", "receiver_player_id"]).agg(
        tgt=("pass_attempt", "sum"), rec=("complete_pass", "sum"), yds=("receiving_yards", "sum"),
        adot=("air_yards", "mean"), ib=("ib2_matchup", "first")).reset_index()
    rg["yds"] = rg.yds.fillna(0)
    rg = rg.sort_values(["receiver_player_id", "season", "week"])
    grp = rg.groupby(["receiver_player_id", "season"])
    for c in ["rec", "yds", "tgt", "adot"]:
        rg[f"pre_{c}"] = (grp[c].cumsum() - rg[c]) / grp.cumcount().replace(0, np.nan)
    rg["n_prior"] = grp.cumcount()
    rg = rg[rg.n_prior >= 3]
    primary = rg[rg.pre_yds >= 50]                       # WR1/TE1-type volume receivers
    checkdown = rg[(rg.pre_adot < 4) & (rg.pre_tgt >= 3)]  # RBs/TEs living behind or near the line
    def by_ib(frame, stat):
        t = frame.groupby("ib").apply(lambda x: pd.Series({
            "players": len(x), "avg_vs_own": (x[stat] - x[f"pre_{stat}"]).mean(),
            "under_own_rate": (x[stat] < x[f"pre_{stat}"]).mean()}), include_groups=False)
        return [{"ib2_matchup": int(k), **{kk: round(float(v), 3) for kk, v in r.items()}} for k, r in t.iterrows()]
    return {"target_depth_mix_by_ib2_matchup": {int(k): v for k, v in mix.to_dict("index").items()},
            "adot_by_ib2_matchup": {int(k): float(v) for k, v in adot.items()},
            "primary_receiver_yds": by_ib(primary, "yds"),
            "checkdown_receptions": by_ib(checkdown, "rec")}


# ── F: QB pressure profile -- is the QB's reaction to pressure a stable trait? ──

def section_f(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    d = df[df.passer_player_id.notna()]
    rows = []
    for (pid, s), x in d.groupby(["passer_player_id", "season"]):
        if len(x) < 200:
            continue
        pr, cl = x[x.pressure == 1], x[x.pressure == 0]
        rows.append({"passer_player_id": pid, "season": s, "name": x.passer_player_name.mode().iat[0],
                     "team": x.posteam.mode().iat[0], "dropbacks": len(x),
                     "pressure_rate_faced": x.pressure.mean(),
                     "pressure_to_sack": pr.sack.mean(),
                     "epa_clean": cl.epa.mean(), "epa_pressured": pr.epa.mean(),
                     "pressure_epa_drop": cl.epa.mean() - pr.epa.mean(),
                     "int_worthy_clean": cl.int_worthy.mean(), "int_worthy_pressured": pr.int_worthy.mean(),
                     "ttt": x.time_to_throw.mean(), "hold_3s_rate": (x.time_to_throw >= 3).mean(),
                     "out_of_pocket_rate": x.is_qb_out_of_pocket.mean(), "int_worthy_rate": x.int_worthy.mean()})
    q = pd.DataFrame(rows)
    nxt = q.merge(q.assign(season=q.season - 1), on=["passer_player_id", "season"], suffixes=("", "_next"))
    stab = {c: round(float(nxt[c].corr(nxt[f"{c}_next"])), 3)
            for c in ["pressure_rate_faced", "pressure_to_sack", "pressure_epa_drop", "epa_clean", "epa_pressured",
                      "int_worthy_clean", "int_worthy_pressured", "ttt", "hold_3s_rate", "int_worthy_rate"]}
    return {"year_over_year_corr": stab, "qb_pairs": int(len(nxt))}, q


def main() -> None:
    df = load_dropbacks()
    print(f"dropbacks {len(df):,}  pressure coverage {df.was_pressure.notna().mean():.1%}  "
          f"FTN coverage {df.is_interception_worthy.notna().mean():.1%}")
    a = section_a(df)
    b = section_b(df)
    c, games = section_c(df)
    d = section_d(df)
    e = section_e(df, games)
    f, qb = section_f(df)
    qb.round(4).to_csv(GOLD / "ib2_qb_pressure_profile.csv", index=False)

    # 2026 proxy check: can pbp-only (sack/hit/scramble) stand in for true pressure at the team level?
    proxy = df.assign(proxy=((df.sack == 1) | (df.qb_hit == 1) | (df.qb_scramble == 1)).astype(int)) \
              .groupby(["season", "defteam"]).agg(p=("pressure", "mean"), x=("proxy", "mean"))
    c["proxy_team_corr"] = round(float(proxy.p.corr(proxy.x)), 3)

    summary = {"A_int_conditions": a, "B_rattle": b, "C_defense": c, "D_in_game": d, "E_receivers": e, "F_qb": f,
               "n_dropbacks": int(len(df)), "n_int": int(df.interception.sum()),
               "n_int_worthy": int(df.int_worthy.sum())}
    GOLD.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(a["table"]).to_csv(GOLD / "ib2_int_conditions.csv", index=False)
    keep = ["season", "week", "game_id", "defteam", "posteam", "db", "pressure", "sack", "interception", "int_worthy",
            "pass_yds", "pre_off_pass_yds", "pre_pressure_rate", "pre_pressure4_rate", "pre_blitz_rate",
            "pre_int_worthy_rate", "pre_epa_per_db", "pre_off_pressure_allowed", "exp_pressure",
            "ib1", "ib2", "ib2_matchup", "ib2_raw", "ib2_matchup_raw"]
    games[keep].round(4).to_csv(GOLD / "ib2_defense_game_backtest.csv", index=False)
    (REPO / "lake" / "gold" / "nfl" / "ib2_deep_dive_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "A_int_conditions"}, indent=1, default=str)[:12000])
    print(json.dumps({k: v for k, v in a.items() if k != "table"}, indent=1))


if __name__ == "__main__":
    main()
