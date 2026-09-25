"""
Build lake/gold/nfl/team_game_stats.csv -- one row per team per regular-season
game, modern era only (2023 onward: current rules and the legal-betting
era), with the TeamRankings-style team stats the matchup predictor uses.
Offense columns are this team's; the defense's "opponent-" stats come from
joining the opponent's row (backend/matchup.py does that).

Sources (nflverse, raw files land in lake/bronze/nflverse/, never committed):
  schedules/games.csv                  finals, home/away, neutral site
  pbp/play_by_play_{season}.csv.gz     everything else, one season at a time

Red-zone TD % is exact: a red-zone trip is a drive that reached the opponent
20 (drive_inside20), and it scores when fixed_drive_result == 'Touchdown'.

Run from the repo root:
    backend/.venv/bin/python scripts/build_team_game_stats.py [--seasons 2023-2026]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
BRONZE = REPO / "lake" / "bronze" / "nflverse"
GOLD = REPO / "lake" / "gold" / "nfl"
RELEASES = "https://github.com/nflverse/nflverse-data/releases/download"

PBP_COLS = [
    "game_id", "season", "season_type", "posteam", "defteam", "fixed_drive", "fixed_drive_result",
    "drive_inside20", "play_type", "pass_attempt", "complete_pass", "passing_yards", "pass_touchdown",
    "rush_attempt", "rushing_yards", "rush_touchdown", "sack", "interception", "fumble", "fumble_lost",
    "touchdown", "td_team", "two_point_attempt", "solo_tackle", "tackle_with_assist",
    "pass_defense_1_player_id", "pass_defense_2_player_id",
]

OUT_COLS = [
    "season", "week", "game_id", "game_date", "team", "opponent", "home", "points_for", "points_against",
    "margin", "win", "tds", "rz_trips", "rz_tds", "rush_att", "rush_yds", "rush_tds", "dropbacks",
    "completions", "pass_yds", "pass_tds", "sacks_taken", "ints_thrown", "fumbles", "fumbles_lost",
    "def_passes_defended", "def_tackles_solo", "def_tackles_total",
]


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=600) as resp, tmp.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    tmp.rename(dest)
    return dest


# pbp uses current franchise codes; the schedule keeps the historical ones.
RELOCATED = {"STL": "LA", "SD": "LAC", "OAK": "LV"}


def season_games(games: pd.DataFrame, season: int) -> pd.DataFrame:
    g = games[(games["season"] == season) & (games["game_type"] == "REG")]
    g = g.dropna(subset=["home_score", "away_score"]).copy()
    g["home_team"] = g["home_team"].replace(RELOCATED)
    g["away_team"] = g["away_team"].replace(RELOCATED)
    return g


def team_rows(pbp: pd.DataFrame, games: pd.DataFrame) -> list[dict]:
    plays = pbp[(pbp["season_type"] == "REG") & (pbp["two_point_attempt"].fillna(0) == 0)]
    # Official box scores count kneels as rushes and spikes as pass attempts.
    scrimmage = plays[plays["play_type"].isin(["pass", "run", "qb_kneel", "qb_spike"])]

    off = scrimmage.groupby(["game_id", "posteam"]).agg(
        rush_att=("rush_attempt", "sum"),
        rush_yds=("rushing_yards", "sum"),
        dropbacks=("pass_attempt", "sum"),
        completions=("complete_pass", "sum"),
        pass_yds=("passing_yards", "sum"),
        sacks_taken=("sack", "sum"),
        ints_thrown=("interception", "sum"),
        fumbles=("fumble", "sum"),
        fumbles_lost=("fumble_lost", "sum"),
    )

    td = plays[plays["touchdown"].fillna(0) == 1]
    tds = td.groupby(["game_id", "td_team"]).size().rename("tds")
    rush_tds = td[td["rush_touchdown"] == 1].groupby(["game_id", "td_team"]).size().rename("rush_tds")
    pass_tds = td[td["pass_touchdown"] == 1].groupby(["game_id", "td_team"]).size().rename("pass_tds")

    drives = plays.dropna(subset=["fixed_drive"]).drop_duplicates(["game_id", "posteam", "fixed_drive"])
    rz = drives[drives["drive_inside20"] == 1]
    rz_trips = rz.groupby(["game_id", "posteam"]).size().rename("rz_trips")
    rz_tds = rz[rz["fixed_drive_result"] == "Touchdown"].groupby(["game_id", "posteam"]).size().rename("rz_tds")

    pd_count = (scrimmage["pass_defense_1_player_id"].notna().astype(int)
                + scrimmage["pass_defense_2_player_id"].notna().astype(int))
    dfn = scrimmage.assign(pd_count=pd_count).groupby(["game_id", "defteam"]).agg(
        def_passes_defended=("pd_count", "sum"),
        def_tackles_solo=("solo_tackle", "sum"),
        def_tackles_assisted=("tackle_with_assist", "sum"),
    )

    def val(series_or_frame, key, col=None, default=0.0):
        try:
            v = series_or_frame.loc[key] if col is None else series_or_frame.loc[key, col]
        except KeyError:
            return default
        return float(v) if pd.notna(v) else default

    rows = []
    for _, g in games.iterrows():
        neutral = g["location"] == "Neutral"
        for team, opp, pf, pa, is_home in (
            (g["home_team"], g["away_team"], g["home_score"], g["away_score"], True),
            (g["away_team"], g["home_team"], g["away_score"], g["home_score"], False),
        ):
            key = (g["game_id"], team)
            if key not in off.index:
                raise SystemExit(f"pbp missing offense rows for {key}")
            margin = float(pf) - float(pa)
            row = {
                "season": int(g["season"]), "week": int(g["week"]), "game_id": g["game_id"],
                "game_date": g["gameday"], "team": team, "opponent": opp,
                "home": 0 if neutral else (1 if is_home else -1),
                "points_for": int(pf), "points_against": int(pa), "margin": int(margin),
                "win": 1.0 if margin > 0 else (0.5 if margin == 0 else 0.0),
                "tds": val(tds, key), "rz_trips": val(rz_trips, key), "rz_tds": val(rz_tds, key),
                "rush_tds": val(rush_tds, key), "pass_tds": val(pass_tds, key),
                "def_passes_defended": val(dfn, key, "def_passes_defended"),
                "def_tackles_solo": val(dfn, key, "def_tackles_solo"),
                "def_tackles_total": val(dfn, key, "def_tackles_solo") + val(dfn, key, "def_tackles_assisted"),
            }
            for col in off.columns:
                row[col] = val(off, key, col)
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2023-2026")
    ap.add_argument("--keep-raw", action="store_true", help="keep downloaded pbp files in lake/bronze")
    args = ap.parse_args()
    lo, hi = (int(x) for x in args.seasons.split("-"))

    games_path = download(f"{RELEASES}/schedules/games.csv", BRONZE / "games.csv")
    games = pd.read_csv(games_path, low_memory=False)

    rows: list[dict] = []
    for season in range(lo, hi + 1):
        g = season_games(games, season)
        if g.empty:
            print(f"{season}: no finished regular-season games, skipped")
            continue
        pbp_path = BRONZE / f"pbp_{season}.csv.gz"
        if not pbp_path.exists():
            download(f"{RELEASES}/pbp/play_by_play_{season}.csv.gz", pbp_path)
        pbp = pd.read_csv(pbp_path, usecols=PBP_COLS, low_memory=False)
        season_rows = team_rows(pbp, g)
        rows.extend(season_rows)
        print(f"{season}: {len(g)} games -> {len(season_rows)} team rows")
        if not args.keep_raw:
            pbp_path.unlink()

    out = GOLD / "team_game_stats.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["season"], r["week"], r["game_id"], r["team"])):
            w.writerow({c: r[c] for c in OUT_COLS})
    print(f"wrote {len(rows)} rows -> {out.relative_to(REPO)}")

    register_chart("team_game_stats", "scripts/build_team_game_stats.py",
                   "one row per team per regular-season game, 2023+", len(rows),
                   "nflverse pbp + schedules (derived)")


def register_chart(name: str, source: str, grain: str, row_count: int, source_name: str) -> None:
    """Add or replace this chart's row in _index.csv, the status gate every endpoint honors."""
    index = GOLD / "_index.csv"
    with index.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys())
    rows = [r for r in rows if r["chart_name"] != name]
    rows.append({
        "chart_name": name,
        "source_table_or_view": source,
        "grain": grain,
        "row_count": str(row_count),
        "last_exported_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_name": source_name,
        "status": "ok" if row_count else "empty",
    })
    with index.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
