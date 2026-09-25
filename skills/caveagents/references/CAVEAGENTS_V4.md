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

## Core Mechanisms

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

Multi-agent coordination introduces substantial token overhead compared to single-agent execution: in our benchmarks, standard teamwork incurred 12.58x the token cost of a pruned single-agent control. CaveAgents v4 significantly reduces this multi-agent overhead through tool pruning and telegraphic messaging, but single-agent monoliths remain structurally cheaper across evaluated scales:

#### Tier 1: Single Algorithmic Component (`TokenBucket`, 91 LOC, $n=1$)
- **Standard Teamwork** (Live 3-Agent Run, 16 Tools): **143,219 tokens** (12.58x Control)
- **CaveAgents v4 Team** (Live 3-Agent Sequential TDD Run, 5 Tools): **26,784 tokens** (2.35x Control; 81.3% reduction vs Standard Teamwork)
- **Standard Monolith** (Verbose Baseline, 16 Tools): **30,241 tokens** (2.66x Control)
- **Caveman Monolith** (Terse Baseline, 16 Tools): **16,285 tokens** (1.43x Control)
- **Pruned Monolith Control** (Terse Control, 5 Tools): **11,381 tokens** (1.00x Control Baseline)

#### Tier 2: Multi-File Asynchronous Service (`taskflow`, ~500 LOC, $n=10$ per Arm, $N=20$)
- **Pruned Monolith Control ($n=10$)**: **27,824 ± 5,440 tokens** (1.00x Baseline), 153.8s ± 30.6s latency, 159/160 hidden tests passed (99.38%).
- **CaveAgents v4-lite Team ($n=10$)**: **85,782 ± 11,462 tokens** (3.08x Control, +208.3%), 155.5s ± 29.2s latency, 160/160 hidden tests passed (100.00%).
- **Expenditure Decomposition**: Foundation worker consumed 29,722 tokens (exceeding the entire monolith), while Executor worker consumed 56,059 tokens.

> **Key Takeaway & Architecture Distinction**:
> 1. **Minimal Team Shape, Maximum Tax**: Tier 2 evaluated a stripped-down 2-worker variant (**CaveAgents v4-lite**: Foundation → Executor, no review gate). Even this cheapest possible team shape costs **3.08x tokens (+208.3%)** for zero demonstrated benefit on this task.
> 2. **Latency Parity is Functional Serialization**: Concurrent worker dispatch achieved exact wall-clock parity (155.5s vs 153.8s, 1.01x) because Executor was blocked polling the filesystem for Foundation models, eliminating parallel acceleration.
> 3. **Defect Signal**: The 160/160 vs 159/160 pass rate was a single timeout cancellation failure in Trial 08, which sits within stochastic noise rather than proving systematic superiority.
> 4. **Untested Mechanisms**: Genuine parallel speedups (on fully independent modules) and adversarial review efficacy (with a dedicated reviewer stage) remain the two empirical hypotheses to test going forward.

