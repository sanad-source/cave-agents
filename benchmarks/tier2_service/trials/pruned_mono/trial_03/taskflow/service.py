import threading
import time
from typing import Any, Callable, Optional
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.storage import JobStorage, MemoryJobStorage
from taskflow.queue import PriorityTaskQueue
from taskflow.executor import WorkerPool


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
            num_workers=num_workers,
            storage=self.storage,
        )
        self._job_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

        self.worker_pool.add_listener("on_success", self._on_job_terminal)
        self.worker_pool.add_listener("on_failure", self._on_job_terminal)

    def _on_job_terminal(self, job: Job) -> None:
        with self._lock:
            event = self._job_events.get(job.job_id)
            if event:
                event.set()

    def register_handler(self, name: str, fn: Callable) -> None:
        self.worker_pool.register_handler(name, fn)

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        self.worker_pool.add_listener(event, callback)

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
        scheduled_at = time.time() + delay if delay > 0 else 0.0
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
            self._job_events[job.job_id] = threading.Event()
        self.storage.save_job(job)
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
            raise ValueError(f"Job '{job_id}' not found")

        if job.status == JobStatus.COMPLETED:
            return job.result
        if job.status == JobStatus.FAILED:
            raise RuntimeError(job.error or f"Job '{job_id}' failed")
        if job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Job '{job_id}' was cancelled")

        with self._lock:
            job = self.storage.get_job(job_id)
            if job.status == JobStatus.COMPLETED:
                return job.result
            if job.status == JobStatus.FAILED:
                raise RuntimeError(job.error or f"Job '{job_id}' failed")
            if job.status == JobStatus.CANCELLED:
                raise RuntimeError(f"Job '{job_id}' was cancelled")

            if job_id not in self._job_events:
                self._job_events[job_id] = threading.Event()
            event = self._job_events[job_id]

        signaled = event.wait(timeout=timeout)
        if not signaled:
            raise TimeoutError(f"Timed out waiting for job '{job_id}' result")

        job = self.storage.get_job(job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' not found")
        if job.status == JobStatus.COMPLETED:
            return job.result
        if job.status == JobStatus.FAILED:
            raise RuntimeError(job.error or f"Job '{job_id}' failed")
        if job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Job '{job_id}' was cancelled")
        raise RuntimeError(f"Job '{job_id}' ended with unexpected status: {job.status}")

    def cancel_job(self, job_id: str) -> bool:
        cancelled = self.queue.cancel(job_id)
        if cancelled:
            self.storage.update_status(job_id, JobStatus.CANCELLED)
            with self._lock:
                event = self._job_events.get(job_id)
                if event:
                    event.set()
            return True

        job = self.storage.get_job(job_id)
        if job and job.status in (JobStatus.PENDING, JobStatus.RETRYING):
            self.storage.update_status(job_id, JobStatus.CANCELLED)
            with self._lock:
                event = self._job_events.get(job_id)
                if event:
                    event.set()
            return True

        return False

    def get_metrics(self) -> dict:
        return {
            "total_jobs": len(self.storage.list_jobs()),
            "completed": len(self.storage.list_jobs(JobStatus.COMPLETED)),
            "failed": len(self.storage.list_jobs(JobStatus.FAILED)),
            "retrying": len(self.storage.list_jobs(JobStatus.RETRYING)),
            "queue_size": self.queue.size(),
            "active_workers": self.worker_pool.active_workers,
        }

    def start(self) -> None:
        self.worker_pool.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        self.worker_pool.shutdown(wait=True, timeout=timeout)

    def __enter__(self) -> "TaskQueueService":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
