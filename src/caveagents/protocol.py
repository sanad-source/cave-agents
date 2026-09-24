"""Message protocol and serialization schemas for CaveAgents peer-to-peer and DAG communications."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageType(str, Enum):
    """Permitted message action types under the Cave protocol."""
    TASK = "TASK"
    HANDOFF = "HANDOFF"
    RESULT = "RESULT"
    SYNC = "SYNC"
    ACK = "ACK"
    ALERT = "ALERT"


@dataclass
class CaveMessage:
    """Standardized terse wire format for inter-agent communications."""
    sender: str
    recipient: str
    action: MessageType = MessageType.TASK
    payload: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    status: str = "ok"

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary representation."""
        data = asdict(self)
        data["action"] = self.action.value if isinstance(self.action, MessageType) else str(self.action)
        return data

    def to_wire(self) -> str:
        """Serialize to compact wire format minimizing token footprint."""
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_wire(cls, raw: str) -> CaveMessage:
        """Parse compact JSON string into CaveMessage."""
        data = json.loads(raw)
        return cls(
            sender=data.get("sender", "unknown"),
            recipient=data.get("recipient", "all"),
            action=MessageType(data.get("action", MessageType.TASK.value)),
            payload=data.get("payload", {}),
            summary=data.get("summary", ""),
            status=data.get("status", "ok"),
        )


class MessageProtocol:
    """Protocol enforcement and validation suite for terse agent communication."""

    # Words prohibited in terse cave mode (filler, pleasantries, hedging)
    BANNED_FILLER_PATTERNS = [
        r"\b(?:hello|hi|hey|greetings|dear|kind regards|best regards|cheers|sincerely)\b",
        r"\b(?:please let me know|hope you are doing well|thank you very much|thanks a lot)\b",
        r"\b(?:i would be happy to|as an ai language model|allow me to explain)\b",
        r"\b(?:just wanted to check in|without further ado|needless to say)\b",
    ]

    @classmethod
    def validate_terseness(cls, text: str) -> tuple[bool, List[str]]:
        """Validate text against Caveman style guidelines (no conversational filler)."""
        violations: List[str] = []
        lower = text.lower()
        for pat in cls.BANNED_FILLER_PATTERNS:
            matches = re.findall(pat, lower)
            if matches:
                violations.extend(matches)
        return (len(violations) == 0, violations)

    @classmethod
    def pack(cls, sender: str, recipient: str, action: MessageType, payload: Dict[str, Any], summary: str = "") -> str:
        """Pack an outbound message into wire format."""
        msg = CaveMessage(
            sender=sender,
            recipient=recipient,
            action=action,
            payload=payload,
            summary=summary,
        )
        return msg.to_wire()

    @classmethod
    def unpack(cls, raw: str) -> CaveMessage:
        """Unpack raw wire string to CaveMessage."""
        return CaveMessage.from_wire(raw)


def format_cave_message(sender: str, recipient: str, action: str | MessageType, **kwargs: Any) -> str:
    """Utility helper to produce a validated compact JSON message string."""
    act = MessageType(action) if isinstance(action, str) else action
    msg = CaveMessage(
        sender=sender,
        recipient=recipient,
        action=act,
        payload=kwargs.get("payload", kwargs),
        summary=kwargs.get("summary", ""),
        status=kwargs.get("status", "ok"),
    )
    return msg.to_wire()


def parse_cave_message(raw_data: str | Dict[str, Any]) -> CaveMessage:
    """Utility helper to parse raw wire string or dictionary into CaveMessage."""
    if isinstance(raw_data, str):
        return CaveMessage.from_wire(raw_data)
    elif isinstance(raw_data, dict):
        return CaveMessage(
            sender=raw_data.get("sender", "unknown"),
            recipient=raw_data.get("recipient", "all"),
            action=MessageType(raw_data.get("action", MessageType.TASK.value)),
            payload=raw_data.get("payload", {}),
            summary=raw_data.get("summary", ""),
            status=raw_data.get("status", "ok"),
        )
    raise TypeError(f"Expected str or dict, got {type(raw_data)}")
