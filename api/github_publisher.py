"""Publishes EPUB files to GitHub and regenerates the library index.html."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()
logger = logging.getLogger(__name__)

CHAPTERS_PER_VOLUME = 100
_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
_GITHUB_REPO = os.getenv("GITHUB_REPO", "damorest/witch-book")
_PAGES_URL = (
    f"https://{_GITHUB_REPO.split('/')[0]}.github.io"
    f"/{_GITHUB_REPO.split('/')[1]}"
)


# ---------------------------------------------------------------------------
# Low-level GitHub helpers
# ---------------------------------------------------------------------------

def _get_file(repo, path: str):
    try:
        return repo.get_contents(path)
    except GithubException:
        return None


def _upsert(repo, path: str, content: bytes, message: str) -> None:
    existing = _get_file(repo, path)
    if existing:
        repo.update_file(path, message, content, existing.sha)
    else:
        repo.create_file(path, message, content)
    logger.info("GitHub ← %s", path)


# ---------------------------------------------------------------------------
# books.json helpers
# ---------------------------------------------------------------------------

def _load_books(repo) -> list[dict]:
    f = _get_file(repo, "books.json")
    return json.loads(f.decoded_content) if f else []


def _save_books(repo, books: list[dict]) -> None:
    raw = json.dumps(books, ensure_ascii=False, indent=2).encode("utf-8")
    _upsert(repo, "books.json", raw, "Update books.json")


# ---------------------------------------------------------------------------
# HTML generator
# ---------------------------------------------------------------------------

def _plural_uk(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return "книг"
    r = n % 10
    if r == 1:
        return "книга"
    if 2 <= r <= 4:
        return "книги"
    return "книг"


def _build_index(books: list[dict]) -> str:
    cards_html = ""
    for b in books:
        slug = b["slug"]
        files_html = "".join(
            f'      <a class="btn" href="books/{slug}/{ep["name"]}" download>'
            f'{ep["label"]} · {ep["size_kb"]} КБ</a>\n'
            for ep in b.get("epub_files", [])
        )
        cards_html += f"""
  <div class="card">
    <div class="card-title">{b["title"]}</div>
    <div class="card-meta">{b["chapters"]} розділів</div>
    <div class="downloads">
{files_html}    </div>
  </div>"""

    total = len(books)
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Моя бібліотека</title>
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
    header {{ text-align: center; margin-bottom: 3rem; }}
    header h1 {{ font-size: 2rem; color: #c8a96e; margin-bottom: 0.4rem; }}
    header p {{ font-size: 0.9rem; color: #9090a0; font-family: sans-serif; }}
    .library {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1.5rem;
      width: 100%;
      max-width: 920px;
    }}
    .card {{
      background: #16213e;
      border: 1px solid #2a2a4a;
      border-radius: 12px;
      padding: 1.6rem;
      display: flex;
      flex-direction: column;
      gap: 0.8rem;
      transition: border-color 0.2s;
    }}
    .card:hover {{ border-color: #c8a96e; }}
    .card-title {{ font-size: 1.15rem; color: #c8a96e; }}
    .card-meta {{ font-size: 0.82rem; color: #7878a0; font-family: sans-serif; }}
    .downloads {{ display: flex; flex-direction: column; gap: 0.45rem; margin-top: 0.4rem; }}
    .btn {{
      display: block;
      padding: 0.5rem 1rem;
      background: #c8a96e;
      color: #1a1a2e;
      text-decoration: none;
      border-radius: 6px;
      font-family: sans-serif;
      font-size: 0.85rem;
      font-weight: bold;
      text-align: center;
      transition: background 0.2s;
    }}
    .btn:hover {{ background: #e0c080; }}
    footer {{ margin-top: 3rem; font-family: sans-serif; font-size: 0.8rem; color: #44445a; }}
  </style>
</head>
<body>
  <header>
    <h1>Моя бібліотека</h1>
    <p>{total} {_plural_uk(total)}</p>
  </header>
  <div class="library">{cards_html}
  </div>
  <footer>Особиста EPUB-бібліотека</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def publish_book(job) -> str:
    """Upload EPUBs, update books.json and index.html. Returns site URL."""
    g = Github(_GITHUB_TOKEN)
    repo = g.get_repo(_GITHUB_REPO)

    slug = job.slug
    epub_meta: list[dict] = []

    for ep_path in job.epub_files:
        github_path = f"books/{slug}/{ep_path.name}"
        content = ep_path.read_bytes()
        size_kb = len(content) // 1024

        _upsert(repo, github_path, content, f"Add {ep_path.name}")

        if "full" in ep_path.name:
            label = "Повна книга"
        else:
            try:
                vol = int(ep_path.stem.split("_")[-1])
                lo = (vol - 1) * CHAPTERS_PER_VOLUME + 1
                hi = vol * CHAPTERS_PER_VOLUME
                label = f"Том {vol} (розд. {lo}–{hi})"
            except ValueError:
                label = ep_path.stem

        epub_meta.append({"name": ep_path.name, "label": label, "size_kb": size_kb})

    # Put full book first in the list
    epub_meta.sort(key=lambda e: (0 if "full" in e["name"] else 1, e["name"]))

    books = _load_books(repo)
    books = [b for b in books if b["slug"] != slug]
    books.append({
        "slug": slug,
        "title": job.title,
        "chapters": job.total,
        "epub_files": epub_meta,
    })
    _save_books(repo, books)

    html = _build_index(books)
    _upsert(repo, "index.html", html.encode("utf-8"), f"Library: add «{job.title}»")

    return f"{_PAGES_URL}"
