import heapq
import itertools
import threading
import time
from typing import Any, Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._ready_queue: list[tuple[int, float, int, Job]] = []
        self._scheduled_queue: list[tuple[float, int, float, int, Job]] = []
        self._counter = itertools.count()

    def _promote_scheduled(self, now: float) -> None:
        while self._scheduled_queue and self._scheduled_queue[0][0] <= now:
            entry = heapq.heappop(self._scheduled_queue)
            # entry: (scheduled_at, p_val, created_at, seq, job)
            _, p_val, created_at, seq, job = entry
            heapq.heappush(self._ready_queue, (p_val, created_at, seq, job))

    def push(self, job: Job) -> None:
        with self._cond:
            now = time.time()
            seq = next(self._counter)
            p_val = -int(job.priority)
            if job.scheduled_at > now:
                heapq.heappush(
                    self._scheduled_queue,
                    (job.scheduled_at, p_val, job.created_at, seq, job),
                )
            else:
                heapq.heappush(
                    self._ready_queue,
                    (p_val, job.created_at, seq, job),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        deadline = (time.time() + timeout) if timeout is not None else None
        with self._cond:
            while True:
                now = time.time()
                self._promote_scheduled(now)

                if self._ready_queue:
                    entry = heapq.heappop(self._ready_queue)
                    if self._ready_queue:
                        self._cond.notify()
                    return entry[-1]

                if deadline is not None and now >= deadline:
                    return None

                wait_time: Optional[float] = None
                if deadline is not None:
                    wait_time = deadline - now

                if self._scheduled_queue:
                    time_until_scheduled = max(0.0, self._scheduled_queue[0][0] - now)
                    if wait_time is None:
                        wait_time = time_until_scheduled
                    else:
                        wait_time = min(wait_time, time_until_scheduled)

                if wait_time is not None:
                    if wait_time <= 0:
                        continue
                    self._cond.wait(timeout=wait_time)
                else:
                    self._cond.wait()

    def peek(self) -> Optional[Job]:
        with self._cond:
            self._promote_scheduled(time.time())
            if self._ready_queue:
                return self._ready_queue[0][-1]
            return None

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            for i, entry in enumerate(self._ready_queue):
                if entry[-1].job_id == job_id:
                    job = entry[-1]
                    del self._ready_queue[i]
                    heapq.heapify(self._ready_queue)
                    job.status = JobStatus.CANCELLED
                    return True

            for i, entry in enumerate(self._scheduled_queue):
                if entry[-1].job_id == job_id:
                    job = entry[-1]
                    del self._scheduled_queue[i]
                    heapq.heapify(self._scheduled_queue)
                    job.status = JobStatus.CANCELLED
                    return True

            return False

    def size(self) -> int:
        with self._cond:
            return len(self._ready_queue) + len(self._scheduled_queue)

    def is_empty(self) -> bool:
        with self._cond:
            return len(self._ready_queue) == 0 and len(self._scheduled_queue) == 0
