"""
Money Ball audio — voices the show script with Kokoro via NVIDIA's free TTS endpoint.

Uses the same NVIDIA integration pattern as intelligence.py:
  POST https://integrate.api.nvidia.com/v1/audio/speech
  Authorization: Bearer NVIDIA_API_KEY
  json: { model: <kokoro>, input: text, voice: <voice>, response_format: "mp3" }

Two voices for the cast: MY BOO (host) + BIG PROPPA (analyst). Each persona line is
voiced, then the clips are concatenated into one audio file. Cached per day.
"""
from __future__ import annotations

import os
import io
from pathlib import Path

import httpx

import moneyball

_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_KOKORO_MODEL = "nvidia/parakeet-tdt-0.6b-v2"  # placeholder; set to your Kokoro model id
_BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "moneyball"

# two distinct Kokoro voices for the cast
VOICES = {
    "MY BOO": "af_heart",      # warm, playful female
    "BIG PROPPA": "am_michael",  # confident male
}


def _key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "")


def _voice_line(text: str, speaker: str) -> bytes | None:
    key = _key()
    if not key:
        return None
    voice = VOICES.get(speaker, "af_heart")
    try:
        resp = httpx.post(
            f"{_NVIDIA_BASE}/audio/speech",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": _KOKORO_MODEL, "input": text, "voice": voice, "response_format": "mp3"},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _stitch(clips: list[bytes]) -> bytes:
    """Join MP3 clips with a short gap. (Simplest: concat — MP3 frame headers allow it.)"""
    gap = b""  # MP3 concat needs no explicit gap; add a pause clip if desired
    return gap.join(clips)


def generate_audio() -> bytes | None:
    """Generate the full episode audio, cached per day."""
    _BASE.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    day = datetime.now().strftime("%Y-%m-%d")
    out = _BASE / f"moneyball_{day}.mp3"
    if out.exists():
        return out.read_bytes()

    key = _key()
    if not key:
        return None
    show = moneyball.generate_show()
    clips = []
    for line in show["lines"]:
        clip = _voice_line(line["text"], line["speaker"])
        if clip:
            clips.append(clip)
    if not clips:
        return None
    audio = _stitch(clips)
    out.write_bytes(audio)
    return audio


def serve_audio():
    from fastapi.responses import Response
    audio = generate_audio()
    if audio is None:
        return Response("NVIDIA_API_KEY not set (or no voice configured). Set the key to enable Money Ball audio.", status_code=503)
    return Response(audio, media_type="audio/mpeg", headers={"Content-Disposition": "inline"})


if __name__ == "__main__":
    audio = generate_audio()
    print("audio bytes:", len(audio) if audio else None)
