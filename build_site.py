"""Generates site/index.html from all EPUB files in output/.

Run after downloading chapters:
    python build_site.py
"""

import shutil
from pathlib import Path

OUTPUT_DIR = Path("output")
SITE_DIR = Path("site")
FULL_EPUB_NAME = "zvilnyty_vidmu_full.epub"
CHAPTERS_PER_VOLUME = 100

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Звільнити цю відьму — EPUB</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: Georgia, serif;
      background: #1a1a2e;
      color: #e0d9c8;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem 1rem;
    }}

    header {{
      text-align: center;
      margin-bottom: 2.5rem;
    }}

    header h1 {{
      font-size: 2rem;
      color: #c8a96e;
      letter-spacing: 0.03em;
      margin-bottom: 0.4rem;
    }}

    header p {{
      font-size: 0.95rem;
      color: #9090a0;
      font-family: sans-serif;
    }}

    .section-label {{
      width: 100%;
      max-width: 860px;
      font-family: sans-serif;
      font-size: 0.78rem;
      font-weight: bold;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #55556a;
      margin-bottom: 0.8rem;
      padding-bottom: 0.4rem;
      border-bottom: 1px solid #2a2a4a;
    }}

    /* Full book hero card */
    .full-book {{
      width: 100%;
      max-width: 860px;
      background: linear-gradient(135deg, #1e1e40 0%, #16213e 100%);
      border: 1px solid #c8a96e55;
      border-radius: 14px;
      padding: 2rem;
      display: flex;
      flex-direction: column;
      gap: 0.9rem;
      margin-bottom: 2.5rem;
    }}

    .full-book-title {{
      font-size: 1.4rem;
      color: #c8a96e;
    }}

    .full-book-meta {{
      font-size: 0.9rem;
      color: #9090a0;
      font-family: sans-serif;
    }}

    .btn-full {{
      display: inline-block;
      align-self: flex-start;
      padding: 0.75rem 2rem;
      background: #c8a96e;
      color: #1a1a2e;
      text-decoration: none;
      border-radius: 8px;
      font-family: sans-serif;
      font-size: 0.95rem;
      font-weight: bold;
      transition: background 0.2s;
    }}

    .btn-full:hover {{ background: #e0c080; }}

    /* Volume grid */
    .volumes {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 1.2rem;
      width: 100%;
      max-width: 860px;
      margin-bottom: 3rem;
    }}

    .card {{
      background: #16213e;
      border: 1px solid #2a2a4a;
      border-radius: 10px;
      padding: 1.4rem 1.2rem;
      display: flex;
      flex-direction: column;
      gap: 0.8rem;
      transition: border-color 0.2s;
    }}

    .card:hover {{ border-color: #c8a96e; }}

    .card-title {{
      font-size: 1.05rem;
      color: #c8a96e;
    }}

    .card-meta {{
      font-size: 0.82rem;
      color: #7878a0;
      font-family: sans-serif;
    }}

    .btn {{
      display: inline-block;
      margin-top: auto;
      padding: 0.55rem 1rem;
      background: #c8a96e;
      color: #1a1a2e;
      text-decoration: none;
      border-radius: 6px;
      font-family: sans-serif;
      font-size: 0.88rem;
      font-weight: bold;
      text-align: center;
      transition: background 0.2s;
    }}

    .btn:hover {{ background: #e0c080; }}

    footer {{
      font-family: sans-serif;
      font-size: 0.8rem;
      color: #44445a;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Звільнити цю відьму</h1>
    <p>Особистий архів EPUB-файлів · {total} томів · {chapters} розділів</p>
  </header>

{full_book_section}

  <div class="section-label">Томи окремо</div>

  <div class="volumes">
{cards}
  </div>

  <footer>Згенеровано автоматично · для особистого використання</footer>
</body>
</html>"""

FULL_BOOK_SECTION = """  <div class="section-label">Вся книга повністю</div>

  <div class="full-book">
    <div class="full-book-title">Звільнити цю відьму — повне видання</div>
    <div class="full-book-meta">Всі {chapters} розділів в одному файлі · {size}</div>
    <a class="btn-full" href="{filename}" download>⬇ Завантажити повну книгу (EPUB)</a>
  </div>
"""

CARD_TEMPLATE = """    <div class="card">
      <div class="card-title">Том {vol}</div>
      <div class="card-meta">Розділи {ch_start}–{ch_end} · {size}</div>
      <a class="btn" href="{filename}" download>⬇ Завантажити EPUB</a>
    </div>"""


def _human_size(path: Path) -> str:
    kb = path.stat().st_size / 1024
    return f"{kb:.0f} КБ" if kb < 1024 else f"{kb/1024:.1f} МБ"


def build() -> None:
    SITE_DIR.mkdir(exist_ok=True)

    epubs = sorted(OUTPUT_DIR.glob("zvilnyty_vidmu_vol_*.epub"))
    if not epubs:
        print("Немає EPUB-файлів в output/ — спочатку запусти main.py")
        return

    # Volume cards
    cards = []
    total_chapters = 0
    for epub_path in epubs:
        vol = int(epub_path.stem.split("_")[-1])
        ch_start = (vol - 1) * CHAPTERS_PER_VOLUME + 1
        ch_end = vol * CHAPTERS_PER_VOLUME
        shutil.copy2(epub_path, SITE_DIR / epub_path.name)
        cards.append(CARD_TEMPLATE.format(
            vol=vol,
            ch_start=ch_start,
            ch_end=ch_end,
            size=_human_size(epub_path),
            filename=epub_path.name,
        ))
        total_chapters += CHAPTERS_PER_VOLUME

    # Full book section (only if the merged file exists)
    full_epub_src = OUTPUT_DIR / FULL_EPUB_NAME
    if full_epub_src.exists():
        shutil.copy2(full_epub_src, SITE_DIR / FULL_EPUB_NAME)
        full_book_section = FULL_BOOK_SECTION.format(
            chapters=total_chapters,
            size=_human_size(full_epub_src),
            filename=FULL_EPUB_NAME,
        )
    else:
        full_book_section = (
            '  <!-- full book not yet generated; run: python merge_volumes.py -->\n'
        )

    html = HTML_TEMPLATE.format(
        total=len(epubs),
        chapters=total_chapters,
        full_book_section=full_book_section,
        cards="\n".join(cards),
    )

    index = SITE_DIR / "index.html"
    index.write_text(html, encoding="utf-8")
    print(f"Готово: {index}  ({len(epubs)} томів, full={full_epub_src.exists()})")


if __name__ == "__main__":
    build()
