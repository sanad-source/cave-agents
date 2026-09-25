# Tier 2 Benchmark Specification: `taskflow` Asynchronous Job Scheduling Service

## Overview
Implement a modular, thread-safe asynchronous task execution and job scheduling service package named `taskflow`.
The package must be implemented across exactly five decoupled Python modules in the `taskflow/` directory:
1. `taskflow/models.py`: Data models, enums, retry policies, and serialization.
2. `taskflow/storage.py`: Storage interfaces and thread-safe in-memory storage with snapshot persistence.
3. `taskflow/queue.py`: Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling.
4. `taskflow/executor.py`: Multi-threaded worker pool with retry logic, timeouts, and event listeners.
5. `taskflow/service.py`: High-level facade coordinating storage, queue, executor, metrics, and lifecycle.

---

## Detailed Module Specifications

### 1. `taskflow/models.py`
- **`JobPriority`** (`enum.IntEnum`):
  - `LOW = 1`
  - `MEDIUM = 2`
  - `HIGH = 3`
  - `CRITICAL = 4`
- **`JobStatus`** (`enum.Enum`):
  - `PENDING = "pending"`
  - `RUNNING = "running"`
  - `COMPLETED = "completed"`
  - `FAILED = "failed"`
  - `RETRYING = "retrying"`
  - `CANCELLED = "cancelled"`
- **`RetryPolicy`** (`dataclass`):
  - `max_attempts: int = 3` (must be >= 1)
  - `base_delay: float = 0.05`
  - `backoff_factor: float = 2.0`
  - `jitter: bool = False`
  - `get_delay(attempt: int) -> float`: Calculates `base_delay * (backoff_factor ** (attempt - 1))`. If `jitter` is True, adds uniform random jitter between 0 and `0.5 * delay`.
- **`Job`** (`dataclass`):
  - `job_id: str`: Unique identifier (UUID string if not provided).
  - `fn_name: str`: Registered function name to execute.
  - `args: tuple = ()`
  - `kwargs: dict = field(default_factory=dict)`
  - `priority: JobPriority = JobPriority.MEDIUM`
  - `status: JobStatus = JobStatus.PENDING`
  - `retry_policy: Optional[RetryPolicy] = None`
  - `attempts: int = 0`
  - `result: Any = None`
  - `error: Optional[str] = None`
  - `created_at: float = field(default_factory=time.time)`
  - `scheduled_at: float = 0.0` (timestamp when job becomes eligible for dequeue)
  - `timeout: Optional[float] = None` (execution timeout in seconds)
  - `to_dict() -> dict`: Returns JSON-serializable dictionary representation.
  - `from_dict(data: dict) -> Job`: Class method recreating Job from dictionary.

### 2. `taskflow/storage.py`
- **`JobStorage`** (Abstract Base Class via `abc.ABC`):
  - `@abstractmethod save_job(job: Job) -> None`
  - `@abstractmethod get_job(job_id: str) -> Optional[Job]`
  - `@abstractmethod list_jobs(status: Optional[JobStatus] = None) -> list[Job]`
  - `@abstractmethod update_status(job_id: str, status: JobStatus, result: Any = None, error: Optional[str] = None) -> bool`
  - `@abstractmethod delete_job(job_id: str) -> bool`
- **`MemoryJobStorage(JobStorage)`**:
  - Thread-safe storage utilizing `threading.RLock`.
  - Implements all `JobStorage` methods.
  - `save_snapshot(filepath: str) -> None`: Exports all stored jobs as JSON file.
  - `load_snapshot(filepath: str) -> int`: Replays jobs from JSON file into storage, returning count of loaded jobs.

