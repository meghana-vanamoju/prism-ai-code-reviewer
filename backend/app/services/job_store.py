import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import settings
from app.models.job import (
    TERMINAL_STATUSES,
    JobProgress,
    JobResponse,
    JobStatus,
    ReviewResult,
    SkippedFile,
    SourceMode,
)


@dataclass
class Job:
    id: str
    mode: SourceMode
    status: JobStatus = JobStatus.QUEUED
    progress: JobProgress = field(default_factory=JobProgress)
    result: Optional[ReviewResult] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_requested: bool = False
    handle: object = None  # asyncio.Task, typed loosely to avoid import cost
    skipped: List[SkippedFile] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}

    def create(self, mode: SourceMode) -> Job:
        self.purge_expired()
        job = Job(id=uuid.uuid4().hex, mode=mode)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def touch(self, job: Job, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(job, key, value)
        job.updated_at = time.time()

    def set_progress(
        self,
        job: Job,
        step: Optional[str] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
        current_file: Optional[str] = None,
    ) -> None:
        if step is not None:
            job.progress.step = step
        if current is not None:
            job.progress.current = current
        if total is not None:
            job.progress.total = total
        job.progress.current_file = current_file
        job.updated_at = time.time()

    def request_cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if not job.is_terminal:
            job.cancel_requested = True
            job.updated_at = time.time()
        return True

    def cancel(self, job: Job) -> None:
        job.status = JobStatus.CANCELLED
        job.updated_at = time.time()

    def purge_expired(self) -> None:
        ttl = settings.job_ttl_seconds
        now = time.time()
        expired = [jid for jid, j in self._jobs.items() if now - j.updated_at > ttl]
        for jid in expired:
            del self._jobs[jid]

    def to_response(self, job: Job) -> JobResponse:
        return JobResponse(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            result=job.result,
            error=job.error,
            mode=job.mode,
            skipped=list(job.skipped),
        )


job_store = JobStore()
