"""
BUDDY COSELL · FRONTAL LOBE SPORTS

Sports reporter persona writing 500-700 word articles in the voice of a
1940s-50s New York Times football journalist. Buddy hangs around Jimmy the
Greek to get scoops -- the scoop IS the correlated parlay, and the sportsbook
line is placed "under investigation" in every column.

Entry: articles_today() -> list[dict]
  Each article is keyed to one Engine slip and one game from the schedule.
  If no data supports a convincing article, that slip is PASSED (no article
  generated -- the article IS the final confirmation gate per the user spec).

Article schema:
  {
    "slipId":       str,
    "gameId":       str,
    "headline":     str,
    "deck":         str,               # 1-2 sentence subhead
    "byline":       str,               # "By Buddy Cosell, FRONTAL LOBE SPORTS"
    "dateline":     str,               # "CITY, State -- "
    "body":         str,               # 500-700 word article body (paragraphs sep by \\n\\n)
    "verdict":      str,               # one-line sportsbook investigation
    "correlationType": str,
    "confidence":   float,             # avg jimmy prob across legs
    "legCount":     int,
    "homeTeam":     str,
    "awayTeam":     str,
    "gameDate":     str,
    "gameTime":     str,
    "passed":       bool,              # True = Big Proppa passes on this parlay
    "passReason":   str | None,
  }

HEURISTIC. NOT BACKTESTED. Same discipline as every other lake output.
"""
from __future__ import annotations

from functools import lru_cache

import data
import jimmy as jimmy_mod
import parlay_engine as engine_mod


_STADIUM_CITY: dict[str, str] = {
    "ARI": "GLENDALE, Ariz.",
    "ATL": "ATLANTA, Ga.",
    "BAL": "BALTIMORE, Md.",
    "BUF": "ORCHARD PARK, N.Y.",
    "CAR": "CHARLOTTE, N.C.",
    "CHI": "CHICAGO, Ill.",
    "CIN": "CINCINNATI, Ohio",
    "CLE": "CLEVELAND, Ohio",
    "DAL": "ARLINGTON, Texas",
    "DEN": "DENVER, Colo.",
    "DET": "DETROIT, Mich.",
    "GB": "GREEN BAY, Wis.",
    "HOU": "HOUSTON, Texas",
    "IND": "INDIANAPOLIS, Ind.",
    "JAX": "JACKSONVILLE, Fla.",
    "KC": "KANSAS CITY, Mo.",
    "LAC": "INGLEWOOD, Calif.",
    "LA": "INGLEWOOD, Calif.",
    "LV": "LAS VEGAS, Nev.",
    "MIA": "MIAMI GARDENS, Fla.",
    "MIN": "MINNEAPOLIS, Minn.",
    "NE": "FOXBOROUGH, Mass.",
    "NO": "NEW ORLEANS, La.",
    "NYG": "EAST RUTHERFORD, N.J.",
    "NYJ": "EAST RUTHERFORD, N.J.",
    "PHI": "PHILADELPHIA, Pa.",
    "PIT": "PITTSBURGH, Pa.",
    "SEA": "SEATTLE, Wash.",
    "SF": "SANTA CLARA, Calif.",
    "TB": "TAMPA, Fla.",
    "TEN": "NASHVILLE, Tenn.",
    "WAS": "LANDOVER, Md.",
}

_FULL_TEAM: dict[str, str] = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

_IB_CAT_PROSE: dict[str, str] = {
    "CAT 1": "the most hospitable stretch of pasture this side of training camp",
    "CAT 2": "a defense that has shown little taste for confrontation",
    "CAT 3": "a unit that plays its game-plan cards close to the vest",
    "CAT 4": "a front seven that has given signal-callers nothing but misery",
    "CAT 5": "the most forbidding defensive outfit in the professional game today",
}

_CORR_LABEL: dict[str, str] = {
    "COACHES_SON": "the Coaches Son parlay",
    "IB_CASCADE": "the IB Cascade find",
    "VOLUME_STACK": "the Volume Stack ticket",
    "SINGLE_HERO": "the Single Hero three-bagger",
}


