"""Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

import abc
import json
import threading
from typing import Any, Optional

from taskflow.models import Job, JobStatus

_SENTINEL = object()


class JobStorage(abc.ABC):
    @abc.abstractmethod
    def save_job(self, job: Job) -> None:
        """Save or overwrite a job in storage."""
        pass

    @abc.abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        pass

    @abc.abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """List jobs, optionally filtered by status."""
        pass

    @abc.abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update job status and optionally result/error. Returns True if job was found and updated."""
        pass

    @abc.abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID. Returns True if job was found and removed."""
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
            target_status = status
            if isinstance(status, str):
                try:
                    target_status = JobStatus(status)
                except ValueError:
                    pass
            return [j for j in self._jobs.values() if j.status == target_status]

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
            
            target_status = status
            if isinstance(status, str):
                try:
                    target_status = JobStatus(status)
                except ValueError:
                    pass

            job.status = target_status
            if result is not None:
                job.result = result
            elif target_status == JobStatus.COMPLETED and result is None and job.result is None:
                job.result = None

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
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

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
