"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

import abc
import json
import os
import threading
from typing import Any, Optional

from taskflow.models import Job, JobStatus


class JobStorage(abc.ABC):
    @abc.abstractmethod
    def save_job(self, job: Job) -> None:
        """Persist or update a job in storage."""
        pass

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its ID."""
        pass

    @abc.abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List all jobs, optionally filtered by status."""
        pass

    @abc.abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update job status, result, and/or error. Returns True if job found and updated."""
        pass

    @abc.abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID. Returns True if found and deleted."""
        pass


class MemoryJobStorage(JobStorage):
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
            if isinstance(status, str) and not isinstance(status, JobStatus):
                status = JobStatus(status)
            return [job for job in self._jobs.values() if job.status == status]

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
            if isinstance(status, str) and not isinstance(status, JobStatus):
                status = JobStatus(status)
            job.status = status
            if result is not None or status == JobStatus.COMPLETED:
                job.result = result
            if error is not None or status == JobStatus.FAILED:
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
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def load_snapshot(self, filepath: str) -> int:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "jobs" in data and isinstance(data["jobs"], list):
                items = data["jobs"]
            else:
                items = list(data.values())
        else:
            items = []

        with self._lock:
            count = 0
            for item in items:
                job = Job.from_dict(item)
                self._jobs[job.job_id] = job
                count += 1
            return count
