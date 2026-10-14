"""
Obsidian vault export of a BETTER-VERSE Strategy Lab study.

Unzip it, choose "Open folder as vault" in Obsidian, then open Graph view (Ctrl/Cmd+G). Every tier, style, strategy,
slip shape and big winner is a note joined by [[wikilinks]], so the graph shows what connects to what and which kinds of parlay win most:

    Tier ── Strategy (style x tier) ── Style
                    │
                 Slip shape ── Better (a winner who won with it)

    Rankings ── the parlay types and strategies most likely to make money (probability of profit)

The vault ships with .obsidian/graph.json already coloring nodes: tier colors, bright yellow = top-5 by probability of
profit, gold = proven money-maker, red = confident loser, white = better. Charts are Mermaid blocks (Obsidian renders them natively) with a plain table beside each one.

CLI: python betterverse_obsidian.py <study_id> <out_dir>
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import betterverse_bettors as mb

ROOT = "BETTER-VERSE Vault"
_BAD = re.compile(r'[\\/:*?"<>|#^\[\]]')


def _fn(s: str) -> str:
    return re.sub(r"\s+", " ", _BAD.sub("-", s)).strip(" .")[:80] or "note"


def _shape(sig: str) -> str:
    """'anytime_td:yes x3|ml:fav +SGP' -> 'Anytime TD x3 + Moneyline fav (SGP)'"""
    name = {"spread": "Spread", "ml": "Moneyline", "total": "Game Total", "pass_yds": "Pass Yds", "pass_tds": "Pass TDs",
            "completions": "Completions", "pass_att": "Pass Att", "ints": "INTs", "rush_yds": "Rush Yds", "rec_yds": "Rec Yds",
            "receptions": "Receptions", "rush_rec_yds": "Rush+Rec", "anytime_td": "Anytime TD"}
    sgp = sig.endswith(" +SGP")
    body = sig[: -len(" +SGP")] if sgp else sig
    parts = []
    for p in body.split("|"):
        m = re.match(r"([a-z_]+):([a-z]+)(?: x(\d+))?$", p)
        if not m:
            parts.append(p)
            continue
        mk, side, n = m.groups()
        parts.append(f"{name.get(mk, mk)}{'' if side == 'yes' else ' ' + side}{' x' + n if n else ''}")
    return " + ".join(parts) + (" (SGP)" if sgp else "")


def _pct(x, d=1) -> str:
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def _prob_rows(r: dict) -> str:
    if r.get("p_both_seasons") is None:
        return ""
    ps = r.get("p_profit_by_season", {})
    return (f"| **Chance of profit in BOTH seasons** | {r['p_both_seasons'] * 100:.0f}% |\n"
            f"| Chance of profit, each season | 2024 {ps.get('2024', 0) * 100:.0f}% · 2025 {ps.get('2025', 0) * 100:.0f}% |\n"
            f"| Chance of profit overall | {r['p_profit'] * 100:.0f}% |\n"
            f"| Chance of beating the field | {r['p_beat_field'] * 100:.0f}% |\n"
            f"| Slip hit probability (95% range) | {r['hit_rate'] * 100:.1f}% ({r['hit_lo'] * 100:.1f}% to {r['hit_hi'] * 100:.1f}%) |\n"
            f"| Probability the price implies | {r['implied'] * 100:.1f}% |\n"
            f"| Edge vs the price | {r['edge_pts'] * 100:+.1f} pts |\n"
            f"| Probability rank (1 = most likely to profit) | #{r['rank_p']} |\n")


def _chart_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", s)).strip()[:26] or "shape"


def _line_bar(title: str, labels: list[str], bars: list[float], line: list[float], y_title: str) -> str:
    xs = ", ".join(f'"{l}"' for l in labels)
    hi = max(bars + line + [1.0])
    return ("```mermaid\nxychart-beta\n"
            f'    title "{title}"\n    x-axis [{xs}]\n    y-axis "{y_title}" 0 --> {int(hi * 1.15) + 1}\n'
            f"    bar [{', '.join(f'{v:.1f}' for v in bars)}]\n    line [{', '.join(f'{v:.1f}' for v in line)}]\n```\n")


def _quadrant(title: str, rows: list[dict], name_fn) -> str:
    mx = max((r["hit_rate"] for r in rows), default=1) or 1
    pts = "\n".join(f"    {_chart_name(name_fn(r))} {i}: [{r['hit_rate'] / mx:.2f}, {r['p_both_seasons']:.2f}]" for i, r in enumerate(rows, 1))
    return ("```mermaid\nquadrantChart\n"
            f"    title {title}\n    x-axis Rarely hits --> Hits often\n    y-axis Unlikely to profit --> Likely to profit in both seasons\n"
            "    quadrant-1 Hits often and profits\n    quadrant-2 Rare wins that still profit\n"
            "    quadrant-3 Rare and losing\n    quadrant-4 Hits often but loses\n" + pts + "\n```\n")


def _bar(title: str, labels: list[str], values: list[float], y_title: str = "ROI %") -> str:
    vals = [round(v * 100, 1) for v in values]
    lo, hi = min(vals + [0]), max(vals + [0])
    pad = max(2, (hi - lo) * 0.1)
    xs = ", ".join('"' + l.replace('"', "'") + '"' for l in labels)
    return ("```mermaid\nxychart-beta\n"
            f'    title "{title}"\n    x-axis [{xs}]\n    y-axis "{y_title}" {int(lo - pad)} --> {int(hi + pad) + 1}\n'
            f"    bar [{', '.join(str(v) for v in vals)}]\n```\n")


def _fm(**kw) -> str:
    lines = ["---"]
    for k, v in kw.items():
        if isinstance(v, (list, tuple)):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n---\n"


def build(study: dict) -> dict[str, str]:
    """{relative path inside the vault: markdown text}"""
    dims = study["dims"]
    field = study["field"]["roi"]
    notes: dict[str, str] = {}
    tier_names = {k: v["label"] for k, v in mb.TIERS.items()}
    arch_names = {k: v["label"] for k, v in mb.ARCHETYPES.items()}

    def link(folder: str, name: str, alias: str | None = None) -> str:
        return f"[[{folder}/{_fn(name)}|{alias or name}]]"

    def cell(wikilink: str) -> str:
        """Inside a Markdown table the alias pipe must be escaped or Obsidian splits the column."""
        return wikilink.replace("|", "\\|")

    # ---- strategies (style x tier)
    strat_rows = dims["style_tier"]
    strat_note = {}
    for r in strat_rows:
        arch, tier = r["key"].split("|")
        strat_note[r["key"]] = _fn(f"{arch_names[arch]} - {tier_names[tier]}")
    shape_rows = {r["key"]: r for r in dims["shape"]}
    shape_note = {k: _fn(_shape(k)) for k in shape_rows}
    uses: dict[str, list[tuple[str, dict]]] = {}                      # shape -> [(strategy key, usage row)]
    for key, lst in study.get("style_shapes", {}).items():
        for u in lst:
            uses.setdefault(u["shape"], []).append((key, u))

    def flags(r: dict) -> list[str]:
        t = []
        if r["profitable_95"]:
            t.append("proven")
        if r.get("profitable_both_seasons"):
            t.append("both-seasons")
        if r["ci_hi"] < 0:
            t.append("loser")
        if r.get("rank_p") and r["rank_p"] <= 5:
            t.append("top5")
        return t

    def metrics_table(r: dict) -> str:
        s24, s25 = r["by_season"].get("2024"), r["by_season"].get("2025")
        return ("| Metric | Value |\n|---|---|\n"
                f"| ROI (profit per $ staked) | {_pct(r['roi'])} |\n"
                f"| 95% range | {_pct(r['ci_lo'])} to {_pct(r['ci_hi'])} |\n"
                f"| vs the whole field | {_pct(r['edge_vs_field'])} |\n"
                f"| Profit per slip | ${r['profit_per_slip']:+.2f} |\n"
                f"| Slip hit rate | {r['hit_rate'] * 100:.1f}% |\n"
                f"| Bettor-seasons in profit | {r['profitable_share'] * 100:.0f}% |\n"
                f"| 2024 / 2025 ROI | {_pct(s24, 0)} / {_pct(s25, 0)} |\n"
                f"| Slips | {r['slips']:,} |\n" + _prob_rows(r))

    for r in strat_rows:
        arch, tier = r["key"].split("|")
        body = _fm(type="strategy", tags=[f"tier/{tier}"] + flags(r), roi=r["roi"], ci_lo=r["ci_lo"], ci_hi=r["ci_hi"], slips=r["slips"],
                   p_both_seasons=r.get("p_both_seasons", ""), p_profit=r.get("p_profit", ""), hit_prob=r["hit_rate"], implied=r.get("implied", ""), rank=r.get("rank_p", ""))
        body += f"# {r['label']}\n\n{link('Tiers', tier_names[tier])} · {link('Styles', arch_names[arch])}\n\n"
        body += f"*{mb.ARCHETYPES[arch]['desc']}.*\n\n" + metrics_table(r)
        verdict = ("**Proven money-maker**: the whole 95% range is above zero. " if r["profitable_95"] else
                   "**Confident loser**: the whole 95% range is below zero. " if r["ci_hi"] < 0 else
                   "Not proven either way: the 95% range includes break-even. ")
        body += f"\n{verdict}{'It was in profit in both real seasons. ' if r.get('profitable_both_seasons') else ''}\n"
        sh = study.get("style_shapes", {}).get(r["key"], [])
        if sh:
            body += "\n## Slip shapes this strategy actually builds\n\n| Shape | Slips | Won | ROI |\n|---|---|---|---|\n"
            for u in sh:
                nm = cell(link("Shapes", _shape(u["shape"]))) if u["shape"] in shape_note else _shape(u["shape"])
                body += f"| {nm} | {u['slips']} | {u['wins']} | {_pct(u['roi'])} |\n"
        notes[f"Strategies/{strat_note[r['key']]}.md"] = body

    # ---- shapes
    for k, r in shape_rows.items():
        body = _fm(type="shape", tags=["shape"] + flags(r), roi=r["roi"], ci_lo=r["ci_lo"], ci_hi=r["ci_hi"], slips=r["slips"],
                   p_both_seasons=r.get("p_both_seasons", ""), p_profit=r.get("p_profit", ""), hit_prob=r["hit_rate"], implied=r.get("implied", ""), rank=r.get("rank_p", ""))
        body += f"# {_shape(k)}\n\n`{k}`\n\n" + metrics_table(r)
        if k in uses:
            body += "\n## Strategies that build it\n\n"
            for sk, u in sorted(uses[k], key=lambda x: -x[1]["slips"]):
                if sk in strat_note:
                    body += f"- {link('Strategies', strat_note[sk], [x for x in strat_rows if x['key'] == sk][0]['label'])}: {u['slips']} slips, {_pct(u['roi'])} ROI\n"
        notes[f"Shapes/{shape_note[k]}.md"] = body

    # ---- tiers and styles
    for r in dims["tier"]:
        tier = r["key"]
        mine = [x for x in strat_rows if x["key"].endswith("|" + tier)]
        body = _fm(type="tier", tags=[f"tier/{tier}"], roi=r["roi"], slips=r["slips"])
        body += f"# {r['label']}\n\n*{mb.TIERS[tier]['note']}.*\n\n" + metrics_table(r)
        body += "\n## ROI by style in this tier\n\n"
        if mine:
            body += _bar(f"{r['label']}: ROI by style (%)", [x["label"].split(" · ")[0] for x in mine], [x["roi"] for x in mine])
        for x in sorted(mine, key=lambda x: -x["roi"]):
            body += f"- {link('Strategies', strat_note[x['key']], x['label'])}: {_pct(x['roi'])}\n"
        notes[f"Tiers/{_fn(r['label'])}.md"] = body
    for r in dims["archetype"]:
        arch = r["key"]
        mine = [x for x in strat_rows if x["key"].startswith(arch + "|")]
        body = _fm(type="style", tags=["style"], roi=r["roi"], slips=r["slips"])
        body += f"# {r['label']}\n\n*{mb.ARCHETYPES[arch]['desc']}.*\n\n" + metrics_table(r) + "\n## By tier\n\n"
        for x in sorted(mine, key=lambda x: -x["roi"]):
            body += f"- {link('Strategies', strat_note[x['key']], x['label'])}: {_pct(x['roi'])}\n"
        notes[f"Styles/{_fn(r['label'])}.md"] = body

    # ---- winners
    seen: dict[str, int] = {}
    winners = study["top_winners"][:15] + [w for w in study["rookie_winners"] if w not in study["top_winners"][:15]][:10]
    for w in winners:
        base = _fn(f"{w['username']} (u{w['universe']} {w['season']})")
        seen[base] = seen.get(base, 0) + 1
        tier = next((k for k, v in tier_names.items() if v == w["tier_label"]), "casual")
        arch = next((k for k, v in arch_names.items() if v == w["label"]), None)
        skey = f"{arch}|{tier}" if arch else None
        body = _fm(type="better", tags=["better", f"tier/{tier}"], final_bankroll=w["final_bankroll"], season=w["season"])
        body += f"# {w['username']}\n\n{link('Tiers', w['tier_label'])} · {w['label']} · ${w['unit']} base bets · {w['season']} season\n\n"
        body += f"Turned **$100** into **${w['final_bankroll']:,.2f}** over {w['slips']} slips.\n\n"
        sig = w["best_signature"]
        shp = link("Shapes", _shape(sig)) if sig in shape_note else f"`{_shape(sig)}`"
        body += f"Biggest win: {shp} at {w['best_odds']:.1f}x paid ${w['best_payout']:,.2f}.\n\n"
        if skey in strat_note:
            r = next(x for x in strat_rows if x["key"] == skey)
            body += f"Their strategy overall: {link('Strategies', strat_note[skey], r['label'])} ({_pct(r['roi'])} ROI). A big win is not proof of a good strategy.\n"
        notes[f"Betters/{base}.md"] = body

    # ---- findings
    makers = [r for r in strat_rows + dims["shape"] if r["profitable_95"]]
    losers = sorted([r for r in strat_rows if r["ci_hi"] < 0], key=lambda r: r["roi"])[:12]

    def ref(r):
        if "|" in r["key"] and r["key"] in strat_note:
            return link("Strategies", strat_note[r["key"]], r["label"])
        return link("Shapes", _shape(r["key"])) if r["key"] in shape_note else _shape(r["key"])

    notes["Findings/Money Makers.md"] = (_fm(type="finding", tags=["finding", "proven"]) + "# Money makers\n\nStrategies and slip shapes whose whole 95% range "
                                         "is above break-even. The tag `proven` colors them gold in the graph.\n\n" +
                                         ("\n".join(f"- {ref(r)}: {_pct(r['roi'])} (95%: {_pct(r['ci_lo'])} to {_pct(r['ci_hi'])}), "
                                                    f"{'profit in both seasons' if r.get('profitable_both_seasons') else 'not in profit in both seasons'}" for r in makers)
                                          or "Nothing cleared that bar in this study."))
    notes["Findings/Money Losers.md"] = (_fm(type="finding", tags=["finding", "loser"]) + "# Money losers\n\nWhole 95% range below break-even.\n\n" +
                                         "\n".join(f"- {ref(r)}: {_pct(r['roi'])}, {r['hit_rate'] * 100:.0f}% of slips hit" for r in losers))
    legs = dims["n_legs"]
    notes["Findings/Legs Per Slip.md"] = (_fm(type="finding", tags=["finding"]) + "# Legs per slip\n\nEvery extra leg multiplies the book's margin.\n\n" +
                                          _bar("ROI by legs per slip (%)", [r["label"].replace(" slip", "") for r in legs], [r["roi"] for r in legs]) +
                                          "\n| Legs | ROI | Hit rate | Slips |\n|---|---|---|---|\n" +
                                          "\n".join(f"| {r['label']} | {_pct(r['roi'])} | {r['hit_rate'] * 100:.1f}% | {r['slips']:,} |" for r in legs))
    sg = dims["sgp"]
    notes["Findings/Same-Game vs Cross-Game.md"] = (_fm(type="finding", tags=["finding"]) + "# Same-game parlays vs cross-game slips\n\n" +
                                                    _bar("ROI (%)", [r["label"] for r in sg], [r["roi"] for r in sg]) +
                                                    "\nBooks price same-game legs below the plain product of their odds because the legs move together.\n\n" +
                                                    "\n".join(f"- {r['label']}: {_pct(r['roi'])} over {r['slips']:,} slips" for r in sg))

    notes["Glossary.md"] = _fm(type="glossary") + GLOSSARY

    # ---- probability rankings: which kinds of parlay win most
    def rank_note(rows, folder, notename, title, name_fn, link_fn, blurb):
        rk = sorted([r for r in rows if r.get("rank_p")], key=lambda r: r["rank_p"])
        if not rk:
            return []
        top = rk[:10]
        body = _fm(type="ranking", tags=["ranking"]) + f"# {title}\n\n{blurb}\n\n"
        body += _bar("Chance of profit in BOTH real seasons, top 10 (%)", [f"#{r['rank_p']}" for r in top], [r["p_both_seasons"] for r in top], "probability %")
        body += "\n" + _line_bar("Slip hit probability (bars) vs probability the price implies (line), top 10 (%)", [f"#{r['rank_p']}" for r in top],
                                  [r["hit_rate"] * 100 for r in top], [r["implied"] * 100 for r in top], "%")
        body += "\n" + _quadrant("Hit rate vs chance of profit, top 12", rk[:12], name_fn) + "\n"
        body += ("| Rank | Parlay | Profit both seasons | Profit overall | Beat field | Slips hit (95% range) | Price implies | Edge | ROI | Slips |\n"
                 "|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rk:
            body += (f"| {r['rank_p']} | {cell(link_fn(r))} | {r['p_both_seasons'] * 100:.0f}% | {r['p_profit'] * 100:.0f}% | {r['p_beat_field'] * 100:.0f}% | "
                     f"{r['hit_rate'] * 100:.1f}% ({r['hit_lo'] * 100:.1f}-{r['hit_hi'] * 100:.1f}) | {r['implied'] * 100:.1f}% | {r['edge_pts'] * 100:+.1f} | {_pct(r['roi'])} | {r['slips']:,} |\n")
        notes[f"Rankings/{notename}.md"] = body
        return rk

    shape_link = lambda r: link("Shapes", _shape(r["key"]))
    strat_link = lambda r: link("Strategies", strat_note[r["key"]], r["label"])
    blurb = ("Ranked by the **probability of making money in both real seasons**: each season is resampled on its own (300 bootstrap replays of the "
             "betters' results) and the two probabilities are multiplied. A parlay type that won big in one season and lost in the other ranks low. "
             "Also shown: how often the slip hits against the probability its price implies, and whether it beats the field.")
    shape_rank = rank_note(dims["shape"], "Rankings", "Parlay Shape Ranking", "Parlay shape ranking: which kinds of parlay win most",
                           lambda r: _shape(r["key"]), shape_link, blurb)
    strat_rank = rank_note(strat_rows, "Rankings", "Strategy Ranking", "Strategy ranking: which betting styles win most",
                           lambda r: r["label"], strat_link, blurb)
    hub = _fm(type="ranking", tags=["ranking", "hub"]) + "# Top parlays\n\nThe parlay types and strategies most likely to make money, best first. They are the bright nodes in the graph.\n\n"
    if shape_rank:
        hub += "## Parlay shapes\n\n" + "\n".join(
            f"{i}. {shape_link(r)}: {r['p_both_seasons'] * 100:.0f}% chance of profit in both seasons, {r['hit_rate'] * 100:.0f}% of slips hit vs {r['implied'] * 100:.0f}% implied, ROI {_pct(r['roi'])}"
            for i, r in enumerate(shape_rank[:10], 1)) + "\n\n"
    if strat_rank:
        hub += "## Strategies\n\n" + "\n".join(
            f"{i}. {strat_link(r)}: {r['p_both_seasons'] * 100:.0f}% chance of profit in both seasons, ROI {_pct(r['roi'])}" for i, r in enumerate(strat_rank[:8], 1)) + "\n\n"
    hub += "Full tables: " + link("Rankings", "Parlay Shape Ranking") + " · " + link("Rankings", "Strategy Ranking") + "\n"
    notes["Rankings/Top Parlays.md"] = hub

    # ---- home
    tiers = dims["tier"]
    home = _fm(type="home", tags=["home"], study=study["study_id"], created=study.get("created", ""))
    home += (f"# BETTER-VERSE report\n\nStudy `{study['study_id']}`: **{study['universes']} universes × {study['bettors_per_universe']} betters × 2 real seasons** = "
             f"{study['bettor_seasons']:,} bettor-seasons and {study['slips']:,} slips. The house kept **{-field * 100:.1f}%** of every dollar staked "
             f"(2024 {-study['field']['by_season']['2024'] * 100:.1f}%, 2025 {-study['field']['by_season']['2025'] * 100:.1f}%).\n\n")
    home += "## Headlines\n\n" + "\n".join(f"- {h}" for h in study["headlines"]) + "\n\n"
    home += "## ROI by tier\n\n" + _bar("ROI by tier (%)", [r["label"] for r in tiers], [r["roi"] for r in tiers])
    home += "\n" + "\n".join(f"- {link('Tiers', r['label'])}: {_pct(r['roi'])}" for r in tiers) + "\n\n"
    top = strat_rows[:8]
    if shape_rank:
        tp = shape_rank[:8]
        home += "## Most winning parlay types\n\n" + _bar("Chance of profit in both real seasons (%)", [_shape(r["key"])[:22] for r in tp], [r["p_both_seasons"] for r in tp], "probability %")
        home += "\n" + "\n".join(f"{i}. {shape_link(r)}: {r['p_both_seasons'] * 100:.0f}% both seasons · {r['hit_rate'] * 100:.0f}% hit vs {r['implied'] * 100:.0f}% implied · ROI {_pct(r['roi'])}"
                                  for i, r in enumerate(tp, 1)) + "\n\n" + "Full ranking: " + link("Rankings", "Parlay Shape Ranking") + " · " + link("Rankings", "Top Parlays") + "\n\n"
    home += "## Best and worst strategies by ROI\n\n" + _bar("Top 8 strategies, ROI (%)", [r["label"].replace(" · ", " / ") for r in top], [r["roi"] for r in top])
    bot = strat_rows[-8:]
    home += _bar("Bottom 8 strategies, ROI (%)", [r["label"].replace(" · ", " / ") for r in bot], [r["roi"] for r in bot])
    home += ("\n## Explore\n\n- " + link("Findings", "Money Makers") + "\n- " + link("Findings", "Money Losers") + "\n- " + link("Findings", "Legs Per Slip") +
             "\n- " + link("Findings", "Same-Game vs Cross-Game") + "\n- " + link("Rankings", "Top Parlays") + "\n- [[Glossary]]\n\n")
    home += ("## How the pieces connect\n\n```mermaid\nflowchart LR\n  B[Betters<br/>Sharp Grinder Casual Degen] --> E[Season engine<br/>real 2024-25 results]\n"
             "  E --> L[Strategy Lab<br/>pooled universes]\n  L --> V[This vault]\n  L --> M[MY BOO priors]\n  M --> J[JIMMY]\n  M --> K[JEV]\n```\n\n")
    home += "Open **Graph view** (Ctrl/Cmd+G). Bright yellow nodes are the top-5 parlay types and strategies by probability of profit, gold nodes are proven money-makers, red nodes are confident losers, white nodes are individual winning betters.\n"
    notes["00 Home.md"] = home

    colors = {"tag:#tier/sharp": "38bdf8", "tag:#tier/grinder": "34d399", "tag:#tier/casual": "fbbf24", "tag:#tier/degen": "f87171",
              "tag:#top5": "ffe14d", "tag:#proven": "ffb81c", "tag:#loser": "ef4444", "tag:#ranking": "f472b6", "tag:#better": "ffffff", "tag:#shape": "a78bfa"}
    order = ["tag:#top5", "tag:#proven", "tag:#loser", "tag:#ranking", "tag:#better", "tag:#shape", "tag:#tier/sharp", "tag:#tier/grinder", "tag:#tier/casual", "tag:#tier/degen"]
    notes[".obsidian/graph.json"] = json.dumps({
        "collapse-filter": False, "search": "", "showTags": False, "showAttachments": False, "hideUnresolved": False, "showOrphans": True,
        "collapse-color-groups": False,
        "colorGroups": [{"query": q, "color": {"a": 1, "rgb": int(colors[q], 16)}} for q in order],
        "collapse-display": True, "showArrow": True, "textFadeMultiplier": -0.5, "nodeSizeMultiplier": 1.2, "lineSizeMultiplier": 1,
        "collapse-forces": True, "centerStrength": 0.45, "repelStrength": 12, "linkStrength": 1, "linkDistance": 220, "scale": 1, "close": True}, indent=2)
    notes[".obsidian/app.json"] = json.dumps({"defaultViewMode": "preview", "showFrontmatter": False}, indent=2)
    return notes


GLOSSARY = """# Glossary

