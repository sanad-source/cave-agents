# Benchmarks

## Overview

This document presents empirical results and benchmark evaluation data measuring total token usage across multiple agent frameworks and configurations performing an identical Python rate limiter implementation and concurrency test task (`TokenBucket`).

All benchmarks were evaluated under identical task scopes, repository environments, test harness conditions, and model foundations (Google Gemini 3.8 Flash, with offline `tiktoken cl100k_base` accounting).

---

## Results Table

| Architecture / Framework | Real Transcript / Run GUID | Input Tokens | Output Tokens | Total Token Usage | vs Standard Mono | Multi-Agent Coordination |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Caveman Mono** | `9a1b3ca8-9267-4169-a201-3f9f1434aed5` | 13,905 | 2,380 | **16,285** | -46.1% | None (1 Agent) |
| **CaveAgents v4** | `6a8c617e / 611f72cc / bc6206fb` | 23,384 | 3,400 | **26,784** | **-11.4%** | **3-Agent Team** |
| **Standard Mono** | `8e45e081-55f1-433a-8900-cdafb7afb923` | 25,669 | 4,572 | **30,241** | Baseline | None (1 Agent) |
| **CaveAgents v3** | `1af678ac / b3c9b503 / efe5c647` | 46,000 | 4,395 | **50,395** | +66.6% | 3-Agent Team |
| **CaveAgents v2** | `ee34719a / e96f0467 / ea071eb7` | 85,760 | 5,672 | **91,432** | +202.3% | 3-Agent Team |
| **CaveAgents v1** | `06c2eb6b / 9e765fdd / d49c842a` | 102,240 | 7,744 | **109,984** | +263.7% | 3-Agent Team |
| **Standard Teamwork (Live)** | `22a1996f / 9b3dbf3b / a4ab4fcb` | 132,366 | 10,853 | **143,219** | +373.6% | 3-Agent Team |
| **AgentTeams** | `0fa36434 / b39f54d0 / f21c2b4e` | 146,117 | 8,881 | **154,998** | +412.5% | 3-Agent Team |

*(Note: Prior unconstrained theoretical projections estimated Teamwork at 208,555 tokens; this live measured run confirms 143,219 tokens on TokenBucket, and up to 615,568 tokens in complex multi-deliverable tournaments).*

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
| **CaveAgents v4** | **5 tools (pruned)** | **~380 tokens** | **~360 tokens** | **~740 tokens** |
| **Caveman Mono** | 16 tools | ~2,480 tokens | ~350 tokens | ~2,830 tokens |

Notice how **CaveAgents v4** slashes the fixed schema declaration cost from ~2,480 tokens down to ~380 tokens per turn via Dynamic Tool Pruning (`define_subagent`), saving over 2,100 tokens on every single tool execution step.

---

## The Inverted Cost Frontier: Analysis & Context

In traditional multi-agent orchestration, multi-agent overhead was taken as an unavoidable cost of modularity:

$$\text{Cost}(\text{Multi-Agent}) \gg \text{Cost}(\text{Monolithic})$$

CaveAgents v4 demonstrates that when tool schemas are pruned dynamically and ASD-STE100 terseness is enforced:

$$\text{Cost}(\text{CaveAgents v4}) = 26{,}784 < 30{,}241 = \text{Cost}(\text{Standard Mono})$$

### Crucial Baseline Caveat & Experimental Control
While CaveAgents v4 operates at a lower token cost than an unpruned, verbose single agent (30,241 tokens), **an unpruned single agent with terse prompting (Caveman Mono) consumes only 16,285 tokens**—approximately 39% lower than CaveAgents v4.

Furthermore, if the single agent is equipped with the exact same 5-tool pruned registry (~740 tokens/step across ~6 steps ≈ 4–5k tokens), **a pruned monolith is estimated to be roughly 5x–6x cheaper than CaveAgents v4**. 

This disparity underscores fundamental systems principles:
1. **Tool Pruning is Orthogonal**: Dynamic tool pruning is a general lever that reduces token consumption in both single-agent and multi-agent systems. When applied to a single agent, it achieves the lowest absolute cost.
2. **Coordination Overhead on Small Tasks**: On small, single-component tasks (such as a single 91-line rate limiter class), monolithic execution incurs zero inter-agent communication, zero handoffs, and zero duplicate context loading. Multi-agent teams only demonstrate structural efficiency advantages when tasks exceed single-context boundaries or require parallel execution across independent repositories.
3. **Prompt Caching Economics**: In real-world API billing, static tool schemas reside in the system prompt prefix and are subject to server-side prompt caching (typically billed at a 75%–80% discount for cache hits in Google Gemini and Anthropic). Therefore, pruning static tool schemas saves far more raw un-cached tokens on paper than it saves in actual billing dollars.

---

## 🔬 Limitations & Threats to Validity

1. **Accounting Assumptions & Built-In Schema Constants**: The reported token breakdowns use offline `tiktoken` accounting where tool schema costs were modeled by adding fixed schema size estimates (~2,480 vs ~380 tokens) multiplied by turn counts, rather than extracting live API response metadata. Furthermore, counting per-turn transcript entries underestimates cumulative conversational history re-sent on each API request. Real-world API billing metadata must replace these estimates.
2. **Micro-Task Scope & Sample Size ($n=1$)**: The benchmark is evaluated on a single run of a 91-line Python rate limiter. Model sampling variance was not statistically bounded. On small tasks, single agents naturally have an advantage because coordination costs cannot be amortized.
3. **Execution Topology (Serial Pipeline)**: On this single-component task, the team executed sequentially (QA → Coder → Reviewer) rather than in parallel. Parallel multi-agent execution only occurs when a task DAG contains independent, non-blocking subtasks.
4. **Held-Out Quality Evaluation**: Code correctness was verified against tests authored by an LLM in the same loop rather than an independent held-out benchmark suite (e.g., SWE-bench, HumanEval) or human expert review.
5. **Inferred Savings vs. Empirical Ablation**: Attributing ~80%–85% of savings to tool pruning and ~10%–15% to terseness was an analytical inference based on schema sizes, not an isolated single-variable empirical ablation.

---

## Verified Live Token Expenditure Chart

<p align="center">
  <img src="../assets/chart_tokens.png" alt="CaveAgents Inverted Cost Frontier" width="100%"/>
</p>
