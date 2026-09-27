"""
CFB JIMMY — College football game intelligence. v2 (SP+ / PPA / Elo / Talent upgrade)

Signal stack per game:
  Layer 1 — Recent results   : avg pts scored/allowed/margin (last 3-5 games)
  Layer 2 — SP+ ratings      : Bill Connelly offense/defense ratings (best CFB model)
  Layer 3 — PPA efficiency   : Per-play Expected Points Added (offense + defense)
  Layer 4 — Explosiveness    : Big-play rate (drives outcomes beyond avg pts)
  Layer 5 — Havoc rate       : Defensive disruption (TFLs, sacks, pass breakups)
  Layer 6 — Elo              : Quality-of-opponent-adjusted win history
  Layer 7 — Talent composite : Recruiting depth differential
  Layer 8 — Pregame WP       : SP+-calibrated model win probability

Over/under projection formula (upgraded):
  proj_total = 0.35 * scored_signal
             + 0.35 * ppa_signal
             + 0.20 * explosiveness_signal
             + 0.10 * field_position_bonus
  Where:
    scored_signal      = avg(fav_scored + dog_scored, fav_allowed + dog_allowed)
    ppa_signal         = calibrated from combined PPA → expected pts per drive
    explosiveness_signal = big-play adjustment (+/- pts if explosiveness > baseline)
    field_position_bonus = points added when avg start > 65% field

HOT DOG qualifier (upgraded from 3 metrics to 8-signal composite):
  Classic metrics (3): avg_scored, avg_allowed, avg_margin
  New metrics  (5):  SP+ delta, PPA delta, Elo delta, Talent delta, Havoc delta
  Dog must win >= 4 of 8 (was 2 of 3) for certification.
  Signal-weighted composite score 0-10 added for sorting.

HEURISTIC. NOT BACKTESTED. Same lake discipline as everything else here.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

from zoneinfo import ZoneInfo

_CST = ZoneInfo("America/Chicago")  # New Orleans: Central time, daylight saving handled


def _to_cst(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_CST).strftime("%-I:%M %p CT")
    except Exception:
        return ""


import bpl
import cfb_data


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_GAMES          = 2     # need at least this many completed games
MIN_METRICS_WON    = 4     # of 8 total signals (was 2 of 3)
PPA_TO_PTS_FACTOR  = 38.0  # empirical: avg drives per game × pts-per-drive scale
ELO_BASELINE       = 1500.0
TALENT_BASELINE    = 850.0  # avg FBS talent composite
HAVOC_BASELINE     = 0.13   # ~avg FBS havoc rate
EXPL_BASELINE      = 1.20   # avg CFB explosiveness


# ---------------------------------------------------------------------------
# Recent-results performance (Layer 1)
# ---------------------------------------------------------------------------

def _perf(games: list[dict]) -> dict | None:
    if len(games) < MIN_GAMES:
        return None
    scored  = [g["points_for"]     for g in games]
    allowed = [g["points_against"] for g in games]
    margin  = [g["points_for"] - g["points_against"] for g in games]
    wins    = sum(g["win"] for g in games)
    return {
        "avg_scored":  round(sum(scored)  / len(scored),  1),
        "avg_allowed": round(sum(allowed) / len(allowed), 1),
        "avg_margin":  round(sum(margin)  / len(margin),  1),
        "wins":        wins,
        "games":       len(games),
        "win_pct":     round(wins / len(games), 3),
    }


# ---------------------------------------------------------------------------
# 8-signal comparison (dog vs fav)
# ---------------------------------------------------------------------------

_SIGNALS = [
    # (key, label, weight, higher_is_better_for_dog)
    ("avg_scored",      "Avg pts scored",    1.0,  True),
    ("avg_allowed",     "Avg pts allowed",   1.0,  False),
    ("avg_margin",      "Avg margin",        1.0,  True),
    ("sp_overall",      "SP+ overall",       1.5,  True),
    ("ppa_net",         "PPA net",           1.5,  True),
    ("elo",             "Elo rating",        1.0,  True),
    ("talent",          "Talent composite",  0.75, True),
    ("def_havoc",       "Def havoc rate",    0.75, True),
]


def _build_signal_row(team: str, perf: dict | None,
                      adv: dict, sp: dict, elos: dict, talent: dict) -> dict:
    """Gather all 8 signal values for one team into a flat dict."""
    sp_entry  = sp.get(team, {})
    adv_entry = adv.get(team, {})
    row = {
        "avg_scored":  perf["avg_scored"]  if perf else None,
        "avg_allowed": perf["avg_allowed"] if perf else None,
        "avg_margin":  perf["avg_margin"]  if perf else None,
        "sp_overall":  sp_entry.get("overall"),
        "ppa_net":     _safe_sub(adv_entry.get("off_ppa"), adv_entry.get("def_ppa")),
        "elo":         elos.get(team),
        "talent":      talent.get(team),
        "def_havoc":   adv_entry.get("def_havoc"),
        # extras for over engine
        "off_ppa":            adv_entry.get("off_ppa"),
        "def_ppa":            adv_entry.get("def_ppa"),
        "off_explosiveness":  adv_entry.get("off_explosiveness"),
        "def_explosiveness":  adv_entry.get("def_explosiveness"),
        "sp_offense_rating":  sp_entry.get("offense_rating"),
        "sp_defense_rating":  sp_entry.get("defense_rating"),
        "sp_offense_rank":    sp_entry.get("offense_rank"),
        "sp_defense_rank":    sp_entry.get("defense_rank"),
    }
    return row


def _compare_signals(dog_row: dict, fav_row: dict) -> tuple[list[dict], int, float]:
    """
    Compare dog vs fav on all 8 signals.
    Returns (detail_rows, signals_dog_won, composite_score_0_to_10).
    """
    rows  = []
    won   = 0
    total_weight = sum(w for _, _, w, _ in _SIGNALS)
    weighted_won = 0.0

    for key, label, weight, dog_higher_wins in _SIGNALS:
        dog_val = dog_row.get(key)
        fav_val = fav_row.get(key)
        if dog_val is None or fav_val is None:
            rows.append({"key": key, "label": label, "dog": dog_val,
                         "fav": fav_val, "dogWins": None, "weight": weight})
            continue
        # for avg_allowed lower is better → flip direction
        diff = (dog_val - fav_val) if dog_higher_wins else (fav_val - dog_val)
        dog_wins = diff > 0
        if dog_wins:
            won += 1
            weighted_won += weight
        rows.append({
            "key":     key,
            "label":   label,
            "dog":     round(dog_val, 3) if isinstance(dog_val, float) else dog_val,
            "fav":     round(fav_val, 3) if isinstance(fav_val, float) else fav_val,
            "dogWins": dog_wins,
            "weight":  weight,
        })

    composite = round((weighted_won / total_weight) * 10, 2)
    return rows, won, composite


def _safe_sub(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 4)


# ---------------------------------------------------------------------------
# Over/Under projection (upgraded 4-layer formula)
# ---------------------------------------------------------------------------

def _project_total(fav_row: dict, dog_row: dict,
                   fav_perf: dict | None, dog_perf: dict | None) -> dict:
    """
    Multi-signal total projection.
    Returns dict with proj_total and component breakdown.
    """
    components: dict[str, float | None] = {}

    # Layer 1: scored/allowed averages
    if fav_perf and dog_perf:
        off_signal = fav_perf["avg_scored"] + dog_perf["avg_scored"]
        def_signal = fav_perf["avg_allowed"] + dog_perf["avg_allowed"]
        scored_signal = round((off_signal + def_signal) / 2, 1)
    else:
        scored_signal = None
    components["scored_signal"] = scored_signal

    # Layer 2: PPA-based projection
    fav_off = fav_row.get("off_ppa")
    fav_def = fav_row.get("def_ppa")
    dog_off = dog_row.get("off_ppa")
    dog_def = dog_row.get("def_ppa")
    if all(v is not None for v in (fav_off, fav_def, dog_off, dog_def)):
        # offense PPA projected into points: PPA × drives_factor
        # defense PPA is negative when holding → opponent scores less
        fav_pts_proj = (fav_off - dog_def) * PPA_TO_PTS_FACTOR  # what fav scores
        dog_pts_proj = (dog_off - fav_def) * PPA_TO_PTS_FACTOR  # what dog scores
        ppa_signal = round(max(fav_pts_proj, 0) + max(dog_pts_proj, 0), 1)
    else:
        ppa_signal = None
    components["ppa_signal"] = ppa_signal

    # Layer 3: explosiveness bonus/penalty
    fav_expl = fav_row.get("off_explosiveness")
    dog_expl = dog_row.get("off_explosiveness")
    if fav_expl and dog_expl:
        avg_expl = (fav_expl + dog_expl) / 2
        # each 0.1 above baseline ≈ +1.5 pts to total
        expl_bonus = round((avg_expl - EXPL_BASELINE) * 15.0, 1)
    else:
        expl_bonus = 0.0
    components["expl_bonus"] = expl_bonus

    # Layer 4: SP+ offense-driven total adjustment
    fav_sp_off = fav_row.get("sp_offense_rating")
    dog_sp_off = dog_row.get("sp_offense_rating")
    fav_sp_def = fav_row.get("sp_defense_rating")
    dog_sp_def = dog_row.get("sp_defense_rating")
    if all(v is not None for v in (fav_sp_off, dog_sp_off, fav_sp_def, dog_sp_def)):
        # SP+ offense rating scale: higher = more pts; defense rating: higher = fewer pts allowed
        # fav_sp_def suppresses dog scoring; dog_sp_def suppresses fav scoring
        sp_total_proxy = ((fav_sp_off - dog_sp_def) + (dog_sp_off - fav_sp_def)) * 0.55
        # scale factor empirically maps SP+ differential to pts
        sp_signal = round(sp_total_proxy + 45.0, 1)  # anchor at ~45 pts average CFB total
    else:
        sp_signal = None
    components["sp_signal"] = sp_signal

    # Blend: weight by signal availability
    signals = []
    weights = []
    if scored_signal:
        signals.append(scored_signal); weights.append(0.30)
    if ppa_signal:
        signals.append(ppa_signal + expl_bonus); weights.append(0.40)
    if sp_signal:
        signals.append(sp_signal); weights.append(0.30)

    if not signals:
        return {"proj_total": None, **components}

    total_w = sum(weights)
    proj = sum(s * w for s, w in zip(signals, weights)) / total_w
    return {"proj_total": round(proj, 1), **components}


def _over_prob(proj_total: float, total_line: float, std: float = 8.5) -> float:
    """Normal-CDF probability that combined score exceeds total_line."""
    if total_line <= 0:
        return 0.5
    z = (proj_total - total_line) / std
    return round(0.5 * (1 + math.erf(z / math.sqrt(2))), 3)


# ---------------------------------------------------------------------------
# Total direction for Hot Dog parlay leg
# ---------------------------------------------------------------------------

def _total_direction(dog_row: dict, fav_row: dict,
                     dog_perf: dict | None, fav_perf: dict | None) -> str:
    proj = _project_total(fav_row, dog_row, fav_perf, dog_perf)
    if proj["proj_total"] and proj["proj_total"] > 0:
        # if projected total is above average we lean over; below → under
        return "over" if proj["proj_total"] > 46.0 else "under"
    # fallback to simple avg
    if fav_perf and dog_perf:
        combined_avg = (fav_perf["avg_scored"] + dog_perf["avg_scored"]) / 2
        combined_def = (fav_perf["avg_allowed"] + dog_perf["avg_allowed"]) / 2
        return "over" if combined_avg > 28 and combined_def > 25 else "under"
    return "under"


# ---------------------------------------------------------------------------
# Slate (same as before — top-25 game list with lines)
# ---------------------------------------------------------------------------

def cfb_game_slate() -> list[dict]:
    """
    This week's FBS games where the favorite is AP top 25.
    Augmented with SP+, Elo, pregame WP for each game.
    """
    games    = cfb_data.current_week_games()
    lines    = cfb_data.current_week_lines()
    rankings = cfb_data.ap_poll()
    sp       = cfb_data.sp_ratings()
    elos     = cfb_data.elo_ratings()
    wp_map   = cfb_data.pregame_wp()

    if not games:
        return []

    time_map = {raw.get("id"): (raw.get("startDate") or "") for raw in games}

    out = []
    for g in games:
        gid  = g.get("id")
        home = g.get("homeTeam", "")
        away = g.get("awayTeam", "")
        line = lines.get(gid)
        if not line:
            continue

        home_rank = rankings.get(home)
        away_rank = rankings.get(away)

        home_ml = line.get("home_moneyline")
        away_ml = line.get("away_moneyline")
        try:
            hml = float(home_ml) if home_ml else None
            aml = float(away_ml) if away_ml else None
        except (TypeError, ValueError):
            hml, aml = None, None

        if hml is not None and aml is not None:
            home_fav = _ml_to_prob(hml) > 0.5
        elif home_rank and not away_rank:
            home_fav = True
        elif away_rank and not home_rank:
            home_fav = False
        else:
            continue

        fav_team = home if home_fav else away
        dog_team = away if home_fav else home
        fav_rank = home_rank if home_fav else away_rank

        if not fav_rank:
            continue

        spread  = line["spread"]
        total   = line["over_under"]
        dog_ml  = aml if home_fav else hml
        fav_ml  = hml if home_fav else aml
        dog_ats = f"+{abs(spread):.1f}" if not home_fav else f"+{spread:.1f}"

        wp_entry   = wp_map.get(gid, {})
        home_wp    = wp_entry.get("home_wp")
        fav_wp     = home_wp if home_fav else (1 - home_wp if home_wp else None)
        fav_sp     = (sp.get(fav_team) or {})
        dog_sp     = (sp.get(dog_team) or {})
        fav_elo    = elos.get(fav_team)
        dog_elo    = elos.get(dog_team)

        raw_start = time_map.get(gid, "")
        out.append({
            "gameId":          gid,
            "week":            g.get("week"),
            "home":            home,
            "away":            away,
            "homeRank":        home_rank,
            "awayRank":        away_rank,
            "favorite":        fav_team,
            "favRank":         fav_rank,
            "underdog":        dog_team,
            "dogRank":         (away_rank if home_fav else home_rank),
            "spread":          spread,
            "dogAts":          dog_ats,
            "total":           total,
            "dogMl":           dog_ml,
            "favMl":           fav_ml,
            "provider":        line["provider"],
            "startDate":       raw_start[:10],
            "gameTime":        _to_cst(raw_start),
            "startIso":        raw_start,
            "favWp":           round(fav_wp, 3) if fav_wp is not None else None,
            "favSpOverall":    fav_sp.get("overall"),
            "dogSpOverall":    dog_sp.get("overall"),
            "favElo":          fav_elo,
            "dogElo":          dog_elo,
        })

    return sorted(out, key=lambda g: (g["favRank"] or 99))


# ---------------------------------------------------------------------------
# Hot Dogs — upset alerts with 8-signal composite
# ---------------------------------------------------------------------------

def cfb_hot_dogs() -> list[dict]:
    """
    2-leg upset alert parlays: Dog ML + Total direction.
    Now requires dog to win >= 4 of 8 signals (weighted composite).
    """
    slate  = cfb_game_slate()
    adv    = cfb_data.advanced_stats()
    sp     = cfb_data.sp_ratings()
    elos   = cfb_data.elo_ratings()
    talent = cfb_data.talent_composite()

    dogs = []
    for g in slate:
        dog = g["underdog"]
        fav = g["favorite"]

        dog_games = cfb_data.team_recent_games(dog, 5)
        fav_games = cfb_data.team_recent_games(fav, 5)
        dog_perf  = _perf(dog_games)
        fav_perf  = _perf(fav_games)

        dog_row = _build_signal_row(dog, dog_perf, adv, sp, elos, talent)
        fav_row = _build_signal_row(fav, fav_perf, adv, sp, elos, talent)

        stats, metrics_won, composite = _compare_signals(dog_row, fav_row)
        certified = metrics_won >= MIN_METRICS_WON

        total_dir  = _total_direction(dog_row, fav_row, dog_perf, fav_perf)
        total_odds = g.get("totalOverOdds" if total_dir == "over" else "totalUnderOdds")

        game_time = g.get("gameTime", "")
        t = f" ({game_time})" if game_time else ""
        legs = [
            {
                "label":   f"TAKE {dog} ML{t}",
                "market":  "moneyline",
                "team":    dog,
                "odds":    g["dogMl"],
                "gameTime": game_time,
            },
            {
                "label":   f"TAKE {total_dir.upper()} {g['total']} · {fav} vs {dog}{t}",
                "market":  "total",
                "direction": total_dir,
                "line":    g["total"],
                "odds":    total_odds,
                "gameTime": game_time,
            },
        ]

        parlay_odds = _combine_ml([g["dogMl"], total_odds])

        dogs.append({
            "gameId":       g["gameId"],
            "week":         g["week"],
            "dog":          dog,
            "fav":          fav,
            "favRank":      g["favRank"],
            "dogRank":      g["dogRank"],
            "certified":    certified,
            "metricsWon":   metrics_won,
            "composite":    composite,
            "stats":        stats,
            "dogPerf":      dog_perf,
            "favPerf":      fav_perf,
            "dogSpOverall": g.get("dogSpOverall"),
            "favSpOverall": g.get("favSpOverall"),
            "dogElo":       g.get("dogElo"),
            "favElo":       g.get("favElo"),
            "favWp":        g.get("favWp"),
            "legs":         legs,
            "parlayOdds":   parlay_odds,
            "type":         "UPSET ALERT" if not g["dogRank"] else "RANKED DOG",
        })

    dogs.sort(key=lambda d: (not d["certified"], -d["composite"], d["favRank"] or 99))
    return dogs


# ---------------------------------------------------------------------------
# Over/Under engine (upgraded)
# ---------------------------------------------------------------------------

def cfb_big_money_overs(date_filter: str | None = None) -> list[dict]:
    """
    Games with highest probability of going OVER the total line.
    Uses 4-layer projection: scored averages + PPA + explosiveness + SP+.
    """
    slate  = cfb_game_slate()
    adv    = cfb_data.advanced_stats()
    sp     = cfb_data.sp_ratings()
    elos   = cfb_data.elo_ratings()
    talent = cfb_data.talent_composite()

    out = []
    for g in slate:
        if date_filter and g.get("startDate", "") != date_filter:
            continue
        if not g["total"] or g["total"] <= 0:
            continue

        fav_games = cfb_data.team_recent_games(g["favorite"], 5)
        dog_games = cfb_data.team_recent_games(g["underdog"], 5)
        fav_perf  = _perf(fav_games)
        dog_perf  = _perf(dog_games)

        fav_row = _build_signal_row(g["favorite"], fav_perf, adv, sp, elos, talent)
        dog_row = _build_signal_row(g["underdog"], dog_perf, adv, sp, elos, talent)

        proj = _project_total(fav_row, dog_row, fav_perf, dog_perf)
        if proj["proj_total"] is None:
            continue

        proj_total = proj["proj_total"]
        over_margin = round(proj_total - g["total"], 1)
        prob = _over_prob(proj_total, g["total"])

        # signal flags
        fav_expl = fav_row.get("off_explosiveness") or 0
        dog_expl = dog_row.get("off_explosiveness") or 0
        both_explosive = fav_expl > EXPL_BASELINE and dog_expl > EXPL_BASELINE

        fav_off_ppa = fav_row.get("off_ppa") or 0
        dog_off_ppa = dog_row.get("off_ppa") or 0
        both_ppa_positive = fav_off_ppa > 0.15 and dog_off_ppa > 0.15

        fav_sp_off_rank = fav_row.get("sp_offense_rank") or 200
        dog_sp_off_rank = dog_row.get("sp_offense_rank") or 200
        both_top50_offense = fav_sp_off_rank <= 50 and dog_sp_off_rank <= 50

        # legacy scored flags (kept for UI)
        fav_avg_scored  = fav_perf["avg_scored"]  if fav_perf else None
        dog_avg_scored  = dog_perf["avg_scored"]  if dog_perf else None
        fav_avg_allowed = fav_perf["avg_allowed"] if fav_perf else None
        dog_avg_allowed = dog_perf["avg_allowed"] if dog_perf else None

        grade = "A" if prob >= 0.68 else "B" if prob >= 0.58 else "C" if prob >= 0.50 else "D"

        official = bpl.cfb_game_total(g["home"], g["away"])
        bpl_total = official["bpl"] if official else None

        out.append({
            "gameId":            g["gameId"],
            "bplTotal":          bpl_total,
            "bplDiffPct":        bpl.diff_pct(bpl_total, g["total"]),
            "gameDate":          g.get("startDate", ""),
            "gameTime":          g.get("gameTime", ""),
            "fav":               g["favorite"],
            "favRank":           g["favRank"],
            "dog":               g["underdog"],
            "dogRank":           g["dogRank"],
            "totalLine":         g["total"],
            "projTotal":         proj_total,
            "overMargin":        over_margin,
            "overProb":          prob,
            "grade":             grade,
            # projection breakdown
            "scoredSignal":      proj.get("scored_signal"),
            "ppaSignal":         proj.get("ppa_signal"),
            "explBonus":         proj.get("expl_bonus"),
            "spSignal":          proj.get("sp_signal"),
            # signal flags
            "bothExplosive":     both_explosive,
            "bothPpaPositive":   both_ppa_positive,
            "bothTop50Offense":  both_top50_offense,
            # detail
            "favOffPpa":         round(fav_off_ppa, 3),
            "dogOffPpa":         round(dog_off_ppa, 3),
            "favOffExplosiveness": fav_expl,
            "dogOffExplosiveness": dog_expl,
            "favSpOffRank":      fav_sp_off_rank,
            "dogSpOffRank":      dog_sp_off_rank,
            # legacy
            "favAvgScored":      fav_avg_scored,
            "dogAvgScored":      dog_avg_scored,
            "favAvgAllowed":     fav_avg_allowed,
            "dogAvgAllowed":     dog_avg_allowed,
            "dogMl":             g["dogMl"],
            "spread":            g["spread"],
        })

    out.sort(key=lambda x: -x["overProb"])
    return out


# ---------------------------------------------------------------------------
# Lock cover dogs
# ---------------------------------------------------------------------------

LOCK_MAX_SPREAD = 18.0
LOCK_MAX_DOG_ML = 325
LOCK_MIN_METRICS = 4   # raised from 2 to 4 (8-signal system)


def cfb_lock_cover_dogs(date_filter: str | None = None) -> list[dict]:
    """
    Hot dogs that can cover AND win outright.
    Upgraded: composite score replaces metrics_won for sorting.
    """
    dogs      = cfb_hot_dogs()
    slate_map = {g["gameId"]: g for g in cfb_game_slate()}

    out = []
    for d in dogs:
        game_entry = slate_map.get(d["gameId"])
        if game_entry is None:
            continue
        game_date = game_entry.get("startDate", "")
        if date_filter and game_date != date_filter:
            continue

        raw_spread = abs(game_entry["spread"])
        dog_ml     = d["legs"][0]["odds"]

        if raw_spread > LOCK_MAX_SPREAD:
            continue
        if dog_ml is None or abs(dog_ml) > LOCK_MAX_DOG_ML:
            continue
        if d["metricsWon"] < LOCK_MIN_METRICS:
            continue
        if not d["dogPerf"] or d["dogPerf"]["wins"] == 0:
            continue

        dog_perf = d["dogPerf"]
        lock_score = (
            d["composite"] * 0.6
            + (LOCK_MAX_DOG_ML - abs(dog_ml)) / LOCK_MAX_DOG_ML * 2.0
            + (1 if raw_spread <= 10 else 0)
        )
        is_locked = (
            d["metricsWon"] >= 5
            and dog_perf["wins"] > dog_perf["games"] / 2
        )

        out.append({
            **d,
            "spread":    raw_spread,
            "gameDate":  game_date,
            "gameTime":  game_entry.get("gameTime", ""),
            "lockScore": round(lock_score, 2),
            "isLocked":  is_locked,
        })

    out.sort(key=lambda x: (-x["isLocked"], -x["lockScore"]))
    return out


# ---------------------------------------------------------------------------
# Big Money Parlays
# ---------------------------------------------------------------------------

def cfb_big_money_parlays(date_filter: str | None = None) -> list[dict]:
    overs = cfb_big_money_overs(date_filter)[:3]
    locks = cfb_lock_cover_dogs(date_filter)[:2]

    parlays = []

    def _over_leg(o: dict) -> dict:
        t = f" ({o['gameTime']})" if o.get("gameTime") else ""
        grade_tag = f"[{o['grade']}] " if o.get("grade") else ""
        return {"label": f"{grade_tag}TAKE OVER {o['totalLine']} · {o['fav']} vs {o['dog']}{t}",
                "odds": -110, "bet": "over", "gameTime": o.get("gameTime", "")}

    def _dog_ml_leg(lock: dict) -> dict:
        t = f" ({lock['gameTime']})" if lock.get("gameTime") else ""
        ml = lock["legs"][0]["odds"]
        return {"label": f"TAKE {lock['dog']} ML{t}",
                "odds": int(ml) if ml is not None else None,
                "bet": "dog_ml", "gameTime": lock.get("gameTime", "")}

    def _dog_ats_leg(lock: dict) -> dict:
        t = f" ({lock['gameTime']})" if lock.get("gameTime") else ""
        return {"label": f"TAKE {lock['dog']} +{lock['spread']} ATS{t}",
                "odds": -110, "bet": "dog_ats", "gameTime": lock.get("gameTime", "")}

    if len(overs) >= 2:
        o1, o2 = overs[0], overs[1]
        parlays.append({
            "type":       "DOUBLE OVER",
            "tag":        "SCORING FEAST",
            "legs":       [_over_leg(o1), _over_leg(o2)],
            "parlayOdds": _combine_ml([-110, -110]),
            "confidence": round(o1["overProb"] * o2["overProb"], 3),
            "reasoning":  (
                f"{o1['fav']} vs {o1['dog']} proj {o1['projTotal']} pts "
                f"(line {o1['totalLine']}, +{o1['overMargin']}, PPA {o1['ppaSignal']}) · "
                f"{o2['fav']} vs {o2['dog']} proj {o2['projTotal']} pts "
                f"(line {o2['totalLine']}, +{o2['overMargin']})"
            ),
        })

    if overs and locks:
        o1   = overs[0]
        lock = locks[0]
        ml   = lock["legs"][0]["odds"]
        if ml is not None:
            parlays.append({
                "type":       "UPSET SPECIAL",
                "tag":        "DOG + SCORING",
                "legs":       [_over_leg(o1), _dog_ml_leg(lock)],
                "parlayOdds": _combine_ml([-110, int(ml)]),
                "confidence": round(o1["overProb"] * (lock["composite"] / 10), 3),
                "reasoning":  (
                    f"OVER: {o1['fav']} vs {o1['dog']} proj {o1['projTotal']} pts · "
                    f"DOG: {lock['dog']} composite {lock['composite']}/10 "
                    f"vs #{lock['favRank']} {lock['fav']}"
                ),
            })

    if len(overs) >= 2 and locks:
        o1, o2 = overs[0], overs[1]
        lock   = locks[0]
        parlays.append({
            "type":       "HOT DOG TRIPLE",
            "tag":        "BIG MONEY",
            "legs":       [_over_leg(o1), _over_leg(o2), _dog_ats_leg(lock)],
            "parlayOdds": _combine_ml([-110, -110, -110]),
            "confidence": round(o1["overProb"] * o2["overProb"] * (lock["composite"] / 10), 3),
            "reasoning":  f"2x OVERs + {lock['dog']} cover vs #{lock['favRank']} {lock['fav']}",
        })

    if len(locks) >= 2:
        l1, l2 = locks[0], locks[1]
        ml1 = l1["legs"][0]["odds"]
        ml2 = l2["legs"][0]["odds"]
        if ml1 and ml2:
            parlays.append({
                "type":       "DOG FIGHT",
                "tag":        "BOTH DOGS WIN",
                "legs":       [_dog_ml_leg(l1), _dog_ml_leg(l2)],
                "parlayOdds": _combine_ml([ml1, ml2]),
                "confidence": round((l1["composite"] / 10) * (l2["composite"] / 10), 3),
                "reasoning":  (
                    f"{l1['dog']} composite {l1['composite']}/10 vs #{l1['favRank']} {l1['fav']} · "
                    f"{l2['dog']} composite {l2['composite']}/10 vs #{l2['favRank']} {l2['fav']}"
                ),
            })

    return parlays


# ---------------------------------------------------------------------------
# Crazy Horse
# ---------------------------------------------------------------------------

def cfb_crazy_horse(date_filter: str | None = None) -> list[dict]:
    """CRAZY HORSE — all >= 85% confidence picks grouped by day."""
    overs = cfb_big_money_overs(date_filter)
    locks = cfb_lock_cover_dogs(date_filter)

    CONF_THRESHOLD = 0.85

    def _day(iso_or_ymd: str) -> int:
        if not iso_or_ymd:
            return -1
        try:
            return datetime.fromisoformat(iso_or_ymd[:10]).weekday()
        except Exception:
            return -1

    all_legs: list[dict] = []

    for o in overs:
        if o["overProb"] < CONF_THRESHOLD:
            continue
        t = f" ({o['gameTime']})" if o.get("gameTime") else ""
        all_legs.append({
            "label":    f"TAKE OVER {o['totalLine']} · {o['fav']} vs {o['dog']}{t}",
            "odds":     -110,
            "bet":      "over",
            "gameDate": o.get("gameDate", ""),
            "gameTime": o.get("gameTime", ""),
            "day":      _day(o.get("gameDate", "")),
            "prob":     o["overProb"],
        })

    for l in locks:
        if not l.get("isLocked"):
            continue
        ml = l["legs"][0]["odds"]
        if ml is None:
            continue
        t = f" ({l['gameTime']})" if l.get("gameTime") else ""
        all_legs.append({
            "label":    f"TAKE {l['dog']} ML{t}",
            "odds":     int(ml),
            "bet":      "dog_ml",
            "gameDate": l.get("gameDate", ""),
            "gameTime": l.get("gameTime", ""),
            "day":      _day(l.get("gameDate", "")),
            "prob":     l["composite"] / 10,
        })

    sat_legs = [l for l in all_legs if l["day"] == 5]
    sun_legs = [l for l in all_legs if l["day"] == 6]

    out: list[dict] = []

    def _horse(horse_type: str, tag: str, legs: list[dict]) -> dict:
        conf = 1.0
        for l in legs:
            conf *= l["prob"]
        return {
            "type":       horse_type,
            "tag":        tag,
            "legs":       legs,
            "parlayOdds": _combine_ml([l["odds"] for l in legs]),
            "confidence": round(conf, 3),
            "wager":      5,
            "reasoning":  f"{len(legs)}-leg sweep of all >= 85% confidence picks.",
        }

    if len(sat_legs) >= 2:
        out.append(_horse("CRAZY HORSE SATURDAY", "SATURDAY SWEEP", sat_legs))
    if len(sun_legs) >= 2:
        out.append(_horse("CRAZY HORSE SUNDAY", "SUNDAY SWEEP", sun_legs))
    if sat_legs and sun_legs and len(sat_legs) + len(sun_legs) >= 3:
        out.append(_horse("SUPER CRAZY HORSE", "FULL WEEKEND SWEEP", sat_legs + sun_legs))

    return out


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def cfb_status() -> dict:
    available = cfb_data.available()
    week      = cfb_data.current_week() if available else None
    rankings  = cfb_data.ap_poll()      if available else {}
    games     = cfb_data.current_week_games() if available else []
    sp        = cfb_data.sp_ratings()   if available else {}
    adv       = cfb_data.advanced_stats() if available else {}
    elos      = cfb_data.elo_ratings()  if available else {}

    return {
        "available":      available,
        "apiKeyVar":      "CFBD_API_KEY",
        "season":         cfb_data._current_season() if available else None,
        "week":           week,
        "rankingsLoaded": len(rankings),
        "gamesOnSlate":   len(games),
        "top25Games":     len(cfb_game_slate()) if available else 0,
        "hotDogs":        len(cfb_hot_dogs())   if available else 0,
        "signalLayers":   {
            "sp_teams":   len(sp),
            "adv_teams":  len(adv),
            "elo_teams":  len(elos),
        },
    }


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _ml_to_prob(ml: float) -> float:
    if ml > 0:
        return 100 / (ml + 100)
    return -ml / (-ml + 100)


def _ml_to_decimal(ml: float | None) -> float | None:
    if ml is None:
        return None
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml > 0:
        return round(ml / 100 + 1, 3)
    return round(100 / (-ml) + 1, 3)


def _combine_ml(mls: list) -> int | None:
    decimals = [_ml_to_decimal(m) for m in mls]
    if any(d is None for d in decimals):
        return None
    combined = math.prod(d for d in decimals if d)
    if combined >= 2.0:
        return int(round((combined - 1) * 100))
    return int(round(-100 / (combined - 1)))