- **ROI**: profit per $1 staked. +10% means $10 won for every $100 bet; -20% means $20 lost.
- **95% range**: the span ROI would land in about 95 times out of 100 if the study were rerun. If the whole range is above 0 the strategy is *proven* to make money; if the whole range is below 0 it is a *confident loser*.
- **Proven $**: the whole 95% range is above zero.
- **Chance of profit in both seasons**: resample each real season on its own (300 replays of the betters' results), take the share of replays in profit for each season, multiply. High = consistent; a one-season fluke scores low.
- **Hit probability vs price-implied probability**: how often the slip really cashes vs the probability its odds say (1 / decimal odds). Edge in points is the gap.
- **Both seasons**: in profit in 2024 and in 2025. A strategy that only wins one season probably fit that season's luck.
- **Hold**: the share of every dollar the house keeps.
- **Slip shape**: the structure of a slip without the players, e.g. `Anytime TD x3` or `Game Total over x2`.
- **SGP**: same-game parlay. Books pay it less than the plain product of the leg odds.
- **Tier**: Sharp (researches), Grinder (disciplined), Casual (gut), Degen (chases, long parlays).
- **Universe**: one roster of betters with its own random picks. The Strategy Lab pools many.
- **Table limits**: $5/$10 base bets, max $10 until $500, $20 until $1,000, then free.
"""


def zip_bytes(study: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, text in build(study).items():
            z.writestr(f"{ROOT}/{path}", text)
    return buf.getvalue()


def write_vault(study: dict, out: Path) -> int:
    n = 0
    for path, text in build(study).items():
        f = Path(out) / ROOT / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        n += 1
    return n


if __name__ == "__main__":
    import betterverse_study as st
    sid, out = sys.argv[1], Path(sys.argv[2])
    study = st.load(sid)
    if study is None:
        sys.exit(f"study {sid} not found")
    print(f"wrote {write_vault(study, out)} notes to {out / ROOT}")
