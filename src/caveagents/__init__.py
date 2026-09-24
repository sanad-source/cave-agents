"""CaveAgents: Token-pruned multi-agent orchestration framework operating on an inverted cost frontier."""

__version__ = "0.4.0"

from caveagents.protocol import CaveMessage, MessageProtocol, format_cave_message, parse_cave_message
from caveagents.evaluator import CostEvaluator, evaluate
from caveagents.cli import main

__all__ = [
    "__version__",
    "CaveMessage",
    "MessageProtocol",
    "format_cave_message",
    "parse_cave_message",
    "CostEvaluator",
    "evaluate",
    "main",
]
