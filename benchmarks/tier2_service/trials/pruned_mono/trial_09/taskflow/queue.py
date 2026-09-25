from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from taskflow.models import Job, JobStatus


@dataclass(order=True)
class _ReadyItem:
    priority_neg: int
    created_at: float
    seq: int
    job: Any = field(compare=False)


@dataclass(order=True)
class _DelayedItem:
    scheduled_at: float
    seq: int
    job: Any = field(compare=False)


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._ready: list[_ReadyItem] = []
        self._delayed: list[_DelayedItem] = []
        self._counter = 0

    def _seq(self) -> int:
        self._counter += 1
        return self._counter

    def _transfer_ready(self, now: float) -> None:
        while self._delayed and self._delayed[0].scheduled_at <= now:
            item = heapq.heappop(self._delayed)
            heapq.heappush(
                self._ready,
                _ReadyItem(
                    priority_neg=-int(item.job.priority),
                    created_at=item.job.created_at,
                    seq=item.seq,
                    job=item.job,
                ),
            )

    def push(self, job: Job) -> None:
        with self._cond:
            now = time.time()
            seq = self._seq()
            if job.scheduled_at <= now:
                heapq.heappush(
                    self._ready,
                    _ReadyItem(
                        priority_neg=-int(job.priority),
                        created_at=job.created_at,
                        seq=seq,
                        job=job,
                    ),
                )
            else:
                heapq.heappush(
                    self._delayed,
                    _DelayedItem(
                        scheduled_at=job.scheduled_at,
                        seq=seq,
                        job=job,
                    ),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        with self._cond:
            start_time = time.time()
            while True:
                now = time.time()
                self._transfer_ready(now)
                if self._ready:
                    return heapq.heappop(self._ready).job

                if timeout is not None:
                    elapsed = now - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None
                else:
                    remaining = None

                if self._delayed:
                    time_to_eligible = self._delayed[0].scheduled_at - now
                    if time_to_eligible <= 0:
                        continue
                    if remaining is not None:
                        wait_for = min(remaining, time_to_eligible)
                    else:
                        wait_for = time_to_eligible
                else:
                    if remaining is not None:
                        wait_for = remaining
                    else:
                        wait_for = None

                if wait_for is not None:
                    self._cond.wait(timeout=wait_for)
                else:
                    self._cond.wait()

    def peek(self) -> Optional[Job]:
        with self._cond:
            self._transfer_ready(time.time())
            if self._ready:
                return self._ready[0].job
            return None

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            for i, item in enumerate(self._ready):
                if item.job.job_id == job_id:
                    job = item.job
                    job.status = JobStatus.CANCELLED
                    self._ready.pop(i)
                    heapq.heapify(self._ready)
                    self._cond.notify_all()
                    return True
            for i, item in enumerate(self._delayed):
                if item.job.job_id == job_id:
                    job = item.job
                    job.status = JobStatus.CANCELLED
                    self._delayed.pop(i)
                    heapq.heapify(self._delayed)
                    self._cond.notify_all()
                    return True
            return False

    def size(self) -> int:
        with self._cond:
            return len(self._ready) + len(self._delayed)

    def is_empty(self) -> bool:
        with self._cond:
            return (len(self._ready) + len(self._delayed)) == 0
