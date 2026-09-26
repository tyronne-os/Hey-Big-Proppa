"""
CFB JIMMY — College football game intelligence.

Different rules than NFL:
  - NO player props — we only bet game-level markets
  - Markets: moneyline, total (O/U), ATS
  - Favorite MUST be AP top 25 ranked to qualify
  - HOT DOG: 2-leg upset alert parlay only
      - An unranked team (or ranked underdog) faces a ranked favorite
      - The dog has outperformed the favorite on at least 2 of 3 metrics
        over the last 3 weeks: avg points scored, avg points allowed,
        avg margin
      - Both legs target the same game: Dog ML + Total
        (under when both defenses hold up, over if the dog scores high)

HEURISTIC. NOT BACKTESTED. Same lake discipline as everything else here.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from functools import lru_cache

# CST = UTC-6 (no DST adjustment — close enough for a bet slip display)
_CST = timezone(timedelta(hours=-6))


def _to_cst(iso_str: str) -> str:
    """'2026-09-27T17:00:00.000Z' → '11:00 AM CST'."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_CST).strftime("%-I:%M %p CST")
    except Exception:
        return ""

import cfb_data

# ---------------------------------------------------------------------------
# Performance comparison — 3-week window
# ---------------------------------------------------------------------------

MIN_GAMES = 2          # need at least this many completed games to compare
MIN_METRICS_WON = 2   # dog must win at least 2 of 3 metrics to be a Hot Dog

METRICS = [
    ("avg_scored",   "Avg pts scored",   1),   # higher = better
    ("avg_allowed",  "Avg pts allowed",  -1),  # lower = better
    ("avg_margin",   "Avg margin",       1),   # higher = better
]


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


def _compare(dog_perf: dict, fav_perf: dict) -> tuple[list[dict], int]:
    rows = []
    won  = 0
    for key, label, better in METRICS:
        dog_val = dog_perf[key]
        fav_val = fav_perf[key]
        dog_wins = (dog_val - fav_val) * better > 0
        if dog_wins:
            won += 1
        rows.append({
            "key":     key,
            "label":   label,
            "dog":     dog_val,
            "fav":     fav_val,
            "dogWins": dog_wins,
        })
    return rows, won


# ---------------------------------------------------------------------------
# Slate & Hot Dogs
# ---------------------------------------------------------------------------

def _total_direction(dog_perf: dict, fav_perf: dict) -> str:
    """
    If the dog scores well AND the favorite leaks points → OVER.
    If both defenses hold → UNDER.
    Default to under (upset games tend to be tighter/lower scoring).
    """
    combined_avg = (dog_perf["avg_scored"] + fav_perf["avg_scored"]) / 2
    combined_def = (dog_perf["avg_allowed"] + fav_perf["avg_allowed"]) / 2
    return "over" if combined_avg > 28 and combined_def > 25 else "under"


