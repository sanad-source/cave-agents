"""Data models, enums, retry policies, and serialization for taskflow."""

from __future__ import annotations

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

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def get_delay(self, attempt: int) -> float:
        attempt_idx = max(1, attempt) - 1
        delay = self.base_delay * (self.backoff_factor ** attempt_idx)
        if self.jitter:
            delay += random.uniform(0.0, 0.5 * delay)
        return delay

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
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
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
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
        if isinstance(self.args, list):
            self.args = tuple(self.args)

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> Job:
        data = dict(data)
        priority = JobPriority(data["priority"]) if "priority" in data else JobPriority.MEDIUM
        status = JobStatus(data["status"]) if "status" in data else JobStatus.PENDING
        retry_policy_data = data.get("retry_policy")
        retry_policy = RetryPolicy.from_dict(retry_policy_data) if retry_policy_data is not None else None
        args = tuple(data.get("args", ()))
        kwargs = dict(data.get("kwargs", {}))

        return cls(
            job_id=data.get("job_id", str(uuid.uuid4())),
            fn_name=data.get("fn_name", ""),
            args=args,
            kwargs=kwargs,
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
