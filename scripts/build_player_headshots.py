"""
Build lake/gold/nfl/player_headshots.csv (gsis_id -> headshot URL) from nflverse's
public players table. Only players active since 2024 are kept (about 3k rows).

    python3 scripts/build_player_headshots.py
"""
import csv
import io
import urllib.request
from pathlib import Path

URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
OUT = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "player_headshots.csv"


def main() -> None:
    raw = urllib.request.urlopen(URL, timeout=90).read().decode("utf-8")
    rows = [(r["gsis_id"], r["headshot"]) for r in csv.DictReader(io.StringIO(raw))
            if r.get("gsis_id") and r.get("headshot") and (r.get("last_season") or "0") >= "2024"]
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player_id", "headshot_url"])
        w.writerows(sorted(rows))
    print(f"wrote {len(rows)} headshots to {OUT}")


if __name__ == "__main__":
    main()
