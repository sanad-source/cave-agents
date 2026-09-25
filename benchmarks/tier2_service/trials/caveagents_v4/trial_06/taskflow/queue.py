"""Thread-safe priority task queue with strict FIFO tie-breaking and delayed scheduling."""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from taskflow.models import Job, JobPriority, JobStatus


@dataclass(order=True)
class _ReadyEntry:
    priority: int
    created_at: float
    seq: int
    job: Job = field(compare=False)


@dataclass(order=True)
class _ScheduledEntry:
    scheduled_at: float
    priority: int
    created_at: float
    seq: int
    job: Job = field(compare=False)


class PriorityTaskQueue:
    """Thread-safe priority queue with delayed execution and FIFO tie-breaking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._ready_queue: list[_ReadyEntry] = []
        self._scheduled_queue: list[_ScheduledEntry] = []
        self._counter: int = 0
        self._job_ids: set[str] = set()

    def _promote_due_jobs(self, now: float) -> None:
        """Move scheduled jobs that have reached their scheduled_at into ready_queue."""
        while self._scheduled_queue and self._scheduled_queue[0].scheduled_at <= now:
            entry = heapq.heappop(self._scheduled_queue)
            heapq.heappush(
                self._ready_queue,
                _ReadyEntry(
                    priority=entry.priority,
                    created_at=entry.created_at,
                    seq=entry.seq,
                    job=entry.job,
                ),
            )

    def push(self, job: Job) -> None:
        """Push a job into the queue, sorting by eligibility, priority, and creation order."""
        with self._cond:
            self._counter += 1
            seq = self._counter
            self._job_ids.add(job.job_id)

            p_val = -int(job.priority.value if hasattr(job.priority, "value") else job.priority)
            now = time.time()
            if job.scheduled_at > now:
                heapq.heappush(
                    self._scheduled_queue,
                    _ScheduledEntry(
                        scheduled_at=job.scheduled_at,
                        priority=p_val,
                        created_at=job.created_at,
                        seq=seq,
                        job=job,
                    ),
                )
            else:
                heapq.heappush(
                    self._ready_queue,
                    _ReadyEntry(
                        priority=p_val,
                        created_at=job.created_at,
                        seq=seq,
                        job=job,
                    ),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        """Block up to timeout seconds waiting for an eligible job. Returns None if timeout expires."""
        deadline = time.time() + timeout if timeout is not None else None
        with self._cond:
            while True:
                now = time.time()
                self._promote_due_jobs(now)

                if self._ready_queue:
                    entry = heapq.heappop(self._ready_queue)
                    self._job_ids.discard(entry.job.job_id)
                    return entry.job

                if deadline is not None and now >= deadline:
                    return None

                wait_time: Optional[float] = None
                if self._scheduled_queue:
                    wait_time = max(0.0, self._scheduled_queue[0].scheduled_at - now)

                if deadline is not None:
                    time_left = max(0.0, deadline - now)
                    if wait_time is not None:
                        wait_time = min(wait_time, time_left)
                    else:
                        wait_time = time_left

                if wait_time is not None and wait_time <= 0:
                    now = time.time()
                    self._promote_due_jobs(now)
                    if self._ready_queue:
                        entry = heapq.heappop(self._ready_queue)
                        self._job_ids.discard(entry.job.job_id)
                        return entry.job
                    return None

                self._cond.wait(timeout=wait_time)

    def peek(self) -> Optional[Job]:
        """Return the next eligible job without removing it, or None."""
        with self._cond:
            now = time.time()
            self._promote_due_jobs(now)
            if self._ready_queue:
                return self._ready_queue[0].job
            return None

    def cancel(self, job_id: str) -> bool:
        """Mark job cancelled and remove from queue if present. Return True if found and removed."""
        with self._cond:
            if job_id not in self._job_ids:
                return False

            for i, entry in enumerate(self._ready_queue):
                if entry.job.job_id == job_id:
                    job = entry.job
                    job.status = JobStatus.CANCELLED
                    self._ready_queue.pop(i)
                    heapq.heapify(self._ready_queue)
                    self._job_ids.discard(job_id)
                    self._cond.notify_all()
                    return True

            for i, entry in enumerate(self._scheduled_queue):
                if entry.job.job_id == job_id:
                    job = entry.job
                    job.status = JobStatus.CANCELLED
                    self._scheduled_queue.pop(i)
                    heapq.heapify(self._scheduled_queue)
                    self._job_ids.discard(job_id)
                    self._cond.notify_all()
                    return True

            return False

    def size(self) -> int:
        """Return the current count of queued eligible and scheduled jobs."""
        with self._cond:
            return len(self._ready_queue) + len(self._scheduled_queue)

    def is_empty(self) -> bool:
        """Return True if no jobs are in the queue."""
        with self._cond:
            return len(self._ready_queue) == 0 and len(self._scheduled_queue) == 0