@lru_cache(maxsize=1)
def cfb_game_slate() -> list[dict]:
    """
    This week's games where the favorite is AP top 25.
    Returns game-level picks: moneyline, total, ATS — no player props.
    """
    games = cfb_data.current_week_games()
    lines = cfb_data.current_week_lines()
    rankings = cfb_data.ap_poll()

    if not games:
        return []

    # full ISO datetime → CST time string for bet-slip display
    time_map: dict = {raw.get("id"): (raw.get("startDate") or "") for raw in games}

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

        # favorite must be top 25
        home_ml = line.get("home_moneyline")
        away_ml = line.get("away_moneyline")
        try:
            hml = float(home_ml) if home_ml else None
            aml = float(away_ml) if away_ml else None
        except (TypeError, ValueError):
            hml, aml = None, None

        # determine favorite by moneyline if available, else by rank
        if hml is not None and aml is not None:
            home_fav = _ml_to_prob(hml) > 0.5
        elif home_rank and not away_rank:
            home_fav = True
        elif away_rank and not home_rank:
            home_fav = False
        else:
            continue

        fav_team  = home if home_fav else away
        dog_team  = away if home_fav else home
        fav_rank  = home_rank if home_fav else away_rank
        dog_rank  = away_rank if home_fav else home_rank

        # at least the favorite must be ranked
        if not fav_rank:
            continue

        spread   = line["spread"]          # home team's spread (negative = home fav)
        total    = line["over_under"]
        dog_ml   = aml if home_fav else hml
        fav_ml   = hml if home_fav else aml

        # ATS recommendation: negative spread = home favored; dog takes the points
        dog_ats = f"+{abs(spread):.1f}" if not home_fav else f"+{spread:.1f}"

        raw_start = time_map.get(gid, "")
        out.append({
            "gameId":     gid,
            "week":       g.get("week"),
            "home":       home,
            "away":       away,
            "homeRank":   home_rank,
            "awayRank":   away_rank,
            "favorite":   fav_team,
            "favRank":    fav_rank,
            "underdog":   dog_team,
            "dogRank":    dog_rank,
            "spread":     spread,
            "dogAts":     dog_ats,
            "total":      total,
            "dogMl":      dog_ml,
            "favMl":      fav_ml,
            "provider":   line["provider"],
            "markets":    ["moneyline", "ats", "total"],
            "startDate":  raw_start[:10],
            "gameTime":   _to_cst(raw_start),
        })

    return sorted(out, key=lambda g: (g["favRank"] or 99))


@lru_cache(maxsize=1)
def cfb_hot_dogs() -> list[dict]:
    """
    2-leg upset alert parlays.
    Both legs target the same game: Dog ML + Total direction.
    Only games where the favorite is ranked and the dog has outperformed
    on at least 2 of 3 metrics over the last 3 weeks.
    """
    slate = cfb_game_slate()
    if not slate:
        return []

    dogs = []
    for g in slate:
        dog  = g["underdog"]
        fav  = g["favorite"]

        dog_games = cfb_data.team_recent_games(dog, 3)
        fav_games = cfb_data.team_recent_games(fav, 3)

        dog_perf = _perf(dog_games)
        fav_perf = _perf(fav_games)

        if dog_perf is None or fav_perf is None:
            continue

        stats, metrics_won = _compare(dog_perf, fav_perf)
        certified = metrics_won >= MIN_METRICS_WON

        total_dir = _total_direction(dog_perf, fav_perf)
        total_odds = g.get("totalOverOdds" if total_dir == "over" else "totalUnderOdds")

        game_time = g.get("gameTime", "")
        time_suffix = f" ({game_time})" if game_time else ""
        # build the 2-leg parlay
        legs = [
            {
                "label":   f"TAKE {dog} ML{time_suffix}",
                "market":  "moneyline",
                "team":    dog,
                "odds":    g["dogMl"],
                "gameTime": game_time,
            },
            {
                "label":   f"TAKE {total_dir.upper()} {g['total']} · {fav} vs {dog}{time_suffix}",
                "market":  "total",
                "direction": total_dir,
                "line":    g["total"],
                "odds":    total_odds,
                "gameTime": game_time,
            },
        ]

        # approximate parlay odds
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
            "stats":        stats,
            "dogPerf":      dog_perf,
            "favPerf":      fav_perf,
            "legs":         legs,
            "parlayOdds":   parlay_odds,
            "type":         "UPSET ALERT" if not g["dogRank"] else "RANKED DOG",
        })

    # sort: certified first, then by metrics won descending
    dogs.sort(key=lambda d: (not d["certified"], -d["metricsWon"], d["favRank"] or 99))
    return dogs


# ---------------------------------------------------------------------------
# Over probability engine
# ---------------------------------------------------------------------------

