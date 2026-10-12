"""Gradio-SDK Space in raw mode: serves the Big Proppa React app (incl. React Flow) untouched.

Gradio supplies only the SDK runtime. The page everyone sees is the built frontend/dist plus the
landing page, served by the same FastAPI backend as the Docker Space. Gradio itself is mounted at
/__gradio as a status page and never replaces a route.
"""
import os
import sys
from pathlib import Path

import gradio as gr
import uvicorn

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

import main as bp  # noqa: E402  the existing FastAPI app, unchanged

with gr.Blocks(title="Big Proppa runtime") as status:
    gr.Markdown("Big Proppa is running. The app is at the site root.")

app = gr.mount_gradio_app(bp.app, status, path="/__gradio")

def _diag() -> None:
    import subprocess
    keys = {k: v for k, v in os.environ.items() if k.startswith(("GRADIO", "PORT", "SYSTEM", "SPACE"))}
    print("DIAG env", {k: v for k, v in keys.items() if "TOKEN" not in k and "KEY" not in k}, flush=True)
    print("DIAG name", __name__, "argv", sys.argv, flush=True)
    print(subprocess.run("ps -eo pid,args | cut -c1-200", shell=True, capture_output=True, text=True).stdout, flush=True)


if __name__ == "__main__":
    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
    except BaseException:
        _diag()
        raise
