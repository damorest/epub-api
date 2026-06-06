"""HTTP scraper for baka.in.ua — fetches and parses novel chapters."""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from parser import cache as html_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://baka.in.ua"
_CHAPTER_TEMPLATE = "{base}/chapters/zvilnyty-tsiu-vidmu-rozdil-{num}-0"

_DELAY = 1.0        # seconds between successful requests
_RETRY_DELAY = 5.0  # seconds between retry attempts
_MAX_RETRIES = 3
_TIMEOUT = 30
_MAX_CONSECUTIVE_FAILURES = 3

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk,en;q=0.5",
}

# Candidate CSS selectors for the chapter body, tried in order.
_CONTENT_SELECTORS = [
    {"class_": "prose"},           # baka.in.ua — Tailwind prose block
    {"class_": "chapter-content"},
    {"class_": "text"},
    {"class_": "reader-content"},
    {"class_": "entry-content"},
    {"class_": "content"},
    {"id": "content"},
]


@dataclass
class Chapter:
    number: int
    title: str
    content_html: str  # sanitised XHTML fragment (<p>…</p> blocks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chapter_url(number: int) -> str:
    return _CHAPTER_TEMPLATE.format(base=BASE_URL, num=number)


def _fetch_raw(url: str, use_cache: bool = True) -> Optional[str]:
    """GET *url* and return HTML text, or None on 404 / permanent failure."""
    if use_cache:
        cached = html_cache.load(url)
        if cached is not None:
            return cached

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 404:
                logger.debug("404: %s", url)
                return None
            resp.raise_for_status()
            html = resp.text
            if use_cache:
                html_cache.save(url, html)
            return html
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, url, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)

    return None


def _extract_content(soup: BeautifulSoup) -> list[str]:
    """Return a list of <p>…</p> XHTML strings from the chapter body."""
    container: Optional[Tag] = None

    for selector in _CONTENT_SELECTORS:
        container = soup.find("div", **selector)  # type: ignore[arg-type]
        if container is not None:
            break

    # Fallback: use <article> or <main>, then the whole body.
    if container is None:
        container = soup.find("article") or soup.find("main") or soup.body

    if container is None:
        return []

    paragraphs = container.find_all("p")
    result: list[str] = []
    for p in paragraphs:
        # Preserve inline tags (em, strong, a, br) but strip block-level noise.
        inner = p.decode_contents().strip()
        if inner:
            result.append(f"<p>{inner}</p>")

    return result


def _is_not_found_page(soup: BeautifulSoup) -> bool:
    """Heuristic: returns True if the page is a generic 404 / redirect page."""
    h1 = soup.find("h1")
    if h1 is None:
        return True
    title_text = h1.get_text(strip=True).lower()
    not_found_markers = [
        "не знайдено", "404", "not found", "сторінку не знайдено",
        "помилка", "error",
    ]
    return any(m in title_text for m in not_found_markers)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_chapter(number: int) -> Optional[Chapter]:
    """Download, parse, and return *Chapter* for *number*, or None if absent."""
    url = _chapter_url(number)
    logger.info("[%d] %s", number, url)

    html = _fetch_raw(url)
    if html is None:
        logger.info("[%d] → не знайдено (HTTP 404 або мережева помилка)", number)
        return None

    soup = BeautifulSoup(html, "lxml")

    if _is_not_found_page(soup):
        logger.info("[%d] → сторінку не знайдено (вміст 404)", number)
        return None

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else f"Розділ {number}"
    paragraphs = _extract_content(soup)

    if not paragraphs:
        logger.warning("[%d] → заголовок знайдено, але текст відсутній", number)
        paragraphs = [f"<p>(Текст розділу {number} не вдалося отримати)</p>"]

    content_html = "\n".join(paragraphs)
    logger.info("[%d] «%s» — %d абзаців", number, title, len(paragraphs))

    time.sleep(_DELAY)
    return Chapter(number=number, title=title, content_html=content_html)


def fetch_range(
    start: int,
    end: int,
    *,
    stop_on_missing: bool = True,
) -> list[Chapter]:
    """Fetch chapters *start*…*end* inclusive.

    When *stop_on_missing* is True (default), stops after
    _MAX_CONSECUTIVE_FAILURES chapters in a row cannot be fetched.
    """
    chapters: list[Chapter] = []
    consecutive_failures = 0

    for num in range(start, end + 1):
        chapter = fetch_chapter(num)
        if chapter is None:
            consecutive_failures += 1
            if stop_on_missing and consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.info(
                    "Зупиняємось після %d невдалих спроб поспіль (розділ %d).",
                    _MAX_CONSECUTIVE_FAILURES,
                    num,
                )
                break
        else:
            consecutive_failures = 0
            chapters.append(chapter)

    return chapters


def detect_last_chapter(probe_start: int = 100) -> int:
    """Binary-search the last available chapter number.

    Strategy: double *probe_start* until we hit a 404, then binary-search
    the interval.  Uses the cache so repeated runs are fast.
    """
    logger.info("Визначаємо останній доступний розділ…")

    # Find upper bound
    upper = probe_start
    while True:
        html = _fetch_raw(_chapter_url(upper), use_cache=False)
        time.sleep(_DELAY)
        if html is None:
            break
        soup = BeautifulSoup(html, "lxml")
        if _is_not_found_page(soup):
            break
        upper *= 2

    lower = upper // 2

    # Binary search [lower, upper)
    while lower < upper - 1:
        mid = (lower + upper) // 2
        html = _fetch_raw(_chapter_url(mid), use_cache=False)
        time.sleep(_DELAY)
        exists = html is not None and not _is_not_found_page(BeautifulSoup(html, "lxml"))
        if exists:
            lower = mid
        else:
            upper = mid

    logger.info("Останній доступний розділ: %d", lower)
    return lower
