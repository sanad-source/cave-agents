"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

import abc
import json
import os
import threading
from typing import Any, List, Optional

from taskflow.models import Job, JobStatus


class JobStorage(abc.ABC):
    """Abstract base class defining the job storage interface."""

    @abc.abstractmethod
    def save_job(self, job: Job) -> None:
        """Saves or updates a job in storage."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieves a job by its ID, or returns None if not found."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
        """Lists all jobs, optionally filtered by status."""
        raise NotImplementedError

    @abc.abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Updates the status and optional result or error of a job. Returns True if updated."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Deletes a job by ID from storage. Returns True if deleted, False otherwise."""
        raise NotImplementedError


class MemoryJobStorage(JobStorage):
    """Thread-safe in-memory job storage utilizing threading.RLock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}

    def save_job(self, job: Job) -> None:
        """Saves a job in storage."""
        with self._lock:
            self._jobs[job.job_id] = job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieves a job by its ID, or returns None if not found."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
        """Lists all jobs, optionally filtered by status."""
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
        """Updates status, result, and error of a job. Returns True if found and updated."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if isinstance(status, str) and not isinstance(status, JobStatus):
                status = JobStatus(status)
            job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            return True

    def delete_job(self, job_id: str) -> bool:
        """Deletes a job by ID from storage. Returns True if found and deleted."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def save_snapshot(self, filepath: str) -> None:
        """Exports all stored jobs as a JSON file."""
        with self._lock:
            data = [job.to_dict() for job in self._jobs.values()]
        abs_path = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_snapshot(self, filepath: str) -> int:
        """Replays jobs from JSON file into storage, returning count of loaded jobs."""
        abs_path = os.path.abspath(filepath)
        with open(abs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self._lock:
            count = 0
            for item in data:
                job = Job.from_dict(item)
                self._jobs[job.job_id] = job
                count += 1
            return count
