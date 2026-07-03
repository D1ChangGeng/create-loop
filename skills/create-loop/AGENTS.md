# skills/create-loop/ — THE INSTALLABLE SKILL

The `create-loop` Agent Skill proper. Everything a host loads. Turns a short goal into a `loop.plan`: a recursive execution-control DAG + evidence gates + a resumable filesystem state contract. `SKILL.md` is the entrypoint; depth lives in `references/`.

## STRUCTURE
```
skills/create-loop/
├── SKILL.md         entrypoint, ≤1000 lines (HARD budget, enforced by tests); Modes A/B/C + reference map
├── references/      19 docs: locked vocabulary, spec, state model, live-loop, recursion, policies, recursive-planning-immersive-execution
├── templates/       19 fill-in run artifacts (loop.plan.yaml, checkpoint.yaml, task_profile.yaml, …)
├── schemas/         11 JSON Schemas (Draft-07) — machine contract mirror of references
├── scripts/         Python validators R1–R41 + integrity gate + DAG renderer (see its AGENTS.md)
├── examples/        3 worked loops (incl. recursive child-loop tree)
└── tests/           acceptance_tests.md (green gate) + failure_mode_tests.md (rejection catalog)
```

## THE THREE-LAYER MODEL (organizing idea)
- **Layer 0 — Charter interview** (`templates/task_profile.yaml`, node N0): captures control profile ONLY — goal/true_intent, success/failure/non-goals, risk, approval boundary, platform capability, persistence. Asks design-time invariants ONLY.
- **Layer 1 — `loop.plan v0`** (`templates/loop.plan.yaml`): `design_invariant: true` governance nodes only. NO vendor names, file paths, or test specs here.
- **Layer 2 — runtime subgraphs**: concrete work materialized inside `mapper` / `allow_subgraph: true` nodes once research makes it knowable.

Three runtime principles: **Autonomy-first** (resolve branches/unknowns/blockers by spawning subgraphs + gathering evidence; escalate only at genuine boundaries) and **Live Loop Semantics** (stable goal + invariant skeleton + live runtime subgraphs; evidence-driven completeness growth, NOT scope creep); and **Recursive Planning ⇄ Immersive Execution** (recursively switch between a global whole-graph planning view and local immersive per-node execution; descend into a subgraph/subloop on local complexity and write results back to the parent).

## SOURCE-OF-TRUTH ORDER (when editing the skill)
1. `references/loop_plan_spec.md` + `references/state_model.md` = **locked vocabulary** (enums, fields, transitions). Anything disagreeing with them is wrong.
2. `references/recursive_loops.md` + `subgraph_subloop_policy.md` = recursion/tier vocabulary.
3. `schemas/*.json` = machine contract. Change these FIRST when altering a field/enum, THEN templates, THEN examples.
4. `scripts/checks/__init__.py` = the single Python mirror of every enum/regex/required-tuple.
5. `SKILL.md` reference map must register every new `references/` or `templates/` doc.

## LOCKED VOCABULARY (canonical spellings)
- **15 node statuses**: undiscovered, discovered, needs_clarification, pending, ready, running, waiting_external, waiting_user, blocked, verifying, verification_failed, retry_pending, completed·cancelled·deprecated (terminal).
- **8 subgraph statuses** (DISJOINT from node statuses): proposed, admitted, running, blocked, completed, failed, promoted_to_subloop, cancelled.
- **8 node kinds**: milestone, gate, mapper, branch, fanout, join, approval, compensation.
- **8 gate kinds**: automated_check, test, llm_judge, self_consistency, evaluator_optimizer, step_verifier, human_approval, artifact_exists.
- **4-rung escalation ladder** (ordered): local_retry → local_patch → replan → escalate.
- **3 execution tiers** (by governance need, not size): `action` → `subgraph` → `subloop`.
- **Loop IDs** (IMMUTABLE): top `L<seq>` (3-digit); child `<parent>.<seq>` (2-digit); dir `L<seq>-<slug>` under `.agents/loops/`, children under `_loops/`.

## CONVENTIONS
- Every `loop.plan` node carries all **21 fields** (the 21st is `child_loops`, empty sentinel `[]`, REQUIRED on every node).
- A node → `completed` ONLY when its latest evidence-ledger entry has `verdict: pass`; else `verification_failed`.
- Underscore-prefixed dir (`_loops/`, `_archive/`) = control structure; plain (`artifacts/`, `loop.plan.yaml`) = work content.
- Per-loop directory layout is **isomorphic at every depth** — root, child, grandchild carry the same file set.
- Extend workflow (add gate/node/status): edit refs → update `schemas/*.json` → update `scripts/` → add fixture in `tests/failure_mode_tests.md` → re-run acceptance gate.

## ANTI-PATTERNS (THIS SKILL)
- NEVER let `SKILL.md` exceed 1000 lines — put depth in `references/`.
- NEVER apply the 15 node statuses to a subgraph, or the 8 subgraph statuses to a node.
- NEVER edit `loop.plan.yaml` and `checkpoint.yaml` independently — both must agree on `plan_id`, `plan_version`, every `node_id`.
- NEVER ask the user first on a branch/unknown/blocker — spawn a subgraph. Escalate ONLY at a §3 boundary (goal, scope, irreversible/external side effect, cost, legal, value, authorization).
- NEVER change top-level `goal`/`true_intent`/`non_goals`/`deliverable_class` without user confirmation.
- NEVER delete a retired node (tombstone with `retirement{type,reason}`); NEVER let inactive evidence keep `verdict: pass`.
- NEVER write into `.agents/knowledge/` (durable self-evolution store) from this skill — the transient/durable boundary is strict.
