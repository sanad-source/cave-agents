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
        self.queue: PriorityTaskQueue = PriorityTaskQueue()
        self.executor: WorkerPool = WorkerPool(
            queue=self.queue,
            num_workers=num_workers,
            storage=self.storage,
        )

        self._lock = threading.RLock()
        self._job_events: dict[str, threading.Event] = {}

        self.executor.add_listener("on_success", self._on_job_success)
        self.executor.add_listener("on_failure", self._on_job_failure)

    def _get_or_create_event(self, job_id: str) -> threading.Event:
        with self._lock:
            if job_id not in self._job_events:
                self._job_events[job_id] = threading.Event()
            return self._job_events[job_id]

    def _notify_job_event(self, job_id: str) -> None:
        with self._lock:
            event = self._job_events.get(job_id)
            if event:
                event.set()

    def _on_job_success(self, job: Job) -> None:
        self._notify_job_event(job.job_id)

    def _on_job_failure(self, job: Job) -> None:
        self._notify_job_event(job.job_id)

    def register_handler(self, name: str, fn: Callable) -> None:
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
        now = time.time()
        scheduled_at = now + delay if delay > 0.0 else 0.0
        job = Job(
            fn_name=fn_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            retry_policy=retry_policy,
            timeout=timeout,
            scheduled_at=scheduled_at,
        )
        self.storage.save_job(job)
        self._get_or_create_event(job.job_id)
        self.queue.push(job)
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.storage.get_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        job = self.storage.get_job(job_id)
        return job.status if job else None

    def get_job_result(self, job_id: str, timeout: Optional[float] = None) -> Any:
        job = self.storage.get_job(job_id)
        if job is None:
            raise KeyError(f"Job '{job_id}' not found in storage")

        event = self._get_or_create_event(job_id)
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            event.set()

        start_time = time.monotonic()
        while True:
            current_job = self.storage.get_job(job_id)
            if current_job is None:
                raise KeyError(f"Job '{job_id}' not found in storage")

            if current_job.status == JobStatus.COMPLETED:
                return current_job.result
            if current_job.status == JobStatus.FAILED:
                raise RuntimeError(current_job.error or "Job execution failed")
            if current_job.status == JobStatus.CANCELLED:
                raise RuntimeError(f"Job '{job_id}' was cancelled")

            if timeout is not None:
                elapsed = time.monotonic() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    raise TimeoutError(
                        f"Job '{job_id}' timed out after {timeout} seconds without completion"
                    )
                wait_step = min(remaining, 0.05)
            else:
                wait_step = 0.05

            event.wait(timeout=wait_step)

    def cancel_job(self, job_id: str) -> bool:
        job = self.storage.get_job(job_id)
        if job is None:
            return False

        removed_from_queue = self.queue.cancel(job_id)
        if removed_from_queue:
            self.storage.update_status(job_id, JobStatus.CANCELLED)
            self._notify_job_event(job_id)
            return True

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        job.status = JobStatus.CANCELLED
        self.storage.update_status(job_id, JobStatus.CANCELLED)
        self._notify_job_event(job_id)
        return True

    def get_metrics(self) -> dict:
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
            "active_workers": self.executor.active_workers,
        }

    def start(self) -> None:
        self.executor.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        self.executor.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> "TaskQueueService":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
