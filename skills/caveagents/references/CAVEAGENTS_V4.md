# CaveAgents v4: Dynamic Tool Registry Pruning & Bounded TDD

`CAVEAGENTS_V4` minimizes multi-agent overhead through dynamic tool schema pruning, strict context scoping, and direct peer-to-peer messaging—reducing multi-agent token expenditure by 81.3% compared to standard teamwork (26,784 vs 143,219 tokens).

---

## Architecture Overview

```mermaid
graph TD
    User([Task Specification]) --> Captain[Cave Captain DAG Planner]
    Captain -->|define_subagent: PRUNED TOOLS| W1[Worker 1: Core Engine]
    Captain -->|define_subagent: PRUNED TOOLS| W2[Worker 2: Test Harness]
    W1 <-->|P2P Compact Wire Comms| W2
    W1 --> VGate[Verifier Quality Gate: Short-Circuit TDD]
    W2 --> VGate
    VGate -->|Exit 0 Verification| Captain
    Captain --> User
```

## Core Breakthroughs

### 1. Dynamic Tool Registry Pruning
In standard agent frameworks, every step of an agent invocation injects JSON Schema definitions for every registered tool (the default Antigravity environment registers 16 tools, totaling ~2,480 tokens per step).
In v4, subagents are dynamically instantiated with only the exact tools required for their role:
- Workers receive only `run_command`, `write_to_file`, `replace_file_content`, `view_file`, and `send_message`.
- Omitted: `generate_image`, `notebook_edit`, `read_url_content`, `search_web`, `schedule`, `manage_task`, etc.
- **Direct Impact**: Reduces per-turn tool schema overhead from ~2,480 down to ~380 tokens, saving ~2,100 tokens on every single step turn across all subagents.

### 2. Autonomous Local Inspection
Subagents perform targeted inspection of precise files and symbols rather than loading large context payloads into the initial prompt.

### 3. Compound Verification & Early Exit
Tests are structured with fast failing assertions (`--tb=short`, `-q`), avoiding lengthy error traceback generation in the context window.

### 4. Multi-Agent Optimization vs. Single-Agent Control
Standard dogma holds that multi-agent systems incur a heavy token tax (typically 5x–7x the cost of a single agent). CaveAgents v4 significantly reduces this overhead:
- Standard Teamwork (Live 3-Agent Run, 16 Tools): **143,219 tokens**
- CaveAgents v4 Multi-Agent (Live 3-Agent Sequential TDD Run, 5 Tools): **26,784 tokens** (81.3% reduction vs Standard Teamwork)
- Standard Monolith (Verbose Baseline, 16 Tools): **30,241 tokens** (v4 is 11.4% cheaper)
- Caveman Monolith (Terse Baseline, 16 Tools): **16,285 tokens** (39.2% cheaper than v4)
- Pruned Monolith Control (Terse Control, 5 Tools): **11,381 tokens** (2.35x cheaper than v4)

> **Key Takeaway**: The apparent "Inverted Cost Frontier" vs Standard Mono was an artifact of comparing an unpruned monolith (16 tools) against a pruned team (5 tools). Under rigorous experimental control with identical 5-tool registries, a single agent is 2.35x cheaper on micro-tasks because it pays zero coordination or handoff tax. Multi-agent teams provide architectural value primarily when problems exceed a single context window or require parallel code generation across decoupled submodules.
