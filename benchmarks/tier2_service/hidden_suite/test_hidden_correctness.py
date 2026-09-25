"""Held-Out Adversarial Test Suite for taskflow.
This test suite is NOT accessible to agents during development.
It is evaluated post-hoc to measure defect-catch rate and deep edge-case/concurrency resilience.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.storage import MemoryJobStorage
from taskflow.queue import PriorityTaskQueue
from taskflow.executor import WorkerPool
from taskflow.service import TaskQueueService


def test_hidden_fifo_tie_breaking():
    """Identical priorities must be dequeued in strict FIFO creation order."""
    q = PriorityTaskQueue()
    jobs = []
    base_t = time.time()
    for i in range(10):
        j = Job(job_id=f"job-{i}", fn_name="test", priority=JobPriority.HIGH, created_at=base_t + i)
        jobs.append(j)
        q.push(j)

    for i in range(10):
        popped = q.pop(timeout=0.2)
        assert popped is not None
        assert popped.job_id == f"job-{i}", f"Expected FIFO ordering job-{i}, got {popped.job_id}"


def test_hidden_delayed_scheduling_withholding():
    """Jobs scheduled in future must not be popped prematurely."""
    q = PriorityTaskQueue()
    future_time = time.time() + 0.4
    j = Job(job_id="delayed", fn_name="fn", priority=JobPriority.CRITICAL, scheduled_at=future_time)
    q.push(j)

    # Should time out immediately because job is not ready
    popped = q.pop(timeout=0.1)
    assert popped is None

    # After delay elapses, should be popped
    time.sleep(0.35)
    popped = q.pop(timeout=0.3)
    assert popped is not None
    assert popped.job_id == "delayed"


def test_hidden_queue_cancellation():
    """Cancelled jobs must be purged and not returned by pop."""
    q = PriorityTaskQueue()
    j1 = Job(job_id="j1", fn_name="fn", priority=JobPriority.MEDIUM)
    j2 = Job(job_id="j2", fn_name="fn", priority=JobPriority.HIGH)
    q.push(j1)
    q.push(j2)

    cancelled = q.cancel("j2")
    assert cancelled is True
    assert q.size() == 1

    popped = q.pop(timeout=0.1)
    assert popped.job_id == "j1"


def test_hidden_concurrent_producer_consumer_race():
    """Multi-threaded enqueue and dequeue must maintain state without data loss."""
    q = PriorityTaskQueue()
    total_items = 100
    pushed_ids = set()
    lock = threading.Lock()

    def producer(start_idx):
        for i in range(start_idx, start_idx + 10):
            jid = f"item-{i}"
            with lock:
                pushed_ids.add(jid)
            q.push(Job(job_id=jid, fn_name="noop", priority=JobPriority.MEDIUM))

    threads = [threading.Thread(target=producer, args=(i * 10,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert q.size() == total_items

    popped_ids = set()
    for _ in range(total_items):
        item = q.pop(timeout=0.5)
        assert item is not None
        popped_ids.add(item.job_id)

    assert popped_ids == pushed_ids


def test_hidden_memory_storage_thread_safety():
    """Concurrent updates to storage must not corrupt records."""
    storage = MemoryJobStorage()
    for i in range(50):
        storage.save_job(Job(job_id=f"rec-{i}", fn_name="test", status=JobStatus.PENDING))

    def updater(idx):
        storage.update_status(f"rec-{idx}", JobStatus.COMPLETED, result=idx * 2)

    threads = [threading.Thread(target=updater, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    completed = storage.list_jobs(JobStatus.COMPLETED)
    assert len(completed) == 50
    for job in completed:
        idx = int(job.job_id.split("-")[1])
        assert job.result == idx * 2


def test_hidden_unregistered_handler_failure():
    """Calling an unregistered handler must mark job FAILED and not crash workers."""
    service = TaskQueueService(num_workers=2)
    with service:
        job_id = service.submit_job("non_existent_function", 1, 2)
        with pytest.raises(RuntimeError, match="(?i)handler|unregistered|not found"):
            service.get_job_result(job_id, timeout=2.0)
        assert service.get_job_status(job_id) == JobStatus.FAILED


def test_hidden_timeout_abortion():
    """Jobs exceeding timeout must be failed with timeout notice."""
    service = TaskQueueService(num_workers=2)
    service.register_handler("sleep_forever", lambda: time.sleep(2.0))

    with service:
        job_id = service.submit_job("sleep_forever", timeout=0.1)
        with pytest.raises(RuntimeError, match="(?i)timeout|timed out|exceeded"):
            service.get_job_result(job_id, timeout=2.0)
        assert service.get_job_status(job_id) == JobStatus.FAILED


def test_hidden_retry_max_attempts_exhaustion():
    """Permanent failures must retry exactly max_attempts times then mark FAILED."""
    service = TaskQueueService(num_workers=2)
    attempts_recorded = []

    def always_fail():
        attempts_recorded.append(time.time())
        raise ValueError("Deterministic crash")

    service.register_handler("fail_always", always_fail)

    with service:
        policy = RetryPolicy(max_attempts=3, base_delay=0.02, backoff_factor=1.0)
        job_id = service.submit_job("fail_always", retry_policy=policy)
        with pytest.raises(RuntimeError):
            service.get_job_result(job_id, timeout=3.0)

        assert service.get_job_status(job_id) == JobStatus.FAILED
        assert len(attempts_recorded) == 3


def test_hidden_retry_backoff_delay_adherence():
    """Retry intervals must exhibit exponential backoff."""
    policy = RetryPolicy(max_attempts=4, base_delay=0.1, backoff_factor=2.0, jitter=False)
    d1 = policy.get_delay(1)
    d2 = policy.get_delay(2)
    d3 = policy.get_delay(3)
    assert abs(d1 - 0.1) < 1e-4
    assert abs(d2 - 0.2) < 1e-4
    assert abs(d3 - 0.4) < 1e-4


def test_hidden_graceful_shutdown_waits_for_inflight():
    """stop(wait=True) must allow active jobs to finish without early termination."""
    service = TaskQueueService(num_workers=2)
    completed_flag = {"done": False}

    def slow_task():
        time.sleep(0.3)
        completed_flag["done"] = True
        return "success"

    service.register_handler("slow", slow_task)
    service.start()
    jid = service.submit_job("slow")

    # Give worker time to pick up job
    time.sleep(0.05)
    service.stop(timeout=3.0)

    assert completed_flag["done"] is True
    job = service.get_job(jid)
    assert job.status == JobStatus.COMPLETED


def test_hidden_metrics_consistency():
    """Service metrics must accurately track job lifecycle tallies."""
    service = TaskQueueService(num_workers=2)
    service.register_handler("quick_add", lambda x: x + 1)
    service.register_handler("quick_err", lambda: 1 / 0)

    with service:
        j1 = service.submit_job("quick_add", 5)
        j2 = service.submit_job("quick_err")
        time.sleep(0.3)
        metrics = service.get_metrics()
        assert metrics["total_jobs"] == 2
        assert metrics["completed"] == 1
        assert metrics["failed"] == 1


def test_hidden_context_manager_cleanup():
    """Context manager must leave zero running threads."""
    service = TaskQueueService(num_workers=2)
    with service:
        pass
    # All worker pool threads should be terminated or stopping
    time.sleep(0.1)
    metrics = service.get_metrics()
    assert metrics["active_workers"] == 0 or metrics.get("running_threads", 0) == 0


def test_hidden_snapshot_persistence_integrity(tmp_path):
    """Snapshot save and load must preserve full state including enums and kwargs."""
    storage = MemoryJobStorage()
    job = Job(
        job_id="persisted-1",
        fn_name="complex_task",
        args=(1, [2, 3]),
        kwargs={"mode": "fast", "retries": 2},
        priority=JobPriority.CRITICAL,
        status=JobStatus.COMPLETED,
        result={"status": "ok", "value": 99},
        attempts=2
    )
    storage.save_job(job)
    filepath = str(tmp_path / "state_dump.json")
    storage.save_snapshot(filepath)

    reloaded_storage = MemoryJobStorage()
    reloaded_storage.load_snapshot(filepath)
    loaded = reloaded_storage.get_job("persisted-1")
    assert loaded is not None
    assert loaded.priority == JobPriority.CRITICAL
    assert loaded.status == JobStatus.COMPLETED
    assert loaded.result["value"] == 99
    assert loaded.attempts == 2


def test_hidden_result_timeout_exception():
    """get_job_result must raise TimeoutError if job does not complete in time."""
    service = TaskQueueService(num_workers=1)
    service.register_handler("very_slow", lambda: time.sleep(1.0))
    with service:
        jid = service.submit_job("very_slow")
        with pytest.raises(TimeoutError):
            service.get_job_result(jid, timeout=0.1)


def test_hidden_result_failed_job_exception():
    """get_job_result must raise RuntimeError on failed job execution."""
    service = TaskQueueService(num_workers=1)
    service.register_handler("blow_up", lambda: (_ for _ in ()).throw(ValueError("Boom")))
    with service:
        jid = service.submit_job("blow_up")
        with pytest.raises(RuntimeError):
            service.get_job_result(jid, timeout=2.0)
        assert service.get_job_status(jid) == JobStatus.FAILED


def test_hidden_high_throughput_burst():
    """Service must process a burst of 40 short tasks across 4 workers without dropping any."""
    service = TaskQueueService(num_workers=4)
    service.register_handler("square", lambda x: x * x)

    with service:
        job_ids = [service.submit_job("square", i, priority=JobPriority.HIGH) for i in range(40)]
        results = [service.get_job_result(jid, timeout=5.0) for jid in job_ids]
        assert results == [i * i for i in range(40)]
