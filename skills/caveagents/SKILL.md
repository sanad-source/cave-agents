---
name: caveagents
description: Ultra-efficient multi-agent orchestration framework using Dynamic Tool Registry Pruning and ASD-STE100 terseness to minimize coordination overhead.
version: 0.4.0
default_engine: v4
license: MIT
---

# CaveAgents Skill

CaveAgents is a high-performance multi-agent orchestration framework designed to eliminate the multi-agent token tax. By combining macro-level Directed Acyclic Graph (DAG) task scheduling with micro-level ASD-STE100 terse communication and Dynamic Tool Registry Pruning, CaveAgents slashes multi-agent coordination overhead by -81.3% compared to standard teamwork.

## Default Engine: v4 (Dynamic Tool Registry Pruning)

The skill defaults to **v4** execution mode (`CAVEAGENTS_V4`). In v4:
1. **Dynamic Tool Registry Pruning**: Subagents receive strictly pruned tool definitions via `define_subagent` (saving ~2,500 tokens per tool call turn).
2. **Peer-to-Peer Direct Comms**: Subagents communicate peer-to-peer without routing conversational chatter through the Captain.
3. **ASD-STE100 Terseness**: Strict telegraphic syntax. No pleasantries, no tool narration, no boilerplate filler.
4. **TDD Quality Gate**: Test execution precedes synthesis. Strict exit code verification.

## Activation Prompt

To engage CaveAgents in any project session:

```markdown
Activate CaveAgents v4 mode:
- Topology: Captain DAG with P2P direct worker coordination.
- Mode: Caveman ultra-active, ASD-STE100 terse. Drop pleasantries, tool narration, and filler.
- Toolsets: Dynamic tool pruning enabled per subagent role.
- Verification: TDD quality gates with automated test suites before task resolution.
```

## Core Agent Roles

Detailed definitions in [references/roles.md](references/roles.md):
- **Captain (`cave_captain`)**: High-level planner, DAG decomposition, worker lifecycle manager, quality gate enforcer. Never conducts low-level file edits.
- **Worker (`cave_worker`)**: Autonomous implementer. Receives scoped inScope files, executes exact terminal commands, writes code, runs test suites.
- **Reviewer / Verifier (`cave_verifier`)**: Independent validation subagent. Audits test coverage, benchmarks token overhead, enforces AST/lint standards.

## Reference Specifications

- [Architecture Reference](../../docs/ARCHITECTURE.md)
- [Version 1: Serial Pipeline](references/CAVEAGENTS_V1.md)
- [Version 2: Clones & P2P Direct Comms](references/CAVEAGENTS_V2.md)
- [Version 3: Pre-Flight Bound](references/CAVEAGENTS_V3.md)
- [Version 4: Dynamic Tool Pruning](references/CAVEAGENTS_V4.md)