@lru_cache(maxsize=1)
def _defense_ib_map() -> dict[str, dict]:
    return {r["team"]: r for r in data.load("defense_ib_score")}


@lru_cache(maxsize=1)
def _usage_map() -> dict[str, dict]:
    return {r["player_id"]: r for r in data.load("player_usage") if r.get("player_id")}


@lru_cache(maxsize=1)
def _td_corr_map() -> dict[str, dict]:
    return {r["player_id"]: r for r in data.load("player_usage_td_correlation") if r.get("player_id")}


@lru_cache(maxsize=1)
def _redzone_map() -> dict[str, dict]:
    return {r["player_id"]: r for r in data.load("redzone_tiers") if r.get("player_id")}


def _avg_prob(legs: list[dict]) -> float:
    probs = [lg["probability"] for lg in legs if lg.get("probability") is not None]
    return round(sum(probs) / len(probs), 3) if probs else 0.0


def _full_team(abbr: str) -> str:
    return _FULL_TEAM.get(abbr, abbr)


def _city(team: str) -> str:
    return _STADIUM_CITY.get(team, team)


def _ib_prose(team: str) -> str:
    ib = _defense_ib_map().get(team, {})
    cat = (ib.get("ib_category") or "").split(" --")[0].strip()
    return _IB_CAT_PROSE.get(cat, "a defense of indeterminate character")


# ---------------------------------------------------------------------------
# Article writers -- one per correlationType
# ---------------------------------------------------------------------------

def _write_coaches_son(slip: dict, game: dict) -> str:
    legs = slip["legs"]
    player = legs[0]
    name = player["name"]
    team = player["team"]
    opp = game["away_team"] if game["home_team"] == team else game["home_team"]
    opp_full = _full_team(opp)
    team_full = _full_team(team)
    game_time = game.get("game_time_local", "")
    game_date = game.get("game_date", "")

    usage = _usage_map().get(player["playerId"], {})
    usage_role = usage.get("usage_role", "a featured back")
    usage_score = float(usage.get("usage_index_score") or 60)
    td_corr = _td_corr_map().get(player["playerId"], {})
    td_flag = td_corr.get("correlation_flag", "MIXED")
    rz = _redzone_map().get(player["playerId"], {})
    i5_pct = float(rz.get("pct_i5_intra") or 0)

    ib = _defense_ib_map().get(opp, {})
    ib_cat = ib.get("ib_category", "")
    ib_prose = _ib_prose(opp)

    avg_prob = _avg_prob(legs)
    props_listed = "; ".join(lg["prop"] for lg in legs)
    boost_pct = int(slip["boost"] * 100)
    boosted = slip["boostedPayout"]
    wager = slip["wager"]

    td_sentence = ""
    if td_flag == "AGREEMENT":
        td_sentence = (
            f"The lake's own touchdown correlation table lists {name} as an AGREEMENT talent -- "
            f"a man whose usage and his actual touchdowns are in lockstep, not at odds. "
            f"When the coach trusts him near the goal line, the scoreboard has a way of confirming it."
        )
    elif td_flag == "OPPORTUNITY":
        td_sentence = (
            f"The pond marks {name} as an OPPORTUNITY finisher: the touchdowns haven't come in great numbers yet, "
            f"but the redzone targets suggest the opportunity is real and the conversion rate will follow."
        )

    i5_sentence = ""
    if i5_pct >= 0.18:
        i5_sentence = (
            f"Inside the five-yard line, {name} commands {int(i5_pct * 100)} percent of his club's "
            f"opportunities -- the sort of figure that makes a bookmaker's hand tremble."
        )

    body = f"""Your correspondent has spent the better part of this week in the company of one Jimmy the Greek, that most deliberate of oddsmakers, and the Greek has pressed upon me a matter he considers of the utmost urgency before Sunday's kickoff.

The subject is {name}, late of the {team_full}, who will face the {opp_full} on {game_date} at {game_time}. Jimmy informs me that the pond-keepers at Frontal Lobe Sports have catalogued this gentleman as {usage_role.lower()} -- a designation earned through {int(usage_score)} usage points on the proprietary index, a figure your correspondent is told represents the coaching staff's considered confidence in the man's deployment.

Now, the {opp_full} arrive as {ib_prose}. Jimmy places their pass-rush index at {ib_cat}, and your correspondent will take the Greek's word for it, having observed this unit with some dismay over the preceding fortnight.

{td_sentence}

{i5_sentence}

What Jimmy the Greek has surfaced this week is what the sportsmen in these precincts call the Coaches Son ticket: three legs for a single player, each rooted in the same causal logic rather than three separate wagers dressed up as correlation. The props under scrutiny are: {props_listed}. The average probability, per the Greek's lake-only engine, stands at {int(avg_prob * 100)} percent -- and your correspondent notes that this figure derives not from any single statistic but from the composite of recent form, the coaching staff's own usage declaration, and the quality of the opposition Jimmy has been so kind as to evaluate.

The Greek reminds me, as he always does, that this is a heuristic. It has not been backtested. The 1940s were not a golden age of sample-size discipline. Nevertheless, a {int(avg_prob * 100)}-percent composite from three independent signals is not the sort of number a careful reader dismisses without investigation.

A {wager:.0f}-dollar wager, boosted at {boost_pct} percent by the establishment, returns {boosted:.2f} dollars should all three propositions prove correct. Jimmy considers this adequate compensation for the risk, and your correspondent, after due deliberation, is inclined to agree.

The line, gentlemen, is under investigation."""

    return body.strip()


