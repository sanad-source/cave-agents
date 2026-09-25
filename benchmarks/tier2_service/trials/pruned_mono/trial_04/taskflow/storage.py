"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Optional

from taskflow.models import Job, JobStatus

_UNSET = object()


class JobStorage(ABC):
    """Abstract base class for job storage backends."""

    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Persist or update a job."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        pass

    @abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List all jobs or jobs matching a given status."""
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = _UNSET,
        error: Optional[str] = _UNSET,
    ) -> bool:
        """Update status and optionally result/error of a job."""
        pass

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        pass


class MemoryJobStorage(JobStorage):
    """Thread-safe in-memory implementation of JobStorage."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}

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
        result: Any = _UNSET,
        error: Optional[str] = _UNSET,
    ) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = status
            if result is not _UNSET:
                job.result = result
            if error is not _UNSET:
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

        dir_name = os.path.dirname(os.path.abspath(filepath))
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_snapshot(self, filepath: str) -> int:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        with self._lock:
            count = 0
            for item in data:
                job = Job.from_dict(item)
                self._jobs[job.job_id] = job
                count += 1
            return count
