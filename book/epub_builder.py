"""Builds EPUB files from parsed Chapter objects."""

import logging
import uuid
from pathlib import Path
from typing import Optional

from ebooklib import epub

from parser.scraper import Chapter
from book import cover as cover_gen

logger = logging.getLogger(__name__)

BOOK_LANGUAGE = "uk"
BOOK_AUTHOR = "Автор невідомий"

_CSS = """\
@charset "UTF-8";

body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1em;
    line-height: 1.75;
    margin: 1.2em 2em;
    color: #1a1a1a;
    background: #fefefe;
}

h1 {
    font-size: 1.35em;
    font-weight: bold;
    text-align: center;
    margin: 0 0 1.8em 0;
    padding-bottom: 0.4em;
    border-bottom: 1px solid #ccc;
    color: #2c2c2c;
}

p {
    text-indent: 1.5em;
    margin: 0.25em 0;
    text-align: justify;
    orphans: 2;
    widows: 2;
}

em { font-style: italic; }
strong { font-weight: bold; }
"""

_CHAPTER_TEMPLATE = """\
<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="uk">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../style/main.css"/>
</head>
<body>
  <h1>{title}</h1>
  {content}
</body>
</html>"""


def _make_epub_chapter(chapter: Chapter, css_item: epub.EpubItem) -> epub.EpubHtml:
    """Wrap a *Chapter* in an EpubHtml item."""
    file_name = f"text/chapter_{chapter.number:05d}.xhtml"
    uid = f"ch-{chapter.number}"

    item = epub.EpubHtml(title=chapter.title, file_name=file_name, lang=BOOK_LANGUAGE)
    item.set_content(
        _CHAPTER_TEMPLATE.format(
            title=chapter.title,
            content=chapter.content_html,
        ).encode("utf-8")
    )
    item.add_item(css_item)
    return item


def build_volume(
    chapters: list[Chapter],
    volume: int,
    output_dir: Path,
    *,
    title: str = "Книга",
    slug: str = "book",
    add_cover: bool = True,
) -> Path:
    """Build a single EPUB volume and write it to *output_dir*.

    Returns the path of the written file.
    """
    if not chapters:
        raise ValueError("chapters list is empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    if volume == 0:
        out_path = output_dir / f"{slug}_full.epub"
        epub_title = title
        description = f"Всі розділи: {chapters[0].number}–{chapters[-1].number}"
    else:
        out_path = output_dir / f"{slug}_vol_{volume}.epub"
        epub_title = f"{title} — Том {volume}"
        description = f"Том {volume}, розділи {chapters[0].number}–{chapters[-1].number}"

    book = epub.EpubBook()
    book.set_identifier(f"{slug}-vol-{volume}-{uuid.uuid4().hex[:8]}")
    book.set_title(epub_title)
    book.set_language(BOOK_LANGUAGE)
    book.add_author(BOOK_AUTHOR)
    book.add_metadata("DC", "description", description)

    # Cover
    if add_cover:
        try:
            cover_bytes = cover_gen.generate(volume, title=title)
            book.set_cover("images/cover.jpg", cover_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Обкладинку пропущено: %s", exc)

    # Stylesheet
    css_item = epub.EpubItem(
        uid="style-main",
        file_name="style/main.css",
        media_type="text/css",
        content=_CSS.encode("utf-8"),
    )
    book.add_item(css_item)

    # Chapters
    epub_chapters: list[epub.EpubHtml] = []
    toc: list[epub.Link] = []

    for chapter in chapters:
        item = _make_epub_chapter(chapter, css_item)
        book.add_item(item)
        epub_chapters.append(item)
        toc.append(epub.Link(item.file_name, chapter.title, f"ch-{chapter.number}"))

    # Navigation
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + epub_chapters  # type: ignore[list-item]

    epub.write_epub(str(out_path), book, {})
    logger.info("EPUB збережено: %s (%d розділів)", out_path, len(chapters))
    return out_path
