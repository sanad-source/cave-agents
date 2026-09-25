"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class WorkerPool:
    """Worker pool managing background daemon threads to execute jobs from queue."""

    def __init__(
        self,
        queue: Optional[PriorityTaskQueue] = None,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
    ) -> None:
        self._queue = queue if queue is not None else PriorityTaskQueue()
        self.num_workers = num_workers
        self._storage = storage
        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._lock = threading.RLock()
        self._active_workers = 0
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._started = False

    @property
    def queue(self) -> PriorityTaskQueue:
        return self._queue

    @queue.setter
    def queue(self, val: PriorityTaskQueue) -> None:
        self._queue = val

    @property
    def storage(self) -> Optional[JobStorage]:
        return self._storage

    @storage.setter
    def storage(self, val: Optional[JobStorage]) -> None:
        self._storage = val

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a handler callable by function name."""
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register an event listener for on_start, on_success, on_failure, on_retry."""
        with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)

    def _fire_event(self, event: str, job: Job) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def _execute_job(self, job: Job) -> None:
        if job.status == JobStatus.CANCELLED:
            return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        if self._storage:
            self._storage.update_status(job.job_id, JobStatus.RUNNING)
        self._fire_event("on_start", job)

        with self._lock:
            handler = self._handlers.get(job.fn_name)

        if handler is None:
            job.status = JobStatus.FAILED
            job.error = f"No handler registered for '{job.fn_name}'"
            if self._storage:
                self._storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
            self._fire_event("on_failure", job)
            return

        timed_out = False
        failed = False
        exc_error: Optional[Exception] = None
        result: Any = None

        if job.timeout is not None and job.timeout > 0:
            res_container: list[Any] = []
            err_container: list[Exception] = []

            def target() -> None:
                try:
                    res_container.append(handler(*job.args, **job.kwargs))
                except Exception as e:
                    err_container.append(e)

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(timeout=job.timeout)
            if t.is_alive():
                timed_out = True
            elif err_container:
                failed = True
                exc_error = err_container[0]
            else:
                result = res_container[0] if res_container else None
        else:
            try:
                result = handler(*job.args, **job.kwargs)
            except Exception as e:
                failed = True
                exc_error = e

        if timed_out:
            job.status = JobStatus.FAILED
            job.error = f"Job execution timed out after {job.timeout} seconds"
            if self._storage:
                self._storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
            self._fire_event("on_failure", job)
            return

        if failed:
            if job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
                job.status = JobStatus.RETRYING
                delay = job.retry_policy.get_delay(job.attempts)
                job.scheduled_at = time.time() + delay
                if self._storage:
                    self._storage.update_status(job.job_id, JobStatus.RETRYING)
                self._queue.push(job)
                self._fire_event("on_retry", job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(exc_error)
                if self._storage:
                    self._storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
                self._fire_event("on_failure", job)
            return

        # Success
        job.status = JobStatus.COMPLETED
        job.result = result
        if self._storage:
            self._storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
        self._fire_event("on_success", job)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self._queue.pop(timeout=0.05)
            if job is None:
                continue
            with self._lock:
                self._active_workers += 1
            try:
                self._execute_job(job)
            finally:
                with self._lock:
                    self._active_workers -= 1

    def start(self) -> None:
        """Start worker threads."""
        with self._lock:
            if self._started and any(t.is_alive() for t in self._threads):
                return
            self._stop_event.clear()
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    daemon=True,
                    name=f"WorkerPool-Worker-{i}",
                )
                self._threads.append(t)
                t.start()
            self._started = True

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Signal workers to stop and optionally wait for running jobs to finish."""
        self._stop_event.set()
        if wait:
            deadline = (time.time() + timeout) if timeout is not None else None
            for t in self._threads:
                if t.is_alive():
                    remaining = (
                        max(0.0, deadline - time.time())
                        if deadline is not None
                        else None
                    )
                    t.join(timeout=remaining)
        with self._lock:
            self._started = False
