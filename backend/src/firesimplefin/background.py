"""In-memory background job store (push jobs)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class JobState:
    status: str  # "pending" | "running" | "completed" | "failed"
    result: Any = None  # PushResponse when completed; error message when failed
    processed: int = 0  # number of transactions pushed so far (while running)
    created_at: str = ""


_jobs: dict[str, JobState] = {}
_MAX_JOBS = 1000


def create_job() -> str:
    """Create a new job in pending state. Returns job_id."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobState(status="pending", created_at=datetime.now(timezone.utc).isoformat())
    _evict_if_needed()
    return job_id


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


def set_job_running(job_id: str) -> None:
    if job_id in _jobs:
        _jobs[job_id].status = "running"
        _jobs[job_id].processed = 0


def set_job_progress(job_id: str, processed: int) -> None:
    """Update how many transactions have been pushed (call from running job)."""
    if job_id in _jobs and _jobs[job_id].status == "running":
        _jobs[job_id].processed = processed


def set_job_completed(job_id: str, result: Any) -> None:
    if job_id in _jobs:
        _jobs[job_id].status = "completed"
        _jobs[job_id].result = result


def set_job_failed(job_id: str, message: str | None = None) -> None:
    if job_id in _jobs:
        _jobs[job_id].status = "failed"
        _jobs[job_id].result = message


def get_running_count() -> int:
    """Number of jobs that are pending or running."""
    return sum(1 for j in _jobs.values() if j.status in ("pending", "running"))


def _evict_if_needed() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    # Remove oldest by created_at (keep recent)
    by_time = sorted(_jobs.items(), key=lambda x: x[1].created_at)
    to_remove = len(_jobs) - _MAX_JOBS
    for job_id, _ in by_time[:to_remove]:
        del _jobs[job_id]
