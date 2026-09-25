"""Job storage interfaces and in-memory implementation."""

from __future__ import annotations

import abc
import json
import threading
from typing import Any, Dict, List, Optional

from taskflow.models import Job, JobStatus


class JobStorage(abc.ABC):
    """Abstract base class for job persistence."""

    @abc.abstractmethod
    def save_job(self, job: Job) -> None:
        """Persist or update a job."""
        pass

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its ID."""
        pass

    @abc.abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
        """List jobs optionally filtered by status."""
        pass

    @abc.abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update job status and optionally result or error."""
        pass

    @abc.abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        pass


class MemoryJobStorage(JobStorage):
    """Thread-safe in-memory job storage using RLock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}

    def save_job(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
        with self._lock:
            if status is None:
                return list(self._jobs.values())
            return [j for j in self._jobs.values() if j.status == status]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = status
            if result is not None:
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
        """Export all stored jobs as a JSON file."""
        with self._lock:
            records = [job.to_dict() for job in self._jobs.values()]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    def load_snapshot(self, filepath: str) -> int:
        """Replay jobs from JSON file into storage, returning count of loaded jobs."""
        with open(filepath, "r", encoding="utf-8") as f:
            records = json.load(f)
        count = 0
        with self._lock:
            for rec in records:
                job = Job.from_dict(rec)
                self._jobs[job.job_id] = job
                count += 1
        return count
