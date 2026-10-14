"""Assemble and upload the Gradio-SDK (raw mode) Space. Needs frontend/dist built and HF_TOKEN.

    SPACE_ID=AIBRUH/big-proppa-live python scripts/deploy_gradio_space.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SPACE_ID = os.environ.get("SPACE_ID", "AIBRUH/big-proppa-live")
IGNORE = ["__pycache__", "*.pyc", ".venv", "*.duckdb*", "*.db", "*.sqlite", "*.pem", "*.key",
          "*_cookies.txt", "player_photos"]


def main() -> None:
    if not (ROOT / "frontend/dist/index.html").exists():
        sys.exit("frontend/dist/index.html missing: run npm run build in frontend/")
    api = HfApi(token=os.environ["HF_TOKEN"])
    private = os.environ.get("PRIVATE", "0") == "1"
    api.create_repo(SPACE_ID, repo_type="space", space_sdk="gradio", private=private, exist_ok=True)
    ign = shutil.ignore_patterns(*IGNORE)
    with tempfile.TemporaryDirectory() as t:
        out = Path(t)
        for src, dst in [("backend", "backend"), ("landing", "landing"),
                         ("lake/gold/nfl", "lake/gold/nfl"), ("frontend/dist", "frontend/dist")]:
            shutil.copytree(ROOT / src, out / dst, ignore=ign)
        for f in ("app.py", "README.md", "requirements.txt"):
            shutil.copy(ROOT / "space_gradio" / f, out / f)
        # Only these paths are ever pruned, so stale files from older deploys disappear without
        # touching the Space's own housekeeping files (.gitattributes, .gitignore, lake/gold/.gitkeep).
        api.upload_folder(folder_path=str(out), repo_id=SPACE_ID, repo_type="space",
                          delete_patterns=["backend/**", "landing/**", "lake/gold/nfl/**", "frontend/dist/**"],
                          commit_message="Deploy: clean assembled tree")
    print(f"uploaded -> https://huggingface.co/spaces/{SPACE_ID}")


if __name__ == "__main__":
    main()
