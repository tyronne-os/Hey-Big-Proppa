"""
Money Ball audio — voices the show script with LOCAL Kokoro (no inference API, no subscription).

We downloaded the model + voices (kokoro-v1.0.onnx, voices-v1.0.bin) from the official
thewh1teagle/kokoro-onnx release and run it on CPU via onnxruntime. Two voices for the
cast: MY BOO (host, af_heart) + BIG PROPPA (analyst, am_michael). Each persona line is
voiced, then the clips are concatenated into one audio file. Cached per day.

Fully local and free — this is the open-source "real voice" for the Money Ball podcast.
"""
from __future__ import annotations

import os
import struct
import wave
from datetime import datetime
from pathlib import Path

import moneyball

# Kokoro files (downloaded to the repo root) and the cast voices.
_KOKORO_MODEL = "kokoro-v1.0.onnx"
_KOKORO_VOICES = "voices-v1.0.bin"
_BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "moneyball"

VOICES = {
    "MY BOO": "af_heart",       # warm, playful female host
    "BIG PROPPA": "am_michael",  # confident male analyst
}

_ENGINE = None


def _engine():
    """Lazy-load the Kokoro engine once."""
    global _ENGINE
    if _ENGINE is None:
        from kokoro_onnx import Kokoro
        root = Path(__file__).resolve().parent.parent
        _ENGINE = Kokoro(str(root / _KOKORO_MODEL), str(root / _KOKORO_VOICES))
    return _ENGINE


def _voice_line(text: str, speaker: str) -> bytes | None:
    """Synthesize one line as WAV bytes."""
    try:
        voice = VOICES.get(speaker, "af_heart")
        samples, sr = _engine().create(text, voice=voice, speed=1.0)
        buf = io_bytes = None
        import io
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
        return buf.getvalue()
    except Exception:
        return None


def _stitch(clips: list[bytes]) -> bytes:
    """Properly merge WAV clips into one continuous WAV.

    Raw WAV concatenation breaks because each clip has its own header + length field;
    players only read the first header. So we strip the headers, concatenate the PCM
    frames, and write a single valid WAV with the combined length.
    """
    import io
    import struct as _s

    channels, sampwidth, framerate = 1, 2, 24000
    frames = b""
    for c in clips:
        try:
            w = wave.open(io.BytesIO(c), "r")
            if w.getframerate() != framerate or w.getnchannels() != channels:
                w.close()
                continue
            frames += w.readframes(w.getnframes())
            w.close()
        except Exception:
            continue
    if not frames:
        return b""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(frames)
    return out.getvalue()


def generate_audio() -> bytes | None:
    """Generate the full episode audio, cached per day."""
    _BASE.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    out = _BASE / f"moneyball_{day}.wav"
    if out.exists():
        return out.read_bytes()

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
        return Response("Could not generate Money Ball audio (check the Kokoro model files).", status_code=503)
    return Response(audio, media_type="audio/wav", headers={"Content-Disposition": "inline"})


if __name__ == "__main__":
    audio = generate_audio()
    print("audio bytes:", len(audio) if audio else None)
