"""Storage interfaces and in-memory thread-safe implementation with snapshotting."""

from __future__ import annotations

import abc
import json
import os
import threading
from typing import Any, Optional

from taskflow.models import Job, JobStatus


class JobStorage(abc.ABC):
    """Abstract Base Class defining the job persistence interface."""

    @abc.abstractmethod
    def save_job(self, job: Job) -> None:
        """Persist or overwrite a job record."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its unique identifier."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List jobs, optionally filtered by lifecycle status."""
        raise NotImplementedError

    @abc.abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update job status, result, and/or error. Returns True if job was found and updated."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Remove a job by identifier. Returns True if job was found and deleted."""
        raise NotImplementedError


class MemoryJobStorage(JobStorage):
    """Thread-safe in-memory job storage using threading.RLock with snapshot persistence."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}

    def save_job(self, job: Job) -> None:
        """Persist or update a job record in memory."""
        with self._lock:
            self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by id, or None if not found."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List jobs, optionally filtered by status."""
        with self._lock:
            if status is None:
                return list(self._jobs.values())
            if isinstance(status, str):
                try:
                    status = JobStatus(status)
                except ValueError:
                    pass
            return [j for j in self._jobs.values() if j.status == status]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update job status and optionally result/error. Returns True if updated."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if isinstance(status, str):
                status = JobStatus(status)
            job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            return True

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by id. Returns True if job was found and deleted."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def save_snapshot(self, filepath: str) -> None:
        """Export all stored jobs as JSON file."""
        with self._lock:
            data = [job.to_dict() for job in self._jobs.values()]

        parent_dir = os.path.dirname(filepath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_snapshot(self, filepath: str) -> int:
        """Replay jobs from JSON file into storage, returning count of loaded jobs."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        loaded_jobs = [Job.from_dict(item) for item in data]
        with self._lock:
            for job in loaded_jobs:
                self._jobs[job.job_id] = job
            return len(loaded_jobs)
