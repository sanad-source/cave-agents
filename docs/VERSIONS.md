# Versions

This document tracks the version history of CaveAgents from early centralized prototypes to the high-efficiency v4 architecture.

---

## Comparison

| Version | Core Architecture | Coordination Mechanism | Tool Registry | Benchmark Tokens | vs Teamwork Baseline |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Teamwork Baseline** | Star Mesh | Unconstrained Conversational | Static (Full Catalog) | 208,555 | 0.0% |
| **AgentTeams Baseline** | Centralized DAG | Structured Conversational | Static (Full Catalog) | 154,998 | -25.7% |
| **v1** | Serial Pipeline | Centralized Captain Relay | Static (Full Catalog) | 109,984 | -47.3% |
| **v2** | Clones + P2P | Direct Peer-to-Peer Messaging | Static (Full Catalog) | 91,432 | -56.2% |
| **v3** | Pre-Flight Bound | P2P + Scoped Context Injection | Static (Full Catalog) | 50,395 | -75.8% |
| **Standard Mono Baseline** | Single Agent | N/A (Monolithic Turn-by-Turn) | Static (Full Catalog) | 30,241 | -85.5% |
| **v4 (Current)** | Dynamic Tool Pruning | P2P + Inverted Cost Frontier | Dynamic Role-Pruned Registry | **26,784** | **-87.2%** |
| **Caveman Mono Baseline** | Single Agent | N/A (Terse Prompting) | Static (Full Catalog) | 16,285 | -92.2% |

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

### Version 4: Dynamic Tool Pruning & Inverted Cost Frontier (`v4`)
- **Released**: State-of-the-art production engine.
- **Topology**: Dynamic tool-pruned worker DAG with autonomous inspection and compound verifications.
- **Key Changes**:
  - **Dynamic Tool Pruning**: Defined subagents with role-specific tool subsets via `define_subagent`. Dropped unused tools (e.g. web search, browsers, image generators, notebooks), saving ~2,500 tokens per tool call turn.
  - **Autonomous Inspection**: Subagents perform surgical symbol lookups rather than consuming upfront bulk context.
  - **Compound Verifications**: Multi-layer hermetic test validation ensuring zero regressions.
  - **Inverted Cost Frontier**: Total multi-agent token expenditure reached **26,784 tokens**—achieving parallel multi-agent execution at a lower token cost than a standard monolithic single agent (**30,241 tokens**).
- **Token Result**: **26,784 tokens** (87.2% reduction vs Teamwork baseline).
