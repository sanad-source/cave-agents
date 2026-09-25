"""Data models, enums, retry policies, and serialization for taskflow."""

from __future__ import annotations

import enum
import random
import time
import uuid
from dataclasses import dataclass, field, fields
from typing import Any, Optional, Dict, Tuple


class JobPriority(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.05
    backoff_factor: float = 2.0
    jitter: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def get_delay(self, attempt: int) -> float:
        attempt_idx = max(0, attempt - 1)
        delay = self.base_delay * (self.backoff_factor ** attempt_idx)
        if self.jitter:
            delay += random.uniform(0.0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict:
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RetryPolicy:
        return cls(**data)


@dataclass
class Job:
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    fn_name: str = ""
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: JobPriority = JobPriority.MEDIUM
    status: JobStatus = JobStatus.PENDING
    retry_policy: Optional[RetryPolicy] = None
    attempts: int = 0
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    scheduled_at: float = 0.0
    timeout: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = str(uuid.uuid4())
        if isinstance(self.priority, int) and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        if isinstance(self.status, str) and not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)
        if not isinstance(self.args, tuple):
            self.args = tuple(self.args) if self.args is not None else ()
        if self.kwargs is None:
            self.kwargs = {}

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value if isinstance(self.priority, JobPriority) else int(self.priority),
            "status": self.status.value if isinstance(self.status, JobStatus) else str(self.status),
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        d = dict(data)
        if "priority" in d and d["priority"] is not None:
            if isinstance(d["priority"], int):
                d["priority"] = JobPriority(d["priority"])
            elif isinstance(d["priority"], str):
                try:
                    d["priority"] = JobPriority[d["priority"]]
                except KeyError:
                    d["priority"] = JobPriority(int(d["priority"]))
        if "status" in d and d["status"] is not None:
            if isinstance(d["status"], str):
                try:
                    d["status"] = JobStatus(d["status"])
                except ValueError:
                    d["status"] = JobStatus[d["status"]]
        if "retry_policy" in d and d["retry_policy"] is not None:
            if isinstance(d["retry_policy"], dict):
                d["retry_policy"] = RetryPolicy.from_dict(d["retry_policy"])
        if "args" in d and isinstance(d["args"], (list, tuple)):
            d["args"] = tuple(d["args"])
        if "kwargs" in d and isinstance(d["kwargs"], dict):
            d["kwargs"] = dict(d["kwargs"])

        valid_fields = {f.name for f in fields(cls)}
        filtered_d = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered_d)
