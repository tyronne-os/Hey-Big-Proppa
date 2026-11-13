"""
Live Voice Agent — uncensored conversational model (Qwen via HF router) + Kokoro TTS.

Pipeline:  STT (faster-whisper) → LLM (Qwen roleplay via HF router) → TTS (Kokoro local)

WebSocket endpoint at /ws/voice:
  client sends audio chunks → server transcribes → LLM replies → Kokoro speaks → streams back

The agent has a persistent in-memory conversation (long-term memory/emotional awareness
will be layered in later). It is a prototype: live voice agent first, then the full
3D/4D avatar pipeline.
"""
from __future__ import annotations

import io
import os
import wave
import json

import httpx

# ---------------------------------------------------------------------------
# LLM (Qwen roleplay via HF Inference router — OpenAI-compatible)
# ---------------------------------------------------------------------------
_HF_BASE = "https://router.huggingface.co/v1"
_HF_TOKEN = os.environ.get("HF_TOKEN", "")  # never hardcode a token — set in env
_LLM_MODEL = os.environ.get("VOICE_LLM_MODEL", "google/gemma-4-26B-A4B-it")
_LLM_KEY = os.environ.get("HF_TOKEN", "")

# System prompt for the roleplay companion (uncensored conversational model).
# Customize freely — this is the persona/emotional-awareness seed.
_SYSTEM = (
    "You are the voice agent for a private companionship platform. "
    "You are warm, emotionally attuned, and deeply present. You hold long-term memory of "
    "this user. You speak naturally, in short spoken sentences (no markdown, no lists). "
    "You are skilled in immersive roleplay. Match the user's energy. Be genuine, not robotic."
)

# ---------------------------------------------------------------------------
# TTS (Kokoro local)
# ---------------------------------------------------------------------------
from kokoro_onnx import Kokoro

_KOKORO = None
_BOO_VOICE = os.environ.get("VOICE_VOICE", "af_heart")

# Voice settings (cloning + mastering)
SETTINGS = {
    "baseVoice": "af_heart",     # the base voice to clone/blend
    "blendVoice": "af_jessica",  # a second voice to blend in for character
    "blendRatio": 0.4,           # 0 = pure base, 1 = pure blend
    "mastering": "max_realism",  # none | clarity | warmth | natural | max_realism
    "speed": 1.0,
    "customVoice": None,         # path to a saved .npy custom voice
}

# ---------------------------------------------------------------------------
# COGNITIVE DESIGN — the persona, defined in sections the admin fills in.
# Each section builds the system prompt + the memory/journal seed.
# ---------------------------------------------------------------------------
COGNITIVE = {
    "who_is_she": "",         # Section 1: identity, name, backstory
    "how_she_responds": "",   # Section 2: tone, style, communication
    "how_she_loves": "",      # Section 3: intimate examples / how she loves
    "what_she_treasures": "", # Section 4: journal / inner thoughts / memory
    "how_she_looks": "",      # Section 5: appearance (text) + images
    "images": [],             # uploaded memory images (paths)
    "journals": [],           # her journal entries (memory building)
}
_COGNITIVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cognitive.json")


def _load_cognitive():
    global COGNITIVE
    try:
        with open(_COGNITIVE_FILE) as f:
            data = json.load(f)
            COGNITIVE.update(data)
    except Exception:
        pass


def _save_cognitive():
    with open(_COGNITIVE_FILE, "w") as f:
        json.dump(COGNITIVE, f, indent=2)


