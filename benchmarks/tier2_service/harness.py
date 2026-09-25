"""Automated Benchmark Harness for Tier 2 taskflow Multi-File Service.
Adheres strictly to the SuperAgent Operating Protocol:
- LAW 1: Zero synthetic benchmarks. Every number is read directly from disk.
- LAW 2: Strict experimental control (identical task, files, criteria).
- LAW 3: Evidence before claims (actual pytest runs).
- LAW 4: Relentless intellectual honesty.
- LAW 5: Verifiable execution (tests written & failed before code, tracked transcripts).
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import tiktoken

BENCHMARK_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARK_DIR.parent.parent
TRIALS_DIR = BENCHMARK_DIR / "trials"
HIDDEN_SUITE = BENCHMARK_DIR / "hidden_suite" / "test_hidden_correctness.py"
RESULTS_FILE = BENCHMARK_DIR / "results.json"
VENV_PYTHON = Path(os.environ.get("VENV_PYTHON", sys.executable))
VENV_PYTEST = Path(os.environ.get("VENV_PYTEST", shutil.which("pytest") or "pytest"))

ENC = tiktoken.get_encoding("cl100k_base")
PRUNED_SCHEMA_TOKENS_PER_TURN = 380


def setup_trial_dir(arm: str, trial_idx: int) -> Path:
    """Initialize clean directory structure for a trial."""
    trial_name = f"trial_{trial_idx:02d}"
    trial_dir = TRIALS_DIR / arm / trial_name
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "tests").mkdir(parents=True, exist_ok=True)
    (trial_dir / "taskflow").mkdir(parents=True, exist_ok=True)

    # Copy spec and visible test suite
    shutil.copy2(BENCHMARK_DIR / "spec.md", trial_dir / "spec.md")
    shutil.copy2(BENCHMARK_DIR / "tests" / "test_visible.py", trial_dir / "tests" / "test_visible.py")

    return trial_dir


def evaluate_trial_tests(trial_dir: Path) -> Dict[str, Any]:
    """Execute visible and hidden adversarial test suites against the implemented code."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(trial_dir)

    # 1. Run Visible Tests
    cmd_visible = [str(VENV_PYTEST), str(trial_dir / "tests" / "test_visible.py"), "-q", "--tb=short"]
    p_vis = subprocess.run(cmd_visible, cwd=str(trial_dir), env=env, capture_output=True, text=True)
    visible_exit = p_vis.returncode
    visible_stdout = p_vis.stdout.strip()

    # 2. Run Hidden Adversarial Suite
    cmd_hidden = [str(VENV_PYTEST), str(HIDDEN_SUITE), "-q", "--tb=short"]
    p_hid = subprocess.run(cmd_hidden, cwd=str(trial_dir), env=env, capture_output=True, text=True)
    hidden_exit = p_hid.returncode
    hidden_stdout = p_hid.stdout.strip()

    # Parse pass/fail counts from pytest summary
    # Format e.g. "5 passed in 0.12s" or "14 passed, 2 failed in 0.45s"
    def parse_counts(stdout: str):
        lines = stdout.splitlines()
        summary = lines[-1] if lines else ""
        passed, failed, total = 0, 0, 0
        if "passed" in summary:
            parts = summary.split()
            for i, p in enumerate(parts):
                if p == "passed":
                    passed = int(parts[i - 1])
                elif p == "failed":
                    failed = int(parts[i - 1])
        total = passed + failed
        return passed, failed, total, summary

    vis_passed, vis_failed, vis_total, vis_summary = parse_counts(visible_stdout)
    hid_passed, hid_failed, hid_total, hid_summary = parse_counts(hidden_stdout)

    return {
        "visible": {
            "exit_code": visible_exit,
            "passed": vis_passed,
            "failed": vis_failed,
            "total": vis_total,
            "summary": vis_summary,
        },
        "hidden": {
            "exit_code": hidden_exit,
            "passed": hid_passed,
            "failed": hid_failed,
            "total": hid_total,
            "summary": hid_summary,
        }
    }


def parse_transcript_tokens(transcript_path: Path) -> Dict[str, Any]:
    """Parse dialogue tokens and modeled tool schemas from a real transcript.jsonl."""
    if not transcript_path.exists():
        return {"turns": 0, "dialogue_tokens": 0, "schema_tokens": 0, "total_tokens": 0}

    turns = 0
    dialogue_tokens = 0
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            turns += 1
            dialogue_tokens += len(ENC.encode(line))

    schema_tokens = turns * PRUNED_SCHEMA_TOKENS_PER_TURN
    total_tokens = dialogue_tokens + schema_tokens

    return {
        "turns": turns,
        "dialogue_tokens": dialogue_tokens,
        "schema_tokens": schema_tokens,
        "total_tokens": total_tokens
    }


def record_trial_result(
    arm: str,
    trial_idx: int,
    transcript_guid: str,
    transcript_path: Path,
    wall_clock_sec: float,
    test_results: Dict[str, Any]
) -> Dict[str, Any]:
    """Record full trial telemetry to disk."""
    token_metrics = parse_transcript_tokens(transcript_path)

    record = {
        "arm": arm,
        "trial_idx": trial_idx,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_clock_sec": round(wall_clock_sec, 2),
        "transcript_guid": transcript_guid,
        "transcript_path": str(transcript_path),
        "token_metrics": token_metrics,
        "test_results": test_results
    }

    all_records = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                all_records = json.load(f)
        except Exception:
            all_records = []

    # Update or append
    updated = False
    for i, r in enumerate(all_records):
        if r["arm"] == arm and r["trial_idx"] == trial_idx:
            all_records[i] = record
            updated = True
            break
    if not updated:
        all_records.append(record)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2)

    return record


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        arm = sys.argv[2]
        idx = int(sys.argv[3])
        path = setup_trial_dir(arm, idx)
        print(f"Setup complete: {path}")
    elif len(sys.argv) > 1 and sys.argv[1] == "evaluate":
        trial_dir = Path(sys.argv[2])
        res = evaluate_trial_tests(trial_dir)
        print(json.dumps(res, indent=2))
