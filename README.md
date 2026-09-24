# CaveAgents ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Framework: Google Antigravity](https://img.shields.io/badge/Framework-Google%20Antigravity-8b5cf6.svg)](https://github.com/sanad-source/cave-agents)
[![Tested On](https://img.shields.io/badge/Tested%20On-Antigravity%20(Gemini%203.8%20Flash)-f97316.svg)](docs/BENCHMARKS.md)
[![Token Reduction](https://img.shields.io/badge/Token%20Reduction-81.3%25%20vs%20Teamwork-22c55e.svg)](docs/BENCHMARKS.md)  
[![Inspired By](https://img.shields.io/badge/Inspired%20By-NanmiCoder%2Fdsh--agent--teams-800080.svg)](https://github.com/NanmiCoder/dsh-agent-teams)
[![CI](https://github.com/sanad-source/cave-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/sanad-source/cave-agents/actions/workflows/ci.yml)

## 📋 Summary

In multi-agent software engineering workflows, team coordination adds significant token overhead: in our benchmark, multi-agent teams expended between 2.35x and 13.62x more tokens than a pruned single-agent control (26,784 to 154,998 vs. 11,381 tokens), driven by inter-agent handoffs, duplicated context loading, and repeated tool schema declarations.

**CaveAgents** is an orchestration framework designed to minimize multi-agent coordination overhead through **dynamic tool registry pruning**, **strict context scoping**, and **direct peer-to-peer messaging**.

In benchmark evaluations on a Python rate-limiter task (`TokenBucket`), CaveAgents v4 completes a full 3-agent TDD cycle (QA, Implementation, Code Review) in **26,784 estimated tokens**—an **81.3% reduction** compared to standard unpruned multi-agent workflows (143,219 tokens).

> **Control Baseline Note**: On small tasks, an optimized single agent remains significantly cheaper (**11,381 tokens** with pruned tools, 2.35x cheaper than CaveAgents v4) because it pays zero coordination overhead. Tool pruning benefits both single agents and teams; multi-agent architectures offer structural value primarily when task scale requires isolated context domains or parallel code generation.

---

## 📊 Benchmarks

The following empirical benchmark measures estimated total token expenditure on an identical Python rate limiter class with concurrency test suite (`TokenBucket`):

| Configuration / Architecture | Estimated Total Tokens | Cost vs Pruned Control (1.00x) | Multi-Agent Coordination | Hidden Tests | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Pruned Mono (Control)** | **11,381** | **1.00x** (Baseline) | None (1 Agent, 5 Tools) | **7/7 (100%)** | 🥇 Lowest absolute tokens (single pruned agent) |
| **Caveman Mono** | **16,285** | **1.43x** (+43.1%) | None (1 Agent, 16 Tools) | **7/7 (100%)** | 🥈 Terse prompting baseline |
| **CaveAgents v4** | **26,784** | **2.35x** (+135.3%) | **3-Agent Team (5 Tools)** | **7/7 (100%)** | Optimized multi-agent team (-81.3% vs Teamwork) |
| **Standard Mono** | 30,241 | 2.66x (+165.7%) | None (1 Agent, 16 Tools) | Not tested | Single agent (verbose baseline) |
| **CaveAgents v3** | 50,395 | 4.43x (+342.8%) | 3-Agent Team (16 Tools) | Not tested | Pre-Flight bound execution strings |
| **CaveAgents v2** | 91,432 | 8.03x (+703.4%) | 3-Agent Team (16 Tools) | Not tested | Cloned coders + direct P2P messaging |
| **CaveAgents v1** | 109,984 | 9.66x (+866.4%) | 3-Agent Team (16 Tools) | Not tested | Serial pipeline with Caveman mode |
| **Standard Teamwork (Live)** | 143,219 | 12.58x (+1,158.4%) | 3-Agent Team (16 Tools) | 5/7 (Failed) | Standard unpruned team collaboration |
| **AgentTeams** | 154,998 | 13.62x (+1,261.9%) | 3-Agent Team (16 Tools) | Not tested | Structured DAG with full tool catalogs |

> **Experimental Control & Scope Note**:
> - **Multi-Agent Optimization**: CaveAgents v4 reduces multi-agent coordination cost down to **26,784 tokens** (-81.3% vs Standard Teamwork at 143k tokens), bringing a 3-agent TDD team down to 2.35x of the pruned single agent control.
> - **The Control Baseline & The Inversion Artifact**: The earlier apparent "Inverted Cost Frontier" was an artifact of a verbose, unpruned baseline (Standard Mono at 30,241 tokens). Caveman Mono (which also carried all 16 tools) was already cheaper at 16,285 tokens. When evaluated under the identical 5-tool pruned registry (**Pruned Mono Control**), the single agent finished in **11,381 tokens**—**2.35x cheaper than CaveAgents v4**. Single agents pay zero handoff or supervisor overhead.
> - **When Teams Matter**: Multi-agent teams provide structural value when problems exceed a single model's context window, require independent role separation, or allow parallel code generation across decoupled submodules.

<p align="center">
  <img src="assets/chart_tokens.png" alt="CaveAgents Benchmark Comparison" width="100%"/>
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
- **v2 (Clones + P2P - 91,432 tokens)**: Introduced worker clones with direct peer-to-peer messaging (which executed serially on this single-file task), eliminating Captain relay overhead.
- **v3 (Pre-Flight Bound - 50,395 tokens)**: Added pre-flight AST analysis and strict `inScope` context bounds to prevent speculative code exploration.
- **v4 (Dynamic Tool Registry Pruning - 26,784 tokens)**: Implemented Dynamic Tool Registry Pruning via `define_subagent`, surgical symbol lookups, and bounded test verifications, reducing multi-agent overhead by 81.3% vs standard teamwork.

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

1. **Accounting Assumptions & Directional Bias of Modeled Totals**: Reported token counts are modeled estimates rather than native API billing telemetry. They combine dialogue tokens (measured offline via `tiktoken cl100k_base` on transcript steps) with fixed modeled tool schema constants (~2,480 tokens/turn for 16 tools, ~380 tokens/turn for 5 tools). Cumulative conversational history re-sent on successive turns is estimated rather than extracted from live provider billing headers.
   - *Directionality of Estimation Error*: The direction of this error matters structurally. A monolithic agent carries a single growing context window re-billed on every step, whereas a team splits execution across shorter, fresher subagent contexts. If re-sent cumulative history is under-counted by offline step parsing, the monolith is likely under-counted to a greater degree than the team. Consequently, the 2.35x control gap on this single-component task may be overstated for workflows requiring deep turn depth, and the crossover point where multi-agent teams become cost-competitive may arrive earlier than these static estimates suggest. Definitive verification requires native API billing telemetry.
2. **Measured Pruned Monolith Control Gap (2.35x)**: When the single agent was evaluated with the identical 5-tool pruned registry (**Pruned Mono Control**), it completed the task in 10 steps and **11,381 tokens**—**2.35x cheaper than CaveAgents v4** (26,784 tokens). This demonstrates that on a single-file micro-task, an optimized single agent remains significantly more efficient than a multi-agent team because it pays zero coordination or handoff tax. The earlier apparent "Inverted Cost Frontier" was an artifact of a verbose, unpruned baseline: Standard Mono was burdened by both a verbose prompt and 16 unused tools, whereas Caveman Mono (which also carried all 16 tools) already beat v4 at 16,285 tokens.
3. **Prompt Caching Economics**: In real-world API billing, static tool schemas reside in the system prompt prefix and are subject to server-side prompt caching (typically billed at a 75%–80% discount for cache hits in Google Gemini and Anthropic). Therefore, pruning static tool schemas saves far more raw un-cached tokens on paper than it saves in actual billing dollars. While this does not alter the relative ratio between team and mono architectures, it means the dollar savings from tool pruning are smaller than raw token counts imply.
4. **Sample Size ($n=1$) & Micro-Task Scope**: The current benchmark reflects a single evaluation on an isolated micro-task (a 91-line Python rate limiter class). Variance from stochastic LLM sampling was not characterized across multi-trial distributions.
5. **Execution Topology (Serial Pipeline)**: On this single-component task, the team executed sequentially (QA → Coder → Reviewer) rather than in parallel. Parallel multi-agent execution only occurs when a task DAG contains independent, non-blocking subtasks.
6. **Post-Hoc Adversarial Test Harness & Reviewer Efficacy**: The 7 adversarial tests (`test_hidden_correctness.py`) were authored post-hoc by the benchmark evaluator using the same model family (Gemini Flash). The test categories (boolean rejection, NaN/Inf bounds, concurrent race conditions, capacity ceilings) overlap heavily with the requirements specified in the QA prompt. While Pruned Mono (7/7), Caveman Mono (7/7), and CaveAgents v4 (7/7) passed, and Standard Teamwork failed 2/7, this is an n=1 observation. It does not statistically separate the top three configurations, nor does it prove that multi-agent teams systematically write worse code. Crucially, the reviewer subagent's independent defect-catch rate was not quantitatively isolated, which remains the primary theoretical justification for multi-agent teams.
7. **Architecture Transitions & Confounded Variables**: Transitions between versions must not be interpreted as clean single-variable parameter sweeps:
   - *Prompt Terseness on Monolith*: Standard Mono (30,241, verbose, 16 tools) → Caveman Mono (16,285, terse, 16 tools) = **~46% reduction** from concise prompting contracts.
   - *Tool Pruning on Monolith*: Caveman Mono (16,285, terse, 16 tools) → Pruned Mono Control (11,381, terse, 5 tools) = **~30% reduction**. Note that Pruned Mono took 10 steps versus ~6 steps for Caveman Mono, so this difference sits within run-to-run stochastic variance at n=1.
   - *Compound Optimization on Teams*: CaveAgents v3 (50,395, terse, 16 tools) → CaveAgents v4 (26,784, terse, 5 tools) = **~47% reduction**. Note that v4 introduced autonomous inspection and compound verifications alongside tool pruning, so this represents a compound version transition rather than an isolated tool-pruning sweep.
   - *Aggregate Multi-Agent Reduction*: Standard Teamwork (143,219, verbose, 16 tools) → CaveAgents v4 (26,784, terse, 5 tools) = **~81% reduction**, compounding tool pruning, telegraphic wire communications, and strict pre-flight scope bounds.

---

## 🗺️ Future Work & Research Roadmap

- [x] **Pruned-Tool Monolith Control**: Benchmarked single-agent monolith with identical 5-tool pruned registry (**11,381 tokens**, 2.35x cheaper than v4 team).
- [ ] **Native API Billing Telemetry**: Extract exact billed input, output, and cached token metadata directly from Gemini API response headers.
- [ ] **Statistical Power ($n \ge 10$)**: Run 10+ randomized trials per arm across varying temperatures to establish confidence intervals and variance bounds.
- [ ] **Multi-Scale Task Evaluation**: Benchmark across 4 distinct task tiers:
  - *Tier 1 (Micro)*: Single-class algorithmic component (TokenBucket).
  - *Tier 2 (Medium)*: Multi-file service with database migrations and HTTP endpoints.
  - *Tier 3 (Large)*: Cross-package refactoring with extensive dependencies.
  - *Tier 4 (Heterogeneous)*: Full-stack application with frontend UI, backend API, and unit tests.
- [ ] **Independent Held-Out Testing**: Evaluate functional correctness against hidden test suites, mutation coverage, and security static analysis to measure if the reviewer stage catches real defects across broader domains.

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
