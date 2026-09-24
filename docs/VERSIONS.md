# Versions

This document tracks the version history of CaveAgents from early centralized prototypes to the high-efficiency v4 architecture.

---

## Comparison

| Version | Core Architecture | Coordination Mechanism | Tool Registry | Benchmark Tokens | vs Teamwork Live |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Standard Teamwork (Live)** | Star Mesh | Unconstrained Conversational | Static (16 Tools) | 143,219 | Baseline |
| **AgentTeams Baseline** | Centralized DAG | Structured Conversational | Static (16 Tools) | 154,998 | +8.2% |
| **v1** | Serial Pipeline | Centralized Captain Relay | Static (16 Tools) | 109,984 | -23.2% |
| **v2** | Clones + P2P | Direct Peer-to-Peer Messaging | Static (16 Tools) | 91,432 | -36.2% |
| **v3** | Pre-Flight Bound | P2P + Scoped Context Injection | Static (16 Tools) | 50,395 | -64.8% |
| **Standard Mono Baseline** | Single Agent | N/A (Monolithic Turn-by-Turn) | Static (16 Tools) | 30,241 | -78.9% |
| **v4 (Current)** | Dynamic Tool Pruning | P2P Direct Messaging | Dynamic Role-Pruned (5 Tools) | **26,784** | **-81.3%** |
| **Caveman Mono Baseline** | Single Agent | N/A (Terse Prompting) | Static (16 Tools) | 16,285 | -88.6% |
| **Pruned Mono Control** | Single Agent | N/A (Control Arm) | Dynamic Role-Pruned (5 Tools) | **11,381** | **-92.1%** |

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
- **Topology**: Parallel worker clones with direct P2P messaging.
- **Key Changes**:
  - Implemented direct subagent-to-subagent message passing (`send_message(Recipient=worker_id)`).
  - Allowed worker clones to execute concurrent subtasks in parallel.
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
- **Released**: State-of-the-art production engine.
- **Topology**: Dynamic tool-pruned worker DAG with autonomous inspection and compound verifications.
- **Key Changes**:
  - **Dynamic Tool Pruning**: Defined subagents with role-specific tool subsets via `define_subagent`. Dropped unused tools (e.g. web search, browsers, image generators, notebooks), reducing per-turn tool schema injection from ~2,480 down to ~380 tokens (~2,100 tokens saved per turn).
  - **Autonomous Inspection**: Subagents perform surgical symbol lookups rather than consuming upfront bulk context.
  - **Compound Verifications**: Multi-layer hermetic test validation ensuring zero regressions.
  - **Multi-Agent Optimization & The Control Gap**: Total multi-agent token expenditure reached **26,784 tokens** (81.3% reduction vs Standard Teamwork at 143k tokens), bringing a 3-agent TDD cycle (QA → Coder → Reviewer) below the cost of an unpruned monolithic single agent (**30,241 tokens**). However, under strict experimental control, an identical 5-tool pruned single-agent control achieves **11,381 tokens** (2.35x cheaper than v4). The earlier apparent "Inverted Cost Frontier" was an artifact of comparing an unpruned monolith (16 tools) against a pruned team (5 tools); on micro-tasks, single agents pay zero handoff or supervisor coordination overhead.
- **Token Result**: **26,784 tokens** (81.3% reduction vs Standard Teamwork Live run at 143,219 tokens).
