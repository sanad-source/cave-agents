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
    print("=" * 72)
    print(" CaveAgents Empirical Benchmark Table (TokenBucket Rate Limiter)")
    print("=" * 72)
    print(f"{'Framework / Configuration':<30} | {'Tokens':<10} | {'vs Control (1.00x)':<24}")
    print("-" * 72)

    control_base = BASELINE_BENCHMARKS.get("Pruned_Mono", 11381)
    for name, tokens in sorted(BASELINE_BENCHMARKS.items(), key=lambda x: x[1]):
        mult = tokens / control_base
        mult_str = "1.00x (Baseline)" if tokens == control_base else f"{mult:.2f}x (+{(mult-1.0)*100:,.1f}%)"
        print(f"{name.replace('_', ' '):<30} | {tokens:>10,d} | {mult_str:>24}")
    print("=" * 72)
    print(" Note: Tool pruning reduces tokens across both paradigms. CaveAgents v4")
    print(" (26,784 tokens) achieves multi-agent TDD isolation for 2.35x of the")
    print(" Pruned Monolith Control (11,381 tokens), while saving -81.3% vs unpruned")
    print(" Teamwork (143,219 tokens).")


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="caveagents",
        description="CaveAgents - Token-pruned multi-agent orchestration framework.",
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
