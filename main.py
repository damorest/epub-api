"""Entry point for the 'Звільнити цю відьму' EPUB generator.

Usage
-----
    python main.py --all
    python main.py --start 1 --end 200
    python main.py --start 101
"""

import argparse
import logging
import sys
from pathlib import Path

from parser.scraper import fetch_range, detect_last_chapter
from book.epub_builder import build_volume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
CHAPTERS_PER_VOLUME = 100
_SENTINEL_END = 9_999  # upper bound used when --end is not specified


def _volume_for(chapter_num: int) -> int:
    return (chapter_num - 1) // CHAPTERS_PER_VOLUME + 1


def _volume_chapter_range(volume: int) -> tuple[int, int]:
    lo = (volume - 1) * CHAPTERS_PER_VOLUME + 1
    hi = volume * CHAPTERS_PER_VOLUME
    return lo, hi


def _epub_path(volume: int) -> Path:
    return OUTPUT_DIR / f"zvilnyty_vidmu_vol_{volume}.epub"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Завантажує 'Звільнити цю відьму' з baka.in.ua і будує EPUB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Приклади:
  python main.py --all
  python main.py --start 1 --end 200
  python main.py --start 101 --end 300
""",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--all",
        action="store_true",
        help="завантажити всі доступні розділи (авто-визначення кінця)",
    )
    mode.add_argument(
        "--start",
        type=int,
        metavar="N",
        help="перший розділ для завантаження",
    )
    parser.add_argument(
        "--end",
        type=int,
        metavar="N",
        help="останній розділ (використовується з --start; якщо не вказано — авто)",
    )
    parser.add_argument(
        "--no-cover",
        action="store_true",
        help="не генерувати обкладинку (прискорює роботу)",
    )
    parser.add_argument(
        "--detect-end",
        action="store_true",
        help="примусово визначити останній розділ перед завантаженням",
    )
    return parser.parse_args()


def run(start: int, end: int, *, add_cover: bool = True) -> None:
    """Download chapters *start*…*end* and write volume EPUB files."""
    vol_start = _volume_for(start)
    vol_end = _volume_for(end)

    logger.info("Діапазон: розділи %d–%d → томи %d–%d", start, end, vol_start, vol_end)

    for vol in range(vol_start, vol_end + 1):
        epub_path = _epub_path(vol)
        if epub_path.exists():
            logger.info("Том %d: %s вже існує — пропускаємо.", vol, epub_path.name)
            continue

        vol_lo, vol_hi = _volume_chapter_range(vol)
        ch_start = max(start, vol_lo)
        ch_end = min(end, vol_hi)

        logger.info("Том %d: завантажуємо розділи %d–%d…", vol, ch_start, ch_end)
        chapters = fetch_range(ch_start, ch_end, stop_on_missing=True)

        if not chapters:
            logger.warning("Том %d: жодного розділу не знайдено — зупиняємось.", vol)
            break

        build_volume(chapters, vol, OUTPUT_DIR, add_cover=add_cover)

        # If fetch stopped early (consecutive failures), don't try further volumes.
        last_fetched = chapters[-1].number
        if last_fetched < ch_end and last_fetched < end:
            logger.info("Отримано розділи лише до %d — зупиняємось.", last_fetched)
            break


def main() -> None:
    args = _parse_args()

    if args.all:
        start = 1
        if args.detect_end:
            end = detect_last_chapter()
        else:
            end = _SENTINEL_END  # fetch_range stops at consecutive failures
    else:
        start = args.start
        if args.end:
            end = args.end
        elif args.detect_end:
            end = detect_last_chapter()
        else:
            end = _SENTINEL_END

    if start < 1:
        logger.error("--start має бути >= 1")
        sys.exit(1)
    if end < start:
        logger.error("--end (%d) має бути >= --start (%d)", end, start)
        sys.exit(1)

    run(start, end, add_cover=not args.no_cover)
    logger.info("Готово. Файли збережено в: %s/", OUTPUT_DIR)


if __name__ == "__main__":
    main()
