"""High-level facade coordinating storage, queue, executor, metrics, and lifecycle."""

import threading
import time
import uuid
from typing import Any, Callable, Optional

from taskflow.executor import WorkerPool
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        self._storage: JobStorage = storage if storage is not None else MemoryJobStorage()
        self._queue = PriorityTaskQueue()
        self._worker_pool = WorkerPool(
            queue=self._queue,
            storage=self._storage,
            num_workers=num_workers,
        )
        self._terminal_lock = threading.Lock()
        self._terminal_cond = threading.Condition(self._terminal_lock)

        self._worker_pool.add_listener("on_success", self._on_job_terminal)
        self._worker_pool.add_listener("on_failure", self._on_job_terminal)

    def _on_job_terminal(self, job: Job) -> None:
        with self._terminal_cond:
            self._terminal_cond.notify_all()

    def register_handler(self, name: str, fn: Callable) -> None:
        self._worker_pool.register_handler(name, fn)

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
        sched = (time.time() + delay) if delay > 0 else 0.0
        job = Job(
            job_id=str(uuid.uuid4()),
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            status=JobStatus.PENDING,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=sched,
        )
        self._storage.save_job(job)
        self._queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        job = self._storage.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        start_time = time.time()
        with self._terminal_cond:
            while True:
                job = self._storage.get_job(job_id)
                if job is None:
                    raise KeyError(f"Job '{job_id}' not found")

                if job.status == JobStatus.COMPLETED:
                    return job.result
                elif job.status == JobStatus.FAILED:
                    raise RuntimeError(job.error or f"Job '{job_id}' failed")
                elif job.status == JobStatus.CANCELLED:
                    raise RuntimeError(f"Job '{job_id}' was cancelled")

                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        raise TimeoutError(f"Job '{job_id}' did not complete within {timeout} seconds")
                    self._terminal_cond.wait(timeout=remaining)
                else:
                    self._terminal_cond.wait(timeout=0.5)

    def cancel_job(self, job_id: str) -> bool:
        job = self._storage.get_job(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        self._queue.cancel(job_id)
        self._storage.update_status(job_id, JobStatus.CANCELLED)
        job.status = JobStatus.CANCELLED
        with self._terminal_cond:
            self._terminal_cond.notify_all()
        return True

    def get_metrics(self) -> dict:
        jobs = self._storage.list_jobs()
        return {
            "total_jobs": len(jobs),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "retrying": sum(1 for j in jobs if j.status == JobStatus.RETRYING),
            "queue_size": self._queue.size(),
            "active_workers": self._worker_pool.active_workers,
        }

    def start(self) -> None:
        self._worker_pool.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        self._worker_pool.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> "TaskQueueService":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