def _write_ib_cascade(slip: dict, game: dict) -> str:
    legs = slip["legs"]
    qb_leg = next((lg for lg in legs if "Pass Yards" in lg["prop"] or "pass" in lg["market"].lower()), legs[0])
    rb_leg = next((lg for lg in legs if lg["playerId"] != qb_leg["playerId"]), None)

    qb_name = qb_leg["name"]
    qb_team = qb_leg["team"]
    opp = game["away_team"] if game["home_team"] == qb_team else game["home_team"]
    opp_full = _full_team(opp)
    team_full = _full_team(qb_team)
    game_date = game.get("game_date", "")
    game_time = game.get("game_time_local", "")

    ib = _defense_ib_map().get(opp, {})
    ib_score = int(float(ib.get("ib_score") or 3))
    ib_cat = ib.get("ib_category", "")
    ib_prose = _ib_prose(opp)
    tox = float(ib.get("toxicity_index_0_100") or 50)
    sacks = float(ib.get("sacks") or 0)
    pts = float(ib.get("points_allowed_per_game") or 20)

    cascade_target = rb_leg["name"] if rb_leg else "the check-down target"
    cascade_team = rb_leg["team"] if rb_leg else qb_team
    cascade_prop = rb_leg["prop"] if rb_leg else ""
    cascade_note = rb_leg["correlationNote"] if rb_leg else ""

    avg_prob = _avg_prob(legs)
    boost_pct = int(slip["boost"] * 100)
    boosted = slip["boostedPayout"]
    wager = slip["wager"]

    body = f"""Jimmy the Greek has a theory about defensive front sevens that he has pressed upon your correspondent with some vigor this week, and the theory concerns what happens to a signal-caller -- no matter how distinguished his pedigree -- when he operates behind a line that cannot hold.

The quarterback in question is {qb_name} of the {team_full}, who will take the field against the {opp_full} on {game_date}. The opposition's pass-rush index, per the lake at Frontal Lobe Sports, reads {ib_cat}. Your correspondent translates: {ib_prose}. They have registered {sacks:.0f} sacks across the early going and surrendered a mere {pts:.1f} points per contest -- numbers that do not comfort an offensive coordinator.

The Greek's IB Cascade logic proceeds as follows. A quarterback under sustained pressure does not have the luxury of waiting for his primary receiver to work free. He takes what the defense surrenders, and what a collapsing pocket most reliably surrenders is the check-down: the short pass to the back aligned in the flat, the man who requires no time at all to reach.

That man, in this instance, is {cascade_target} of the {_full_team(cascade_team)}. {cascade_note} The prop under investigation: {cascade_prop}.

Simultaneously, the Greek notes that {qb_name} himself faces a proposition the bookmakers have perhaps set with insufficient respect for the {opp_full}'s defensive temperament. The pressure cascade, when it comes -- and at IB Category {ib_score}, the Greek considers it a question of when, not whether -- will suppress the passing yards with mechanical regularity.

Jimmy places the combined probability of this two-leg cascade at {int(avg_prob * 100)} percent. The toxicity of the {opp_full}'s defensive alignment, measured at {tox:.0f} on the hundred-point lake index, is the sort of figure that renders the bookmaker's over/under line worthy of investigation.

A {wager:.0f}-dollar position, boosted {boost_pct} percent, returns {boosted:.2f} dollars should this cascade unfold as Jimmy predicts. Your correspondent, having examined the Greek's pond data with some care, finds the logic compelling.

The line is under investigation. Proceed with the caution this column has always counseled and the conviction the numbers seem to warrant."""

    return body.strip()


