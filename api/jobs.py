"""In-memory job store for parse/publish tasks."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# status flow: pending → running → done → published
#                                 ├→ error
#                                 └→ cancelled


@dataclass
class Job:
    id: str
    title: str
    slug: str
    status: str = "pending"
    progress: int = 0
    total: int = 0
    current: str = ""
    epub_files: list[Path] = field(default_factory=list)
    # actual chapter ranges per epub: [{"path": Path, "first": int, "last": int}]
    epub_ranges: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    site_url: Optional[str] = None


_store: dict[str, Job] = {}


def create(title: str, slug: str) -> Job:
    job = Job(id=uuid.uuid4().hex[:8], title=title, slug=slug)
    _store[job.id] = job
    return job


def get(job_id: str) -> Optional[Job]:
    return _store.get(job_id)


def all_jobs() -> list[Job]:
    return list(_store.values())