def _over_prob(proj_total: float, total_line: float, std: float = 9.0) -> float:
    """
    Rough normal-CDF probability that the game goes OVER.
    std ≈ 9 pts is empirically typical for CFB combined-score variance.
    """
    if total_line <= 0:
        return 0.5
    z = (proj_total - total_line) / std
    return round(0.5 * (1 + math.erf(z / math.sqrt(2))), 3)


@lru_cache(maxsize=1)
def cfb_big_money_overs(date_filter: str | None = None) -> list[dict]:
    """
    Games with highest probability of going OVER the total line.

    Projection formula (blended offense + defensive leakiness):
      proj = (fav_avg_scored + dog_avg_scored +   ← what both offenses produce
               fav_avg_allowed + dog_avg_allowed)  ← what both defenses give up
             / 2                                   ← average of the two signals
    Then compare to the line via a normal-CDF P(over).

    Only games where both teams have at least 2 completed games.
    date_filter: "YYYY-MM-DD" string to limit to one day's games.
    HEURISTIC. NOT BACKTESTED.
    """
    slate = cfb_game_slate()

    out = []
    for g in slate:
        if date_filter and g.get("startDate", "") != date_filter:
            continue
        if not g["total"] or g["total"] <= 0:
            continue

        fav_games = cfb_data.team_recent_games(g["favorite"], 3)
        dog_games = cfb_data.team_recent_games(g["underdog"], 3)
        fav_p = _perf(fav_games)
        dog_p = _perf(dog_games)
        if fav_p is None or dog_p is None:
            continue

        # offensive projection: what both units score on average
        off_proj = fav_p["avg_scored"] + dog_p["avg_scored"]
        # defensive projection: how many points both defenses surrender
        def_proj = fav_p["avg_allowed"] + dog_p["avg_allowed"]
        # blended expected total
        proj_total = round((off_proj + def_proj) / 2, 1)
        over_margin = round(proj_total - g["total"], 1)
        prob = _over_prob(proj_total, g["total"])

        # signal flags
        both_offenses_hot  = fav_p["avg_scored"] > g["total"] * 0.47 and dog_p["avg_scored"] > g["total"] * 0.47
        both_defenses_leaky = fav_p["avg_allowed"] > g["total"] * 0.47 and dog_p["avg_allowed"] > g["total"] * 0.47

        # grade: A = prob >= 0.68, B = >= 0.58, C = >= 0.50
        grade = "A" if prob >= 0.68 else "B" if prob >= 0.58 else "C" if prob >= 0.50 else "D"

        out.append({
            "gameId":       g["gameId"],
            "gameDate":     g.get("startDate", ""),
            "gameTime":     g.get("gameTime", ""),
            "fav":          g["favorite"],
            "favRank":      g["favRank"],
            "dog":          g["underdog"],
            "dogRank":      g["dogRank"],
            "totalLine":    g["total"],
            "projTotal":    proj_total,
            "overMargin":   over_margin,
            "overProb":     prob,
            "grade":        grade,
            "offProj":      round(off_proj, 1),
            "defProj":      round(def_proj, 1),
            "favAvgScored": fav_p["avg_scored"],
            "dogAvgScored": dog_p["avg_scored"],
            "favAvgAllowed":fav_p["avg_allowed"],
            "dogAvgAllowed":dog_p["avg_allowed"],
            "bothOffensesHot":  both_offenses_hot,
            "bothDefensesLeaky":both_defenses_leaky,
            "dogMl":        g["dogMl"],
            "spread":       g["spread"],
        })

    # sort by over probability descending
    out.sort(key=lambda x: -x["overProb"])
    return out


# ---------------------------------------------------------------------------
# Lock cover dogs — can cover AND win outright
# ---------------------------------------------------------------------------

LOCK_MAX_SPREAD  = 18.0   # dog within 18 pts — not a blowout spot
LOCK_MAX_DOG_ML  = 325    # no lottery tickets: dog odds must be +325 or better
LOCK_MIN_METRICS = 2      # must pass at least 2 of 3 performance metrics