def _write_volume_stack(slip: dict, game: dict) -> str:
    legs = slip["legs"]
    players = list({lg["name"]: lg for lg in legs}.values())
    team = players[0]["team"]
    opp = game["away_team"] if game["home_team"] == team else game["home_team"]
    opp_full = _full_team(opp)
    team_full = _full_team(team)
    game_date = game.get("game_date", "")
    game_time = game.get("game_time_local", "")

    ib = _defense_ib_map().get(opp, {})
    ib_prose = _ib_prose(opp)
    tox = float(ib.get("toxicity_index_0_100") or 50)

    names_listed = " and ".join(p["name"] for p in players[:3])
    props_listed = "; ".join(lg["prop"] for lg in legs)
    avg_prob = _avg_prob(legs)
    boost_pct = int(slip["boost"] * 100)
    boosted = slip["boostedPayout"]
    wager = slip["wager"]

    body = f"""There is a proposition that Jimmy the Greek returns to with some frequency when the conditions are favorable, and he has returned to it again this week with the urgency of a man who believes the establishment has not done its sums with sufficient care.

The proposition concerns the {team_full} and their upcoming engagement with the {opp_full} on {game_date}. The Greek's volume stack is built upon a simple premise: when one man on a given offense thrives, his immediate colleagues do not languish. The ball moves. The opportunities distribute themselves across the unit. What rises for one man tends to lift another.

The players in question are {names_listed}. The props the Greek has placed under investigation: {props_listed}.

Now, the {opp_full} present themselves as {ib_prose}. Their toxicity index registers {tox:.0f} on the hundred-point scale -- a figure that suggests the {team_full}'s offense will be permitted to accumulate yards without undue interference. A defense that cannot impose its will in the trenches will, the Greek reasons, find its secondary equally unable to suppress a well-organized passing game.

The lake's own pond data confirms the usage alignment among these gentlemen. Jimmy has verified that the correlations are positive and genuine -- not the spurious coincidences that afflict lesser analyses. When the offense functions, each man named above functions with it. This is not a matter of opinion but of measured volume distributions across the seventeen weeks this organization has made available to statistical examination.

The combined Jimmy probability stands at {int(avg_prob * 100)} percent. The Greek notes that the bookmakers have priced each proposition in isolation, apparently without consulting the correlation structure the lake makes plain.

{wager:.0f} dollars, boosted {boost_pct} percent, returns {boosted:.2f} should the machine operate as its designers intended. Your correspondent has seen few arguments as tidy as the one Jimmy has presented this week.

The line, as ever when the Greek is this certain, is under investigation."""

    return body.strip()


