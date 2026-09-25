"""taskflow.storage: Storage interfaces and thread-safe in-memory storage with snapshot persistence."""

import json
import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Optional

from taskflow.models import Job, JobStatus


class JobStorage(ABC):
    @abstractmethod
    def save_job(self, job: Job) -> None:
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        pass

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        pass


class MemoryJobStorage(JobStorage):
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
            target_status = JobStatus(status) if isinstance(status, str) else status
            return [job for job in self._jobs.values() if job.status == target_status]

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
            job.status = JobStatus(status) if isinstance(status, str) else status
            if result is not None or job.status == JobStatus.COMPLETED:
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

        dirpath = os.path.dirname(os.path.abspath(filepath))
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

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
