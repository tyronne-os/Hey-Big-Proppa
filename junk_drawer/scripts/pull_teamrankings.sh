#!/usr/bin/env bash
# Fully automatic TeamRankings reference pull with integrity manifest.
#
# One-time archival snapshot of chart pages (team-stats, player-stats, standings,
# schedules, odds, projections) per league, for schema/design modeling in Phase 1.
# Live data comes from API wrappers later -- this is NOT a recurring scraper.
#
# NHL is intentionally excluded -- TeamRankings has no NHL section (confirmed 2026-09-24,
# see docs/NHL_GAP.md). NCF uses the /college-football/ URL prefix for stat/player-stat deep
# links (the short /ncf/ alias only works for the section root and a few top-level pages).
#
# Runs with ZERO prompts. Behavior:
#   - If ~/.teamrankings_cookies.txt exists and is valid, it's used (authenticated pull).
#   - If not, the script proceeds anonymously (no premium stats) -- it never stops
#     to ask you for anything.
#
# One-time setup for authenticated data (do this yourself, outside this script --
# a script cannot read your browser session for you, that's a browser security boundary):
#   1. Log into https://www.teamrankings.com in your browser.
#   2. Install a "Get cookies.txt LOCALLY" extension (or DevTools -> Application -> Cookies).
#   3. Export as Netscape format, save to: ~/.teamrankings_cookies.txt
#   4. chmod 600 ~/.teamrankings_cookies.txt
#   5. Re-run this script -- it will auto-detect the file and use it.
set -uo pipefail   # no -e: a single failed fetch must not kill the whole run

# ========== CONFIG ==========
BASE="https://www.teamrankings.com"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$HOME/frontal-lobe2/lake/bronze/reference/teamrankings/$STAMP"
COOKIES="${COOKIES:-$HOME/.teamrankings_cookies.txt}"
WAIT=2   # base seconds between requests; be polite

# League -> URL path segment (ncf's deep links need the long form; section root still uses ncf)
declare -A LEAGUE_PATH=( [nfl]=nfl [nba]=nba [mlb]=mlb [ncf]=ncf )
declare -A LEAGUE_STAT_PATH=( [nfl]=nfl [nba]=nba [mlb]=mlb [ncf]=college-football )
LEAGUES=(nfl ncf nba mlb)
PATHS=(stats standings schedules odds projections player-stats rankings)

declare -A SAMPLE_STAT=(
  [nfl]="stat/points-per-game"
  [ncf]="stat/points-per-game"
  [nba]="stat/points-per-game"
  [mlb]="stat/runs-per-game"
)

mkdir -p "$DEST"
MANIFEST="$DEST/manifest.csv"
LOG="$DEST/pull.log"
echo "url,local_filename,http_status,sha256,bytes,fetched_at_utc" > "$MANIFEST"
exec > >(tee -a "$LOG") 2>&1

echo "=== TeamRankings reference pull starting $STAMP ==="
echo "Destination: $DEST"

# ========== COOKIE / AUTH MODE (auto-detected, never blocks) ==========
AUTH_MODE="anonymous"
if [[ -f "$COOKIES" && -s "$COOKIES" ]]; then
  chmod 600 "$COOKIES" 2>/dev/null || true
  code=$(curl -sS -b "$COOKIES" -A "$UA" --compressed --max-time 15 \
             -w '%{http_code}' -o /dev/null "$BASE/nfl/stats/" 2>/dev/null || echo "000")
  if [[ "$code" == "200" ]]; then
    AUTH_MODE="authenticated"
    echo "Cookie file found and valid -> running AUTHENTICATED (HTTP $code)."
  else
    COOKIES="/dev/null"
    echo "Cookie file found but auth check returned HTTP $code -> falling back to ANONYMOUS."
  fi
else
  COOKIES="/dev/null"
  echo "No cookie file at $COOKIES -> running ANONYMOUS (premium stats/projections will be missing)."
  echo "  To include those next time: export cookies to that path (see script header) and re-run."
fi

# ========== FETCH ==========
fetch() {
  local url="$1"
  local rel="${url#"$BASE"/}"; rel="${rel%/}"
  [[ -z "$rel" ]] && rel="index"
  local out="$DEST/${rel//\//_}.html"
  mkdir -p "$(dirname "$out")"

  local code
  code=$(curl -sS -L -b "$COOKIES" -A "$UA" \
              --compressed --max-time 45 \
              -w '%{http_code}' -o "$out" "$url" 2>/dev/null || echo "000")

  local sha bytes
  if [[ -f "$out" ]]; then
    sha=$(sha256sum "$out" | awk '{print $1}')
    bytes=$(stat -c%s "$out")
  else
    sha="ERROR"; bytes=0
  fi

  printf '"%s","%s",%s,%s,%s,%s\n' "$url" "$(basename "$out")" "$code" "$sha" "$bytes" "$(date -u +%FT%TZ)" >> "$MANIFEST"
  printf '[%3s] %7s bytes  %s\n' "$code" "$bytes" "$url"

  sleep $(( WAIT + RANDOM % 2 ))
}

for lg in "${LEAGUES[@]}"; do
  echo "==== $lg ===="
  seg="${LEAGUE_PATH[$lg]}"
  statseg="${LEAGUE_STAT_PATH[$lg]}"
  fetch "$BASE/$seg/"
  for p in "${PATHS[@]}"; do
    fetch "$BASE/$seg/$p/"
  done
  fetch "$BASE/$statseg/${SAMPLE_STAT[$lg]}"
done

# ========== SUMMARY ==========
total=$(( $(wc -l < "$MANIFEST") - 1 ))
ok=$(awk -F, 'NR>1 && $3=="200"' "$MANIFEST" | wc -l)
bad=$(( total - ok ))

echo
echo "=== DONE ($AUTH_MODE) ==="
echo "Snapshot:  $DEST"
echo "Manifest:  $MANIFEST"
echo "Log:       $LOG"
echo "Fetched:   $total   OK: $ok   Non-200: $bad"
echo
if [[ "$bad" -gt 0 ]]; then
  echo "Non-200 responses (these paths likely need adjusting for that league):"
  awk -F, 'NR>1 && $3!="200" {print "  HTTP "$3"  "$1}' "$MANIFEST" | tr -d '"'
fi