def _write_single_hero(slip: dict, game: dict) -> str:
    legs = slip["legs"]
    player = legs[0]
    name = player["name"]
    team = player["team"]
    opp = game["away_team"] if game["home_team"] == team else game["home_team"]
    opp_full = _full_team(opp)
    team_full = _full_team(team)
    game_date = game.get("game_date", "")
    game_time = game.get("game_time_local", "")

    usage = _usage_map().get(player["playerId"], {})
    usage_role = usage.get("usage_role", "a featured performer")
    usage_score = float(usage.get("usage_index_score") or 60)

    ib_prose = _ib_prose(opp)
    avg_prob = _avg_prob(legs)
    boost_pct = int(slip["boost"] * 100)
    boosted = slip["boostedPayout"]
    wager = slip["wager"]
    props_listed = "; ".join(lg["prop"] for lg in legs)

    markets = len(legs)
    body = f"""There are, in the annals of professional football, certain performers whose contributions to their club's enterprise are so thorough and so consistent that the oddsmaker, however diligent, cannot account for them in any single line. Jimmy the Greek has identified such a figure this week, and he has done so with the sort of excitement that in this correspondent's long experience precedes a particularly well-supported column.

The subject is {name} of the {team_full}, who will perform against the {opp_full} on {game_date} at {game_time}. The lake at Frontal Lobe Sports catalogues this gentleman as {usage_role.lower()} -- a designation supported by a usage index score of {usage_score:.0f}, which is to say that the coaching staff's reliance upon him is not a matter of conjecture but of documented deployment.

The {opp_full} are, per Jimmy's pond data, {ib_prose}. This is not irrelevant. A defense that cannot impose its will creates the conditions under which a player of {name}'s designation may accumulate statistics across multiple dimensions simultaneously.

The Greek's Single Hero ticket calls for {markets} independent markets to clear eighty-five percent probability in the same contest. This is not the work of an afternoon. Jimmy has examined {name}'s recent form, his usage certification from the lake, and the matchup conditions with the {opp_full}, and across all {markets} propositions the lake's composite probability exceeds that threshold. The props in question: {props_listed}.

Your correspondent would note that these are not three bets dressed up as a correlation. They are three consequences of the same underlying fact: a player trusted by his coaches, facing a defense that the lake rates as permissive, in a game where the conditions favor offensive production. When these elements align for a single performer, the bookmakers' individual prices, taken together, represent an arithmetic opportunity.

The combined return on a {wager:.0f}-dollar position, boosted {boost_pct} percent by the establishment, is {boosted:.2f} dollars. Jimmy considers this adequate. This correspondent, having reviewed the pond data, is disinclined to disagree.

The line is under investigation. {name}'s performance will either vindicate the Greek's methodology or provide your correspondent with a useful cautionary note for a future column. Jimmy, for what it is worth, has not asked for a cautionary note."""

    return body.strip()


_WRITERS = {
    "COACHES_SON": _write_coaches_son,
    "IB_CASCADE": _write_ib_cascade,
    "VOLUME_STACK": _write_volume_stack,
    "SINGLE_HERO": _write_single_hero,
}


def _headline_deck(slip: dict, game: dict) -> tuple[str, str]:
    legs = slip["legs"]
    ct = slip["correlationType"]
    avg_prob = _avg_prob(legs)
    prob_str = f"{int(avg_prob * 100)}"
    team = legs[0]["team"]
    opp = game["away_team"] if game["home_team"] == team else game["home_team"]
    name = legs[0]["name"]

    if ct == "COACHES_SON":
        headline = f"JIMMY THE GREEK ON {name.upper()}: '{_full_team(team)} BACK A {prob_str}-PERCENT PROPOSITION'"
        deck = (
            f"The oddsmaker's pond-driven analysis certifies {name} as a {prob_str}% confidence play "
            f"against {_full_team(opp)} — three correlated props, one unified thesis, "
            f"the sportsbook line under investigation."
        )
    elif ct == "IB_CASCADE":
        ib = _defense_ib_map().get(opp, {})
        ib_cat = (ib.get("ib_category") or "").split(" --")[0]
        headline = f"FRONTAL LOBE EXCLUSIVE: {opp} DEFENSIVE FRONT PUTS {name.upper()} ON NOTICE"
        deck = (
            f"Jimmy the Greek's IB Cascade identifies {ib_cat} pressure conditions against "
            f"{_full_team(opp)}, elevating the check-down target and suppressing the air attack — "
            f"a {prob_str}% composite finding the establishment has yet to price correctly."
        )
    elif ct == "VOLUME_STACK":
        headline = f"THE {_full_team(team).upper()} VOLUME MACHINE: JIMMY'S STACK FINDS THE ESTABLISHMENT FLAT-FOOTED"
        deck = (
            f"When the {_full_team(team)} offense operates, it operates in concert — "
            f"Jimmy the Greek's Volume Stack identifies {len(legs)} correlated props the bookmakers have priced in isolation."
        )
    else:
        headline = f"THE COMPLETE PERFORMER: {name.upper()} CLEARS {prob_str}% ACROSS {len(legs)} INDEPENDENT MARKETS"
        deck = (
            f"Jimmy the Greek's Single Hero analysis certifies {name} as a {len(legs)}-market "
            f"proposition against {_full_team(opp)} — usage, matchup, and recent form all aligned."
        )

    return headline, deck


