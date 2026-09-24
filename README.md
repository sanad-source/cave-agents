# CaveAgents

## Executive Summary

Traditional multi-agent orchestration frameworks impose a heavy **Multi-Agent Token Tax**—routinely incurring a 5x–7x token penalty compared to single-agent workflows. This overhead is driven by redundant conversational fluff, bloated tool schema declarations injected on every turn, and unconstrained context window replication.

**CaveAgents** solves this by unifying macro-level Directed Acyclic Graph (DAG) task orchestration with micro-level ASD-STE100 terseness and **Dynamic Tool Registry Pruning**. In its latest iteration (**v4**), CaveAgents crosses the **Inverted Cost Frontier**: achieving full parallel multi-agent decomposition and automated TDD quality gates at **26,784 tokens**—consuming fewer tokens than a standard monolithic single-agent baseline (**30,241 tokens**).

---

## Benchmark & Empirical Results

The following empirical benchmark measures total token expenditure on an identical multi-file Python refactoring and verification task:

| Configuration / Architecture | Total Tokens | vs Teamwork Baseline | vs Standard Monolithic | Description |
| :--- | :---: | :---: | :---: | :--- |
| **Teamwork** | 208,555 | Baseline (0.0%) | +589.6% | Unconstrained conversational star-mesh |
| **AgentTeams** | 154,998 | -25.7% | +412.5% | Structured DAG with full tool catalogs |
| **CaveAgents v1** | 109,984 | -47.3% | +263.7% | Serial pipeline + ASD-STE100 terseness |
| **CaveAgents v2** | 91,432 | -56.2% | +202.3% | Parallel worker clones + direct P2P messaging |
| **CaveAgents v3** | 50,395 | -75.8% | +66.6% | Pre-Flight Bound context injection |
| **Standard Mono** | 30,241 | -85.5% | Baseline | Single monolithic agent (standard instructions) |
| **CaveAgents v4** | **26,784** | **-87.2%** | **-11.4%** | **Dynamic Tool Pruning + Inverted Cost Frontier** |
| **Caveman Mono** | 16,285 | -92.2% | -46.1% | Single monolithic agent (Caveman mode) |

Detailed dual-context accounting and token breakdowns are documented in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

---

## Architecture

CaveAgents couples a supervisory DAG orchestrator (`cave_captain`) with autonomous implementers (`cave_worker`) communicating via direct peer-to-peer (P2P) wire messages, bounded by an automated verification gate (`cave_verifier`).

```mermaid
graph TD
    Client([Client Request]) --> Captain[Cave Captain: DAG Planner]

    subgraph OrchestrationLayer [Supervisory DAG Scheduling]
        Captain -->|define_subagent: PRUNED TOOLS| Worker1[Cave Worker 1: Engine]
        Captain -->|define_subagent: PRUNED TOOLS| Worker2[Cave Worker 2: API & Tests]
    end

    subgraph PeerToPeer [P2P Compact Wire Protocol]
        Worker1 <-->|Compact JSON Wire Comms| Worker2
    end

    subgraph QualityGate [TDD Quality Gate]
        Worker1 --> Verifier[Cave Verifier Gate]
        Worker2 --> Verifier
        Verifier -->|Exit Code 0 Signoff| Captain
    end

    Captain --> Client
```

### Key Pillars

1. **Dynamic Tool Registry Pruning**: Rather than injecting 15–20 tool schemas on every step (~2,500 tokens/turn), `define_subagent` registers only the exact 5 tools required by each worker. This saves ~2,100–2,500 tokens on every step turn.
2. **P2P Direct Messaging**: Workers coordinate directly without proxying chatter through the supervisor's context.
3. **ASD-STE100 Terseness**: Telegraphic communication eliminating all conversational filler and tool narration.
4. **Pre-Flight Bound Analysis**: File scopes and AST boundaries are calculated before worker execution begins.
5. **TDD Quality Gate**: Automated short-circuit test verification ensuring all changes pass with exit code 0.

For comprehensive architectural specifications, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Evolution: v1 to v4

- **v1 (Serial Pipeline - 109,984 tokens)**: Combined Caveman prompting with serial agent handoffs. Centralized Captain routing created a relay bottleneck.
- **v2 (Clones + P2P - 91,432 tokens)**: Introduced concurrent worker clones and direct peer-to-peer messaging, eliminating Captain relay overhead.
- **v3 (Pre-Flight Bound - 50,395 tokens)**: Added pre-flight AST analysis and strict `inScope` context bounds to prevent speculative code exploration.
- **v4 (Pruned Tools + Inverted Cost Frontier - 26,784 tokens)**: Implemented Dynamic Tool Registry Pruning via `define_subagent` and compound test verifications, crossing the Inverted Cost Frontier.

Detailed changelogs are available in [docs/VERSIONS.md](docs/VERSIONS.md).

---

## Quickstart

### 1. Installation

Install the Python package locally in editable mode:

```bash
git clone https://github.com/sanad-source/cave-agents.git
cd cave-agents
pip install -e .
```

### 2. CLI Usage

Display the empirical benchmark table:

```bash
caveagents benchmarks
```

Evaluate execution token usage from a transcript:

```bash
caveagents evaluate path/to/transcript.json
```

Validate a communication message against Caveman terseness rules:

```bash
caveagents validate "TASK: Refactor protocol.py. Run pytest tests/."
```

### 3. Python SDK

```python
from caveagents import CaveMessage, CostEvaluator, format_cave_message

# Build compact wire message
wire_msg = format_cave_message(
    sender="worker_core",
    recipient="worker_test",
    action="SYNC",
    payload={"interface": "evaluate", "status": "ready"}
)

# Evaluate token efficiency
evaluator = CostEvaluator()
summary = evaluator.compare_benchmarks(26784)
print(summary)
```

---

## Skill Installation Instructions

To install and enable CaveAgents as a persistent agent skill:

1. Copy the skill directory into your local skill repository:
   ```bash
   mkdir -p ~/.gemini/antigravity/skills
   cp -r skills/caveagents ~/.gemini/antigravity/skills/
   ```

2. Invoke the skill in any session prompt:
   ```text
   Activate CaveAgents v4 mode for this workspace.
   ```

See [skills/caveagents/SKILL.md](skills/caveagents/SKILL.md) and [skills/caveagents/references/roles.md](skills/caveagents/references/roles.md) for full configuration directives.
