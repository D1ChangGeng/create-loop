---
description: Advance an existing create-loop by executing the next ready node(s) (Mode B).
argument-hint: "[node-id]"
---

Use the create-loop skill and run **Mode B (Run / advance a loop)**.

Optional target node or loop: $ARGUMENTS

**Load these skill files BEFORE you execute — they are the source of truth. Read them; do not restate their contents from memory, and do not paste their vocabulary into your output.**

- `skills/create-loop/SKILL.md` §5 (High-Ceiling Execution) — run every node with the **pre-execution review** (is this node still relevant, are its inputs current?) and the **quality-uplift decision** (the gate is the floor, not the ceiling) that bracket the raw loop.
- `skills/create-loop/references/state_model.md` — node status enum, the state transition table, and the per-node claim/lease. A node reaches `completed` ONLY when its latest ledger entry has `verdict: pass`.
- `skills/create-loop/references/loop_plan_spec.md` §6.3 (Topological readiness rule) and §6.4 (Parallel dispatch rule) — how you compute the ready set and order dispatch.
- `skills/create-loop/references/branching_parallelism.md` — `fanout`/`join`, serial-vs-parallel, and cancellation semantics.
- `skills/create-loop/references/evidence_gates.md` — evaluate each node's gate against its defined kind.
- `skills/create-loop/references/exception_handling.md` — the escalation ladder (`local_retry → local_patch → replan → escalate`), retry-policy math, and saga compensation when a node fails.
- `skills/create-loop/references/execution_intelligence_policy.md` — the High-Ceiling temperament: root-cause over symptom, deepening triggers, Goal Alignment Check.
- `skills/create-loop/references/recursive_planning_immersive_execution.md` §6 — the execution rhythm: switch between the whole-graph planning view and the per-node immersive view, descend into a subgraph/subloop when a node proves complex, and write the descent's products/evidence/decisions back to the parent before advancing.
- `skills/create-loop/references/layered_execution_chain.md` §8 — the layer-switch cascade for every work item (execute directly / action plan / subgraph / subloop / plan mutation / human decision) and the leaf-action stop-test: never enter immersive action while the work is still vague, and never keep planning once a leaf action is clear enough to execute and verify.
- `skills/create-loop/references/live_loop_semantics.md` — before admitting new work, judge evidence-driven completeness growth vs scope creep; every growth event is a typed, reasoned `mutation`.
- `skills/create-loop/references/parallel_development_protocol.md` — **CONDITIONAL: read only when more than one code-development unit runs at once** (parallel actions, sibling subgraphs, concurrent sub-loops, or a multi-role team) — git-worktree-per-unit isolation and the owner-gate on push/merge.

Run the integrity gate — `python3 skills/create-loop/scripts/check_loop_integrity.py <loop-dir>` — at THREE moments; a nonzero exit means enter a recovery subgraph, do NOT advance:

- at session start, before picking a node;
- after every node completion;
- after every state mutation.

Then advance per node:

1. Read the latest `checkpoint.yaml` (plus node contract and evidence ledger).
2. Pick a ready node — respect the readiness rule and the per-node claim/lease
   (skip nodes that are live or delegated).
3. Execute the node.
4. Evaluate its evidence gate.
5. Append evidence to `evidence.ledger.yaml` and the `event_log`.
6. Write the new `checkpoint.yaml` LAST (durable snapshot, never in-memory).

Follow the skill's Mode B loop exactly. Never improvise plan changes — route
scope/plan changes through the skill's replan path.
