"""Thread-safe priority task queue with FIFO tie-breaking and delayed scheduling."""

import heapq
import threading
import time
from typing import Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._ready_heap: list[tuple] = []
        self._delayed_heap: list[tuple] = []
        self._job_ids: dict[str, Job] = {}
        self._counter: int = 0

    def _promote_delayed_jobs(self, now: float) -> None:
        while self._delayed_heap and self._delayed_heap[0][0] <= now:
            _, neg_prio, created_at, counter, job = heapq.heappop(self._delayed_heap)
            heapq.heappush(self._ready_heap, (neg_prio, created_at, counter, job))

    def push(self, job: Job) -> None:
        with self._condition:
            self._counter += 1
            now = time.time()
            if job.job_id in self._job_ids:
                del self._job_ids[job.job_id]
                self._ready_heap = [item for item in self._ready_heap if item[3].job_id != job.job_id]
                heapq.heapify(self._ready_heap)
                self._delayed_heap = [item for item in self._delayed_heap if item[4].job_id != job.job_id]
                heapq.heapify(self._delayed_heap)

            self._job_ids[job.job_id] = job
            prio_val = job.priority.value if isinstance(job.priority, JobPriority) else int(job.priority)

            if job.scheduled_at > now:
                # delayed heap tuple: (scheduled_at, -priority, created_at, counter, job)
                heapq.heappush(self._delayed_heap, (job.scheduled_at, -prio_val, job.created_at, self._counter, job))
            else:
                # ready heap tuple: (-priority, created_at, counter, job)
                heapq.heappush(self._ready_heap, (-prio_val, job.created_at, self._counter, job))

            self._condition.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        start_time = time.time()
        with self._condition:
            while True:
                now = time.time()
                self._promote_delayed_jobs(now)

                if self._ready_heap:
                    _, _, _, job = heapq.heappop(self._ready_heap)
                    self._job_ids.pop(job.job_id, None)
                    return job

                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None

                    if self._delayed_heap:
                        next_scheduled = self._delayed_heap[0][0]
                        delay = max(0.0, next_scheduled - time.time())
                        wait_time = min(remaining, delay)
                    else:
                        wait_time = remaining

                    self._condition.wait(timeout=wait_time)
                else:
                    if self._delayed_heap:
                        next_scheduled = self._delayed_heap[0][0]
                        delay = max(0.0, next_scheduled - time.time())
                        self._condition.wait(timeout=delay)
                    else:
                        self._condition.wait()

    def peek(self) -> Optional[Job]:
        with self._condition:
            now = time.time()
            self._promote_delayed_jobs(now)
            if self._ready_heap:
                return self._ready_heap[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            if job_id not in self._job_ids:
                return False
            job = self._job_ids.pop(job_id)
            job.status = JobStatus.CANCELLED
            self._ready_heap = [item for item in self._ready_heap if item[3].job_id != job_id]
            heapq.heapify(self._ready_heap)
            self._delayed_heap = [item for item in self._delayed_heap if item[4].job_id != job_id]
            heapq.heapify(self._delayed_heap)
            return True

    def size(self) -> int:
        with self._condition:
            return len(self._job_ids)

    def is_empty(self) -> bool:
        with self._condition:
            return len(self._job_ids) == 0
