"""Merges all volume EPUBs into a single full-book EPUB.

Usage:
    python merge_volumes.py
"""

import re
import logging
from pathlib import Path

import ebooklib
from ebooklib import epub as epublib
from bs4 import BeautifulSoup

from parser.scraper import Chapter
from book.epub_builder import build_volume

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
FULL_EPUB = OUTPUT_DIR / "zvilnyty_vidmu_full.epub"


def _extract_from_volume(epub_path: Path) -> list[Chapter]:
    """Read a volume EPUB and return its Chapter objects."""
    book = epublib.read_epub(str(epub_path), options={"ignore_ncx": True})
    chapters: list[Chapter] = []

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        name = item.file_name
        if "nav" in name or "ncx" in name:
            continue

        match = re.search(r"chapter_(\d+)", name)
        if not match:
            continue
        num = int(match.group(1))

        soup = BeautifulSoup(item.get_content(), "lxml")
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else f"Розділ {num}"
        paragraphs = [
            f"<p>{p.decode_contents()}</p>"
            for p in soup.find_all("p")
            if p.decode_contents().strip()
        ]
        chapters.append(Chapter(number=num, title=title, content_html="\n".join(paragraphs)))

    return sorted(chapters, key=lambda c: c.number)


def merge() -> Path:
    """Combine all volume EPUBs into one file and return its path."""
    volumes = sorted(OUTPUT_DIR.glob("zvilnyty_vidmu_vol_*.epub"))
    if not volumes:
        raise FileNotFoundError("Немає томів в output/ — спочатку запусти main.py")

    all_chapters: list[Chapter] = []
    for vol_path in volumes:
        chs = _extract_from_volume(vol_path)
        logger.info("%s → %d розділів", vol_path.name, len(chs))
        all_chapters.extend(chs)

    all_chapters.sort(key=lambda c: c.number)
    logger.info("Всього: %d розділів — будуємо єдиний EPUB…", len(all_chapters))

    # Build with volume label 0; rename to final name afterward
    tmp_path = build_volume(all_chapters, 0, OUTPUT_DIR, add_cover=True)
    tmp_path.rename(FULL_EPUB)
    logger.info("Готово: %s  (%.1f МБ)", FULL_EPUB, FULL_EPUB.stat().st_size / 1_048_576)
    return FULL_EPUB


if __name__ == "__main__":
    merge()
