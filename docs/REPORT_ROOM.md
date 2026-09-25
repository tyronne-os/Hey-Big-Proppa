# NFL sports report room

The test for this layer, as stated by the user: could an NFL beat writer sit
down, run a query against the lake, and file a matchup preview -- injuries,
inactives-track, current news, transactions -- without opening a browser tab?

Verified 2026-09-25 with a real upcoming matchup (BUF @ LAC, and separately
KC @ PHI to confirm it isn't team-specific): **yes, for everything short of the
final inactives list** (see gap below). Run it yourself:

```bash
PYTHONPATH=.pylibs python3 scripts/matchup_report.py BUF LAC
PYTHONPATH=.pylibs python3 scripts/matchup_report.py KC PHI --json
```

## Sources

| Data | Source | Confirmed live 2026-09-25 |
|---|---|---|
| Official weekly injury report (practice status, game status, injury type) | nflverse `injuries_2026.csv` | 692 rows, weeks 1-3, real Questionable/Doubtful/Out designations |
| Injury narrative (why it matters, who benefits, return timeline) | ESPN `/injuries` | 800 player rows across all 32 teams in one call |
| News (headlines + summary, tagged to specific players/teams) | ESPN `/news`, `/news?team=<abbr>` | Real dated headlines, structured `athleteId`/`teamId` tags per article (no fuzzy text matching needed) |
| Transactions (signings, releases, IR moves) | ESPN `/transactions` | Real dated roster moves, e.g. "Placed TE David Njoku on injured reserve" |

### The ESPN host caveat (same risk as flagged before, different host)

`site.web.api.espn.com` is the host actually used here. The more commonly
documented host, `site.api.espn.com`, returned HTTP 403 in this environment.
Neither host is an officially sanctioned public API -- ESPN does not publish
documentation or a ToS grant for either. This is the same "unofficial,
undocumented, can change or vanish without notice" risk already flagged
elsewhere in this project for ESPN data, just a currently-reachable host
instead of the more commonly cited one. If this host stops responding,
re-check for a working alternate rather than assuming ESPN data is gone
entirely.

## What this does NOT cover (honest gap)

**The final inactives list is not in this pipeline.** The NFL only releases
official inactives ~90 minutes before kickoff, and neither nflverse nor the
ESPN endpoints used here publish that specific list on that timeline. What
this pipeline gives you, in order of how close to gameday it gets:

1. Wed/Thu/Fri practice participation (`practice_status`) -- nflverse
2. Wed/Thu/Fri game-status designation (`report_status`: Questionable/
   Doubtful/Out) -- nflverse, becomes available partway through the week
   (confirmed: as of this test, week 3's designations hadn't posted yet even
   though practice data had -- the report script uses the latest week that
   *has* a status, not just the latest week number, to avoid silently
   printing blanks)
3. Narrative context and return-date estimates -- ESPN

For the actual final inactive list, a same-day source would be needed later;
not built here.

## Schema (`sql/nfl_report_room_schema.sql`)

- `silver.nfl_injury_report` -- official weekly report, one row per player/week
- `silver.nfl_injury_narrative` -- ESPN narrative, snapshotted (not
  overwritten) so status changes through the week aren't lost; re-running the
  ingest script multiple times in testing will show multiple snapshots for the
  same player, which is by design, not a duplicate bug
- `silver.nfl_news_article` + `silver.nfl_news_article_tag` -- articles and
  their player/team/league tags, split into two tables since one article can
  tag multiple subjects
- `silver.nfl_transaction` -- roster moves, deduplicated by a stable
  `transaction_id`
- `gold.v_nfl_team_report_card` -- all four sections unioned for one team
- `gold.nfl_player_id_bridge` -- scaffold for linking ESPN athlete IDs to
  nflverse `gsis_id`; not populated yet (name-matching logic not built), so
  don't rely on it for joins yet -- use team + player name for now

## The actual deliverable: `scripts/matchup_report.py`

Takes two team abbreviations, returns (or `--json` dumps) a full bundle per
team: official injuries, injury narrative, recent news, transactions, last-3-
weeks team form, and best-price prop lines for that team's players. Built
entirely from `SELECT`s against the lake -- confirmed with two real,
different matchups during testing (not cherry-picked to one team).

## Bugs found and fixed during verification

- `gold.v_nfl_prop_best_price` computes `best_moneyline_price`/
  `best_moneyline_book` correctly, but the first version of
  `matchup_report.py` never selected those columns -- TD-scorer markets
  printed "None (None)" instead of the real price. Fixed; verified real
  moneylines now print (e.g. DraftKings +165 on a player's anytime-TD prop).
- The official injury report query originally used `max(week)` unconditionally,
  which returned blank statuses for a week whose Friday designations hadn't
  posted yet even though practice data existed. Fixed to use the latest week
  that has a non-null `report_status`.
