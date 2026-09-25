"""Multi-threaded worker pool with retry logic, timeouts, and event listeners."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class WorkerPool:
    """Manages background daemon worker threads pulling jobs from PriorityTaskQueue."""

    def __init__(
        self,
        queue: Optional[PriorityTaskQueue] = None,
        storage: Optional[JobStorage] = None,
        num_workers: int = 4,
    ) -> None:
        self.queue = queue if queue is not None else PriorityTaskQueue()
        self.storage = storage
        self.num_workers = num_workers

        self._handlers: dict[str, Callable[..., Any]] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._workers: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._active_workers: int = 0

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def register_handler(self, name: str, fn: Callable[..., Any]) -> None:
        self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def _fire_event(self, event: str, job: Job) -> None:
        for cb in self._listeners.get(event, []):
            try:
                cb(job)
            except Exception:
                pass

    def start(self) -> None:
        with self._lock:
            if self._workers:
                return
            self._stop_event.clear()
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-Worker-{i}",
                    daemon=True,
                )
                t.start()
                self._workers.append(t)

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        self._stop_event.set()
        if wait:
            deadline = (time.time() + timeout) if timeout is not None else None
            for w in list(self._workers):
                if deadline is not None:
                    rem = max(0.0, deadline - time.time())
                    w.join(timeout=rem)
                else:
                    w.join()
        with self._lock:
            self._workers.clear()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self.queue.pop(timeout=0.1)
            if job is None:
                continue
            if job.status == JobStatus.CANCELLED:
                continue
            self._execute_job(job)

    def _execute_job(self, job: Job) -> None:
        with self._lock:
            self._active_workers += 1

        try:
            job.status = JobStatus.RUNNING
            job.attempts += 1
            if self.storage is not None:
                self.storage.update_status(job.job_id, JobStatus.RUNNING)
            self._fire_event("on_start", job)

            handler = self._handlers.get(job.fn_name)
            if handler is None:
                job.status = JobStatus.FAILED
                job.error = f"Handler '{job.fn_name}' not registered"
                if self.storage is not None:
                    self.storage.update_status(job.job_id, JobStatus.FAILED, error=job.error)
                self._fire_event("on_failure", job)
                return

            is_timeout = False
            try:
                if job.timeout is not None:
                    res_holder: list[Any] = []
                    exc_holder: list[Exception] = []

                    def target() -> None:
                        try:
                            res_holder.append(handler(*job.args, **job.kwargs))
                        except Exception as e:
                            exc_holder.append(e)

                    worker_thread = threading.Thread(target=target, daemon=True)
                    worker_thread.start()
                    worker_thread.join(timeout=job.timeout)
                    if worker_thread.is_alive():
                        is_timeout = True
                        raise TimeoutError(f"Job execution timed out after {job.timeout}s")
                    if exc_holder:
                        raise exc_holder[0]
                    result = res_holder[0] if res_holder else None
                else:
                    result = handler(*job.args, **job.kwargs)

                job.status = JobStatus.COMPLETED
                job.result = result
                if self.storage is not None:
                    self.storage.update_status(job.job_id, JobStatus.COMPLETED, result=result)
                self._fire_event("on_success", job)

            except Exception as exc:
                err_msg = str(exc)
                if is_timeout:
                    job.status = JobStatus.FAILED
                    job.error = err_msg
                    if self.storage is not None:
                        self.storage.update_status(job.job_id, JobStatus.FAILED, error=err_msg)
                    self._fire_event("on_failure", job)
                elif job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
                    job.status = JobStatus.RETRYING
                    delay = job.retry_policy.get_delay(job.attempts)
                    job.scheduled_at = time.time() + delay
                    if self.storage is not None:
                        self.storage.update_status(job.job_id, JobStatus.RETRYING)
                    self.queue.push(job)
                    self._fire_event("on_retry", job)
                else:
                    job.status = JobStatus.FAILED
                    job.error = err_msg
                    if self.storage is not None:
                        self.storage.update_status(job.job_id, JobStatus.FAILED, error=err_msg)
                    self._fire_event("on_failure", job)
        finally:
            with self._lock:
                self._active_workers -= 1
