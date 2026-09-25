import heapq
import threading
import time
from typing import Optional
from taskflow.models import Job, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._ready: list[tuple[int, float, int, Job]] = []
        self._scheduled: list[tuple[float, int, Job]] = []
        self._counter: int = 0

    def push(self, job: Job) -> None:
        with self._lock:
            self._counter += 1
            now = time.time()
            if job.scheduled_at > now:
                heapq.heappush(self._scheduled, (job.scheduled_at, self._counter, job))
            else:
                heapq.heappush(
                    self._ready,
                    (-int(job.priority), job.created_at, self._counter, job),
                )
            self._cv.notify_all()

    def _move_scheduled_to_ready(self) -> None:
        now = time.time()
        while self._scheduled and self._scheduled[0][0] <= now:
            _, seq, job = heapq.heappop(self._scheduled)
            heapq.heappush(
                self._ready,
                (-int(job.priority), job.created_at, seq, job),
            )

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        with self._lock:
            start_time = time.time()
            while True:
                self._move_scheduled_to_ready()
                if self._ready:
                    _, _, _, job = heapq.heappop(self._ready)
                    return job

                now = time.time()
                if timeout is not None:
                    remaining = (start_time + timeout) - now
                    if remaining <= 0:
                        return None
                else:
                    remaining = None

                if self._scheduled:
                    earliest_scheduled = self._scheduled[0][0]
                    time_until_scheduled = earliest_scheduled - now
                    if time_until_scheduled <= 0:
                        continue
                    if remaining is not None:
                        wait_time = min(remaining, time_until_scheduled)
                    else:
                        wait_time = time_until_scheduled
                else:
                    if remaining is not None:
                        wait_time = remaining
                    else:
                        wait_time = None

                if wait_time is not None and wait_time <= 0:
                    return None

                self._cv.wait(timeout=wait_time)

    def peek(self) -> Optional[Job]:
        with self._lock:
            self._move_scheduled_to_ready()
            if self._ready:
                return self._ready[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            for i, item in enumerate(self._ready):
                job = item[3]
                if job.job_id == job_id:
                    job.status = JobStatus.CANCELLED
                    self._ready.pop(i)
                    heapq.heapify(self._ready)
                    self._cv.notify_all()
                    return True
            for i, item in enumerate(self._scheduled):
                job = item[2]
                if job.job_id == job_id:
                    job.status = JobStatus.CANCELLED
                    self._scheduled.pop(i)
                    heapq.heapify(self._scheduled)
                    self._cv.notify_all()
                    return True
            return False

    def size(self) -> int:
        with self._lock:
            return len(self._ready) + len(self._scheduled)

    def is_empty(self) -> bool:
        with self._lock:
            return (len(self._ready) + len(self._scheduled)) == 0

    def wake_all(self) -> None:
        with self._lock:
            self._cv.notify_all()
