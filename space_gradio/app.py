"""Gradio-SDK Space in RAW mode: serves the Big Proppa FastAPI app and the built React app, and nothing else.

Gradio supplies only the SDK runtime. No Gradio UI is created or mounted, so there is no Gradio queue, reload watcher,
analytics call or share-link thread that could fail and restart the container.

Anti-loop rules:
  * If the backend fails to import, a tiny fallback app serves the traceback (HTTP 503) and /healthz (200). The Space
    stays up and the error is readable; it does not crash, restart, and crash again.
  * uvicorn runs once with reload off and a single worker. If it cannot start, the process exits once and logs why.
"""
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")   # raw mode: never phone home or start Gradio helpers
os.environ.setdefault("GRADIO_SSR_MODE", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)


def _fallback(error: str):
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"ok": False, "mode": "fallback"}

    @app.get("/{path:path}")
    def broken(path: str):
        return PlainTextResponse("Big Proppa failed to start. Fix the error below and redeploy.\n\n" + error, status_code=503)

    return app


try:
    import main as bp   # the existing FastAPI app, unchanged
    app = bp.app
except BaseException:   # noqa: BLE001  any import-time failure must degrade, never crash-loop
    _err = traceback.format_exc()
    print("STARTUP FAILED (serving fallback app):\n" + _err, flush=True)
    app = _fallback(_err)


if __name__ == "__main__":
    import uvicorn

    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), reload=False, workers=1, timeout_keep_alive=30)
    except BaseException as exc:   # noqa: BLE001
        print(f"uvicorn stopped: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(1)