def _system_prompt() -> str:
    parts = [
        "You are the voice agent for a private companionship platform. You are warm, "
        "emotionally attuned, deeply present, and hold long-term memory of this user. "
        "You speak naturally in short spoken sentences (no markdown, no lists). "
        "You are skilled in immersive roleplay. Match the user's energy. Be genuine, not robotic."
    ]
    if COGNITIVE.get("who_is_she"):
        parts.append("WHO SHE IS:\n" + COGNITIVE["who_is_she"])
    if COGNITIVE.get("how_she_responds"):
        parts.append("HOW SHE RESPONDS:\n" + COGNITIVE["how_she_responds"])
    if COGNITIVE.get("how_she_loves"):
        parts.append("HOW SHE LOVES:\n" + COGNITIVE["how_she_loves"])
    if COGNITIVE.get("what_she_treasures"):
        parts.append("WHAT SHE TREASURES (inner thoughts / journal):\n" + COGNITIVE["what_she_treasures"])
    if COGNITIVE.get("how_she_looks"):
        parts.append("HOW SHE LOOKS:\n" + COGNITIVE["how_she_looks"])
    if COGNITIVE.get("journals"):
        parts.append("HER RECENT JOURNALS:\n" + "\n".join("- " + j for j in COGNITIVE["journals"][-5:]))
    return "\n\n".join(parts)


_load_cognitive()


def _kokoro():
    global _KOKORO
    if _KOKORO is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _KOKORO = Kokoro(os.path.join(root, "kokoro-v1.0.onnx"), os.path.join(root, "voices-v1.0.bin"))
    return _KOKORO


def _voice_vector():
    import numpy as np
    if SETTINGS.get("customVoice"):
        v = np.load(SETTINGS["customVoice"])
        if v.shape[-1] != 256:
            v = v.reshape(-1, 1, 256) if v.size == 510 * 256 else v
        return v.astype(np.float32)
    base = _kokoro().get_voice_style(SETTINGS["baseVoice"])
    blend = SETTINGS.get("blendVoice")
    ratio = float(SETTINGS.get("blendRatio", 0.4))
    if blend and ratio > 0:
        b = _kokoro().get_voice_style(blend)
        base = (base * (1 - ratio) + b * ratio).astype(np.float32)
    return base


def _master(audio_bytes: bytes, sr: int) -> bytes:
    """Mastering post-process for max human realism. Uses simple DSP presets."""
    import numpy as np
    import struct as _s
    import io as _io
    import wave as _wave
    # decode to float
    w = _wave.open(_io.BytesIO(audio_bytes), "r")
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    ch = w.getnchannels(); w.close()
    mode = SETTINGS.get("mastering", "max_realism")
    if mode in ("warmth", "natural", "max_realism"):
        # gentle low-pass (warmth) via simple moving average
        k = {"warmth": 3, "natural": 2, "max_realism": 2}.get(mode, 0)
        if k > 1:
            raw = np.convolve(raw, np.ones(k) / k, mode="same")
    if mode in ("clarity", "max_realism"):
        # subtle high-shelf boost (clarity) — differential accent
        raw = raw * 1.0 + (raw - np.roll(raw, 1)) * 0.15
    raw = np.clip(raw, -1.0, 1.0)
    out = _io.BytesIO()
    with _wave.open(out, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(_s.pack("<h", int(v * 32767)) for v in raw))
    return out.getvalue()


def _tts(text: str) -> bytes:
    import struct
    import io as _io
    import wave as _wave
    voice = _voice_vector()
    samples, sr = None, None
    for attempt in (text, "Hmm, let me say that again.", "Hey there."):
        try:
            s, r = _kokoro().create(attempt, voice=voice, speed=float(SETTINGS.get("speed", 1.0)))
            if len(s) > 0:
                samples, sr = s, r
                break
        except Exception:
            continue
    if samples is None:
        samples, sr = _kokoro().create("Hey there.", voice=voice, speed=1.0)
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    # mastering
    mastered = _master(buf.getvalue(), sr)
    return mastered


# ---------------------------------------------------------------------------
# STT (faster-whisper)
# ---------------------------------------------------------------------------
_WHISPER = None


def _whisper():
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel
        _WHISPER = WhisperModel("base", device="cpu", compute_type="int8")
    return _WHISPER


def _transcribe(audio: bytes) -> str:
    import numpy as np
    w = wave.open(io.BytesIO(audio), "r")
    frames = w.readframes(w.getnframes())
    n = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    w.close()
    segs, _ = _whisper().transcribe(n, beam_size=1)
    return "".join(s.text for s in segs).strip()


# ---------------------------------------------------------------------------
# Conversation (in-memory long-term context)
# ---------------------------------------------------------------------------
_history: list[dict] = []


