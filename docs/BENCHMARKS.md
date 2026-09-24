# Benchmarks

## Overview

This document presents empirical results and benchmark evaluation data measuring total token usage across multiple agent frameworks and configurations performing an identical Python rate limiter implementation and concurrency test task (`TokenBucket`).

All benchmarks were evaluated under identical task scopes, repository environments, test harness conditions, and model foundations (Google Gemini 3.8 Flash, with offline `tiktoken cl100k_base` accounting).

---

## Results Table

| Architecture / Framework | Real Transcript / Run GUID | Input Tokens | Output Tokens | Estimated Total Tokens | Multiple vs Pruned Control (1.00x) | Multi-Agent Coordination | Hidden Tests (Held-Out) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Pruned Mono (Control)** | `b9942f2c-a8a9-4f48-ae0c-687a832c1d6e` | 9,281 | 2,100 | **11,381** | **1.00x** (Baseline) | None (1 Agent, 5 Tools) | **7/7 Passed** (100%) |
| **Caveman Mono** | `9a1b3ca8-9267-4169-a201-3f9f1434aed5` | 13,905 | 2,380 | **16,285** | **1.43x** (+43.1%) | None (1 Agent, 16 Tools) | **7/7 Passed** (100%) |
| **CaveAgents v4** | `6a8c617e / 611f72cc / bc6206fb` | 23,384 | 3,400 | **26,784** | **2.35x** (+135.3%) | **3-Agent Team (5 Tools)** | **7/7 Passed** (100%) |
| **Standard Mono** | `8e45e081-55f1-433a-8900-cdafb7afb923` | 25,669 | 4,572 | **30,241** | 2.66x (+165.7%) | None (1 Agent, 16 Tools) | Not evaluated |
| **CaveAgents v3** | `1af678ac / b3c9b503 / efe5c647` | 46,000 | 4,395 | **50,395** | 4.43x (+342.8%) | 3-Agent Team (16 Tools) | Not evaluated |
| **CaveAgents v2** | `ee34719a / e96f0467 / ea071eb7` | 85,760 | 5,672 | **91,432** | 8.03x (+703.4%) | 3-Agent Team (16 Tools) | Not evaluated |
| **CaveAgents v1** | `06c2eb6b / 9e765fdd / d49c842a` | 102,240 | 7,744 | **109,984** | 9.66x (+866.4%) | 3-Agent Team (16 Tools) | Not evaluated |
| **Standard Teamwork (Live)** | `22a1996f / 9b3dbf3b / a4ab4fcb` | 132,366 | 10,853 | **143,219** | 12.58x (+1,158.4%) | 3-Agent Team (16 Tools) | 5/7 Passed (2 Failed) |
| **AgentTeams** | `0fa36434 / b39f54d0 / f21c2b4e` | 146,117 | 8,881 | **154,998** | 13.62x (+1,261.9%) | 3-Agent Team (16 Tools) | Not evaluated |

*(Note: Prior unconstrained theoretical projections estimated Teamwork at 208,555 tokens; this live measured run confirms 143,219 tokens on the TokenBucket task).*

---

## Token Breakdown

In multi-agent systems, token consumption is divided into two primary categories:
1. **Tool Declaration Schema Tokens**: The fixed cost incurred on every turn by providing the model with JSON tool schemas.
2. **Message / Dialogue Context Tokens**: The variable cost of agent reasoning, conversation turns, file content, and terminal outputs.

### Per-Turn Token Expenditure Analysis

| Configuration | Tools Declared Per Turn | Schema Tokens / Turn | Dialogue Tokens / Turn | Average Step Cost |
| :--- | :---: | :---: | :---: | :---: |
| **Teamwork** | 18 tools | ~2,850 tokens | ~4,500 tokens | ~7,350 tokens |
| **AgentTeams** | 16 tools | ~2,480 tokens | ~3,100 tokens | ~5,580 tokens |
| **CaveAgents v2** | 16 tools | ~2,480 tokens | ~820 tokens | ~3,300 tokens |
| **CaveAgents v3** | 16 tools | ~2,480 tokens | ~450 tokens | ~2,930 tokens |
| **Standard Mono** | 16 tools | ~2,480 tokens | ~950 tokens | ~3,430 tokens |
| **Caveman Mono** | 16 tools | ~2,480 tokens | ~350 tokens | ~2,830 tokens |
| **CaveAgents v4** | **5 tools (pruned)** | **~380 tokens** | **~360 tokens** | **~740 tokens** |
| **Pruned Mono (Control)** | **5 tools (pruned)** | **~380 tokens** | **~750 tokens** | **~1,130 tokens** |

Notice how Dynamic Tool Pruning (`define_subagent`) slashes the fixed schema declaration cost from ~2,480 tokens down to ~380 tokens per turn, saving over 2,100 tokens on every single tool execution step for both single agents and multi-agent teams.

---

## The Inverted Cost Frontier: Empirical Deconstruction

In traditional multi-agent orchestration, multi-agent overhead was taken as an unavoidable cost of modularity:

$$\text{Cost}(\text{Multi-Agent}) \gg \text{Cost}(\text{Monolithic})$$

Comparing CaveAgents v4 against the standard unpruned monolith gave the earlier appearance of an "Inverted Cost Frontier":

