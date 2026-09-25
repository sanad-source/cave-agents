# Versions

This document tracks the version history of CaveAgents from early centralized prototypes to the high-efficiency v4 architecture.

---

## Comparison

### Tier 1 Benchmark: Single Algorithmic Component (`TokenBucket`, 91 LOC, $n=1$)

| Version / Configuration | Core Architecture | Coordination Mechanism | Tool Registry | Estimated Tokens | Multiple vs Pruned Control (1.00x) |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Pruned Mono Control** | Single Agent | N/A (Control Arm) | Dynamic Role-Pruned (5 Tools) | **11,381** | **1.00x** (Baseline Control) |
| **Caveman Mono Baseline** | Single Agent | N/A (Terse Prompting) | Static (16 Tools) | 16,285 | **1.43x** |
| **v4 (Current)** | Dynamic Tool Pruning | P2P Direct Messaging | Dynamic Role-Pruned (5 Tools) | **26,784** | **2.35x** |
| **Standard Mono Baseline** | Single Agent | N/A (Monolithic Turn-by-Turn) | Static (16 Tools) | 30,241 | **2.66x** |
| **v3** | Pre-Flight Bound | P2P + Scoped Context Injection | Static (16 Tools) | 50,395 | **4.43x** |
| **v2** | Clones + P2P | Direct Peer-to-Peer Messaging | Static (16 Tools) | 91,432 | **8.03x** |
| **v1** | Serial Pipeline | Centralized Captain Relay | Static (16 Tools) | 109,984 | **9.66x** |
| **Standard Teamwork (Live)** | Star Mesh | Unconstrained Conversational | Static (16 Tools) | 143,219 | **12.58x** |
| **AgentTeams Baseline** | Centralized DAG | Structured Conversational | Static (16 Tools) | 154,998 | **13.62x** |

### Tier 2 Benchmark: Multi-File Asynchronous Service (`taskflow`, ~500 LOC, $n=10$ per Arm, $N=20$)

| Architecture | Sample Size | Mean Tokens ± SD | Median Tokens | Wall-Clock Latency | Hidden Test Pass Rate | Multiple vs Control |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Pruned Monolith Control** | $n=10$ | **27,824 ± 5,440** | 25,447 | 153.8s ± 30.6s | 159 / 160 (99.38%) | **1.00x** (Baseline) |
| **CaveAgents v4-lite (2-Worker, No Review)** | $n=10$ | **85,782 ± 11,462** | 81,602 | 155.5s ± 29.2s | 160 / 160 (100.00%) | **3.08x** (+208.3%) |

> **Architecture Distinction**: Tier 1 evaluated a 3-agent TDD team (QA → Coder → Reviewer); Tier 2 evaluated a minimal 2-worker team (Foundation → Executor, no reviewer). Even this minimal team carries a **3.08x token tax** at exact latency parity (155.5s vs 153.8s) due to upstream data dependencies causing functional serialization. True parallel speedup and adversarial review efficacy remain to be tested.


---

## Changelog

### Version 1: Serial Pipeline (`v1`)
- **Released**: Initial proof-of-concept.
- **Topology**: Strictly sequential, centralized pipeline.
- **Key Changes**:
  - Combined multi-agent decomposition with ASD-STE100 terseness rules.
  - Implemented the first Captain-to-Worker serial delegation pipeline.
  - Required all worker output to route back through Captain before triggering the next agent.
- **Token Result**: **109,984 tokens** (down from 208,555).
- **Bottlenecks Identified**: Relay duplication caused Captain's context window to inflate rapidly.

### Version 2: Clones & Peer-to-Peer Direct Comms (`v2`)
- **Released**: Distributed routing update.
- **Topology**: Cloned worker subagents with direct P2P messaging (executed serially on this single-file task).
- **Key Changes**:
  - Implemented direct subagent-to-subagent message passing (`send_message(Recipient=worker_id)`).
  - Designed for concurrent execution on independent DAG branches; executed sequentially on single-component tasks.
  - Eliminated Captain message relay overhead during intermediate implementation stages.
  - Introduced standardized compact wire JSON payload schema (`CaveMessage`).
- **Token Result**: **91,432 tokens** (16.9% reduction vs v1).
- **Bottlenecks Identified**: Initial workspace context dumps inflated worker start prompts unnecessarily.

### Version 3: Pre-Flight Bound Architecture (`v3`)
- **Released**: Scoped context optimization.
- **Topology**: Bounded Captain DAG with pre-flight AST analysis.
- **Key Changes**:
  - Introduced the Pre-Flight Bound mechanism: Captain analyzes repository AST and file trees prior to worker dispatch.
  - Enforced strict `inScope` bounding—workers receive only exact relevant file paths, eliminating speculative exploration.
  - Automated TDD short-circuit testing (`pytest -q --tb=short`) to truncate failure stack traces.
- **Token Result**: **50,395 tokens** (44.9% reduction vs v2).
- **Bottlenecks Identified**: Tool schema declarations in each prompt step still consumed ~2,500 tokens.

### Version 4: Dynamic Tool Registry Pruning & Bounded TDD (`v4`)
- **Released**: Current Experimental Architecture.
- **Topology**: Dynamic tool-pruned worker DAG with autonomous inspection and compound verifications.
- **Key Changes**:
  - **Dynamic Tool Pruning**: Defined subagents with role-specific tool subsets via `define_subagent`. Dropped unused tools (e.g. web search, browsers, image generators, notebooks), reducing per-turn tool schema injection from ~2,480 down to ~380 tokens (~2,100 tokens saved per turn).
  - **Autonomous Inspection**: Subagents perform surgical symbol lookups rather than consuming upfront bulk context.
  - **Compound Verifications**: Multi-layer hermetic test validation ensuring zero regressions.
  - **Multi-Agent Optimization & The Control Gap**: Total multi-agent token expenditure reached **26,784 tokens** on Tier 1 (81.3% reduction vs Standard Teamwork at 143k tokens), bringing a 3-agent TDD cycle (QA → Coder → Reviewer) below the cost of an unpruned monolithic single agent (**30,241 tokens**). However, under strict experimental control, an identical 5-tool pruned single-agent control achieves **11,381 tokens** (2.35x cheaper than v4). The earlier apparent "Inverted Cost Frontier" was an artifact of a verbose, unpruned baseline: Standard Mono was burdened by both a verbose prompt contract and 16 unused tools, whereas Caveman Mono (which also carried all 16 tools) already beat v4 at 16,285 tokens (1.43x of control).
  - **Tier 2 Multi-File Service Validation ($n=10$ per Arm, $N=20$)**: Evaluated on an asynchronous service (`taskflow`, ~500 LOC across 5 modules) with **CaveAgents v4-lite (2-worker implementation team, no review stage)**. v4-lite averaged **85,782 ± 11,462 tokens** vs. **27,824 ± 5,440 tokens** for Pruned Monolith Control (3.08x tax, +208.3%). Latency reached exact parity (155.5s vs 153.8s, 1.01x) due to functional serialization (Executor polled waiting for Foundation models), while the 160/160 vs 159/160 pass rate was a single defect in Trial 08, not a systematic quality difference.
- **Token Results**:
  - *Tier 1 (Micro Component, 91 LOC, 3-Agent v4)*: **26,784 tokens** (2.35x of control; -81.3% vs Standard Teamwork at 143,219 tokens).
  - *Tier 2 (Medium Service, ~500 LOC, 2-Worker v4-lite)*: **85,782 tokens** (3.08x of control; 155.5s latency).