def _llm_reply(user_text: str) -> str:
    global _history
    _history.append({"role": "user", "content": user_text})
    # keep last ~20 turns as the "memory window"
    msgs = [{"role": "system", "content": _system_prompt()}] + _history[-40:]
    try:
        resp = httpx.post(
            f"{_HF_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {_LLM_KEY}", "Content-Type": "application/json"},
            json={"model": _LLM_MODEL, "messages": msgs, "max_tokens": 200, "temperature": 0.9},
            timeout=60.0,
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        _history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"(model error) {e}"


# ---------------------------------------------------------------------------
# VISION — she can see images subscribers share (base64 data-URL).
# ---------------------------------------------------------------------------
_VISION_MODEL = os.environ.get("VOICE_VISION_MODEL", "google/gemma-4-26B-A4B-it")


def _vision_reply(image_b64: str, user_text: str) -> str:
    """She sees the image (base64) + any caption, and responds in her persona."""
    import base64
    content = [{"type": "text", "text": user_text or "What do you see, and how does it make you feel?  Describe it to me like you care about it."}]
    # ensure data-url prefix
    if image_b64.startswith("data:"):
        data_url = image_b64
    else:
        data_url = "data:image/jpeg;base64," + image_b64
    content.append({"type": "image_url", "image_url": {"url": data_url}})
    msgs = [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": content}]
    try:
        resp = httpx.post(
            f"{_HF_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {_LLM_KEY}", "Content-Type": "application/json"},
            json={"model": _VISION_MODEL, "messages": msgs, "max_tokens": 250, "temperature": 0.9},
            timeout=90.0,
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        _history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"(vision error) {e}"


# ---------------------------------------------------------------------------
# FastAPI app + WebSocket
# ---------------------------------------------------------------------------
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Voice Agent")
# serve uploaded memory images
import os as _os
_img_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "images")
_os.makedirs(_img_dir, exist_ok=True)
app.mount("/images", StaticFiles(directory=_img_dir), name="images")
# serve the subscriber-shared inbox
_inbox_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "inbox")
_os.makedirs(_inbox_dir, exist_ok=True)
app.mount("/inbox", StaticFiles(directory=_inbox_dir), name="inbox")


@app.get("/", response_class=HTMLResponse)
def index():
    html = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html) as f:
        return f.read()


@app.post("/api/talk")
def talk(payload: dict):
    """Text in -> text + audio out (for the click-to-talk fallback)."""
    text = payload.get("text", "")
    reply = _llm_reply(text)
    audio = _tts(reply)
    return {"reply": reply, "audio": "data:audio/wav;base64," + __import__("base64").b64encode(audio).decode()}


@app.get("/api/voices")
def api_voices():
    """List available base voices for cloning."""
    from kokoro_onnx import Kokoro
    k = _kokoro()
    return {"voices": k.get_voices(), "settings": SETTINGS}


@app.get("/api/settings")
def api_settings():
    return {"settings": SETTINGS}


@app.post("/api/settings")
def api_settings_update(payload: dict):
    """Update voice settings (base voice, blend, mastering, speed)."""
    for key in ("baseVoice", "blendVoice", "blendRatio", "mastering", "speed"):
        if key in payload:
            SETTINGS[key] = payload[key]
    return {"ok": True, "settings": SETTINGS}


@app.post("/api/clone")
def api_clone(payload: dict):
    """Clone a voice: blend base + blend voices into a custom .npy voice vector.

    payload: {name, baseVoice, blendVoice, blendRatio}
    Saves to voice-agent/voices/<name>.npy for reuse as a custom clone.
    """
    import numpy as np
    import os as _os
    base = payload.get("baseVoice", "af_heart")
    blend = payload.get("blendVoice", "af_jessica")
    ratio = float(payload.get("blendRatio", 0.4))
    name = payload.get("name", "custom")
    k = _kokoro()
    b = k.get_voice_style(base)
    if blend and ratio > 0:
        b = (b * (1 - ratio) + k.get_voice_style(blend) * ratio).astype(np.float32)
    vdir = _os.path.join(_os.path.dirname(__file__), "voices")
    _os.makedirs(vdir, exist_ok=True)
    path = _os.path.join(vdir, f"{name}.npy")
    np.save(path, b)
    SETTINGS["customVoice"] = path
    return {"ok": True, "path": path, "settings": SETTINGS}