$$\text{Cost}(\text{CaveAgents v4}) = 26{,}784 < 30{,}241 = \text{Cost}(\text{Standard Mono})$$

### Crucial Baseline Caveat & Experimental Ground Truth
However, strict experimental control reveals that **this earlier inversion was an artifact of a verbose, unpruned baseline**:
1. **The Role of Prompt Verbosity**: Standard Mono (30,241 tokens) was burdened by both a verbose prompting contract and 16 unused tool schemas. Caveman Mono (which also carried all 16 tools) already completed the task in **16,285 tokens** (1.43x of control)—39% cheaper than CaveAgents v4.
2. **Pruned Monolith Control (11,381 tokens)**: When the single agent is tested under the exact same 5-tool pruned registry, it finishes the task in **10 steps and 11,381 tokens** (1.00x Control Baseline), passing 7/7 on the independent held-out adversarial test suite.
3. **The 2.35x Multi-Agent Tax**: On this small single-component task, CaveAgents v4 (26,784 tokens) is **2.35x more expensive** than the Pruned Monolith Control (+15,403 tokens). Single agents pay zero handoff, duplicate context loading, or supervisor routing overhead.
4. **Quality vs. Overhead**: While both the Pruned Monolith and CaveAgents v4 achieved 100% correctness (7/7) on the held-out test suite (outperforming Standard Teamwork which failed 2 tests), the 3-agent team paid 135% coordination overhead without increasing correctness on a single-file module.

### Core Systems Principles
1. **Comparing Architecture Transitions**: The levers must be evaluated with experimental context:
   - *Prompt Terseness on Monolith*: Standard Mono (30,241, verbose, 16 tools) → Caveman Mono (16,285, terse, 16 tools) = **~46% reduction** from concise prompting contracts.
   - *Tool Pruning on Monolith*: Caveman Mono (16,285, terse, 16 tools) → Pruned Mono Control (11,381, terse, 5 tools) = **~30% reduction**. Note that Pruned Mono took 10 steps versus ~6 steps for Caveman Mono, so this difference sits within run-to-run stochastic variance at n=1.
   - *Compound Optimization on Teams*: CaveAgents v3 (50,395, terse, 16 tools) → CaveAgents v4 (26,784, terse, 5 tools) = **~47% reduction**. Note that v4 introduced autonomous inspection and compound verifications alongside tool pruning, so this represents a compound version transition rather than an isolated tool-pruning sweep.
   - *Aggregate Multi-Agent Reduction*: Standard Teamwork (143,219, verbose, 16 tools) → CaveAgents v4 (26,784, terse, 5 tools) = **~81% reduction**, compounding tool pruning, telegraphic wire communications, and strict pre-flight scope bounds.
2. **Coordination Overhead on Small Tasks**: On micro-tasks (like a 91-line rate limiter), single agents have zero inter-agent handoffs, zero duplicate context loading, and zero supervisor routing. Multi-agent teams only amortize this overhead when tasks exceed a single context window or require parallel code generation across decoupled submodules.
3. **Prompt Caching Economics**: In real-world API billing, static tool schemas reside in the system prompt prefix and are subject to server-side prompt caching (typically billed at a 75%–80% discount for cache hits in Gemini and Anthropic). Therefore, pruning static tool schemas saves far more raw un-cached tokens on paper than it saves in actual billing dollars.

---

## 🔬 Limitations & Threats to Validity

1. **Offline Modeled & Measured Accounting**: Reported token totals are modeled estimates rather than native API billing telemetry. They combine dialogue tokens (measured offline via `tiktoken cl100k_base` on transcript steps) with fixed modeled tool schema constants (~2,480 tokens/turn for 16 tools, ~380 tokens/turn for 5 tools). Cumulative conversational history re-sent on successive turns is estimated rather than extracted from live provider billing headers. Real-world API response telemetry is required for definitive billing verification.
2. **Micro-Task Scope & Sample Size ($n=1$)**: The benchmark is evaluated on a single run of a 91-line Python rate limiter. Model sampling variance was not statistically bounded across multiple random seeds.
3. **Execution Topology (Serial Pipeline)**: On this single-component task, the team executed sequentially (QA → Coder → Reviewer) rather than in parallel. Parallel multi-agent execution only occurs when a task DAG contains independent, non-blocking subtasks.
4. **Post-Hoc Adversarial Test Harness & Reviewer Efficacy**: The 7 adversarial tests in `test_hidden_correctness.py` were authored post-hoc by the benchmark evaluator using the same model family (Gemini Flash). The test categories (boolean rejection, NaN/Inf bounds, concurrent race conditions, capacity ceilings) overlap heavily with the requirements specified in the QA prompt. While Pruned Mono (7/7), Caveman Mono (7/7), and CaveAgents v4 (7/7) passed, and Standard Teamwork failed 2/7, this is an n=1 observation. It does not statistically separate the top three configurations, nor does it prove that multi-agent teams systematically write worse code. Crucially, the reviewer subagent's independent defect-catch rate was not quantitatively isolated, which remains the primary theoretical justification for multi-agent teams.

---

## Verified Live Token Expenditure Chart

<p align="center">
  <img src="../assets/chart_tokens.png" alt="CaveAgents Token Benchmark Comparison" width="100%"/>
</p>