def articles_today() -> list[dict]:
    slips = engine_mod.run_engine()
    game_by_team = jimmy_mod.next_game_by_team()
    if not game_by_team:
        return []

    articles = []
    for slip in slips:
        legs = slip.get("legs", [])
        if not legs:
            continue

        primary_team = jimmy_mod.player_team(legs[0]["playerId"]) or legs[0]["team"]
        game = game_by_team.get(primary_team)
        if not game:
            articles.append({
                "slipId": slip["id"],
                "gameId": "",
                "passed": True,
                "passReason": f"No scheduled game found for {primary_team} this week — Big Proppa passes.",
                "correlationType": slip["correlationType"],
                "confidence": _avg_prob(legs),
                "legCount": len(legs),
                "homeTeam": primary_team,
                "awayTeam": "",
                "gameDate": "",
                "gameTime": "",
                "headline": "",
                "deck": "",
                "byline": "",
                "dateline": "",
                "body": "",
                "verdict": "",
            })
            continue

        avg_prob = _avg_prob(legs)

        # Pass gate: if avg confidence is below 0.65, article cannot be written convincingly
        if avg_prob < 0.65:
            articles.append({
                "slipId": slip["id"],
                "gameId": game["game_id"],
                "passed": True,
                "passReason": (
                    f"Jimmy's lake composite averages {int(avg_prob * 100)}% — "
                    f"below the threshold for a convincing column. Big Proppa passes."
                ),
                "correlationType": slip["correlationType"],
                "confidence": avg_prob,
                "legCount": len(legs),
                "homeTeam": game["home_team"],
                "awayTeam": game["away_team"],
                "gameDate": game.get("game_date", ""),
                "gameTime": game.get("game_time_local", ""),
                "headline": "",
                "deck": "",
                "byline": "",
                "dateline": "",
                "body": "",
                "verdict": "",
            })
            continue

        writer = _WRITERS.get(slip["correlationType"])
        if not writer:
            continue

        try:
            body = writer(slip, game)
        except Exception as exc:
            articles.append({
                "slipId": slip["id"],
                "gameId": game["game_id"],
                "passed": True,
                "passReason": f"Article generation error: {exc}",
                "correlationType": slip["correlationType"],
                "confidence": avg_prob,
                "legCount": len(legs),
                "homeTeam": game["home_team"],
                "awayTeam": game["away_team"],
                "gameDate": game.get("game_date", ""),
                "gameTime": game.get("game_time_local", ""),
                "headline": "",
                "deck": "",
                "byline": "",
                "dateline": "",
                "body": "",
                "verdict": "",
            })
            continue

        headline, deck = _headline_deck(slip, game)
        home = game["home_team"]
        city = _city(home)
        game_date_str = game.get("game_date", "")

        articles.append({
            "slipId": slip["id"],
            "gameId": game["game_id"],
            "passed": False,
            "passReason": None,
            "correlationType": slip["correlationType"],
            "confidence": avg_prob,
            "legCount": len(legs),
            "homeTeam": home,
            "awayTeam": game["away_team"],
            "gameDate": game_date_str,
            "gameTime": game.get("game_time_local", ""),
            "headline": headline,
            "deck": deck,
            "byline": "By Buddy Cosell, FRONTAL LOBE SPORTS",
            "dateline": f"{city} --",
            "body": body,
            "verdict": (
                f"JIMMY THE GREEK'S VERDICT: {_CORR_LABEL[slip['correlationType']].upper()} "
                f"· {int(avg_prob * 100)}% COMPOSITE · {len(legs)}-LEG PARLAY · "
                f"LINE UNDER INVESTIGATION"
            ),
        })

    return articles
