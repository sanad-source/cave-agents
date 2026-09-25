import heapq
import threading
import time
from typing import List, Optional, Tuple

from taskflow.models import Job, JobPriority, JobStatus


class PriorityTaskQueue:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        # Entry in ready_queue: (-priority, created_at, counter, job)
        self._ready_queue: List[Tuple[int, float, int, Job]] = []
        # Entry in delayed_queue: (scheduled_at, -priority, created_at, counter, job)
        self._delayed_queue: List[Tuple[float, int, float, int, Job]] = []
        self._counter: int = 0

    def _promote_delayed_locked(self, now: float) -> None:
        while self._delayed_queue and self._delayed_queue[0][0] <= now:
            _, neg_prio, created_at, _, job = heapq.heappop(self._delayed_queue)
            self._counter += 1
            heapq.heappush(self._ready_queue, (neg_prio, created_at, self._counter, job))

    def push(self, job: Job) -> None:
        with self._cond:
            self._counter += 1
            now = time.time()
            prio_val = int(job.priority.value if isinstance(job.priority, JobPriority) else job.priority)
            if job.scheduled_at and job.scheduled_at > now:
                heapq.heappush(
                    self._delayed_queue,
                    (job.scheduled_at, -prio_val, job.created_at, self._counter, job),
                )
            else:
                heapq.heappush(
                    self._ready_queue,
                    (-prio_val, job.created_at, self._counter, job),
                )
            self._cond.notify_all()

    def pop(self, timeout: Optional[float] = None) -> Optional[Job]:
        with self._cond:
            deadline = (time.monotonic() + timeout) if timeout is not None else None
            while True:
                now = time.time()
                self._promote_delayed_locked(now)

                if self._ready_queue:
                    _, _, _, job = heapq.heappop(self._ready_queue)
                    return job

                monotonic_now = time.monotonic()
                if deadline is not None:
                    remaining_timeout = deadline - monotonic_now
                    if remaining_timeout <= 0:
                        return None
                else:
                    remaining_timeout = None

                if self._delayed_queue:
                    delay_wait = max(0.0, self._delayed_queue[0][0] - time.time())
                    if remaining_timeout is not None:
                        wait_time = min(remaining_timeout, delay_wait)
                    else:
                        wait_time = delay_wait
                else:
                    wait_time = remaining_timeout

                if wait_time is not None and wait_time <= 0:
                    continue

                self._cond.wait(timeout=wait_time)

    def peek(self) -> Optional[Job]:
        with self._cond:
            now = time.time()
            self._promote_delayed_locked(now)
            if self._ready_queue:
                return self._ready_queue[0][3]
            return None

    def cancel(self, job_id: str) -> bool:
        with self._cond:
            # Check ready queue
            for i, entry in enumerate(self._ready_queue):
                if entry[3].job_id == job_id:
                    job = entry[3]
                    job.status = JobStatus.CANCELLED
                    self._ready_queue.pop(i)
                    heapq.heapify(self._ready_queue)
                    return True
            # Check delayed queue
            for i, entry in enumerate(self._delayed_queue):
                if entry[4].job_id == job_id:
                    job = entry[4]
                    job.status = JobStatus.CANCELLED
                    self._delayed_queue.pop(i)
                    heapq.heapify(self._delayed_queue)
                    return True
            return False

    def size(self) -> int:
        with self._cond:
            return len(self._ready_queue) + len(self._delayed_queue)

    def is_empty(self) -> bool:
        with self._cond:
            return (len(self._ready_queue) + len(self._delayed_queue)) == 0