@lru_cache(maxsize=1)
def cfb_lock_cover_dogs(date_filter: str | None = None) -> list[dict]:
    """
    Hot dogs that are STRONG COVERS and realistic outright WIN candidates.

    Filters on top of the standard hot dog logic:
      - Spread within LOCK_MAX_SPREAD (dog has a shot to win)
      - Dog ML at LOCK_MAX_DOG_ML or better (not a longshot)
      - Dog has winning record over last 3 games
      - Passes LOCK_MIN_METRICS performance metrics

    Sorted: perfect 3/3 first, then best ML odds (closest to even).
    HEURISTIC. NOT BACKTESTED.
    """
    dogs = cfb_hot_dogs()
    slate_map = {g["gameId"]: g for g in cfb_game_slate()}

    out = []
    for d in dogs:
        game_entry_s = slate_map.get(d["gameId"])
        game_date = (game_entry_s or {}).get("startDate", "")
        if date_filter and game_date != date_filter:
            continue

        game_entry = game_entry_s
        if game_entry is None:
            continue

        raw_spread = abs(game_entry["spread"])   # always positive for the spread gap
        dog_ml     = d["legs"][0]["odds"]        # first leg is always Dog ML

        if raw_spread > LOCK_MAX_SPREAD:
            continue
        if dog_ml is None or abs(dog_ml) > LOCK_MAX_DOG_ML:
            continue
        if d["metricsWon"] < LOCK_MIN_METRICS:
            continue
        if d["dogPerf"]["wins"] == 0:            # dog must have at least 1 win in window
            continue

        lock_score = d["metricsWon"] * 10 + (LOCK_MAX_DOG_ML - abs(dog_ml)) / LOCK_MAX_DOG_ML * 5
        # perfect 3/3 AND dog has winning record = LOCKED
        is_locked = (d["metricsWon"] == 3 and d["dogPerf"]["wins"] > d["dogPerf"]["games"] / 2)

        out.append({
            **d,
            "spread":    raw_spread,
            "gameDate":  game_date,
            "gameTime":  (game_entry_s or {}).get("gameTime", ""),
            "lockScore": round(lock_score, 2),
            "isLocked":  is_locked,
        })

    out.sort(key=lambda x: (-x["isLocked"], -x["lockScore"]))
    return out


