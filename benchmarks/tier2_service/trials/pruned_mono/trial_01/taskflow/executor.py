"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue


class JobExecutionTimeout(TimeoutError):
    """Raised when job execution duration exceeds job.timeout."""
    pass


class WorkerPool:
    """Manages worker daemon threads pulling and executing tasks from a PriorityTaskQueue."""

    VALID_EVENTS = {"on_start", "on_success", "on_failure", "on_retry"}

    def __init__(
        self,
        queue: Optional[PriorityTaskQueue] = None,
        storage: Optional[Any] = None,
        num_workers: int = 4,
    ) -> None:
        if isinstance(queue, int):
            num_workers = queue
            queue = None

        self.queue: PriorityTaskQueue = queue if queue is not None else PriorityTaskQueue()
        self.storage: Optional[Any] = storage
        self.num_workers: int = num_workers

        self._handlers: dict[str, Callable[..., Any]] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            event: [] for event in self.VALID_EVENTS
        }
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active_workers: int = 0
        self._running: bool = False

    def register_handler(self, name: str, fn: Callable[..., Any]) -> None:
        """Register a callable handler by name."""
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register an event listener for on_start, on_success, on_failure, or on_retry."""
        if event not in self.VALID_EVENTS:
            raise ValueError(f"Unknown event '{event}'. Supported: {self.VALID_EVENTS}")
        with self._lock:
            self._listeners[event].append(callback)

    def _notify_listeners(self, event: str, job: Job) -> None:
        callbacks = []
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def get_active_worker_count(self) -> int:
        """Return the number of workers currently processing jobs."""
        with self._lock:
            return self._active_workers

    @property
    def active_workers(self) -> int:
        return self.get_active_worker_count()

    def start(self) -> None:
        """Start worker daemon threads."""
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-Worker-{i}",
                    daemon=True,
                )
                t.start()
                self._threads.append(t)
            self._running = True

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Signal workers to stop and optionally wait for running jobs to finish."""
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            threads = list(self._threads)

        if wait and threads:
            deadline = None if timeout is None else time.time() + max(0.0, timeout)
            for t in threads:
                if deadline is not None:
                    remaining = max(0.0, deadline - time.time())
                else:
                    remaining = None
                t.join(timeout=remaining)

        with self._lock:
            self._threads.clear()
            self._running = False

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self.queue.pop(timeout=0.1)
            if job is None:
                continue

            with self._lock:
                self._active_workers += 1
            try:
                self._process_job(job)
            finally:
                with self._lock:
                    self._active_workers -= 1

    def _process_job(self, job: Job) -> None:
        if job.status == JobStatus.CANCELLED:
            return

        if self.storage is not None:
            stored = self.storage.get_job(job.job_id)
            if stored is not None and stored.status == JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
                return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        if self.storage is not None:
            self.storage.update_status(job.job_id, JobStatus.RUNNING)
        self._notify_listeners("on_start", job)

        with self._lock:
            handler = self._handlers.get(job.fn_name)

        if handler is None:
            err = Exception(f"Handler '{job.fn_name}' not registered")
            self._handle_failure(job, err)
            return

        try:
            if job.timeout is not None and job.timeout > 0:
                result = self._execute_with_timeout(handler, job.args, job.kwargs, job.timeout)
            else:
                result = handler(*job.args, **job.kwargs)
        except JobExecutionTimeout as te:
            self._handle_timeout(job, str(te))
            return
        except Exception as exc:
            self._handle_failure(job, exc)
            return

        # Succeeded
        job.status = JobStatus.COMPLETED
        job.result = result
        job.error = None
        if self.storage is not None:
            self.storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
        self._notify_listeners("on_success", job)

    def _execute_with_timeout(
        self, fn: Callable[..., Any], args: tuple, kwargs: dict[str, Any], timeout: float
    ) -> Any:
        res = [None]
        exc = [None]
        done = threading.Event()

        def runner() -> None:
            try:
                res[0] = fn(*args, **kwargs)
            except BaseException as e:
                exc[0] = e
            finally:
                done.set()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        finished = done.wait(timeout=timeout)
        if not finished:
            raise JobExecutionTimeout(f"Job execution timed out after {timeout} seconds")
        if exc[0] is not None:
            raise exc[0]
        return res[0]

    def _handle_timeout(self, job: Job, error_msg: str) -> None:
        job.status = JobStatus.FAILED
        job.error = error_msg
        if self.storage is not None:
            self.storage.update_status(job.job_id, JobStatus.FAILED, error=error_msg)
        self._notify_listeners("on_failure", job)

    def _handle_failure(self, job: Job, exc: Exception) -> None:
        err_msg = str(exc)
        if job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
            job.status = JobStatus.RETRYING
            job.error = err_msg
            delay = job.retry_policy.get_delay(job.attempts)
            job.scheduled_at = time.time() + delay
            if self.storage is not None:
                self.storage.update_status(job.job_id, JobStatus.RETRYING, error=err_msg)
            self.queue.push(job)
            self._notify_listeners("on_retry", job)
        else:
            job.status = JobStatus.FAILED
            job.error = err_msg
            if self.storage is not None:
                self.storage.update_status(job.job_id, JobStatus.FAILED, error=err_msg)
            self._notify_listeners("on_failure", job)
