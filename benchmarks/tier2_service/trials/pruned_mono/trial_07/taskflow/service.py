"""High-level facade coordinating storage, queue, executor, metrics, and lifecycle."""

import threading
import time
from typing import Any, Callable, Optional

from taskflow.executor import WorkerPool
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    """Unified facade composing MemoryJobStorage, PriorityTaskQueue, and WorkerPool."""

    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        self.storage = storage if storage is not None else MemoryJobStorage()
        self.queue = PriorityTaskQueue()
        self.executor = WorkerPool(queue=self.queue, num_workers=num_workers, storage=self.storage)
        self._lock = threading.RLock()
        self._completion_events: dict[str, threading.Event] = {}

        self.executor.add_listener("on_success", self._notify_completion)
        self.executor.add_listener("on_failure", self._notify_completion)

    def _notify_completion(self, job: Job) -> None:
        with self._lock:
            event = self._completion_events.get(job.job_id)
            if event is not None:
                event.set()

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a function handler for jobs by name."""
        self.executor.register_handler(name, fn)

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
        """Create a Job, persist it in storage, enqueue it, and return its job_id."""
        scheduled_at = (time.time() + delay) if delay > 0.0 else 0.0
        job = Job(
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=scheduled_at,
        )
        with self._lock:
            self._completion_events[job.job_id] = threading.Event()
        self.storage.save_job(job)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by id from storage."""
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Retrieve the current JobStatus for a job."""
        job = self.storage.get_job(job_id)
        return job.status if job is not None else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """Block waiting for job to complete or fail.

        Raises TimeoutError if timeout expires; raises RuntimeError if job failed or was cancelled.
        Returns result on success.
        """
        with self._lock:
            event = self._completion_events.setdefault(job_id, threading.Event())

        job = self.storage.get_job(job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")

        if job.status == JobStatus.COMPLETED:
            return job.result
        elif job.status == JobStatus.FAILED:
            raise RuntimeError(job.error or "Job failed")
        elif job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Job '{job_id}' was cancelled")

        signaled = event.wait(timeout=timeout)
        if not signaled:
            job = self.storage.get_job(job_id)
            if job and job.status == JobStatus.COMPLETED:
                return job.result
            if job and job.status == JobStatus.FAILED:
                raise RuntimeError(job.error or "Job failed")
            if job and job.status == JobStatus.CANCELLED:
                raise RuntimeError(f"Job '{job_id}' was cancelled")
            raise TimeoutError(f"Timed out waiting for job '{job_id}' result")

        job = self.storage.get_job(job_id)
        if job is None:
            raise RuntimeError(f"Job '{job_id}' not found after completion")

        if job.status == JobStatus.COMPLETED:
            return job.result
        elif job.status == JobStatus.FAILED:
            raise RuntimeError(job.error or "Job failed")
        elif job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Job '{job_id}' was cancelled")
        else:
            raise RuntimeError(f"Job '{job_id}' finished in unexpected status: {job.status}")

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job in queue or storage. Returns True if job was successfully cancelled."""
        with self._lock:
            removed_from_queue = self.queue.cancel(job_id)
            job = self.storage.get_job(job_id)
            if job is not None:
                if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                    job.status = JobStatus.CANCELLED
                    self.storage.update_status(job_id, JobStatus.CANCELLED)
                    event = self._completion_events.get(job_id)
                    if event:
                        event.set()
                    return True
            if removed_from_queue:
                event = self._completion_events.get(job_id)
                if event:
                    event.set()
                return True
            return False

    def get_metrics(self) -> dict:
        """Return operational metrics for the service."""
        jobs = self.storage.list_jobs()
        total_jobs = len(jobs)
        completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)
        retrying = sum(1 for j in jobs if j.status == JobStatus.RETRYING)
        queue_size = self.queue.size()
        active_workers = self.executor.active_workers
        return {
            "total_jobs": total_jobs,
            "completed": completed,
            "failed": failed,
            "retrying": retrying,
            "queue_size": queue_size,
            "active_workers": active_workers,
        }

    def start(self) -> None:
        """Start the background worker pool."""
        self.executor.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """Stop the background worker pool."""
        self.executor.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> "TaskQueueService":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
