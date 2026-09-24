"""Transcript parser, dual-context accounting, and token cost evaluation engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tiktoken

    def count_tokens(text: str, model: str = "cl100k_base") -> int:
        try:
            enc = tiktoken.get_encoding(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
except ImportError:
    # Heuristic fallback if tiktoken not installed: ~4 chars per token
    def count_tokens(text: str, model: str = "cl100k_base") -> int:
        return max(1, len(text) // 4)


BASELINE_BENCHMARKS: Dict[str, int] = {
    "Teamwork_Live": 143219,
    "AgentTeams": 154998,
    "CaveAgents_v1": 109984,
    "CaveAgents_v2": 91432,
    "CaveAgents_v3": 50395,
    "Standard_Mono": 30241,
    "CaveAgents_v4": 26784,
    "Caveman_Mono": 16285,
    "Pruned_Mono_Control": 11381,
}


@dataclass
class TokenAccounting:
    """Breakdown of token expenditure across system prompts, tools, and message cycles."""
    system_prompt_tokens: int = 0
    tool_declaration_tokens: int = 0
    message_content_tokens: int = 0
    total_tokens: int = 0
    step_count: int = 0
    pruned_tool_savings: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_prompt_tokens": self.system_prompt_tokens,
            "tool_declaration_tokens": self.tool_declaration_tokens,
            "message_content_tokens": self.message_content_tokens,
            "total_tokens": self.total_tokens,
            "step_count": self.step_count,
            "pruned_tool_savings": self.pruned_tool_savings,
        }


class CostEvaluator:
    """Evaluates multi-agent token efficiency, context inflation, and savings frontiers."""

    TOOL_DECLARATION_BASE_COST = 2500  # Typical ~2.5k tokens for full unpruned tool schemas

    def __init__(self, model_encoding: str = "cl100k_base") -> None:
        self.model_encoding = model_encoding

    def count(self, text: str) -> int:
        """Count tokens using current encoder."""
        return count_tokens(text, self.model_encoding)

    def analyze_transcript(self, transcript_data: List[Dict[str, Any]] | Dict[str, Any]) -> TokenAccounting:
        """Parse structured transcript and compute token breakdown."""
        steps = transcript_data if isinstance(transcript_data, list) else transcript_data.get("steps", [])

        sys_tokens = 0
        tool_tokens = 0
        msg_tokens = 0
        pruned_savings = 0

        for step in steps:
            content = step.get("content", "")
            msg_tokens += self.count(str(content))

            # System prompt attribution if present
            if "system" in step:
                sys_tokens += self.count(str(step["system"]))

            # Tool schema footprint accounting
            active_tools = step.get("tools", [])
            is_pruned = step.get("pruned", False)
            if is_pruned:
                # Active pruned tools only
                schema_cost = sum(self.count(str(t)) for t in active_tools) or 400
                tool_tokens += schema_cost
                pruned_savings += max(0, self.TOOL_DECLARATION_BASE_COST - schema_cost)
            else:
                # Full unpruned tool registry
                tool_tokens += self.TOOL_DECLARATION_BASE_COST

        total = sys_tokens + tool_tokens + msg_tokens
        return TokenAccounting(
            system_prompt_tokens=sys_tokens,
            tool_declaration_tokens=tool_tokens,
            message_content_tokens=msg_tokens,
            total_tokens=total,
            step_count=len(steps),
            pruned_pruned_savings=pruned_savings if hasattr(TokenAccounting, "pruned_pruned_savings") else pruned_savings,
        )

    def compare_benchmarks(self, live_total: int) -> Dict[str, Any]:
        """Compute relative savings and efficiency ratio against empirical benchmarks."""
        results: Dict[str, Any] = {
            "live_tokens": live_total,
            "comparisons": {},
        }
        for name, baseline in BASELINE_BENCHMARKS.items():
            diff = baseline - live_total
            pct_saved = (diff / baseline) * 100.0 if baseline > 0 else 0.0
            results["comparisons"][name] = {
                "baseline_tokens": baseline,
                "delta": diff,
                "pct_reduction": round(pct_saved, 2),
                "is_cheaper": live_total < baseline,
            }
        return results


def evaluate(transcript_path_or_data: str | Path | List[Dict[str, Any]] | Dict[str, Any]) -> Dict[str, Any]:
    """Top-level convenience evaluation entrypoint."""
    evaluator = CostEvaluator()

    if isinstance(transcript_path_or_data, (str, Path)):
        p = Path(transcript_path_or_data)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
    else:
        data = transcript_path_or_data

    accounting = evaluator.analyze_transcript(data)
    comparison = evaluator.compare_benchmarks(accounting.total_tokens)

    return {
        "accounting": accounting.to_dict(),
        "benchmarks": comparison,
    }
