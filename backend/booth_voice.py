"""
Big Proppa booth voices: Kokoro-82M (open weights, Apache-2.0) runs on CPU, one clip per line.

Each host gets a fixed voice. Clips are cached on disk by sha1(host + text), so a replayed week
costs nothing and the same line always sounds the same. Synthesis is serialised: the model is not
thread-safe and the Space runs one worker.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from pathlib import Path

SAMPLE_RATE = 24000
VOICES = {
    "Jonah Jacques": ("a", "am_michael"),
    "MY BOO": ("a", "af_heart"),
    "Julian Feltus": ("b", "bm_george"),
}
CACHE = Path(os.environ.get("BOOTH_VOICE_CACHE", Path(tempfile.gettempdir()) / "jimmy_booth_voice"))
_LOCK = threading.Lock()
_PIPES: dict[str, object] = {}


class VoiceUnavailable(RuntimeError):
    pass


def _pipe(lang: str):
    if lang not in _PIPES:
        try:
            from kokoro import KPipeline
        except ImportError as e:
            raise VoiceUnavailable("kokoro is not installed") from e
        _PIPES[lang] = KPipeline(lang_code=lang)
    return _PIPES[lang]


def _key(host: str, text: str) -> Path:
    digest = hashlib.sha1(f"{host}\x00{text}".encode("utf-8")).hexdigest()
    return CACHE / f"{digest}.wav"


def clip(host: str, text: str) -> Path:
    """Path to a WAV for this host saying this text, synthesising it on first request."""
    if host not in VOICES:
        raise VoiceUnavailable(f"no voice for {host}")
    path = _key(host, text)
    if path.exists():
        return path
    lang, voice = VOICES[host]
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        raise VoiceUnavailable("voice runtime is not installed") from e

    with _LOCK:
        if path.exists():
            return path
        pieces = [np.asarray(audio) for _, _, audio in _pipe(lang)(text, voice=voice, speed=1.0) if audio is not None]
        if not pieces:
            raise VoiceUnavailable("empty synthesis")
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.wav")
        sf.write(str(tmp), np.concatenate(pieces), SAMPLE_RATE)
        tmp.replace(path)
    return path

