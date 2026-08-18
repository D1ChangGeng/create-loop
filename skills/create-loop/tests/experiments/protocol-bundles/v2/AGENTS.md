# skills/create-loop/ — THE INSTALLABLE SKILL

The installable `create-loop` payload. v1 is the compatibility default; v2 is explicit opt-in until paired validation completes. `SKILL.md` routes both protocols and depth lives in `references/`.

## STRUCTURE
```
skills/create-loop/
├── SKILL.md         entrypoint, ≤1000 lines (HARD budget, enforced by tests); Modes A/B/C + reference map
├── references/      v1 docs plus protocol_v2.md
├── templates/       v1 artifacts plus goal/plan/journal/resume v2 core
├── schemas/         v1 Draft-07 plus v2 Draft 2020-12 schemas
├── scripts/         v1 validators and v2 projector/validator/resume/migrator
├── examples/        v1 worked loops plus v2 lightweight/persistent fixtures
├── tests/           legacy specs, baseline, and Phase 5 freeze/workspace/evaluation/guard tooling
└── tests_py/        executable v1/v2 safety plus focused workspace/evaluation/guard regressions
```

## V1 THREE-LAYER MODEL (compatibility only)
- **Layer 0 — Charter interview** (`templates/task_profile.yaml`, node N0): captures control profile ONLY — goal/true_intent, success/failure/non-goals, risk, approval boundary, platform capability, persistence. Asks design-time invariants ONLY.
- **Layer 1 — `loop.plan v0`** (`templates/loop.plan.yaml`): `design_invariant: true` governance nodes only. NO vendor names, file paths, or test specs here.
- **Layer 2 — runtime subgraphs**: concrete work materialized inside `mapper` / `allow_subgraph: true` nodes once research makes it knowable.

These v1 runtime principles are compatibility guidance only: **Autonomy-first**
(resolve branches/unknowns/blockers by spawning subgraphs + gathering evidence;
escalate only at genuine boundaries), **Live Loop Semantics** (stable goal +
invariant skeleton + live runtime subgraphs), **Recursive Planning ⇄ Immersive
Execution**, and the **Layered Execution Chain**. v2 instead follows
`references/protocol_v2.md` and materializes work in one versioned plan unless a
risk-triggered child Loop is explicitly enabled.

## SOURCE-OF-TRUTH ORDER (when editing the skill)
0. Select the protocol. Never apply v1 field/status rules to v2 or vice versa.
1. For v1, `references/loop_plan_spec.md` + `references/state_model.md` define
   locked enums, fields, and transitions.
2. For v1, `references/recursive_loops.md` + `subgraph_subloop_policy.md` define
   recursion/tier vocabulary.
3. For the selected protocol, its schemas are the machine shape contract;
   update templates and examples after the schemas.
4. For v1, `scripts/checks/__init__.py` is the Python mirror of every
   enum/regex/required tuple.
5. `SKILL.md` reference map must register every new `references/` or `templates/` doc.

For v2, the order is `references/protocol_v2.md` → v2 Draft 2020-12 schemas →
`schema_runtime.py`/`project_loop.py`/`validate_loop_dir.py` → executable fixtures
→ the short selector/routes in `SKILL.md`. v2 uses stable invariant families,
not new v1 R numbers.

## V1 LOCKED VOCABULARY (compatibility only)
- **15 node statuses**: undiscovered, discovered, needs_clarification, pending, ready, running, waiting_external, waiting_user, blocked, verifying, verification_failed, retry_pending, completed·cancelled·deprecated (terminal).
- **8 subgraph statuses** (DISJOINT from node statuses): proposed, admitted, running, blocked, completed, failed, promoted_to_subloop, cancelled.
- **8 node kinds**: milestone, gate, mapper, branch, fanout, join, approval, compensation.
- **8 gate kinds**: automated_check, test, llm_judge, self_consistency, evaluator_optimizer, step_verifier, human_approval, artifact_exists.
- **4-rung escalation ladder** (ordered): local_retry → local_patch → replan → escalate.
- **3 execution tiers** (by governance need, not size): `action` → `subgraph` → `subloop`.
- **Loop IDs** (IMMUTABLE): top `L<seq>` (3-digit); child `<parent>.<seq>` (2-digit); dir `L<seq>-<slug>` under `.agents/loops/`, children under `_loops/`.

## CONVENTIONS
- Apply admission before creation: ordinary tasks create no Loop. v2 is opt-in;
  detect existing protocol from artifacts and never mix write paths.
- v2 authority is immutable `goal.json`, journal-activated immutable plan,
  append-only `journal.jsonl`, and disposable generated `resume.json`.
- Every v1 `loop.plan` node carries all **21 fields** (the 21st is
  `child_loops`, empty sentinel `[]`, REQUIRED on every node).
- A v1 node → `completed` only from its unique current passing evidence head with
  completion-authorizing declared provenance; deterministic checks do not judge
  evidence adequacy.
- In v1, underscore-prefixed dirs (`_loops/`, `_archive/`) are control
  structures; plain dirs/files are work content.
- The v1 per-loop directory layout is isomorphic at every depth. v2 child Loops
  use the conditional return contract in `protocol_v2.md`.
- Extend v1 workflow vocabulary by editing refs → schemas → `checks/__init__.py`
  → consumers, then add executable reject/control coverage under `tests_py/`;
  Markdown failure files remain specifications, not sufficient regression gates.
- Phase 5 includes an opt-in six-pair Pilot execution chain. Authority-first
  adapter and runner paths validate the canonical grant and a separate
  OS-enforced provider-only network boundary before reading credentials,
  initializing or reserving ledger budget, or launching Codex. Raw provider
  request identity and token usage, workspace/evidence manifests, receipts,
  settlement, traces, oracle results, and blind-review seals are cross-validated.
  The repository remains fail-closed because the Linux reviewer Codex `0.144.1`
  identity and authenticated OS-level network boundary are unresolved, so no
  real provider call has occurred. The legacy network document exposes one
  host-outer prefix; runtime code now permits that shape only for the native
  producer/calibration path and rejects the WSL reviewer before launch. A
  guest-local role/platform contract remains required before reviewer calls can
  execute. Pilot/hard limits are frozen at 23 calls /
  1.33M tokens / 20,100 seconds and 126 calls / 7.56M tokens / 113,400 seconds;
  USD remains `not-measured`. The legacy 42-pair / 84-run plan is prospective
  only. Keep `formal_execution_enabled` false and do not infer v2 superiority.

## ANTI-PATTERNS (THIS SKILL)
- NEVER let `SKILL.md` exceed 1000 lines — put depth in `references/`.
- NEVER silently migrate v1 to v2, make v2 the default, or infer semantic
  completion from deterministic validator success.
- In v1, NEVER apply the 15 node statuses to a subgraph, or the 8 subgraph
  statuses to a node.
- In v1, NEVER edit `loop.plan.yaml` and `checkpoint.yaml` independently; both
  must agree on `plan_id`, `plan_version`, and every `node_id`.
- In v1, resolve an ordinary branch/unknown/blocker through the protocol's
  subgraph path before escalating; v2 follows its progressive-complexity and
  decision-package rules instead.
- In v1, NEVER change top-level `goal`/`true_intent`/`non_goals`/
  `deliverable_class` without user confirmation. In v2, `goal.json` is immutable.
- In v1, NEVER delete a retired node (tombstone with
  `retirement{type,reason}`); in either protocol, NEVER
  edit an accepted evidence observation to change currentness—append a relation.
- NEVER write into `.agents/knowledge/` (durable self-evolution store) from this skill — the transient/durable boundary is strict.
