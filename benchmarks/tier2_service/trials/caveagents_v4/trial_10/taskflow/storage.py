"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List

from taskflow.models import Job, JobStatus

_UNSET = object()


class JobStorage(ABC):
    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Persist or update a job in storage."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job by id, or return None if not found."""
        pass

    @abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List all jobs, optionally filtered by status."""
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update the status, result, and/or error of a job. Returns True if job was found."""
        pass

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete job from storage. Returns True if found and deleted."""
        pass


class MemoryJobStorage(JobStorage):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}

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
            if isinstance(status, str):
                status = JobStatus(status)
            return [job for job in self._jobs.values() if job.status == status]

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
            if isinstance(status, str):
                status = JobStatus(status)
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
        dirname = os.path.dirname(filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
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
