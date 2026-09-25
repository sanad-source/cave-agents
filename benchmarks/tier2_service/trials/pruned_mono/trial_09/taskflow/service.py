from __future__ import annotations

import threading
import time
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
        self.storage: JobStorage = storage if storage is not None else MemoryJobStorage()
        self.queue = PriorityTaskQueue()
        self.worker_pool = WorkerPool(
            queue=self.queue,
            storage=self.storage,
            num_workers=num_workers,
        )
        self.executor = self.worker_pool
        self.num_workers = num_workers
        self._job_events: dict[str, threading.Event] = {}
        self._events_lock = threading.Lock()

        self.worker_pool.add_listener("on_success", self._on_job_terminal)
        self.worker_pool.add_listener("on_failure", self._on_job_terminal)

    def _on_job_terminal(self, job: Job) -> None:
        with self._events_lock:
            ev = self._job_events.get(job.job_id)
            if ev is not None:
                ev.set()

    def register_handler(self, name: str, fn: Callable) -> None:
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
        scheduled_at = time.time() + delay if delay > 0.0 else 0.0
        job = Job(
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=scheduled_at,
            status=JobStatus.PENDING,
        )
        with self._events_lock:
            self._job_events[job.job_id] = threading.Event()
        self.storage.save_job(job)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        job = self.storage.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        start_time = time.time()

        with self._events_lock:
            job = self.storage.get_job(job_id)
            if job is None:
                raise KeyError(f"Job '{job_id}' not found")
            if job.status == JobStatus.COMPLETED:
                return job.result
            if job.status == JobStatus.FAILED:
                raise RuntimeError(job.error or "Job failed")
            if job.status == JobStatus.CANCELLED:
                raise RuntimeError("Job was cancelled")

            if job_id not in self._job_events:
                self._job_events[job_id] = threading.Event()
            event = self._job_events[job_id]

        while True:
            now = time.time()
            if timeout is not None:
                remaining = timeout - (now - start_time)
                if remaining <= 0:
                    raise TimeoutError(f"Job '{job_id}' did not complete within {timeout}s")
                wait_time = remaining
            else:
                wait_time = None

            signaled = event.wait(timeout=wait_time)

            job = self.storage.get_job(job_id)
            if job is None:
                raise KeyError(f"Job '{job_id}' not found")
            if job.status == JobStatus.COMPLETED:
                return job.result
            if job.status == JobStatus.FAILED:
                raise RuntimeError(job.error or "Job failed")
            if job.status == JobStatus.CANCELLED:
                raise RuntimeError("Job was cancelled")

            if not signaled:
                raise TimeoutError(f"Job '{job_id}' did not complete within {timeout}s")

    def cancel_job(self, job_id: str) -> bool:
        job = self.storage.get_job(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        self.queue.cancel(job_id)
        job.status = JobStatus.CANCELLED
        self.storage.update_status(job_id, JobStatus.CANCELLED)
        with self._events_lock:
            ev = self._job_events.get(job_id)
            if ev is not None:
                ev.set()
        return True

    def get_metrics(self) -> dict:
        all_jobs = self.storage.list_jobs()
        total_jobs = len(all_jobs)
        completed = sum(1 for j in all_jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in all_jobs if j.status == JobStatus.FAILED)
        retrying = sum(1 for j in all_jobs if j.status == JobStatus.RETRYING)
        queue_size = self.queue.size()
        active_workers = self.worker_pool.active_workers
        return {
            "total_jobs": total_jobs,
            "completed": completed,
            "failed": failed,
            "retrying": retrying,
            "queue_size": queue_size,
            "active_workers": active_workers,
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
