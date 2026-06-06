"""Universal chapter parser — works with URL patterns or next-link chains.

Content extraction uses trafilatura for any site, with a BeautifulSoup
fallback for sites that block trafilatura.
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from api import jobs as job_store
from book.epub_builder import build_volume
from parser.scraper import Chapter

logger = logging.getLogger(__name__)

DELAY = 1.0
MAX_RETRIES = 3
MAX_CONSECUTIVE_FAILURES = 3
CHAPTERS_PER_VOLUME = 100

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "uk,en;q=0.5",
}

_NEXT_PATTERNS = [
    re.compile(r"наступ", re.I),
    re.compile(r"\bnext\b", re.I),
    re.compile(r"далі", re.I),
    re.compile(r"→|>>|›"),
]

_CONTENT_SELECTORS = [
    {"class_": "prose"},
    {"class_": "chapter-content"},
    {"class_": "entry-content"},
    {"class_": "content"},
    {"class_": "text"},
    {"id": "content"},
]


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _fetch(url: str) -> Optional[str]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(5)
    return None


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def _extract_with_trafilatura(html: str) -> Optional[str]:
    try:
        import trafilatura
        text = trafilatura.extract(html, include_formatting=False, include_links=False)
        if text:
            return "\n".join(
                f"<p>{line}</p>" for line in text.splitlines() if line.strip()
            )
    except Exception:
        pass
    return None


def _extract_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    container = None
    for sel in _CONTENT_SELECTORS:
        container = soup.find("div", **sel)  # type: ignore[arg-type]
        if container:
            break
    if container is None:
        container = soup.find("article") or soup.find("main") or soup.body

    paragraphs = []
    if container:
        for p in container.find_all("p"):
            inner = p.decode_contents().strip()
            if inner:
                paragraphs.append(f"<p>{inner}</p>")
    return "\n".join(paragraphs)


def _extract(html: str) -> tuple[str, str]:
    """Return (title, content_html)."""
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    content = _extract_with_trafilatura(html) or _extract_with_bs4(html)
    return title, content


# ---------------------------------------------------------------------------
# Next-link detection
# ---------------------------------------------------------------------------

def _find_next_url(html: str, current_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")

    tag = soup.find("a", rel="next")
    if tag and tag.get("href"):
        return urljoin(current_url, tag["href"])

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if any(p.search(text) for p in _NEXT_PATTERNS):
            return urljoin(current_url, a["href"])

    return None


# ---------------------------------------------------------------------------
# Main task — runs in a BackgroundTasks thread
# ---------------------------------------------------------------------------

def parse_book(
    job_id: str,
    url: str,
    title: str,
    slug: str,
    start: int,
    end: int,
    follow_next: bool,
) -> None:
    """Download chapters and build EPUB volumes. Updates job state in place."""
    job = job_store.get(job_id)
    if job is None:
        return

    job.status = "running"
    chapters: list[Chapter] = []
    consecutive_failures = 0
    chapter_num = start
    current_url = url

    try:
        while True:
            # --- determine URL for this chapter ---
            if not follow_next:
                if chapter_num > end:
                    break
                if "{n}" in url:
                    current_url = url.replace("{n}", str(chapter_num))
                # else: fixed URL list not supported in this mode

            job.progress = chapter_num - start
            job.current = f"Розділ {chapter_num}…"

            html = _fetch(current_url)
            if html is None:
                consecutive_failures += 1
                logger.info("[%d] not found", chapter_num)
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                chapter_num += 1
                time.sleep(DELAY)
                continue

            consecutive_failures = 0
            ch_title, content_html = _extract(html)
            if not ch_title:
                ch_title = f"Розділ {chapter_num}"

            if content_html:
                chapters.append(Chapter(
                    number=chapter_num,
                    title=ch_title,
                    content_html=content_html,
                ))
                job.current = f"✓ {ch_title}"
                logger.info("[%d] %s", chapter_num, ch_title)

            if follow_next:
                next_url = _find_next_url(html, current_url)
                if not next_url:
                    logger.info("No next link found — stopping.")
                    break
                current_url = next_url

            chapter_num += 1
            time.sleep(DELAY)

        # --- build EPUBs ---
        if not chapters:
            job.status = "error"
            job.error = "Жодного розділу не знайдено"
            return

        job.total = len(chapters)
        job.current = "Генеруємо EPUB…"

        out_dir = Path("output") / slug
        vol_nums = sorted({
            (c.number - 1) // CHAPTERS_PER_VOLUME + 1 for c in chapters
        })
        epub_files = []

        for vol in vol_nums:
            vol_chapters = [
                c for c in chapters
                if (vol - 1) * CHAPTERS_PER_VOLUME < c.number <= vol * CHAPTERS_PER_VOLUME
            ]
            if vol_chapters:
                epub_files.append(build_volume(vol_chapters, vol, out_dir))

        # full book when multiple volumes
        if len(epub_files) > 1:
            full_path = out_dir / f"{slug}_full.epub"
            build_volume(chapters, 0, out_dir).rename(full_path)
            epub_files.insert(0, full_path)

        job.epub_files = epub_files
        job.status = "done"
        job.current = "Готово — очікує публікації"

    except Exception as exc:
        logger.exception("parse_book failed")
        job.status = "error"
        job.error = str(exc)
