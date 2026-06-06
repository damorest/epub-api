"""Local HTML cache to avoid re-downloading chapters."""

import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".cache/html")


def _url_to_path(url: str) -> Path:
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.html"


def load(url: str) -> Optional[str]:
    """Return cached HTML for *url*, or None if not cached."""
    path = _url_to_path(url)
    if path.exists():
        logger.debug("Cache hit: %s", url)
        return path.read_text(encoding="utf-8")
    return None


def save(url: str, html: str) -> None:
    """Persist *html* to the local cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _url_to_path(url).write_text(html, encoding="utf-8")


def invalidate(url: str) -> None:
    """Delete cached entry for *url* if present."""
    path = _url_to_path(url)
    if path.exists():
        path.unlink()
