"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

from abc import ABC, abstractmethod
import json
import os
import threading
from typing import Any, Optional

from taskflow.models import Job, JobStatus

_SENTINEL = object()


class JobStorage(ABC):
    """Abstract base class for job storage backends."""

    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Save a new job or overwrite an existing job."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its unique identifier."""
        pass

    @abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List all jobs, optionally filtering by status."""
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update status, result, and/or error for a job."""
        pass

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID. Returns True if deleted, False if not found."""
        pass


class MemoryJobStorage(JobStorage):
    """Thread-safe in-memory job storage utilizing threading.RLock."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def save_job(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        with self._lock:
            if status is None:
                return list(self._jobs.values())
            return [j for j in self._jobs.values() if j.status == status]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = _SENTINEL,
        error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = status
            if result is not _SENTINEL:
                job.result = result
            if error is not None:
                job.error = error
            return True

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def save_snapshot(self, filepath: str) -> None:
        with self._lock:
            data = [job.to_dict() for job in self._jobs.values()]
        parent = os.path.dirname(os.path.abspath(filepath))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_snapshot(self, filepath: str) -> int:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        with self._lock:
            for item in data:
                job = Job.from_dict(item)
                self._jobs[job.job_id] = job
                count += 1
        return count