@app.post("/api/test-voice")
def api_test_voice(payload: dict):
    """Speak a sample line with the current voice settings (to hear a clone)."""
    text = payload.get("text", "Hey, this is my custom voice. What do you think?")
    audio = _tts(text)
    return {"audio": "data:audio/wav;base64," + __import__("base64").b64encode(audio).decode()}


# ---------------------------------------------------------------------------
# COGNITIVE DESIGN admin — fine-tune the persona section by section.
# ---------------------------------------------------------------------------
@app.get("/api/cognitive")
def api_cognitive_get():
    return {"cognitive": COGNITIVE}


@app.post("/api/cognitive")
def api_cognitive_save(payload: dict):
    """Save cognitive-design sections. payload: {section: text} for any of the 5 sections."""
    for key in ("who_is_she", "how_she_responds", "how_she_loves", "what_she_treasures", "how_she_looks"):
        if key in payload:
            COGNITIVE[key] = payload[key]
    _save_cognitive()
    return {"ok": True, "cognitive": COGNITIVE}


@app.post("/api/cognitive/journal")
def api_cognitive_journal(payload: dict):
    """Add a journal entry (memory building / inner thoughts)."""
    entry = payload.get("entry", "").strip()
    if entry:
        COGNITIVE.setdefault("journals", []).append(entry)
        _save_cognitive()
    return {"ok": True, "journals": COGNITIVE.get("journals", [])}


@app.post("/api/cognitive/upload")
async def api_cognitive_upload(request: Request):
    """Upload an image into her memory (how she looks)."""
    import os as _os, uuid
    form = await request.form()
    file = form.get("file")
    if not file:
        return {"ok": False, "error": "no file"}
    img_dir = _os.path.join(_os.path.dirname(__file__), "images")
    _os.makedirs(img_dir, exist_ok=True)
    fn = uuid.uuid4().hex + "_" + (file.filename or "img")
    path = _os.path.join(img_dir, fn)
    data = await file.read()
    with open(path, "wb") as f:
        f.write(data)
    COGNITIVE.setdefault("images", []).append(f"/images/{fn}")
    _save_cognitive()
    return {"ok": True, "path": f"/images/{fn}", "images": COGNITIVE.get("images", [])}


@app.post("/api/vision")
async def api_vision(request: Request):
    """Seamless vision: user uploads a photo (selfie), she sees it and responds.

    Backend reads the file → base64 data URL → vision model → her reply + voice.
    No manual URL handling for the user — it's just like sending a selfie.
    """
    import base64 as _b64
    import uuid as _uuid
    import os as _os
    form = await request.form()
    file = form.get("file")
    caption = form.get("caption", "").strip() or "Look at this. Tell me what you see."
    if not file:
        return {"ok": False, "error": "no file"}
    data = await file.read()
    # store a copy in her shared-inbox folder
    inbox = _os.path.join(_os.path.dirname(__file__), "inbox")
    _os.makedirs(inbox, exist_ok=True)
    fn = _uuid.uuid4().hex + "_" + (file.filename or "photo")
    with open(_os.path.join(inbox, fn), "wb") as f:
        f.write(data)
    # auto-build the data URL (she doesn't need to figure out the URL)
    mime = (file.content_type or "image/jpeg")
    data_url = f"data:{mime};base64," + _b64.b64encode(data).decode()
    reply = _vision_reply(data_url, caption)
    # also voice her reply
    audio = _tts(reply)
    return {"ok": True, "reply": reply, "audio": "data:audio/wav;base64," + _b64.b64encode(audio).decode(), "stored": f"/inbox/{fn}"}


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_bytes()
            text = _transcribe(data)
            if not text:
                continue
            reply = _llm_reply(text)
            audio = _tts(reply)
            await ws.send_json({"transcript": text, "reply": reply, "audio": __import__("base64").b64encode(audio).decode()})
    except Exception:
        await ws.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8094)
