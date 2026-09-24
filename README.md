# CaveAgents ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Framework: Any Agent](https://img.shields.io/badge/Framework-Any%20Agent-8b5cf6.svg)](https://github.com/sanad-source/cave-agents)
[![Tested On](https://img.shields.io/badge/Tested%20On-Antigravity%20(Gemini%203.8%20Flash)-f97316.svg)](docs/BENCHMARKS.md)
[![Token Savings](https://img.shields.io/badge/Token%20Savings-Up%20to%2087%25-22c55e.svg)](docs/BENCHMARKS.md)  
[![Inspired By](https://img.shields.io/badge/Inspired%20By-NanmiCoder%2Fdsh--agent--teams-800080.svg)](https://github.com/NanmiCoder/dsh-agent-teams)
[![Caveman Mode](https://img.shields.io/badge/Caveman-JuliusBrussee%2Fcaveman-181717.svg?logo=github)](https://github.com/JuliusBrussee/caveman)
[![Tests Passing](https://img.shields.io/badge/Tests-5%2F5%20Passing-10b981.svg)](tests/)

## 📋 Summary

Multi-agent software engineering workflows typically incur an 80%–85% token penalty compared to single-agent execution. This overhead is driven by redundant tool schema re-injection on every turn, conversational pleasantries, and multi-agent coordination churn.

**CaveAgents** is an orchestration framework designed to minimize multi-agent coordination overhead through **dynamic tool registry pruning**, **strict context scoping**, and **direct peer-to-peer messaging**.

In benchmark evaluations on a Python rate-limiter task, CaveAgents v4 completes a full 3-agent TDD cycle (QA, Implementation, Code Review) in **26,784 tokens**—an **81.3% reduction** compared to standard unpruned multi-agent workflows (143,219 tokens).

> **Control Baseline Note**: On small tasks, an optimized single agent remains significantly cheaper (**16,285 tokens**, ~39% lower) because it pays zero coordination overhead. Tool pruning is a general-purpose optimization that benefits both single agents and teams; multi-agent architectures offer structural value primarily when task scale requires isolated context domains or parallel code generation.

---

## 📊 Benchmarks

The following empirical benchmark measures total token expenditure on an identical multi-file Python refactoring and verification task:

| Configuration / Architecture | Total Billed Tokens | vs Standard Mono | Multi-Agent Coordination | Description |
| :--- | :---: | :---: | :---: | :--- |
| **Caveman Mono** | **16,285** | -46.1% | None (1 Agent) | 🥇 Lowest absolute tokens (single terse agent) |
| **CaveAgents v4** | **26,784** | **-11.4%** | **3-Agent Team** | **🏆 Lowest multi-agent (Cheaper than Standard Mono)** |
| **Standard Mono** | 30,241 | Baseline | None (1 Agent) | Single agent (verbose baseline) |
| **CaveAgents v3** | 50,395 | +66.6% | 3-Agent Team | Pre-Flight bound execution strings |
| **CaveAgents v2** | 91,432 | +202.3% | 3-Agent Team | Cloned coders + direct P2P messaging |
| **CaveAgents v1** | 109,984 | +263.7% | 3-Agent Team | Serial pipeline with Caveman mode |
| **Standard Teamwork (Live)** | 143,219 | +373.6% | 3-Agent Team | Standard unpruned team collaboration |
| **AgentTeams** | 154,998 | +412.5% | 3-Agent Team | Structured DAG with full tool catalogs |

> **Experimental Control & Scope Note**:
> - **Multi-Agent Efficiency**: CaveAgents v4 reduces multi-agent coordination cost down to **26,784 tokens** (-81.3% vs Standard Teamwork at 143k tokens), reaching parity with an unpruned single agent (`30,241 tokens`).
> - **Monolith Parity on Small Tasks**: An optimized single agent (**16,285 tokens**) is still **~39% cheaper** than CaveAgents v4 on this micro-task because a single agent incurs zero multi-agent communication or handoff overhead.
> - **Control Baseline**: Tool pruning is an orthogonal lever. Applying tool pruning to a monolith would lower its cost even further. Teams become advantageous when tasks exceed a single context window or require parallel code generation across independent modules.

<p align="center">
  <img src="assets/chart_tokens.png" alt="CaveAgents Inverted Cost Frontier" width="100%"/>
</p>

Detailed transcript GUIDs and per-turn token breakdowns are documented in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

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

1. **Dynamic Tool Registry Pruning**: Rather than injecting 16 tool schemas on every step (~2,480 tokens/turn), `define_subagent` registers only the exact 5 tools required by each worker (~380 tokens/turn). This saves ~2,100 tokens on every step turn.
2. **P2P Direct Messaging**: Workers coordinate directly without proxying chatter through the supervisor's context.
3. **ASD-STE100 Terseness**: Telegraphic communication eliminating conversational filler.
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

## 🔬 Limitations & Threats to Validity

1. **Sample Size ($n=1$) & Task Scope**: The current benchmark reflects a single evaluation on an isolated micro-task (a 91-line Python rate limiter class). Variance from stochastic LLM sampling was not characterized across multi-trial distributions. On micro-tasks, monolithic execution inherently holds an advantage because coordination overhead cannot be amortized across file boundaries.
2. **Asymmetric Tool Baseline**: The Standard Monolith baseline operated with all 16 tools declared (~2,480 schema tokens/turn). Because dynamic tool pruning is orthogonal to team architecture, applying tool pruning to a monolith reduces its token usage even further (as shown by Caveman Mono at 16,285 tokens). The honest comparison is not "teams are cheaper than single agents," but rather "tool pruning enables multi-agent coordination with only modest overhead relative to an unoptimized single agent."
3. **Tokenizer Approximation vs. Billed Usage**: Token counts were measured offline using `tiktoken` (`cl100k_base`) on raw transcript text. This models OpenAI-equivalent token volume rather than exact Google Gemini API billing metadata, SentencePiece tokenization, or server-side prompt caching discounts.
4. **Held-Out Quality Evaluation**: Correctness was verified using a test suite authored by an agent in the same model family, without an independent, held-out benchmark suite (e.g., SWE-bench, HumanEval) or human code review. The reviewer subagent's defect-catch rate was not quantitatively isolated.
5. **Confounded Ablation (v1–v4)**: Historical versions varied prompt terseness, network topology, context scoping, and tool schemas concurrently. Empirical analysis shows that **Dynamic Tool Pruning accounts for ~80%–85% of total token reductions**, while ASD-STE100 output terseness contributes ~10%–15% (since output tokens comprise only ~12% of total expenditure).

---

## 🗺️ Future Work & Research Roadmap

- [ ] **Pruned-Tool Monolith Control**: Benchmark a single-agent monolith equipped with the exact same 5-tool pruned registry as the control.
- [ ] **Statistical Power ($n \ge 10$)**: Run 10+ randomized trials per arm across varying temperatures to establish confidence intervals and variance bounds.
- [ ] **Multi-Scale Task Evaluation**: Benchmark across 4 distinct task tiers:
  - *Tier 1 (Micro)*: Single-class algorithmic component (TokenBucket).
  - *Tier 2 (Medium)*: Multi-file service with database migrations and HTTP endpoints.
  - *Tier 3 (Large)*: Cross-package refactoring with extensive dependencies.
  - *Tier 4 (Heterogeneous)*: Full-stack application with frontend UI, backend API, and unit tests.
- [ ] **Native API Billing Telemetry**: Extract exact billed token metadata, cache read/write ratios, and latency directly from Gemini API response headers.
- [ ] **Independent Held-Out Testing**: Evaluate functional correctness against hidden test suites, mutation coverage, and security static analysis.

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
