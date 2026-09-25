"""WorkerPool implementation for executing jobs from PriorityTaskQueue."""

from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Callable, Dict, List, Optional

from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue


class WorkerPool:
    """Multi-threaded worker pool managing background daemon threads to execute queued jobs."""

    def __init__(self, queue: PriorityTaskQueue, num_workers: int = 4) -> None:
        self.queue = queue
        self.num_workers = num_workers
        self._handlers: Dict[str, Callable] = {}
        self._listeners: Dict[str, List[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._lock = threading.RLock()
        self._threads: List[threading.Thread] = []
        self._running = False
        self._shutdown_event = threading.Event()
        self._active_workers = 0

    def register_handler(self, name: str, fn: Callable) -> None:
        """Register a handler callable by function name."""
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
        """Register an event listener for on_start, on_success, on_failure, on_retry."""
        with self._lock:
            if event in self._listeners:
                self._listeners[event].append(callback)

    def _fire_event(self, event: str, job: Job) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event, []))
        for cb in callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def start(self) -> None:
        """Start worker threads."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._shutdown_event.clear()
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(target=self._worker_loop, name=f"WorkerPool-Worker-{i}", daemon=True)
                self._threads.append(t)
                t.start()

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        """Signal workers to stop and optionally wait for termination."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._shutdown_event.set()

        if wait:
            deadline = (time.time() + timeout) if timeout is not None else None
            for t in self._threads:
                if deadline is not None:
                    rem = max(0.0, deadline - time.time())
                    t.join(timeout=rem)
                else:
                    t.join()

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def _worker_loop(self) -> None:
        while not self._shutdown_event.is_set():
            # Wait for job with small timeout so we can periodically check shutdown_event
            job = self.queue.pop(timeout=0.2)
            if job is None:
                continue

            with self._lock:
                self._active_workers += 1

            try:
                self._execute_job(job)
            finally:
                with self._lock:
                    self._active_workers -= 1

    def _execute_job(self, job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.attempts += 1
        self._fire_event("on_start", job)

        with self._lock:
            handler = self._handlers.get(job.fn_name)

        if handler is None:
            self._handle_failure(job, Exception(f"No handler registered for function '{job.fn_name}'"))
            return

        try:
            if job.timeout is not None and job.timeout > 0:
                # Run with timeout using ThreadPoolExecutor
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(handler, *job.args, **job.kwargs)
                    result = future.result(timeout=job.timeout)
            else:
                result = handler(*job.args, **job.kwargs)

            job.status = JobStatus.COMPLETED
            job.result = result
            job.error = None
            self._fire_event("on_success", job)
        except concurrent.futures.TimeoutError as te:
            self._handle_failure(job, TimeoutError(f"Job execution timed out after {job.timeout}s"))
        except Exception as exc:
            self._handle_failure(job, exc)

    def _handle_failure(self, job: Job, exc: Exception) -> None:
        if job.retry_policy is not None and job.attempts < job.retry_policy.max_attempts:
            job.status = JobStatus.RETRYING
            delay = job.retry_policy.get_delay(job.attempts)
            job.scheduled_at = time.time() + delay
            self.queue.push(job)
            self._fire_event("on_retry", job)
        else:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            self._fire_event("on_failure", job)
