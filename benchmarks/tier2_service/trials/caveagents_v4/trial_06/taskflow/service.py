"""High-level service facade coordinating storage, queue, executor, and metrics."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

from taskflow.executor import WorkerPool
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    """Unified service facade composing storage, priority queue, and worker pool."""

    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(num_workers, JobStorage):
            storage = num_workers
            num_workers = kwargs.get("num_workers", 4)
        if "num_workers" in kwargs:
            num_workers = kwargs["num_workers"]

        self.storage: JobStorage = storage if storage is not None else MemoryJobStorage()
        self.queue: PriorityTaskQueue = PriorityTaskQueue()
        self.pool: WorkerPool = WorkerPool(
            queue=self.queue,
            storage=self.storage,
            num_workers=int(num_workers),
        )
        self.executor = self.pool
        self.worker_pool = self.pool

        self._job_events: Dict[str, threading.Event] = {}
        self._events_lock = threading.Lock()

        self.pool.add_listener("on_success", self._on_job_terminal)
        self.pool.add_listener("on_failure", self._on_job_terminal)

    def _on_job_terminal(self, job: Job) -> None:
        """Callback when a job succeeds or fails terminally to wake up waiting callers."""
        with self._events_lock:
            event = self._job_events.get(job.job_id)
            if event is not None:
                event.set()

    @property
    def is_running(self) -> bool:
        """Return True if background workers are running."""
        return self.pool.is_running

    @property
    def active_workers(self) -> int:
        """Return count of currently active worker threads."""
        return self.pool.active_workers

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a job handler callable by function name."""
        self.pool.register_handler(name, fn)

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register an event listener on the worker pool."""
        self.pool.add_listener(event, callback)

    def remove_listener(self, event: str, callback: Callable[[Job], None]) -> bool:
        """Remove an event listener from the worker pool."""
        return self.pool.remove_listener(event, callback)

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
        """Create a job, save to storage, push to queue, and return unique job_id."""
        if not args and "args" in kwargs and isinstance(kwargs["args"], (list, tuple)):
            args = tuple(kwargs.pop("args"))
        if "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
            inner_kw = kwargs.pop("kwargs")
            kwargs.update(inner_kw)

        if isinstance(priority, int) and not isinstance(priority, JobPriority):
            try:
                priority = JobPriority(priority)
            except ValueError:
                pass
        elif isinstance(priority, str):
            try:
                priority = JobPriority[priority.upper()]
            except KeyError:
                pass

        job_id = kwargs.pop("job_id", None) or str(uuid.uuid4())
        now = time.time()
        delay_val = max(0.0, float(delay))
        scheduled_at = (now + delay_val) if delay_val > 0.0 else 0.0

        job = Job(
            job_id=job_id,
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            status=JobStatus.PENDING,
            retry_policy=retry_policy,
            attempts=0,
            created_at=now,
            scheduled_at=scheduled_at,
            timeout=timeout,
        )

        with self._events_lock:
            self._job_events[job.job_id] = threading.Event()

        self.storage.save_job(job)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job record by job_id from storage."""
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Retrieve current lifecycle status for given job_id."""
        job = self.storage.get_job(job_id)
        if job is None:
            return None
        return job.status

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """Block waiting for job to complete or fail. Raise TimeoutError or RuntimeError."""
        deadline = (time.time() + timeout) if timeout is not None else None

        with self._events_lock:
            if job_id not in self._job_events:
                self._job_events[job_id] = threading.Event()
            event = self._job_events[job_id]

        while True:
            job = self.storage.get_job(job_id)
            if job is None:
                raise KeyError(f"Job with id '{job_id}' not found")

            if job.status == JobStatus.COMPLETED:
                return job.result
            elif job.status == JobStatus.FAILED:
                raise RuntimeError(job.error or f"Job '{job_id}' failed")
            elif job.status == JobStatus.CANCELLED:
                raise RuntimeError(f"Job '{job_id}' was cancelled")

            if deadline is not None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"Job '{job_id}' timed out waiting for result after {timeout}s")
                wait_slice = min(remaining, 0.05)
            else:
                wait_slice = 0.05

            event.wait(timeout=wait_slice)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel job in queue or storage. Return True if cancelled successfully."""
        queue_cancelled = self.queue.cancel(job_id)
        job = self.storage.get_job(job_id)
        if job is None:
            return queue_cancelled

        if queue_cancelled:
            self.storage.update_status(job_id, JobStatus.CANCELLED)
            job.status = JobStatus.CANCELLED
            with self._events_lock:
                event = self._job_events.get(job_id)
                if event is not None:
                    event.set()
            return True

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        self.storage.update_status(job_id, JobStatus.CANCELLED)
        job.status = JobStatus.CANCELLED
        with self._events_lock:
            event = self._job_events.get(job_id)
            if event is not None:
                event.set()
        return True

    def get_metrics(self) -> dict[str, int]:
        """Return runtime execution and queue metrics."""
        jobs = self.storage.list_jobs()
        total_jobs = len(jobs)
        completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
        retrying = sum(1 for j in jobs if j.status == JobStatus.RETRYING)
        queue_size = self.queue.size()
        active_workers = self.pool.active_workers
        return {
            "total_jobs": total_jobs,
            "completed": completed,
            "failed": failed,
            "retrying": retrying,
            "queue_size": queue_size,
            "active_workers": active_workers,
        }

    def start(self) -> None:
        """Start worker pool background threads."""
        self.pool.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """Stop worker pool background threads."""
        self.pool.shutdown(wait=True, timeout=timeout)

    def shutdown(self, timeout: Optional[float] = 5.0) -> None:
        """Alias for stop."""
        self.stop(timeout=timeout)

    def __enter__(self) -> "TaskQueueService":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
