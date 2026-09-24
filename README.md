# CaveAgents ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Framework: Any Agent](https://img.shields.io/badge/Framework-Any%20Agent-8b5cf6.svg)](https://github.com/sanad-source/cave-agents)
[![Tested On](https://img.shields.io/badge/Tested%20On-Antigravity%20(Gemini%203.8%20Flash)-f97316.svg)](docs/BENCHMARKS.md)
[![Token Savings](https://img.shields.io/badge/Token%20Savings-Up%20to%2087%25-22c55e.svg)](docs/BENCHMARKS.md)  
[![Inspired By](https://img.shields.io/badge/Inspired%20By-NanmiCoder%2Fdsh--agent--teams-800080.svg)](https://github.com/NanmiCoder/dsh-agent-teams)
[![Caveman Mode](https://img.shields.io/badge/Caveman-JuliusBrussee%2Fcaveman-181717.svg?logo=github)](https://github.com/JuliusBrussee/caveman)
[![Tests Passing](https://img.shields.io/badge/Tests-5%2F5%20Passing-10b981.svg)](tests/)

## 📋 Summary

Normally, using a team of AI agents uses 5x to 7x more tokens than a single agent because agents talk too much and reload huge tool lists on every turn.

**CaveAgents** lets you run teams of AI agents (QA, coder, reviewer) to write and test code together, but cuts out all the filler and removes unused tools. 

In **v4**, the entire team finishes the job in **26,784 tokens**—making the multi-agent team cheaper than even a single agent running alone (**30,241 tokens**).

### 🔥 TL;DR (Gen Z Edition)

> Regular multi-agent setups have massive negative aura fr fr—they yap 24/7 with polite pleasantries, shove entire tool catalogs into every turn, and run up a 7x token tab that is definitely not giving.  
>  
> **CaveAgents v4** locked in and dropped the ultimate glow up: zero yapping, strictly pruned tool drip via `define_subagent`, and direct P2P DMs so subagents don't spam the group chat. It hits the inverted cost frontier at **26.7k tokens**—literally mogging single-agent monoliths while keeping test-driven verification 100% no cap. Straight cooking.

---

## 📊 Benchmarks

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

<p align="center">
  <img src="assets/chart_inverted_cost_frontier.png" alt="CaveAgents Inverted Cost Frontier" width="100%"/>
</p>

<p align="center">
  <img src="assets/chart_scaling_turns.png" alt="Context Window Scaling Over Turns" width="100%"/>
</p>

Detailed dual-context accounting and token breakdowns are documented in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

---

## 🏛️ Architecture

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

### 💡 Core Ideas

1. **Dynamic Tool Registry Pruning**: Rather than injecting 15–20 tool schemas on every step (~2,500 tokens/turn), `define_subagent` registers only the exact 5 tools required by each worker. This saves ~2,100–2,500 tokens on every step turn.
2. **P2P Direct Messaging**: Workers coordinate directly without proxying chatter through the supervisor's context.
3. **ASD-STE100 Terseness**: Telegraphic communication eliminating all conversational filler and tool narration.
4. **Pre-Flight Bound Analysis**: File scopes and AST boundaries are calculated before worker execution begins.
5. **TDD Quality Gate**: Automated short-circuit test verification ensuring all changes pass with exit code 0.

For comprehensive architectural specifications, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 🧬 Versions

- **v1 (Serial Pipeline - 109,984 tokens)**: Combined Caveman prompting with serial agent handoffs. Centralized Captain routing created a relay bottleneck.
- **v2 (Clones + P2P - 91,432 tokens)**: Introduced concurrent worker clones and direct peer-to-peer messaging, eliminating Captain relay overhead.
- **v3 (Pre-Flight Bound - 50,395 tokens)**: Added pre-flight AST analysis and strict `inScope` context bounds to prevent speculative code exploration.
- **v4 (Pruned Tools + Inverted Cost Frontier - 26,784 tokens)**: Implemented Dynamic Tool Registry Pruning via `define_subagent` and compound test verifications, crossing the Inverted Cost Frontier.

Detailed changelogs are available in [docs/VERSIONS.md](docs/VERSIONS.md).

---

## 🚀 Quickstart

### 1. 📦 Install

Install the Python package locally in editable mode:

```bash
git clone https://github.com/sanad-source/cave-agents.git
cd cave-agents
pip install -e .
```

### 2. 💻 CLI

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

### 3. 🐍 Python SDK

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

## 🛠️ Install as a Skill

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

---

## 🙏 Credits

- **Caveman Mode**: Created by **[Julius Brussee](https://github.com/JuliusBrussee/caveman)** (*"why use many token when few token do trick"*).
- **AgentTeams**: Inspired by **[dsh-agent-teams](https://github.com/NanmiCoder/dsh-agent-teams)** task DAG orchestration.
