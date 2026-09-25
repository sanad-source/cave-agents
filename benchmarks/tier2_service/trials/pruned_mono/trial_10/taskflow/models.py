"""Data models, enums, retry policies, and serialization for taskflow."""

import enum
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


class JobPriority(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(enum.Enum):
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

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def get_delay(self, attempt: int) -> float:
        attempt_idx = max(0, attempt - 1)
        delay = self.base_delay * (self.backoff_factor ** attempt_idx)
        if self.jitter:
            delay += random.uniform(0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict:
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetryPolicy":
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

    def __post_init__(self):
        if not self.job_id:
            self.job_id = str(uuid.uuid4())
        if not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(self.priority)
        if not isinstance(self.status, JobStatus):
            self.status = JobStatus(self.status)
        if isinstance(self.args, list):
            self.args = tuple(self.args)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "fn_name": self.fn_name,
            "args": list(self.args),
            "kwargs": dict(self.kwargs),
            "priority": self.priority.value,
            "status": self.status.value,
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        data_copy = dict(data)
        if "priority" in data_copy and not isinstance(data_copy["priority"], JobPriority):
            data_copy["priority"] = JobPriority(data_copy["priority"])
        if "status" in data_copy and not isinstance(data_copy["status"], JobStatus):
            data_copy["status"] = JobStatus(data_copy["status"])
        if "retry_policy" in data_copy and data_copy["retry_policy"] is not None:
            if isinstance(data_copy["retry_policy"], dict):
                data_copy["retry_policy"] = RetryPolicy.from_dict(data_copy["retry_policy"])
        if "args" in data_copy:
            data_copy["args"] = tuple(data_copy["args"])
        if "kwargs" in data_copy and data_copy["kwargs"] is not None:
            data_copy["kwargs"] = dict(data_copy["kwargs"])
        return cls(**data_copy)
