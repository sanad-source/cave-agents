"""taskflow.models: Data models, enums, retry policies, and serialization."""

import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Optional


class JobPriority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class JobStatus(str, Enum):
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
        exp = max(0, attempt - 1)
        delay = float(self.base_delay) * (float(self.backoff_factor) ** exp)
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
    def from_dict(cls, data: dict) -> "RetryPolicy":
        return cls(
            max_attempts=int(data.get("max_attempts", 3)),
            base_delay=float(data.get("base_delay", 0.05)),
            backoff_factor=float(data.get("backoff_factor", 2.0)),
            jitter=bool(data.get("jitter", False)),
        )


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
        if self.priority is not None and not isinstance(self.priority, JobPriority):
            self.priority = JobPriority(int(self.priority))
        if self.status is not None and not isinstance(self.status, JobStatus):
            self.status = JobStatus(str(self.status))
        if isinstance(self.args, list):
            self.args = tuple(self.args)
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
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy is not None else None,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        retry_policy_raw = data.get("retry_policy")
        retry_policy = RetryPolicy.from_dict(retry_policy_raw) if retry_policy_raw is not None else None

        priority_raw = data.get("priority", JobPriority.MEDIUM)
        if isinstance(priority_raw, JobPriority):
            priority = priority_raw
        elif priority_raw is not None:
            priority = JobPriority(int(priority_raw))
        else:
            priority = JobPriority.MEDIUM

        status_raw = data.get("status", JobStatus.PENDING)
        if isinstance(status_raw, JobStatus):
            status = status_raw
        elif status_raw is not None:
            status = JobStatus(str(status_raw))
        else:
            status = JobStatus.PENDING

        args_raw = data.get("args", ())
        kwargs_raw = data.get("kwargs", {})

        return cls(
            job_id=data.get("job_id") or str(uuid.uuid4()),
            fn_name=data.get("fn_name", ""),
            args=tuple(args_raw),
            kwargs=dict(kwargs_raw),
            priority=priority,
            status=status,
            retry_policy=retry_policy,
            attempts=int(data.get("attempts", 0)),
            result=data.get("result", None),
            error=data.get("error", None),
            created_at=float(data.get("created_at", time.time())),
            scheduled_at=float(data.get("scheduled_at", 0.0)),
            timeout=float(data["timeout"]) if data.get("timeout") is not None else None,
        )
