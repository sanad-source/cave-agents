"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

from __future__ import annotations

import abc
import json
import os
import threading
from typing import Any, Optional

from taskflow.models import Job, JobStatus


class JobStorage(abc.ABC):
    @abc.abstractmethod
    def save_job(self, job: Job) -> None:
        """Store or update a job."""
        pass

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its unique identifier."""
        pass

    @abc.abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List all jobs, optionally filtering by status."""
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
        """Delete a job by id. Returns True if deleted, False otherwise."""
        pass


class MemoryJobStorage(JobStorage):
    """Thread-safe in-memory job storage using RLock."""

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
        """Exports all stored jobs as JSON file."""
        with self._lock:
            data = [job.to_dict() for job in self._jobs.values()]
        
        dir_path = os.path.dirname(os.path.abspath(filepath))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
            
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_snapshot(self, filepath: str) -> int:
        """Replays jobs from JSON file into storage, returning count of loaded jobs."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        with self._lock:
            for item in data:
                job = Job.from_dict(item)
                self._jobs[job.job_id] = job
                count += 1
        return count
