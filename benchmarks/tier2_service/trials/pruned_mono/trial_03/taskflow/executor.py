import threading
import time
from typing import Any, Callable, Optional
from taskflow.models import Job, JobStatus
from taskflow.queue import PriorityTaskQueue
from taskflow.storage import JobStorage


class _JobExecutionThread(threading.Thread):
    def __init__(self, fn: Callable, args: tuple, kwargs: dict) -> None:
        super().__init__(daemon=True)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.result: Any = None
        self.exception: Optional[Exception] = None

    def run(self) -> None:
        try:
            self.result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self.exception = e


class WorkerPool:
    def __init__(
        self,
        queue: Optional[Any] = None,
        num_workers: int = 4,
        storage: Optional[JobStorage] = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(queue, int):
            num_workers, queue = queue, None
        if "num_workers" in kwargs:
            num_workers = kwargs["num_workers"]
        if "storage" in kwargs:
            storage = kwargs["storage"]

        self.num_workers = num_workers
        self.queue: PriorityTaskQueue = queue if isinstance(queue, PriorityTaskQueue) else PriorityTaskQueue()
        self.storage: Optional[JobStorage] = storage
        self._handlers: dict[str, Callable] = {}
        self._listeners: dict[str, list[Callable[[Job], None]]] = {
            "on_start": [],
            "on_success": [],
            "on_failure": [],
            "on_retry": [],
        }
        self._lock = threading.RLock()
        self._active_workers: int = 0
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._is_running = False

    @property
    def active_workers(self) -> int:
        with self._lock:
            return self._active_workers

    def register_handler(self, name: str, fn: Callable) -> None:
        with self._lock:
            self._handlers[name] = fn

    def add_listener(self, event: str, callback: Callable[[Job], None]) -> None:
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
            if self.storage:
                self.storage.update_status(job.job_id, job.status)
            self._fire_event("on_start", job)

            with self._lock:
                fn = self._handlers.get(job.fn_name)

            if fn is None:
                raise RuntimeError(f"No handler registered for function '{job.fn_name}'")

            if job.timeout is not None and job.timeout > 0:
                exec_thread = _JobExecutionThread(fn, job.args, job.kwargs)
                exec_thread.start()
                exec_thread.join(timeout=job.timeout)
                if exec_thread.is_alive():
                    job.status = JobStatus.FAILED
                    job.error = f"Job execution exceeded timeout of {job.timeout}s"
                    if self.storage:
                        self.storage.update_status(job.job_id, job.status, error=job.error)
                    self._fire_event("on_failure", job)
                    return
                elif exec_thread.exception is not None:
                    raise exec_thread.exception
                else:
                    result = exec_thread.result
            else:
                result = fn(*job.args, **job.kwargs)

            job.status = JobStatus.COMPLETED
            job.result = result
            job.error = None
            if self.storage:
                self.storage.update_status(job.job_id, job.status, result=job.result)
            self._fire_event("on_success", job)

        except Exception as exc:
            if job.retry_policy and job.attempts < job.retry_policy.max_attempts:
                job.status = JobStatus.RETRYING
                delay = job.retry_policy.get_delay(job.attempts)
                job.scheduled_at = time.time() + delay
                job.error = str(exc)
                if self.storage:
                    self.storage.update_status(job.job_id, job.status, error=job.error)
                self.queue.push(job)
                self._fire_event("on_retry", job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                if self.storage:
                    self.storage.update_status(job.job_id, job.status, error=job.error)
                self._fire_event("on_failure", job)

        finally:
            with self._lock:
                self._active_workers -= 1

    def start(self) -> None:
        with self._lock:
            if self._is_running:
                return
            self._stop_event.clear()
            self._threads = []
            for i in range(self.num_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"WorkerPool-{i}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()
            self._is_running = True

    def shutdown(self, wait: bool = True, timeout: Optional[float] = 5.0) -> None:
        with self._lock:
            if not self._is_running:
                return
            self._stop_event.set()
            self._is_running = False
            threads = list(self._threads)

        if hasattr(self.queue, "wake_all"):
            self.queue.wake_all()

        if wait:
            start_time = time.time()
            for t in threads:
                if timeout is not None:
                    remaining = (start_time + timeout) - time.time()
                    if remaining <= 0:
                        break
                    t.join(timeout=remaining)
                else:
                    t.join()
