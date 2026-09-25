"""Visible Acceptance Test Suite for taskflow.
Provided to both Arm A (Pruned Monolith) and Arm B (CaveAgents v4) as the standard development contract.
"""

import time
import pytest
from taskflow.models import Job, JobPriority, JobStatus, RetryPolicy
from taskflow.storage import MemoryJobStorage
from taskflow.queue import PriorityTaskQueue
from taskflow.executor import WorkerPool
from taskflow.service import TaskQueueService


def sample_add(a: int, b: int) -> int:
    return a + b


def sample_fail_once(state: dict) -> str:
    state["attempts"] += 1
    if state["attempts"] < 2:
        raise ValueError("Simulated transient failure")
    return "recovered"


def test_models_job_serialization():
    job = Job(
        job_id="test-1",
        fn_name="sample_add",
        args=(2, 3),
        kwargs={"extra": 1},
        priority=JobPriority.HIGH,
        retry_policy=RetryPolicy(max_attempts=3, base_delay=0.01),
    )
    data = job.to_dict()
    assert data["job_id"] == "test-1"
    assert data["fn_name"] == "sample_add"
    assert data["priority"] == JobPriority.HIGH.value

    recreated = Job.from_dict(data)
    assert recreated.job_id == job.job_id
    assert recreated.fn_name == job.fn_name
    assert recreated.priority == JobPriority.HIGH
    assert recreated.retry_policy.max_attempts == 3


def test_memory_storage_crud(tmp_path):
    storage = MemoryJobStorage()
    job = Job(job_id="store-1", fn_name="test_fn", priority=JobPriority.MEDIUM)
    storage.save_job(job)

    fetched = storage.get_job("store-1")
    assert fetched is not None
    assert fetched.job_id == "store-1"

    updated = storage.update_status("store-1", JobStatus.COMPLETED, result=42)
    assert updated is True
    assert storage.get_job("store-1").status == JobStatus.COMPLETED
    assert storage.get_job("store-1").result == 42

    snapshot_path = str(tmp_path / "snapshot.json")
    storage.save_snapshot(snapshot_path)

    new_storage = MemoryJobStorage()
    count = new_storage.load_snapshot(snapshot_path)
    assert count == 1
    assert new_storage.get_job("store-1").result == 42


def test_priority_queue_ordering():
    q = PriorityTaskQueue()
    j_low = Job(job_id="low", fn_name="fn", priority=JobPriority.LOW, created_at=10.0)
    j_high = Job(job_id="high", fn_name="fn", priority=JobPriority.HIGH, created_at=20.0)
    j_crit = Job(job_id="crit", fn_name="fn", priority=JobPriority.CRITICAL, created_at=30.0)

    q.push(j_low)
    q.push(j_crit)
    q.push(j_high)

    assert q.size() == 3
    assert q.pop(timeout=0.1).job_id == "crit"
    assert q.pop(timeout=0.1).job_id == "high"
    assert q.pop(timeout=0.1).job_id == "low"
    assert q.is_empty() is True


def test_service_execution_and_result():
    service = TaskQueueService(num_workers=2)
    service.register_handler("add", sample_add)

    with service:
        job_id = service.submit_job("add", 10, 25, priority=JobPriority.HIGH)
        result = service.get_job_result(job_id, timeout=2.0)
        assert result == 35
        assert service.get_job_status(job_id) == JobStatus.COMPLETED


def test_service_retry_recovery():
    service = TaskQueueService(num_workers=2)
    state = {"attempts": 0}
    service.register_handler("fail_once", lambda: sample_fail_once(state))

    with service:
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, backoff_factor=1.5)
        job_id = service.submit_job("fail_once", priority=JobPriority.HIGH, retry_policy=policy)
        result = service.get_job_result(job_id, timeout=3.0)
        assert result == "recovered"
        assert state["attempts"] == 2
        assert service.get_job_status(job_id) == JobStatus.COMPLETED
