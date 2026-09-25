import heapq
import threading
import time
from typing import Optional

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        # Heap elements: (-priority_value, created_at, seq, job)
        self._ready_heap: list[tuple[int, float, int, Job]] = []
        # Heap elements: (scheduled_at, seq, job)
        self._delayed_heap: list[tuple[float, int, Job]] = []
        self._entries: dict[str, Job] = {}
        self._seq: int = 0

    def _promote_delayed(self) -> None:
        now = time.time()
        while self._delayed_heap and self._delayed_heap[0][0] <= now:
            scheduled_at, seq, job = heapq.heappop(self._delayed_heap)
            if job.job_id in self._entries:
                heapq.heappush(
                    self._ready_heap,
                    (-job.priority.value, job.created_at, seq, job),
                )

    def push(self, job: Job) -> None:
        with self._condition:
            if job.job_id in self._entries:
                self._ready_heap = [
                    item for item in self._ready_heap if item[3].job_id != job.job_id
                ]
                heapq.heapify(self._ready_heap)
                self._delayed_heap = [
                    item for item in self._delayed_heap if item[2].job_id != job.job_id
                ]
                heapq.heapify(self._delayed_heap)

            self._seq += 1
            self._entries[job.job_id] = job
            now = time.time()
            if job.scheduled_at > now:
                heapq.heappush(self._delayed_heap, (job.scheduled_at, self._seq, job))
            else:
                heapq.heappush(
                    self._ready_heap,
                    (-job.priority.value, job.created_at, self._seq, job),
                )
            self._condition.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        with self._condition:
            start_time = time.monotonic()
            while True:
                self._promote_delayed()
                if self._ready_heap:
                    _, _, _, job = heapq.heappop(self._ready_heap)
                    self._entries.pop(job.job_id, None)
                    return job

                now_mono = time.monotonic()
                if timeout is not None:
                    elapsed = now_mono - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None
                else:
                    remaining = None

                wait_time = remaining
                if self._delayed_heap:
                    earliest_scheduled_at = self._delayed_heap[0][0]
                    time_until_scheduled = earliest_scheduled_at - time.time()
                    if time_until_scheduled <= 0:
                        continue
                    if wait_time is None:
                        wait_time = time_until_scheduled
                    else:
                        wait_time = min(wait_time, time_until_scheduled)

                if timeout is not None and wait_time is not None and wait_time <= 0:
                    return None

                self._condition.wait(timeout=wait_time)

    def peek(self) -> Optional[Job]:
        with self._condition:
            self._promote_delayed()
            if self._ready_heap:
                return self._ready_heap[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            if job_id not in self._entries:
                return False
            job = self._entries.pop(job_id)
            job.status = JobStatus.CANCELLED
            self._ready_heap = [
                item for item in self._ready_heap if item[3].job_id != job_id
            ]
            heapq.heapify(self._ready_heap)
            self._delayed_heap = [
                item for item in self._delayed_heap if item[2].job_id != job_id
            ]
            heapq.heapify(self._delayed_heap)
            self._condition.notify_all()
            return True

    def size(self) -> int:
        with self._condition:
            return len(self._entries)

    def is_empty(self) -> bool:
        with self._condition:
            return len(self._entries) == 0
