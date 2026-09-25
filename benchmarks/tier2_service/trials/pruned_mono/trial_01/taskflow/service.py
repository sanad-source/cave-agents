"""High-level facade coordinating storage, queue, executor, metrics, and lifecycle."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional
import uuid

from taskflow.executor import WorkerPool
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    """Unified asynchronous job execution and scheduling service facade."""

    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        self.storage: JobStorage = storage if storage is not None else MemoryJobStorage()
        self.queue: PriorityTaskQueue = PriorityTaskQueue()
        self.executor: WorkerPool = WorkerPool(
            queue=self.queue,
            storage=self.storage,
            num_workers=num_workers,
        )

        self._completion_lock = threading.Lock()
        self._completion_cv = threading.Condition(self._completion_lock)

        self.executor.add_listener("on_success", self._on_job_status_change)
        self.executor.add_listener("on_failure", self._on_job_status_change)
        self.executor.add_listener("on_retry", self._on_job_status_change)

    def _on_job_status_change(self, job: Job) -> None:
        with self._completion_lock:
            self._completion_cv.notify_all()

    def register_handler(self, name: str, fn: Callable[..., Any]) -> None:
        """Register a handler callable with the worker pool."""
        self.executor.register_handler(name, fn)

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Add an event listener to the executor."""
        self.executor.add_listener(event, callback)

    def submit_job(
        self,
        fn_name: str,
        *args: Any,
        priority: JobPriority = JobPriority.MEDIUM,
        retry_policy: Optional[RetryPolicy] = None,
        timeout: Optional[float] = None,
        delay: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """Create a Job, record in storage, enqueue, and return job_id."""
        now = time.time()
        scheduled_at = (now + delay) if delay > 0 else 0.0
        job = Job(
            job_id=str(uuid.uuid4()),
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=scheduled_at,
            created_at=now,
            status=JobStatus.PENDING,
        )
        self.storage.save_job(job)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by job_id from storage."""
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Retrieve the status of a job."""
        job = self.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """Block waiting for job to complete or fail.

        Raises TimeoutError if timeout expires.
        Raises RuntimeError if job failed or was cancelled.
        Returns result on success.
        """
        deadline = None if timeout is None else time.time() + max(0.0, timeout)
        with self._completion_lock:
            while True:
                job = self.get_job(job_id)
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
                        raise TimeoutError(f"Job '{job_id}' timed out waiting for completion")
                    self._completion_cv.wait(min(remaining, 0.05))
                else:
                    self._completion_cv.wait(timeout=0.05)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job in queue or storage. Return True if cancelled."""
        job = self.storage.get_job(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        self.queue.cancel(job_id)
        self.storage.update_status(job_id, JobStatus.CANCELLED)
        with self._completion_lock:
            self._completion_cv.notify_all()
        return True

    def get_metrics(self) -> dict[str, int]:
        """Return execution and queue metrics."""
        jobs = self.storage.list_jobs()
        return {
            "total_jobs": len(jobs),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "retrying": sum(1 for j in jobs if j.status == JobStatus.RETRYING),
            "queue_size": self.queue.size(),
            "active_workers": self.executor.get_active_worker_count(),
        }

    def start(self) -> None:
        """Start the worker pool."""
        self.executor.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """Stop the worker pool, waiting up to timeout for running jobs."""
        self.executor.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> TaskQueueService:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
