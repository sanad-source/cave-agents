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
    """Unified service facade for asynchronous task execution and scheduling."""

    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        self.storage = storage if storage is not None else MemoryJobStorage()
        self.queue = PriorityTaskQueue()
        self.worker_pool = WorkerPool(
            queue=self.queue,
            storage=self.storage,
            num_workers=num_workers,
        )

        self._cond = threading.Condition()
        self.worker_pool.add_listener("on_start", self._on_job_event)
        self.worker_pool.add_listener("on_success", self._on_job_event)
        self.worker_pool.add_listener("on_failure", self._on_job_event)
        self.worker_pool.add_listener("on_retry", self._on_job_event)

    def _on_job_event(self, job: Job) -> None:
        with self._cond:
            self._cond.notify_all()

    def register_handler(self, name: str, fn: Callable[..., Any]) -> None:
        self.worker_pool.register_handler(name, fn)

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
        now = time.time()
        scheduled_at = (now + delay) if delay > 0.0 else 0.0
        job = Job(
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            status=JobStatus.PENDING,
            retry_policy=retry_policy,
            timeout=timeout,
            created_at=now,
            scheduled_at=scheduled_at,
        )
        self.storage.save_job(job)
        self.queue.push(job)
        with self._cond:
            self._cond.notify_all()
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        job = self.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        start_time = time.time()
        with self._cond:
            while True:
                job = self.get_job(job_id)
                if job is None:
                    raise KeyError(f"Job {job_id} not found")

                if job.status == JobStatus.COMPLETED:
                    return job.result
                if job.status == JobStatus.FAILED:
                    raise RuntimeError(job.error or f"Job {job_id} failed")
                if job.status == JobStatus.CANCELLED:
                    raise RuntimeError(f"Job {job_id} was cancelled")

                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        raise TimeoutError(f"Job {job_id} timed out waiting for result")
                    self._cond.wait(timeout=remaining)
                else:
                    self._cond.wait()

    def cancel_job(self, job_id: str) -> bool:
        cancelled_in_queue = self.queue.cancel(job_id)
        job = self.storage.get_job(job_id)
        if job is not None:
            if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.status = JobStatus.CANCELLED
                self.storage.update_status(job_id, JobStatus.CANCELLED)
                with self._cond:
                    self._cond.notify_all()
                return True
        return cancelled_in_queue

    def get_metrics(self) -> dict[str, int]:
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
            "active_workers": self.worker_pool.active_workers,
        }

    def start(self) -> None:
        self.worker_pool.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        self.worker_pool.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> TaskQueueService:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
