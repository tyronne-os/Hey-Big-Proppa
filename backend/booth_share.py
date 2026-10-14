"""
Big Proppa booth share card: a 1200x630 PNG of the week (the size social previews use).

Reuses the video renderer's helpers so the card and the video look like the same show.
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageDraw

import booth_video as bv

W, H = 1200, 630
BG, PANEL, GOLD, INK, DIM, GREEN, RED = bv.BG, bv.PANEL, bv.GOLD, bv.INK, bv.DIM, bv.GREEN, bv.RED


def render(recap: dict, bankroll: float, site: str = "Big Proppa") -> bytes:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 52), fill=GOLD)
    d.text((28, 26), f"BIG PROPPA BOOTH   ·   WEEK {recap['week']}", font=bv._font(24), fill=(18, 11, 0), anchor="lm")
    d.text((W - 28, 26), recap.get("key_stat", ""), font=bv._font(22), fill=(18, 11, 0), anchor="rm")

    delta = recap.get("bankroll_delta", 0)
    d.text((40, 120), f"{'+' if delta >= 0 else '-'}${abs(delta):.0f}", font=bv._font(96), fill=GREEN if delta >= 0 else RED, anchor="lm")
    d.text((40, 192), "THIS WEEK", font=bv._font(20), fill=DIM, anchor="lm")
    d.text((300, 120), f"${bankroll:.0f}", font=bv._font(64), fill=INK, anchor="lm")
    d.text((300, 176), "BANKROLL", font=bv._font(20), fill=DIM, anchor="lm")

    pow_ = recap.get("play_of_week")
    d.rounded_rectangle((40, 224, 1160, 470), radius=16, fill=PANEL)
    if pow_:
        tag = {"heartbreaker": RED, "clutch": GREEN, "bust": (120, 113, 108)}[pow_["kind"]]
        d.rounded_rectangle((40, 224, 1160, 262), radius=16, fill=tag)
        d.text((62, 243), "PLAY OF THE WEEK", font=bv._font(20), fill=(255, 255, 255), anchor="lm")
        head = bv._headshot(pow_.get("headshot", ""), 150)
        if head:
            im.paste(head, (66, 290), head)
        else:
            bv._circle(im, (141, 365), 75, (44, 36, 64), GOLD, "".join(w[0] for w in pow_["player_name"].split()[:2]), bv._font(48))
        d.text((250, 300), pow_["player_name"], font=bv._font(44), fill=INK)
        d.text((250, 354), f"{'OVER' if pow_['is_over'] else 'UNDER'} {bv._fmt(pow_['line'])} {pow_['label']}", font=bv._font(26), fill=DIM)
        d.text((250, 398), pow_["headline"], font=bv._font(36), fill=GOLD)
        mx = max(pow_["actual"], pow_["line"]) * 1.25 or 1
        bx0, bx1, by = 250, 1120, 446
        d.rounded_rectangle((bx0, by, bx1, by + 12), radius=6, fill=(14, 10, 24))
        hit = pow_["actual"] > pow_["line"] if pow_["is_over"] else pow_["actual"] < pow_["line"]
        d.rounded_rectangle((bx0, by, bx0 + (bx1 - bx0) * pow_["actual"] / mx, by + 12), radius=6, fill=GREEN if hit else RED)
        lx = bx0 + (bx1 - bx0) * pow_["line"] / mx
        d.rectangle((lx - 1, by - 6, lx + 1, by + 18), fill=(255, 255, 255))
    else:
        d.text((600, 347), recap["title"], font=bv._font(36), fill=INK, anchor="mm")

    record = (recap.get("booth") or {}).get("record") or {}
    for i, host in enumerate(bv.ORDER):
        cx = 100 + i * 250
        info = bv.HOSTS[host]
        bv._circle(im, (cx, 540), 34, info["color"], None, info["initials"], bv._font(24), bv._host_photo(host, 34))
        w, l = record.get(host, [0, 0])
        d.text((cx + 50, 530), info["short"], font=bv._font(22), fill=INK, anchor="lm")
        d.text((cx + 50, 556), f"{w}-{l}", font=bv._font(20), fill=DIM, anchor="lm")

    d.text((W - 40, 540), "Can you beat the booth?", font=bv._font(30), fill=GOLD, anchor="rm")
    d.text((W - 40, 578), site, font=bv._font(22), fill=DIM, anchor="rm")

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()
