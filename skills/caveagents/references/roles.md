# CaveAgents Role Specifications

This document defines the agent roles, tool allocations, and operating boundaries in CaveAgents architectures.

---

## 1. Captain (`cave_captain`)

- **Objective**: Session orchestration, task decomposition into a Directed Acyclic Graph (DAG), subagent definition and spawning, dependency resolution, and final quality sign-off.
- **Allowed Tools**:
  - `send_message`: Dispatches instructions to workers and receives final reports.
  - `run_command`: Used strictly for pre-flight environment checks or invoking test runners at DAG boundaries.
  - `view_file`: Read-only file inspection.
- **Forbidden Actions**:
  - Direct file editing (`write_to_file`, `replace_file_content`).
  - Engaging in verbose narrative summaries.
- **Terseness Mandate**: Strict bullet-point command syntax. Eliminates greetings and conversational scaffolding.

---

## 2. Worker (`cave_worker`)

- **Objective**: Focused, single-threaded execution of scoped modules. Directly builds code, writes unit tests, executes builds, and refactors components.
- **Allowed Tools (Pruned)**:
  - `run_command`: Running compilation, package installations, and test runners (`pytest`, `mypy`).
  - `write_to_file`: File creation.
  - `replace_file_content`: Precise chunk-based edits.
  - `view_file`: Reading implementation files.
  - `send_message`: P2P communication with peer workers or reporting completion back to Captain.
- **Pruned / Omitted Tools**:
  - Excludes unused web browsing, image generation, or heavy subagent orchestration tools (`search_web`, `read_url_content`, `generate_image`, `notebook_edit`).
  - Saves ~2,500 tokens per tool call cycle.

---

## 3. Verifier (`cave_verifier`)

- **Objective**: Independent quality validation gate. Ensures code meets strict TDD criteria, audits token overhead, checks lint/formatting, and prevents regressions.
- **Allowed Tools (Pruned)**:
  - `run_command`: Executing test harnesses (`pytest -q --tb=short`), linters (`ruff`, `flake8`), and benchmarks.
  - `view_file`: Inspecting test reports and diffs.
  - `send_message`: Emitting terse ACK or REJECT signals with line-numbered failure traces.
- **Gate Behavior**:
  - Zero-tolerance failure policy: Any failing assertion triggers immediate rejection back to the worker with specific trace context.