# ---------------------------------------------------------------------------
# BIG PROPPA BIG MONEY PARLAYS
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def cfb_big_money_parlays(date_filter: str | None = None) -> list[dict]:
    """
    BIG PROPPA BIG MONEY PARLAYS — CFB game-level only.

    Parlay types built:
      DOUBLE OVER:    top 2 over plays  (both totals go OVER)
      UPSET SPECIAL:  top over + top lock cover dog ML
      TRIPLE CROWN:   top 2 overs + top lock dog ATS (cover)
      DOG FIGHT:      top 2 lock dogs ML (if 2 qualify)

    All legs sourced from cfb_big_money_overs() and cfb_lock_cover_dogs().
    Parlay odds are approximate (multiply decimals).
    """
    overs = cfb_big_money_overs(date_filter)[:3]
    locks = cfb_lock_cover_dogs(date_filter)[:2]

    parlays = []

    def _over_leg(o: dict) -> dict:
        t = f" ({o['gameTime']})" if o.get("gameTime") else ""
        return {"label": f"TAKE OVER {o['totalLine']} · {o['fav']} vs {o['dog']}{t}",
                "odds": -110, "bet": "over", "gameTime": o.get("gameTime", "")}

    def _dog_ml_leg(lock: dict) -> dict:
        t = f" ({lock['gameTime']})" if lock.get("gameTime") else ""
        ml = lock["legs"][0]["odds"]
        return {"label": f"TAKE {lock['dog']} ML{t}", "odds": int(ml) if ml is not None else None,
                "bet": "dog_ml", "gameTime": lock.get("gameTime", "")}

    def _dog_ats_leg(lock: dict) -> dict:
        t = f" ({lock['gameTime']})" if lock.get("gameTime") else ""
        return {"label": f"TAKE {lock['dog']} +{lock['spread']} ATS{t}",
                "odds": -110, "bet": "dog_ats", "gameTime": lock.get("gameTime", "")}

    # ── HOT DOG DOUBLE OVER ───────────────────────────────────────────────────
    if len(overs) >= 2:
        o1, o2 = overs[0], overs[1]
        legs = [_over_leg(o1), _over_leg(o2)]
        parlays.append({
            "type":       "DOUBLE OVER",
            "tag":        "🔥 SCORING FEAST",
            "legs":       legs,
            "parlayOdds": _combine_ml([-110, -110]),
            "confidence": round(o1["overProb"] * o2["overProb"], 3),
            "reasoning":  f"{o1['fav']} vs {o1['dog']} proj {o1['projTotal']} pts (line {o1['totalLine']}, +{o1['overMargin']}) · "
                          f"{o2['fav']} vs {o2['dog']} proj {o2['projTotal']} pts (line {o2['totalLine']}, +{o2['overMargin']})",
        })

    # ── HOT DOG UPSET SPECIAL ─────────────────────────────────────────────────
    if overs and locks:
        o1   = overs[0]
        lock = locks[0]
        ml   = lock["legs"][0]["odds"]
        if ml is not None:
            legs = [_over_leg(o1), _dog_ml_leg(lock)]
            parlays.append({
                "type":       "UPSET SPECIAL",
                "tag":        "🐕 DOG + SCORING",
                "legs":       legs,
                "parlayOdds": _combine_ml([-110, int(ml)]),
                "confidence": round(o1["overProb"] * (lock["metricsWon"] / 3), 3),
                "reasoning":  f"OVER: {o1['fav']} vs {o1['dog']} proj {o1['projTotal']} pts · "
                              f"DOG: {lock['dog']} wins {lock['metricsWon']}/3 metrics vs #{lock['favRank']} {lock['fav']}",
            })

    # ── HOT DOG TRIPLE (formerly TRIPLE CROWN) ────────────────────────────────
    if len(overs) >= 2 and locks:
        o1, o2 = overs[0], overs[1]
        lock   = locks[0]
        legs   = [_over_leg(o1), _over_leg(o2), _dog_ats_leg(lock)]
        parlays.append({
            "type":       "HOT DOG TRIPLE",
            "tag":        "💰 BIG MONEY",
            "legs":       legs,
            "parlayOdds": _combine_ml([-110, -110, -110]),
            "confidence": round(o1["overProb"] * o2["overProb"] * (lock["metricsWon"] / 3), 3),
            "reasoning":  f"2x OVERs + {lock['dog']} cover vs #{lock['favRank']} {lock['fav']}",
        })

    # ── HOT DOG FIGHT (DOG FIGHT) ─────────────────────────────────────────────
    if len(locks) >= 2:
        l1, l2 = locks[0], locks[1]
        ml1 = l1["legs"][0]["odds"]
        ml2 = l2["legs"][0]["odds"]
        if ml1 and ml2:
            legs = [_dog_ml_leg(l1), _dog_ml_leg(l2)]
            parlays.append({
                "type":       "DOG FIGHT",
                "tag":        "🐕‍🦺 BOTH DOGS WIN",
                "legs":       legs,
                "parlayOdds": _combine_ml([ml1, ml2]),
                "confidence": round((l1["metricsWon"] / 3) * (l2["metricsWon"] / 3), 3),
                "reasoning":  f"{l1['dog']} {l1['metricsWon']}/3 metrics vs #{l1['favRank']} {l1['fav']} · "
                              f"{l2['dog']} {l2['metricsWon']}/3 metrics vs #{l2['favRank']} {l2['fav']}",
            })

    return parlays