### 3. `taskflow/queue.py`
- **`PriorityTaskQueue`**:
  - Thread-safe priority queue backed by min-heap (`heapq`) or thread-safe heap.
  - Dequeue ordering: Higher numerical priority dequeued first (`CRITICAL` > `HIGH` > `MEDIUM` > `LOW`).
  - Strict FIFO tie-breaking: For equal priority jobs, earlier `created_at` / monotonic insertion order dequeued first.
  - Delayed scheduling: If `scheduled_at > time.time()`, job is not eligible for dequeue until `time.time() >= scheduled_at`.
  - Methods:
    - `push(job: Job) -> None`
    - `pop(timeout: Optional[float] = None) -> Optional[Job]`: Blocks up to `timeout` seconds waiting for an eligible job. Returns `None` if timeout expires without available job.
    - `peek() -> Optional[Job]`: Returns next eligible job without removing it, or `None`.
    - `cancel(job_id: str) -> bool`: Marks job cancelled if in queue and removes it; returns `True` if found and removed.
    - `size() -> int`: Current count of queued eligible and scheduled jobs.
    - `is_empty() -> bool`

### 4. `taskflow/executor.py`
- **`WorkerPool`**:
  - Manages `num_workers: int = 4` background daemon threads.
  - `register_handler(name: str, fn: Callable) -> None`: Registers callable by name.
  - Pulls jobs from `PriorityTaskQueue` and executes registered handlers.
  - Status transitions:
    - Sets job status to `JobStatus.RUNNING` and increments `job.attempts += 1`.
    - If execution succeeds: sets `job.status = JobStatus.COMPLETED`, updates `job.result`, fires `"on_success"`.
    - If execution fails (raises Exception):
      - If `job.retry_policy` exists and `job.attempts < job.retry_policy.max_attempts`:
        - Sets `job.status = JobStatus.RETRYING`.
        - Computes delay via `retry_policy.get_delay(job.attempts)`.
        - Sets `job.scheduled_at = time.time() + delay` and re-pushes to queue.
        - Fires `"on_retry"`.
      - Else:
        - Sets `job.status = JobStatus.FAILED`.
        - Records error string in `job.error`.
        - Fires `"on_failure"`.
  - Timeout enforcement: If `job.timeout` is specified and execution duration exceeds it, task is terminated/aborted as `JobStatus.FAILED` with error indicating timeout.
  - Event listeners:
    - `add_listener(event: str, callback: Callable[[Job], None]) -> None`: Supported events: `"on_start"`, `"on_success"`, `"on_failure"`, `"on_retry"`.
  - Lifecycle:
    - `start() -> None`: Starts worker threads.
    - `shutdown(wait: bool = True, timeout: Optional[float] = 5.0) -> None`: Signals workers to stop. If `wait` is True, waits up to `timeout` seconds for running jobs to complete.

### 5. `taskflow/service.py`
- **`TaskQueueService`**:
  - Unified facade composing `MemoryJobStorage`, `PriorityTaskQueue`, and `WorkerPool`.
  - Constructor: `__init__(self, num_workers: int = 4, storage: Optional[JobStorage] = None)`
  - Methods:
    - `register_handler(name: str, fn: Callable) -> None`
    - `submit_job(fn_name: str, *args, priority: JobPriority = JobPriority.MEDIUM, retry_policy: Optional[RetryPolicy] = None, timeout: Optional[float] = None, delay: float = 0.0, **kwargs) -> str`: Creates Job, records in storage, puts in queue, returns `job_id`.
    - `get_job(job_id: str) -> Optional[Job]`
    - `get_job_status(job_id: str) -> Optional[JobStatus]`
    - `get_job_result(job_id: str, timeout: Optional[float] = None) -> Any`: Blocks waiting for job to complete or fail. Raises `TimeoutError` if timeout expires; raises `RuntimeError` if job failed. Returns result on success.
    - `cancel_job(job_id: str) -> bool`: Cancels job in queue or storage.
    - `get_metrics() -> dict`: Returns `{"total_jobs": int, "completed": int, "failed": int, "retrying": int, "queue_size": int, "active_workers": int}`.
    - `start() -> None`
    - `stop(timeout: Optional[float] = 5.0) -> None`
    - Context manager methods: `__enter__()` and `__exit__()` automatically calling `start()` and `stop()`.
