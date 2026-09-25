# CaveAgents ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Framework: Google Antigravity](https://img.shields.io/badge/Framework-Google%20Antigravity-8b5cf6.svg)](https://github.com/sanad-source/cave-agents)
[![Tested On](https://img.shields.io/badge/Tested%20On-Antigravity%20(Gemini%203.8%20Flash)-f97316.svg)](docs/BENCHMARKS.md)
[![Token Reduction](https://img.shields.io/badge/Token%20Reduction-81.3%25%20vs%20Teamwork-22c55e.svg)](docs/BENCHMARKS.md)  
[![Inspired By](https://img.shields.io/badge/Inspired%20By-NanmiCoder%2Fdsh--agent--teams-800080.svg)](https://github.com/NanmiCoder/dsh-agent-teams)
[![CI](https://github.com/sanad-source/cave-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/sanad-source/cave-agents/actions/workflows/ci.yml)

## 📋 Summary

In multi-agent software engineering workflows, team coordination adds significant token overhead: in our benchmarks, multi-agent teams expended between **2.35x and 13.62x more tokens** than an identical pruned single-agent control (26,784 to 154,998 vs. 11,381 tokens), driven by inter-agent handoffs, duplicate context loading, and repeated tool schema declarations.

**CaveAgents** is an orchestration framework designed to minimize multi-agent coordination overhead through **dynamic tool registry pruning**, **strict context scoping**, and **direct peer-to-peer messaging**.

In empirical evaluations across two distinct software tiers:
- **Tier 1 (Micro Component, 91 LOC)**: CaveAgents v4 completes a full 3-agent TDD cycle (QA, Implementation, Code Review) in **26,784 estimated tokens**—an **81.3% reduction** compared to standard unpruned multi-agent workflows (143,219 tokens), but **2.35x more expensive** than an identical 5-tool pruned single-agent control (11,381 tokens).
- **Tier 2 (Medium Asynchronous Service, ~500 LOC, $n=10$ per Arm, $N=20$)**: Evaluated across 20 randomized trials with 16 held-out adversarial tests, CaveAgents v4 averaged **85,782 ± 11,462 tokens** vs. **27,824 ± 5,440 tokens** for the pruned monolith—demonstrating that the multi-agent coordination tax **widened from 2.35x to 3.08x (+208.3%)** rather than amortizing at medium scale. Wall-clock latency reached **exact parity** (155.5s vs 153.8s, 1.01x), while the team captured 1 edge cancellation bug (100% vs 99.4% held-out test pass rate).

> **Core Systems Finding**: On both micro-tasks and multi-file medium services, an optimized single agent remains significantly cheaper (2.35x–3.08x) because it pays zero inter-agent handoff, duplicate prompt ingestion, or supervisor routing overhead. Dynamic tool pruning benefits both single agents and teams equally. The central open frontier is **Tier 3 (Large Cross-Package Refactoring)**: determining whether the coordination tax continues widening, plateaus, or finally inverts when single-context reasoning capacity saturates.

---

## 📊 Benchmarks

### Tier 1 Results: Single Algorithmic Component (`TokenBucket`, 91 LOC, $n=1$)

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

### Tier 2 Multi-File Service Benchmark ($N=20$, $n=10$ per Arm)

We tested whether multi-agent teams amortize their overhead on a multi-file service (`taskflow`, 5 decoupled modules, ~500 LOC) across 20 automated trials ($n=10$ Pruned Monolith vs. $n=10$ CaveAgents v4) evaluated against 16 held-out adversarial tests:

| Architecture ($n=10$) | Mean Tokens ± SD | Multiple vs Control | Wall-Clock Latency | Hidden Adversarial Pass Rate | Flawless Runs |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Pruned Monolith Control** | **27,824 ± 5,440** | **1.00x** (Baseline) | **153.8s ± 30.6s** | 159 / 160 (99.38%) | 9 / 10 (90%) |
| **CaveAgents v4 Team** | **85,782 ± 11,462** | **3.08x** (+208.3%) | **155.5s ± 29.2s** | **160 / 160 (100.00%)** | **10 / 10 (100%)** |

<p align="center">
  <img src="assets/chart_tier2_benchmark.png" alt="Tier 2 Multi-File Service Benchmark: Pruned Monolith vs. CaveAgents v4" width="100%"/>
</p>

<p align="center">
  <img src="assets/chart_scaling_tiers.png" alt="Cross-Tier Coordination Tax Comparison" width="100%"/>
</p>

- **Did the team win on tokens?** **NO.** Monolith was **3.08x cheaper** (27.8k vs 85.8k tokens).
- **Did the team win on latency?** **NO.** Wall-clock execution was at **exact parity** (155.5s vs 153.8s, 1.01x).
- **Did the team win on defect avoidance?** **MARGINAL.** 100.0% vs 99.4% (v4 avoided 1 thread-level timeout cancellation defect caught in Monolith Trial 08).

See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for full trial records, token decompositions, and statistical distributions.

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
- [x] **Statistical Power ($n \ge 10$) & Tier 2 Medium Service Benchmark**: Completed $N=20$ trial empirical study ($n=10$ Pruned Monolith vs $n=10$ CaveAgents v4) on `taskflow` asynchronous multi-file service (~500 LOC across 5 modules). Monolith remained 3.08x cheaper (27.8k vs 85.8k tokens) at latency parity (153.8s vs 155.5s), while v4 team captured 1 marginal edge defect (100% vs 99.4% held-out test pass rate).
- [ ] **Native API Billing Telemetry**: Extract exact billed input, output, and cached token metadata directly from Gemini API response headers to evaluate prompt cache hits on schema tokens.
- [ ] **Tier 3 Large Cross-Package Refactoring Benchmark**: Test whether the coordination tax (2.35x at Tier 1, 3.08x at Tier 2) continues widening, plateaus at ~3x, or finally inverts when monolithic single context limits are saturated.
- [ ] **Independent Held-Out Mutation Testing**: Evaluate functional correctness against broader mutation coverage and security static analysis across diverse domains.

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
