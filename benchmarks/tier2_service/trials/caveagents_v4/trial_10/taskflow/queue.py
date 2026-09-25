"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from taskflow.models import Job, JobPriority, JobStatus


@dataclass(order=True)
class _ReadyEntry:
    priority_score: int
    created_at: float
    seq: int
    job_id: str = field(compare=False)
    job: Job = field(compare=False)


@dataclass(order=True)
class _DelayedEntry:
    scheduled_at: float
    seq: int
    job_id: str = field(compare=False)
    job: Job = field(compare=False)


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._ready_heap: List[_ReadyEntry] = []
        self._delayed_heap: List[_DelayedEntry] = []
        self._jobs: Dict[str, Job] = {}
        self._seq: int = 0

    def push(self, job: Job) -> None:
        with self._cv:
            self._seq += 1
            seq = self._seq
            self._jobs[job.job_id] = job
            now = time.time()
            if job.scheduled_at > now:
                heapq.heappush(
                    self._delayed_heap,
                    _DelayedEntry(
                        scheduled_at=job.scheduled_at,
                        seq=seq,
                        job_id=job.job_id,
                        job=job,
                    ),
                )
            else:
                priority_val = (
                    job.priority.value
                    if isinstance(job.priority, JobPriority)
                    else int(job.priority)
                )
                heapq.heappush(
                    self._ready_heap,
                    _ReadyEntry(
                        priority_score=-priority_val,
                        created_at=job.created_at,
                        seq=seq,
                        job_id=job.job_id,
                        job=job,
                    ),
                )
            self._cv.notify_all()

    def _promote_delayed(self) -> None:
        now = time.time()
        while self._delayed_heap and self._delayed_heap[0].scheduled_at <= now:
            entry = heapq.heappop(self._delayed_heap)
            if entry.job_id in self._jobs and self._jobs[entry.job_id] is entry.job:
                priority_val = (
                    entry.job.priority.value
                    if isinstance(entry.job.priority, JobPriority)
                    else int(entry.job.priority)
                )
                heapq.heappush(
                    self._ready_heap,
                    _ReadyEntry(
                        priority_score=-priority_val,
                        created_at=entry.job.created_at,
                        seq=entry.seq,
                        job_id=entry.job_id,
                        job=entry.job,
                    ),
                )

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        start_mono = time.monotonic()
        has_timeout = timeout is not None
        timeout_val = float(timeout) if has_timeout else 0.0

        with self._cv:
            while True:
                self._promote_delayed()

                # Try to pop an eligible job
                while self._ready_heap:
                    entry = heapq.heappop(self._ready_heap)
                    job_id = entry.job_id
                    if job_id in self._jobs and self._jobs[job_id] is entry.job:
                        del self._jobs[job_id]
                        return entry.job

                # No ready jobs available right now
                if has_timeout:
                    elapsed = time.monotonic() - start_mono
                    remaining_timeout = timeout_val - elapsed
                    if remaining_timeout <= 0:
                        return None
                else:
                    remaining_timeout = None

                # Find when the earliest delayed job will become ready
                next_delay_wait: Optional[float] = None
                while self._delayed_heap:
                    top_delayed = self._delayed_heap[0]
                    if (
                        top_delayed.job_id not in self._jobs
                        or self._jobs[top_delayed.job_id] is not top_delayed.job
                    ):
                        heapq.heappop(self._delayed_heap)
                        continue
                    wait_sec = top_delayed.scheduled_at - time.time()
                    if wait_sec <= 0:
                        next_delay_wait = 0.0
                    else:
                        next_delay_wait = wait_sec
                    break

                if next_delay_wait is not None and next_delay_wait <= 0:
                    continue

                if has_timeout and remaining_timeout is not None:
                    if next_delay_wait is not None:
                        wait_time = min(remaining_timeout, next_delay_wait)
                    else:
                        wait_time = remaining_timeout
                else:
                    wait_time = next_delay_wait

                if wait_time is not None:
                    if wait_time <= 0:
                        if has_timeout:
                            return None
                        continue
                    self._cv.wait(timeout=wait_time)
                else:
                    self._cv.wait()

    def peek(self) -> Optional[Job]:
        with self._cv:
            self._promote_delayed()
            while self._ready_heap:
                entry = self._ready_heap[0]
                if entry.job_id in self._jobs and self._jobs[entry.job_id] is entry.job:
                    return entry.job
                heapq.heappop(self._ready_heap)
            return None

    def cancel(self, job_id: str) -> bool:
        with self._cv:
            job = self._jobs.pop(job_id, None)
            if job is None:
                return False
            job.status = JobStatus.CANCELLED
            self._ready_heap = [e for e in self._ready_heap if e.job_id != job_id]
            heapq.heapify(self._ready_heap)
            self._delayed_heap = [e for e in self._delayed_heap if e.job_id != job_id]
            heapq.heapify(self._delayed_heap)
            self._cv.notify_all()
            return True

    def size(self) -> int:
        with self._cv:
            return len(self._jobs)

    def is_empty(self) -> bool:
        with self._cv:
            return len(self._jobs) == 0
