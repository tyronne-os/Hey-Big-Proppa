"""
Deploy Big Proppa to Hugging Face Spaces.

Pushes:
  - Dockerfile
  - backend/ (Python source + requirements)
  - frontend/dist/ (pre-built React app — run npm run build first)
  - lake/gold/nfl/ (CSV data lake — player stats, BPL, schedule)
  - README.md (Space metadata: title, sdk, app_port)

Requires:
  HF_TOKEN env var with write access to the Space.
  Run from repo root:
    python scripts/deploy_to_hf_space.py

Optional:
  SPACE_ID env var to override the default repo (e.g. AIBRUH/big-proppa).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    try:
        from huggingface_hub import HfApi, upload_folder
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN environment variable not set.")
        print("  Add it via claude.ai/code → environment → Secrets → HF_TOKEN")
        sys.exit(1)

    space_id = os.environ.get("SPACE_ID", "AIBRUH/big-proppa")
    api = HfApi(token=token)

    # Verify dist/ was built
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").exists():
        print("ERROR: frontend/dist/index.html not found. Run: cd frontend && npm run build")
        sys.exit(1)

    print(f"=== DEPLOYING HEY BIG PROPPA → {space_id} ===")
    print(f"  Dist: {dist}")
    print(f"  Backend: {ROOT / 'backend'}")
    print()

    # Upload everything the Dockerfile needs
    # We upload from ROOT but only include the paths Docker COPYs
    paths_to_include = [
        "Dockerfile",
        "README.md",
        "backend/",
        "frontend/dist/",
        "lake/gold/nfl/",
    ]

    # Build an ignore list — exclude things not needed in the Space
    ignore_patterns = [
        "*.pyc", "__pycache__", ".venv", ".pylibs",
        "*.db", "*.sqlite", "*.duckdb", "*.duckdb.wal",
        "*.pem", "*.key", "*_cookies.txt",
        "lake/bronze/", "lake/silver/",
        "lake/gold/nfl/player_photos/",  # large PNGs — ESPN CDN used instead
        "node_modules/",
        ".git/",
    ]

    print("Uploading to Space (this takes ~30s)...")
    api.upload_folder(
        folder_path=str(ROOT),
        repo_id=space_id,
        repo_type="space",
        ignore_patterns=ignore_patterns,
        commit_message="Deploy: week 4 — evening slate, passcode security, live ticker, ESPN photos",
    )

    print()
    print(f"✅ DEPLOYED → https://huggingface.co/spaces/{space_id}")
    print(f"   App URL  → https://{space_id.replace('/', '-')}.hf.space")
    print()
    print("The Space will rebuild its Docker container (~2-3 min).")
    print("Watch build logs at: https://huggingface.co/spaces/{space_id}/logs".format(space_id=space_id))


if __name__ == "__main__":
    main()