# ---------------------------------------------------------------------------
# CRAZY HORSE — mega-parlay: all >85 % confidence picks grouped by day
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def cfb_crazy_horse(date_filter: str | None = None) -> list[dict]:
    """
    CRAZY HORSE parlays.

    Collects ALL individual picks with confidence >= 85 %:
      • Overs where overProb >= 0.85
      • Lock dogs that are fully LOCKED (3/3 metrics, winning record)

    Groups by day-of-week:
      CRAZY HORSE SATURDAY  — all Saturday picks
      CRAZY HORSE SUNDAY    — all Sunday picks  (NFL integration future)
      SUPER CRAZY HORSE     — Saturday + Sunday combined (requires both)

    Wager: $5.  HEURISTIC. NOT BACKTESTED.
    """
    overs = cfb_big_money_overs(date_filter)
    locks = cfb_lock_cover_dogs(date_filter)

    CONF_THRESHOLD = 0.85

    def _day(iso_or_ymd: str) -> int:
        """Return ISO weekday (0=Mon … 5=Sat, 6=Sun) or -1 if unparseable."""
        if not iso_or_ymd:
            return -1
        try:
            return datetime.fromisoformat(iso_or_ymd[:10]).weekday()
        except Exception:
            return -1

    # Collect high-confidence legs
    all_legs: list[dict] = []

    for o in overs:
        if o["overProb"] < CONF_THRESHOLD:
            continue
        t = f" ({o['gameTime']})" if o.get("gameTime") else ""
        all_legs.append({
            "label":     f"TAKE OVER {o['totalLine']} · {o['fav']} vs {o['dog']}{t}",
            "odds":      -110,
            "bet":       "over",
            "gameDate":  o.get("gameDate", ""),
            "gameTime":  o.get("gameTime", ""),
            "day":       _day(o.get("gameDate", "")),
            "prob":      o["overProb"],
        })

    for l in locks:
        if not l.get("isLocked"):          # LOCKED = 3/3 metrics + winning record
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
            "prob":     l["metricsWon"] / 3,
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
            "reasoning":  f"{len(legs)}-leg sweep of all ≥85% confidence picks — $5 for a big payout.",
        }

    if len(sat_legs) >= 2:
        out.append(_horse("CRAZY HORSE SATURDAY", "🐎 SATURDAY SWEEP", sat_legs))

    if len(sun_legs) >= 2:
        out.append(_horse("CRAZY HORSE SUNDAY", "🐎 SUNDAY SWEEP", sun_legs))

    if sat_legs and sun_legs and len(sat_legs) + len(sun_legs) >= 3:
        out.append(_horse("SUPER CRAZY HORSE", "🐎🔥 FULL WEEKEND SWEEP", sat_legs + sun_legs))

    return out


def cfb_status() -> dict:
    """Connection and data status for the CFB jimmy section."""
    available = cfb_data.available()
    week      = cfb_data.current_week() if available else None
    rankings  = cfb_data.ap_poll()      if available else {}
    games     = cfb_data.current_week_games() if available else []

    return {
        "available":   available,
        "apiKeyVar":   "CFBD_API_KEY",
        "season":      cfb_data._current_season() if available else None,
        "week":        week,
        "rankingsLoaded": len(rankings),
        "gamesOnSlate":   len(games),
        "top25Games":     len(cfb_game_slate()) if available else 0,
        "hotDogs":        len(cfb_hot_dogs())   if available else 0,
    }


# ---------------------------------------------------------------------------
# Moneyline math helpers
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
    """Approximate combined American moneyline for a 2-leg parlay."""
    decimals = [_ml_to_decimal(m) for m in mls]
    if any(d is None for d in decimals):
        return None
    combined = math.prod(d for d in decimals if d)
    # convert back to American
    if combined >= 2.0:
        return int(round((combined - 1) * 100))
    return int(round(-100 / (combined - 1)))
