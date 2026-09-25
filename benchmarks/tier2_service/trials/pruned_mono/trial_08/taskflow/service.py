"""TaskQueueService facade coordinating storage, queue, executor, metrics, and lifecycle."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from taskflow.executor import WorkerPool
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    """Unified facade composing storage, priority queue, and worker pool."""

    def __init__(self, num_workers: int = 4, storage: Optional[JobStorage] = None) -> None:
        self.storage = storage if storage is not None else MemoryJobStorage()
        self.queue = PriorityTaskQueue()
        self.pool = WorkerPool(self.queue, num_workers=num_workers)

        self._lock = threading.RLock()
        self._completion_cond = threading.Condition(self._lock)

        # Wire pool listeners to update storage and notify completion
        self.pool.add_listener("on_start", self._on_job_start)
        self.pool.add_listener("on_success", self._on_job_success)
        self.pool.add_listener("on_failure", self._on_job_failure)
        self.pool.add_listener("on_retry", self._on_job_retry)

    def _on_job_start(self, job: Job) -> None:
        self.storage.save_job(job)

    def _on_job_success(self, job: Job) -> None:
        self.storage.save_job(job)
        with self._completion_cond:
            self._completion_cond.notify_all()

    def _on_job_failure(self, job: Job) -> None:
        self.storage.save_job(job)
        with self._completion_cond:
            self._completion_cond.notify_all()

    def _on_job_retry(self, job: Job) -> None:
        self.storage.save_job(job)

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a handler callable by function name."""
        self.pool.register_handler(name, fn)

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
        """Create Job, record in storage, put in queue, and return job_id."""
        now = time.time()
        scheduled_at = now + delay if delay > 0 else 0.0
        job = Job(
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            status=JobStatus.PENDING,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=scheduled_at,
        )
        self.storage.save_job(job)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its ID."""
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Retrieve job status by job ID."""
        job = self.storage.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """Blocks waiting for job to complete or fail.

        Raises TimeoutError if timeout expires.
        Raises RuntimeError if job failed or cancelled.
        Returns result on success.
        """
        deadline = (time.time() + timeout) if timeout is not None else None

        with self._completion_cond:
            while True:
                job = self.storage.get_job(job_id)
                if job is None:
                    raise KeyError(f"Job {job_id} not found in storage")

                if job.status == JobStatus.COMPLETED:
                    return job.result
                elif job.status == JobStatus.FAILED:
                    raise RuntimeError(f"Job {job_id} failed: {job.error}")
                elif job.status == JobStatus.CANCELLED:
                    raise RuntimeError(f"Job {job_id} was cancelled")

                if deadline is not None:
                    rem = deadline - time.time()
                    if rem <= 0:
                        raise TimeoutError(f"Job {job_id} did not finish within {timeout} seconds")
                    self._completion_cond.wait(timeout=rem)
                else:
                    self._completion_cond.wait()

    def cancel_job(self, job_id: str) -> bool:
        """Cancels job in queue or storage."""
        # Attempt cancel in queue
        cancelled_in_queue = self.queue.cancel(job_id)
        job = self.storage.get_job(job_id)
        if job is not None and job.status in (JobStatus.PENDING, JobStatus.RETRYING):
            self.storage.update_status(job_id, JobStatus.CANCELLED)
            with self._completion_cond:
                self._completion_cond.notify_all()
            return True
        return cancelled_in_queue

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics dict.

        {"total_jobs": int, "completed": int, "failed": int, "retrying": int, "queue_size": int, "active_workers": int}
        """
        jobs = self.storage.list_jobs()
        completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
        retrying = sum(1 for j in jobs if j.status == JobStatus.RETRYING)
        return {
            "total_jobs": len(jobs),
            "completed": completed,
            "failed": failed,
            "retrying": retrying,
            "queue_size": self.queue.size(),
            "active_workers": self.pool.active_workers,
        }

    def start(self) -> None:
        """Start worker pool."""
        self.pool.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """Stop worker pool."""
        self.pool.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> TaskQueueService:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
