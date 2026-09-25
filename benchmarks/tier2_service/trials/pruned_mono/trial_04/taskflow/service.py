"""High-level facade coordinating storage, queue, executor, metrics, and lifecycle."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from taskflow.executor import WorkerPool
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    """Unified service facade for job scheduling and execution."""

    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        self._storage: JobStorage = (
            storage if storage is not None else MemoryJobStorage()
        )
        self._queue = PriorityTaskQueue()
        self._executor = WorkerPool(
            queue=self._queue,
            num_workers=num_workers,
            storage=self._storage,
        )
        self._state_lock = threading.RLock()
        self._state_cond = threading.Condition(self._state_lock)

        def _notify_completion(job: Job) -> None:
            with self._state_cond:
                self._state_cond.notify_all()

        self._executor.add_listener("on_success", _notify_completion)
        self._executor.add_listener("on_failure", _notify_completion)

    @property
    def storage(self) -> JobStorage:
        return self._storage

    @property
    def queue(self) -> PriorityTaskQueue:
        return self._queue

    @property
    def executor(self) -> WorkerPool:
        return self._executor

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a handler callable by function name."""
        self._executor.register_handler(name, fn)

    def submit_job(
        self,
        fn_name: str,
        *args,
        priority: JobPriority = JobPriority.MEDIUM,
        retry_policy: Optional[RetryPolicy] = None,
        timeout: Optional[float] = None,
        delay: float = 0.0,
        **kwargs,
    ) -> str:
        """Create and submit a job for asynchronous execution."""
        scheduled_at = (time.time() + delay) if delay > 0 else 0.0
        job = Job(
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=scheduled_at,
        )
        self._storage.save_job(job)
        self._queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its ID."""
        return self._storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Retrieve the current status of a job."""
        job = self._storage.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """Block waiting for job to complete or fail.

        Raises TimeoutError if timeout expires.
        Raises RuntimeError if job failed or was cancelled.
        Returns job result on success.
        """
        deadline = (time.time() + timeout) if timeout is not None else None
        with self._state_cond:
            while True:
                job = self._storage.get_job(job_id)
                if job is None:
                    raise KeyError(f"Job '{job_id}' not found")
                if job.status == JobStatus.COMPLETED:
                    return job.result
                if job.status == JobStatus.FAILED:
                    raise RuntimeError(job.error or f"Job '{job_id}' failed")
                if job.status == JobStatus.CANCELLED:
                    raise RuntimeError(f"Job '{job_id}' was cancelled")

                if deadline is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Job '{job_id}' did not finish within {timeout} seconds"
                        )
                    self._state_cond.wait(min(remaining, 0.1))
                else:
                    self._state_cond.wait(0.1)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job in the queue or storage."""
        cancelled_in_queue = self._queue.cancel(job_id)
        job = self._storage.get_job(job_id)
        if job is None:
            return False

        if cancelled_in_queue:
            self._storage.update_status(job_id, JobStatus.CANCELLED)
            with self._state_cond:
                self._state_cond.notify_all()
            return True

        if job.status in (JobStatus.PENDING, JobStatus.RETRYING):
            job.status = JobStatus.CANCELLED
            self._storage.update_status(job_id, JobStatus.CANCELLED)
            with self._state_cond:
                self._state_cond.notify_all()
            return True

        return False

    def get_metrics(self) -> dict:
        """Return operational metrics."""
        jobs = self._storage.list_jobs()
        return {
            "total_jobs": len(jobs),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "retrying": sum(1 for j in jobs if j.status == JobStatus.RETRYING),
            "queue_size": self._queue.size(),
            "active_workers": self._executor.active_workers,
        }

    def start(self) -> None:
        """Start worker pool."""
        self._executor.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """Stop worker pool."""
        self._executor.shutdown(wait=True, timeout=timeout)
        with self._state_cond:
            self._state_cond.notify_all()

    def __enter__(self) -> "TaskQueueService":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
