# CaveAgents v4: Dynamic Tool Pruning & Inverted Cost Frontier

`CAVEAGENTS_V4` represents the state-of-the-art in ultra-efficient multi-agent systems, breaking through the **Inverted Cost Frontier** where multi-agent parallel execution consumes fewer total tokens than a single standard monolithic agent.

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
In standard agent frameworks, every step of an agent invocation injects JSON Schema definitions for every registered tool (often 12–20 tools, totaling 2,000–3,500 tokens per step).
In v4, subagents are dynamically instantiated with only the exact tools required for their role:
- Workers receive only `run_command`, `write_to_file`, `replace_file_content`, `view_file`, and `send_message`.
- Omitted: `generate_image`, `notebook_edit`, `read_url_content`, `search_web`, `schedule`, `manage_task`.
- **Direct Impact**: Saves ~2,500 tokens on every single step turn across all subagents.

### 2. Autonomous Local Inspection
Subagents perform targeted inspection of precise files and symbols rather than loading large context payloads into the initial prompt.

### 3. Compound Verification & Early Exit
Tests are structured with fast failing assertions (`--tb=short`, `-q`), avoiding lengthy error traceback generation in the context window.

### 4. The Inverted Cost Frontier
Standard dogma holds that multi-agent systems incur a heavy token tax (typically 5x–7x the cost of a single agent). CaveAgents v4 inverts this relationship:
- Standard Monolithic Agent: **30,241 tokens**
- CaveAgents v4 Multi-Agent Parallel: **26,784 tokens** (11.4% cheaper than monolithic)
- Reduction vs Teamwork (208,555 tokens): **87.2% reduction**
