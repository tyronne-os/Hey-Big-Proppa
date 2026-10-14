"""
Booth host photos. Drop `jonah-jacques`, `my-boo` or `julian-feltus` (.jpg/.jpeg/.png/.webp) into
frontend/public/hosts/ and the web player, the video and the share card pick it up. A host with no
photo keeps the initials badge. MY BOO falls back to her existing site portrait.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SLUGS = {"Jonah Jacques": "jonah-jacques", "MY BOO": "my-boo", "Julian Feltus": "julian-feltus"}
EXTS = (".jpg", ".jpeg", ".png", ".webp")
FALLBACKS = {"MY BOO": "myboo-avatar.jpg"}
SEARCH = (ROOT / "frontend" / "dist", ROOT / "frontend" / "public")


def _find(host: str) -> Optional[tuple[Path, str]]:
    slug = SLUGS.get(host)
    if not slug:
        return None
    for base in SEARCH:
        for ext in EXTS:
            p = base / "hosts" / f"{slug}{ext}"
            if p.is_file():
                return p, f"/hosts/{slug}{ext}"
    fb = FALLBACKS.get(host)
    if fb:
        for base in SEARCH:
            if (base / fb).is_file():
                return base / fb, f"/{fb}"
    return None


def photo_path(host: str) -> Optional[Path]:
    hit = _find(host)
    return hit[0] if hit else None


def photo_urls() -> dict[str, Optional[str]]:
    return {h: (_find(h) or (None, None))[1] for h in SLUGS}
