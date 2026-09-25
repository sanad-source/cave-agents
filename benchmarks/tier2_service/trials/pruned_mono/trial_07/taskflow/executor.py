"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

import concurrent.futures
import threading
import time
from typing import Callable, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class WorkerPool:
    """Manages a pool of background daemon worker threads executing jobs from a PriorityTaskQueue."""

    def __init__(
        self,
        queue: Optional[PriorityTaskQueue] = None,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        if isinstance(queue, int):
            num_workers = queue
            queue = None
        self.queue = queue
        self.num_workers = num_workers
        self.storage = storage

        self._lock = threading.RLock()
        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._running = False
        self._active_workers = 0

    @property
    def active_workers(self) -> int:
        """Return the number of workers currently executing a task."""
        with self._lock:
            return self._active_workers

    def set_queue(self, queue: PriorityTaskQueue) -> None:
        """Set the priority task queue for this worker pool."""
        with self._lock:
            self.queue = queue

    def set_storage(self, storage: JobStorage) -> None:
        """Set the job storage backend for this worker pool."""
        with self._lock:
            self.storage = storage

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a callable handler by function name."""
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register an event listener callback for a given lifecycle event."""
        with self._lock:
            self._listeners.setdefault(event, []).append(callback)

    def _fire(self, event: str, job: Job) -> None:
        """Fire all registered listener callbacks for the given event."""
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def start(self) -> None:
        """Start the background daemon worker threads."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-Worker-{i}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Signal workers to stop and optionally wait for in-progress tasks to complete."""
        self._stop_event.set()
        with self._lock:
            threads = list(self._threads)

        if wait:
            deadline = (time.time() + timeout) if timeout is not None else None
            for t in threads:
                if deadline is not None:
                    remaining = max(0.0, deadline - time.time())
                    t.join(timeout=remaining)
                else:
                    t.join()

        with self._lock:
            self._running = False
            self._threads.clear()

    def _worker_loop(self) -> None:
        """Main loop executed by worker threads."""
        while not self._stop_event.is_set():
            if self.queue is None:
                time.sleep(0.05)
                continue

            try:
                job = self.queue.pop(timeout=0.1)
            except Exception:
                continue

            if job is None:
                continue

            self._execute_job(job)

    def _execute_job(self, job: Job) -> None:
        """Execute a single job with timeout and retry handling."""
        with self._lock:
            self._active_workers += 1

        try:
            job.status = JobStatus.RUNNING
            job.attempts += 1
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.RUNNING)
            self._fire("on_start", job)

            with self._lock:
                handler = self._handlers.get(job.fn_name)

            if handler is None:
                raise ValueError(f"No handler registered for function '{job.fn_name}'")

            if job.timeout is not None and job.timeout > 0:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(handler, *job.args, **job.kwargs)
                    try:
                        result = future.result(timeout=job.timeout)
                    except concurrent.futures.TimeoutError:
                        raise TimeoutError(f"Job {job.job_id} timed out after {job.timeout}s")
            else:
                result = handler(*job.args, **job.kwargs)

            # Mark completed
            job.status = JobStatus.COMPLETED
            job.result = result
            job.error = None
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
            self._fire("on_success", job)

        except TimeoutError as exc:
            job.status = JobStatus.FAILED
            job.error = f"Job {job.job_id} timed out after {job.timeout}s"
            if self.storage:
                self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
            self._fire("on_failure", job)

        except Exception as exc:
            if job.retry_policy and job.attempts < job.retry_policy.max_attempts:
                job.status = JobStatus.RETRYING
                delay = job.retry_policy.get_delay(job.attempts)
                job.scheduled_at = time.time() + delay
                job.error = str(exc)
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.RETRYING, error=job.error)
                self._fire("on_retry", job)
                if self.queue:
                    self.queue.push(job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                if self.storage:
                    self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
                self._fire("on_failure", job)

        finally:
            with self._lock:
                self._active_workers -= 1
