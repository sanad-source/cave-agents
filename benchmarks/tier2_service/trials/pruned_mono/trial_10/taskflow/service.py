"""High-level facade coordinating storage, queue, executor, metrics, and lifecycle."""

import threading
import time
import uuid
from typing import Any, Callable, Optional

from .executor import WorkerPool
from .models import Job, JobPriority, JobStatus, RetryPolicy
from .queue import PriorityTaskQueue
from .storage import JobStorage, MemoryJobStorage


class TaskQueueService:
    """Unified facade coordinating storage, queue, executor, metrics, and lifecycle."""

    def __init__(
        self,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ):
        self.storage: JobStorage = storage if storage is not None else MemoryJobStorage()
        self.queue: PriorityTaskQueue = PriorityTaskQueue()
        self.executor: WorkerPool = WorkerPool(
            queue=self.queue,
            num_workers=num_workers,
            storage=self.storage,
        )
        self._job_events: dict[str, threading.Event] = {}
        self._events_lock = threading.Lock()

        # Listen for terminal states to wake up get_job_result waiters
        self.executor.add_listener("on_success", self._on_job_terminal)
        self.executor.add_listener("on_failure", self._on_job_terminal)

    def _on_job_terminal(self, job: Job) -> None:
        with self._events_lock:
            event = self._job_events.get(job.job_id)
            if event:
                event.set()

    def _get_or_create_event(self, job_id: str) -> threading.Event:
        with self._events_lock:
            if job_id not in self._job_events:
                self._job_events[job_id] = threading.Event()
            return self._job_events[job_id]

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a function handler for jobs."""
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
        """Creates Job, records in storage, puts in queue, returns job_id."""
        now = time.time()
        scheduled_at = (now + delay) if delay > 0.0 else 0.0
        job = Job(
            job_id=str(uuid.uuid4()),
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
        self._get_or_create_event(job.job_id)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job from storage."""
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Retrieve current job status."""
        job = self.storage.get_job(job_id)
        return job.status if job else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        """Blocks waiting for job to complete or fail.
        Raises TimeoutError if timeout expires; raises RuntimeError if job failed.
        Returns result on success.
        """
        job = self.storage.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        if job.status == JobStatus.COMPLETED:
            return job.result
        if job.status == JobStatus.FAILED:
            raise RuntimeError(job.error or f"Job {job_id} failed")
        if job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Job {job_id} was cancelled")

        event = self._get_or_create_event(job_id)
        signaled = event.wait(timeout=timeout)
        if not signaled:
            raise TimeoutError(f"Job {job_id} timed out waiting for completion")

        job = self.storage.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found after event signal")

        if job.status == JobStatus.COMPLETED:
            return job.result
        if job.status == JobStatus.FAILED:
            raise RuntimeError(job.error or f"Job {job_id} failed")
        if job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Job {job_id} was cancelled")

        raise RuntimeError(f"Job {job_id} finished with status: {job.status}")

    def cancel_job(self, job_id: str) -> bool:
        """Cancels job in queue or storage."""
        in_queue = self.queue.cancel(job_id)
        job = self.storage.get_job(job_id)
        if job is None:
            return False

        if in_queue or job.status in (JobStatus.PENDING, JobStatus.RETRYING):
            job.status = JobStatus.CANCELLED
            self.storage.update_status(job_id, JobStatus.CANCELLED)
            with self._events_lock:
                event = self._job_events.get(job_id)
                if event:
                    event.set()
            return True
        return False

    def get_metrics(self) -> dict:
        """Returns metrics summary dictionary."""
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
        """Start worker threads."""
        self.executor.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """Stop worker threads."""
        self.executor.shutdown(wait=True, timeout=timeout)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
