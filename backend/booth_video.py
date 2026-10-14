"""
Big Proppa booth video: renders a week's recap conversation as an MP4.

Frames are drawn with Pillow (host desk, Play of the Week card, season storylines, subtitles),
the audio is the studio voice clips plus a generated theme bed, and ffmpeg muxes them. No
diffusion model is involved: everything on screen is composed from the recap's own data, so a
video is a deterministic function of the script and costs only CPU time.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SR = 1280, 720, 24, 24000
HOSTS = {
    "Jonah Jacques": {"short": "JONAH", "initials": "JJ", "color": (59, 130, 246), "role": "PLAY-BY-PLAY"},
    "MY BOO": {"short": "MY BOO", "initials": "MB", "color": (225, 29, 72), "role": "ANALYST"},
    "Julian Feltus": {"short": "JULIAN", "initials": "JF", "color": (245, 158, 11), "role": "STRATEGY"},
}
ORDER = ["Jonah Jacques", "MY BOO", "Julian Feltus"]
GOLD, BG, PANEL, INK, DIM = (255, 184, 28), (11, 8, 20), (24, 18, 38), (241, 236, 248), (150, 140, 170)
GREEN, RED = (34, 197, 94), (244, 63, 94)

ClipFn = Callable[[str, str], Path]


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:.1f}"


# ------------------------------------------------------------------ audio

def _theme(seconds: float) -> np.ndarray:
    """A short sports-show bed: kick, snare, hats, saw bass and brass-ish chords, 116 BPM."""
    n = int(seconds * SR)
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(7)
    step = 60 / 116 / 2
    roots, chords = [38, 36, 34, 36], [[62, 66, 69], [60, 64, 67], [58, 62, 65], [60, 64, 67]]
    mtof = lambda m: 440 * 2 ** ((m - 69) / 12)

    def add(sig: np.ndarray, at: float, gain: float):
        i = int(at * SR)
        if i >= n:
            return
        j = min(n, i + len(sig))
        out[i:j] += (sig[: j - i] * gain).astype(np.float32)

    def tone(freq: float, dur: float, saw: bool = True, decay: float = 6.0) -> np.ndarray:
        t = np.arange(int(dur * SR)) / SR
        ph = (t * freq) % 1.0
        wave = (2 * ph - 1) if saw else np.sin(2 * np.pi * freq * t)
        return wave * np.exp(-decay * t)

    t = 0.0
    s = 0
    while t < seconds:
        bar, beat = (s // 8) % 4, s % 8
        if beat in (0, 4):
            tt = np.arange(int(0.2 * SR)) / SR
            add(np.sin(2 * np.pi * (45 + 95 * np.exp(-30 * tt)) * tt) * np.exp(-14 * tt), t, 0.9)
        if beat in (2, 6):
            add(rng.uniform(-1, 1, int(0.14 * SR)) * np.exp(-30 * np.arange(int(0.14 * SR)) / SR), t, 0.35)
        add(rng.uniform(-1, 1, int(0.03 * SR)) * np.exp(-90 * np.arange(int(0.03 * SR)) / SR), t, 0.07 if beat % 2 == 0 else 0.035)
        add(tone(mtof(roots[bar]), step * 0.95, decay=5), t, 0.28)
        if beat in (0, 3):
            for m in chords[bar]:
                add(tone(mtof(m), 0.4 if beat == 0 else 0.22, decay=7), t, 0.07)
        t += step
        s += 1
    peak = float(np.abs(out).max()) or 1.0
    return out / peak * 0.6


def _build_audio(turns: list[dict], clip: ClipFn, intro: float, outro: float):
    """Voices on a timeline with the theme underneath; returns (audio, [(start, end)] per turn)."""
    pieces, spans, cursor, prev = [], [], intro, None
    placed = []
    for t in turns:
        gap = 0.7 if prev and prev != t["speaker"] else 0.22
        cursor += gap
        data, sr = sf.read(str(clip(t["speaker"], t["text"])), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != SR:
            data = np.interp(np.linspace(0, len(data), int(len(data) * SR / sr), endpoint=False), np.arange(len(data)), data).astype(np.float32)
        placed.append((cursor, data))
        spans.append((cursor, cursor + len(data) / SR))
        cursor += len(data) / SR
        prev = t["speaker"]
    total = cursor + outro
    music = _theme(total)
    env = np.full(len(music), 0.55, dtype=np.float32)
    ramp = int(0.25 * SR)
    for start, data in placed:                       # duck the theme under every voice line
        a, b = int(start * SR), int(start * SR) + len(data)
        env[a:b] = 0.13
        env[max(0, a - ramp):a] = np.minimum(env[max(0, a - ramp):a], np.linspace(0.55, 0.13, len(env[max(0, a - ramp):a])))
    mix = music * env
    for start, data in placed:
        a = int(start * SR)
        mix[a:a + len(data)] += data[: len(mix) - a] * 0.95
    return np.clip(mix, -1, 1), spans, total


# ------------------------------------------------------------------ frames

def _headshot(url: str, size: int) -> Optional[Image.Image]:
    if not url:
        return None
    try:
        import requests
        r = requests.get(url, timeout=6)
        img = Image.open(io.BytesIO(r.content)).convert("RGB").resize((size, size))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        img.putalpha(mask)
        return img
    except Exception:
        return None


def _circle(im: Image.Image, xy, r: int, fill, ring=None, text="", font=None):
    d = ImageDraw.Draw(im)
    x, y = xy
    if ring:
        d.ellipse((x - r - 5, y - r - 5, x + r + 5, y + r + 5), fill=ring)
    d.ellipse((x - r, y - r, x + r, y + r), fill=fill)
    if text and font:
        d.text((x, y), text, font=font, fill=(255, 255, 255), anchor="mm")


def _base(recap: dict, head: Optional[Image.Image]) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 54), fill=GOLD)
    d.text((28, 27), f"BIG PROPPA BOOTH   ·   WEEK {recap['week']}", font=_font(24), fill=(18, 11, 0), anchor="lm")
    d.text((W - 28, 27), recap.get("key_stat", ""), font=_font(22), fill=(18, 11, 0), anchor="rm")

    pow_ = recap.get("play_of_week")
    d.rounded_rectangle((28, 76, 700, 372), radius=14, fill=PANEL)
    if pow_:
        tag = {"heartbreaker": RED, "clutch": GREEN, "bust": (120, 113, 108)}[pow_["kind"]]
        d.rounded_rectangle((28, 76, 700, 112), radius=14, fill=tag)
        d.text((48, 94), "PLAY OF THE WEEK", font=_font(20), fill=(255, 255, 255), anchor="lm")
        if head:
            im.paste(head, (50, 138), head)
        else:
            _circle(im, (110, 198), 60, (44, 36, 64), GOLD, "".join(w[0] for w in pow_["player_name"].split()[:2]), _font(40))
        d.text((190, 150), pow_["player_name"], font=_font(34), fill=INK)
        d.text((190, 192), f"{'OVER' if pow_['is_over'] else 'UNDER'} {_fmt(pow_['line'])} {pow_['label']}", font=_font(22), fill=DIM)
        d.text((190, 230), pow_["headline"], font=_font(30), fill=GOLD)
        mx = max(pow_["actual"], pow_["line"]) * 1.25 or 1
        bx0, bx1, by = 52, 676, 318
        d.rounded_rectangle((bx0, by, bx1, by + 16), radius=8, fill=(14, 10, 24))
        hit = pow_["actual"] > pow_["line"] if pow_["is_over"] else pow_["actual"] < pow_["line"]
        d.rounded_rectangle((bx0, by, bx0 + (bx1 - bx0) * pow_["actual"] / mx, by + 16), radius=8, fill=GREEN if hit else RED)
        lx = bx0 + (bx1 - bx0) * pow_["line"] / mx
        d.rectangle((lx - 1, by - 8, lx + 1, by + 24), fill=(255, 255, 255))
        d.text((lx, by + 40), f"LINE {_fmt(pow_['line'])}", font=_font(18), fill=INK, anchor="mm")
        d.text((bx0 + (bx1 - bx0) * pow_["actual"] / mx, by - 18), _fmt(pow_["actual"]), font=_font(20), fill=GOLD, anchor="mm")
    else:
        d.text((364, 224), recap["title"], font=_font(32), fill=INK, anchor="mm")

    st = recap.get("storylines") or {}
    d.rounded_rectangle((724, 76, 1252, 372), radius=14, fill=PANEL)
    d.text((748, 98), "THE BOOTH REMEMBERS", font=_font(20), fill=GOLD, anchor="lm")
    rows = [
        ("HERO", (st.get("hero") or {}).get("player_name", "TBD"), GREEN),
        ("VILLAIN", (st.get("villain") or {}).get("player_name", "None yet"), RED),
        ("RUN", f"{(st.get('run') or {}).get('weeks', 0)} {(st.get('run') or {}).get('kind', '')}", INK),
        ("BANKROLL", f"${(st.get('bankroll') or {}).get('now', 0):.0f}", INK),
        ("LEGS", f"{(st.get('legs_season') or {}).get('hit', 0)}-{(st.get('legs_season') or {}).get('miss', 0)} on the year", INK),
    ]
    for i, (k, v, c) in enumerate(rows):
        y = 142 + i * 44
        d.text((748, y), k, font=_font(17), fill=DIM, anchor="lm")
        d.text((880, y), v, font=_font(24), fill=c, anchor="lm")
    return im


def _frame(base: Image.Image, recap: dict, turn: Optional[dict]) -> Image.Image:
    im = base.copy()
    d = ImageDraw.Draw(im)
    active = turn["speaker"] if turn else None
    for i, h in enumerate(ORDER):
        cx, cy = 230 + i * 410, 440
        info = HOSTS[h]
        on = h == active
        _circle(im, (cx, cy), 44 if on else 38, info["color"], (255, 255, 255) if on else None, info["initials"], _font(30))
        d.text((cx + 64, cy - 14), info["short"], font=_font(24), fill=INK if on else DIM, anchor="lm")
        d.text((cx + 64, cy + 14), info["role"], font=_font(15), fill=DIM, anchor="lm")
    d.rounded_rectangle((28, 500, 1252, 696), radius=14, fill=PANEL)
    if turn:
        color = HOSTS[turn["speaker"]]["color"]
        d.rectangle((28, 500, 36, 696), fill=color)
        f = _font(30)
        lines = _wrap(d, turn["text"], f, 1150)[:4]
        d.text((60, 528), HOSTS[turn["speaker"]]["short"], font=_font(20), fill=color, anchor="lm")
        for i, ln in enumerate(lines):
            d.text((60, 566 + i * 36), ln, font=f, fill=INK)
    return im


def _title_card(recap: dict) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 54), fill=GOLD)
    d.text((W // 2, 27), "BIG PROPPA BOOTH", font=_font(26), fill=(18, 11, 0), anchor="mm")
    d.text((W // 2, 250), f"WEEK {recap['week']}", font=_font(64), fill=GOLD, anchor="mm")
    for i, ln in enumerate(_wrap(d, recap["title"], _font(46), 1100)[:3]):
        d.text((W // 2, 340 + i * 58), ln, font=_font(46), fill=INK, anchor="mm")
    delta = recap.get("bankroll_delta", 0)
    d.text((W // 2, 590), f"{'+' if delta >= 0 else '-'}${abs(delta):.0f}   ·   {recap.get('key_stat', '')}", font=_font(32), fill=GREEN if delta >= 0 else RED, anchor="mm")
    return im


def _outro_card(recap: dict) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 54), fill=GOLD)
    booth = recap.get("booth") or {}
    d.text((W // 2, 27), f"BET THE BOOTH  ·  WEEK {booth.get('pick_week', '')}", font=_font(26), fill=(18, 11, 0), anchor="mm")
    picks = booth.get("picks") or {}
    for i, h in enumerate(ORDER):
        p = picks.get(h)
        if not p:
            continue
        x0 = 28 + i * 414
        d.rounded_rectangle((x0, 100, x0 + 394, 640), radius=16, fill=PANEL)
        _circle(im, (x0 + 197, 190), 48, HOSTS[h]["color"], None, HOSTS[h]["initials"], _font(32))
        d.text((x0 + 197, 262), HOSTS[h]["short"], font=_font(30), fill=INK, anchor="mm")
        w, l = (booth.get("record") or {}).get(h, [0, 0])
        d.text((x0 + 197, 296), f"{w}-{l} on the year", font=_font(20), fill=DIM, anchor="mm")
        for j, ln in enumerate(_wrap(d, p["player_name"], _font(34), 350)[:2]):
            d.text((x0 + 197, 370 + j * 40), ln, font=_font(34), fill=INK, anchor="mm")
        d.text((x0 + 197, 462), f"{'OVER' if p['is_over'] else 'UNDER'} {_fmt(p['line'])}", font=_font(32), fill=GOLD, anchor="mm")
        d.text((x0 + 197, 500), p["label"], font=_font(22), fill=DIM, anchor="mm")
        d.rounded_rectangle((x0 + 112, 560, x0 + 282, 612), radius=26, fill=HOSTS[h]["color"])
        d.text((x0 + 197, 586), "TAIL", font=_font(26), fill=(255, 255, 255), anchor="mm")
    return im


# ------------------------------------------------------------------ render

def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def render(recap: dict, clip: ClipFn, out_path: Path, intro: float = 2.6, outro: float = 5.0) -> Path:
    turns = recap.get("turns") or []
    if not turns:
        raise ValueError("recap has no conversation to render")
    audio, spans, total = _build_audio(turns, clip, intro, outro)
    pow_ = recap.get("play_of_week") or {}
    base = _base(recap, _headshot(pow_.get("headshot", ""), 120) if pow_ else None)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        shots: list[tuple[Path, float]] = []

        def shot(img: Image.Image, dur: float):
            p = tmp_dir / f"f{len(shots):03d}.png"
            img.save(p)
            shots.append((p, dur))

        shot(_title_card(recap), spans[0][0])
        for i, t in enumerate(turns):
            begin = spans[i - 1][1] if i else spans[0][0]
            shot(_frame(base, recap, t), max(0.05, spans[i][1] - begin))
        shot(_outro_card(recap), outro)

        listing = tmp_dir / "frames.txt"
        listing.write_text("".join(f"file '{p}'\nduration {d:.3f}\n" for p, d in shots) + f"file '{shots[-1][0]}'\n")
        wav = tmp_dir / "mix.wav"
        sf.write(str(wav), audio, SR)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part = out_path.with_name(out_path.stem + ".part.mp4")
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(wav),
               "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", str(part)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            part.unlink(missing_ok=True)
            raise RuntimeError(res.stderr[-600:] or "ffmpeg failed")
        part.replace(out_path)
    return out_path
