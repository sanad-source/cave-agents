"""Command-line interface for the CaveAgents framework."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from caveagents import __version__
from caveagents.evaluator import BASELINE_BENCHMARKS, CostEvaluator, evaluate
from caveagents.protocol import MessageProtocol


def print_benchmarks() -> None:
    """Print the empirical benchmark comparison table."""
    print("=" * 68)
    print(" CaveAgents Empirical Benchmark Table (Identical Refactor Run)")
    print("=" * 68)
    print(f"{'Framework / Configuration':<30} | {'Tokens':<12} | {'Relative vs Teamwork':<15}")
    print("-" * 68)

    teamwork_base = BASELINE_BENCHMARKS.get("Teamwork_Live", 143219)
    for name, tokens in sorted(BASELINE_BENCHMARKS.items(), key=lambda x: x[1], reverse=True):
        pct = ((tokens - teamwork_base) / teamwork_base) * 100.0
        pct_str = f"{pct:+.1f}%" if tokens != teamwork_base else "Baseline (0.0%)"
        print(f"{name.replace('_', ' '):<30} | {tokens:>10,d} | {pct_str:>20}")
    print("=" * 68)
    print(" Note: Tool pruning reduces tokens across both paradigms. CaveAgents v4")
    print(" (26,784 tokens) achieves multi-agent TDD isolation for 2.35x of the")
    print(" Pruned Monolith Control (11,381 tokens), while saving -81.3% vs unpruned")
    print(" Teamwork (143,219 tokens).")


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="caveagents",
        description="CaveAgents - Token-pruned multi-agent orchestration operating on an inverted cost frontier.",
    )
    parser.add_argument("--version", "-v", action="version", version=f"caveagents {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: benchmarks
    subparsers.add_parser("benchmarks", aliases=["benchmark"], help="Display empirical multi-agent token benchmarks")

    # Command: evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Analyze transcript token consumption")
    eval_parser.add_argument("transcript", type=str, help="Path to transcript JSON file")

    # Command: validate
    val_parser = subparsers.add_parser("validate", help="Validate message against Caveman terseness rules")
    val_parser.add_argument("text", type=str, help="Message text string to validate")

    args = parser.parse_args()

    if args.command in ("benchmarks", "benchmark") or args.command is None:
        print_benchmarks()
        return 0

    if args.command == "evaluate":
        p = Path(args.transcript)
        if not p.exists():
            print(f"Error: Transcript file not found: {args.transcript}", file=sys.stderr)
            return 1
        res = evaluate(p)
        print(json.dumps(res, indent=2))
        return 0

    if args.command == "validate":
        valid, violations = MessageProtocol.validate_terseness(args.text)
        if valid:
            print("VALID: Message adheres to Caveman terse protocol rules.")
            return 0
        else:
            print(f"INVALID: Detected conversational filler words: {violations}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
