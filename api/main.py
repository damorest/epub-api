"""FastAPI server — entry point for the EPUB Generator API."""

import logging
import re

from fastapi import BackgroundTasks, FastAPI, HTTPException

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api import jobs as job_store
from api.github_publisher import delete_book, publish_book
from api.universal_parser import parse_book

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="EPUB Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _clean_url(url: str) -> str:
    """Strip trailing UUID from URL if present."""
    return _UUID_RE.sub("", url.rstrip("/"))


class ParseRequest(BaseModel):
    url: str
    title: str
    start: int = 1
    end: int = 9_999
    follow_next: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "service": "epub-generator"}


@app.get("/ping")
def ping():
    """Keep-alive endpoint — Flutter pings this every 20 s to prevent Render sleep."""
    return {"pong": True}


@app.post("/parse")
def start_parse(req: ParseRequest, background_tasks: BackgroundTasks):
    """Start a parse job. Returns job_id for polling."""
    slug = re.sub(r"[^a-z0-9]+", "-", req.title.lower()).strip("-") or "book"
    job = job_store.create(req.title, slug)

    # Strip UUID only in pattern mode — in follow_next mode the UUID is
    # part of the chapter's actual URL and must be preserved.
    clean = req.url if req.follow_next else _clean_url(req.url)
    background_tasks.add_task(
        parse_book,
        job_id=job.id,
        url=clean,
        title=req.title,
        slug=slug,
        start=req.start,
        end=req.end,
        follow_next=req.follow_next,
    )
    return {"job_id": job.id, "slug": slug}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    """Poll job progress."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "progress": job.progress,
        "total": job.total,
        "current": job.current,
        "error": job.error,
        "site_url": job.site_url,
    }


@app.post("/cancel/{job_id}")
def cancel(job_id: str):
    """Cancel a running job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status: {job.status}")
    job.status = "cancelled"
    return {"cancelled": True}


@app.post("/publish/{job_id}")
def publish(job_id: str):
    """Push EPUBs to GitHub and update the library site."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        raise HTTPException(status_code=400, detail=f"Job not ready (status: {job.status})")

    missing = [str(p) for p in job.epub_files if not p.exists()]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"EPUB files missing (server may have restarted): {missing}",
        )

    try:
        url = publish_book(job)
    except Exception as exc:
        logging.exception("publish_book failed for job %s", job_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job.status = "published"
    job.site_url = url
    return {"url": url}


@app.delete("/books/{slug}")
def remove_book(slug: str):
    """Delete a book from GitHub Pages library."""
    try:
        delete_book(slug)
    except Exception as exc:
        logging.exception("delete_book failed for slug %s", slug)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"deleted": slug}


@app.get("/books")
def list_books():
    """List all jobs (both done and published)."""
    return [
        {
            "id": j.id,
            "title": j.title,
            "slug": j.slug,
            "status": j.status,
            "chapters": j.total,
            "site_url": j.site_url,
        }
        for j in job_store.all_jobs()
    ]
