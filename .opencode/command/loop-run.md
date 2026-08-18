---
description: "Advance an existing v1 or v2 create-loop after detecting and validating its protocol."
---

Use the create-loop skill to run or advance an existing Loop.

Arguments: $ARGUMENTS

Resolve `CREATE_LOOP_SKILL_ROOT` to the directory containing the create-loop
`SKILL.md` loaded for this command. Do not assume a repository-relative path.
Treat every skill-relative path below as relative to that root, and fail clearly
if no single root can be identified.

Parse an optional `--protocol v1|v2`, then locate the target Loop. Detect its
protocol from durable artifacts: `goal.json` with `schema_version: "2.0"` is
v2; `loop.plan.yaml` is v1. An explicit selector must agree with the artifacts.
Fail on mixed or ambiguous write paths; never auto-migrate.

### v2 path

Load `SKILL.md` §"Protocol selection" and `references/protocol_v2.md`. Before
advancing, run
`python "<CREATE_LOOP_SKILL_ROOT>/scripts/validate_loop_dir.py" "<loop-dir>"`.
A nonzero exit is a recovery condition, not permission to proceed.

Read the active plan mode before expecting runtime artifacts. If it is
`lightweight`, there is intentionally no journal or resume: execute the
single-session DAG directly from immutable goal/plan, revalidate after work,
and finish without inventing runtime state. Before the first replan,
cross-session handoff, durable evidence record, external effect, or optional
governance module, atomically upgrade to `persistent`/`governed` by writing a
new immutable plan version and creating the initial journal with this exact
prefix: activate the existing `plan-v1`; append one control-only observation
(`subject_refs:["loop:control_mode"]`, `source_class:"control_trigger"`,
`observed_result:"observation"`); append one decision with
`question:"control_mode_upgrade"`, outcome equal to the new mode, and only that
evidence ref plus `plan_change:null`; then immediately activate `plan-v2` with
the same evidence and decision refs. That bridge may change only plan identity,
version, creation time, and `control`; keep the goal binding and complete node
graph identical. If the executable plan must change, finish the bridge first and
perform a separately evidenced `plan-v3` replan. Generate resume only after the
v2 activation validates. Do not append node work, effects, or other runtime
records while the active mode is lightweight.

Run one evidence-driven ORIENT → DIAGNOSE → DECIDE → WORK → EVIDENCE → JUDGE →
COMMIT cycle. Treat `goal.json`, the journal-selected immutable plan, and
`journal.jsonl` as authority; `resume.json` is generated cache only. Follow the
six-state transition table. Cite prior evidence/decisions exactly. Before a
non-idempotent external effect, append and fsync `effect_pre`; never repeat an
in-doubt effect without checking reality. In COMMIT, append evidence/decision
before transition and regenerate resume atomically with `render_resume.py`.
For every ordinary replan, write a prior `decision` with
`question:"plan_replacement"`, an exact `plan_change` binding for the active and
candidate plan versions/hashes, and exactly the evidence refs used by the
following activation. A historical decision, a challenged cause, or a
control-only upgrade trigger cannot authorize a later replan.
Completion is a model judgment recorded as `completion`, never an aggregation
of done nodes or a validator result. Do not write v1 artifacts.

### v1 compatibility path

For v1, load these skill files before executing — they are the source of truth.
Read them; do not restate their contents from memory:

- `SKILL.md` §5 (High-Ceiling Execution) — run every node with the **pre-execution review** (is this node still relevant, are its inputs current?) and the **quality-uplift decision** (the gate is the floor, not the ceiling) that bracket the raw loop.
- `references/state_model.md` — node status enum, the state transition table, and the per-node claim/lease. A node reaches `completed` ONLY when its latest ledger entry has `verdict: pass`.
- `references/loop_plan_spec.md` §6.3 (Topological readiness rule) and §6.4 (Parallel dispatch rule) — how you compute the ready set and order dispatch.
- `references/branching_parallelism.md` — `fanout`/`join`, serial-vs-parallel, and cancellation semantics.
- `references/evidence_gates.md` — evaluate each node's gate against its defined kind.
- `references/exception_handling.md` — the escalation ladder (`local_retry → local_patch → replan → escalate`), retry-policy math, and saga compensation when a node fails.
- `references/execution_intelligence_policy.md` — the High-Ceiling temperament: root-cause over symptom, deepening triggers, Goal Alignment Check.
- `references/recursive_planning_immersive_execution.md` — the execution rhythm: switch between the whole-graph planning view and the per-node immersive view, descend into a subgraph/subloop when a node proves complex, and write the descent's products/evidence/decisions back to the parent before advancing.
- `references/layered_execution_chain.md` — the layer-switch cascade for every work item (execute directly / action plan / subgraph / subloop / plan mutation / human decision) and the leaf-action stop-test: never enter immersive action while the work is still vague, and never keep planning once a leaf action is clear enough to execute and verify.
- `references/live_loop_semantics.md` — before admitting new work, judge evidence-driven completeness growth vs scope creep; every growth event is a typed, reasoned `mutation`.
- `references/parallel_development_protocol.md` — **CONDITIONAL: read only when more than one code-development unit runs at once** (parallel actions, sibling subgraphs, concurrent sub-loops, or a multi-role team) — git-worktree-per-unit isolation and the owner-gate on push/merge.

Run the integrity gate — `python3 "<CREATE_LOOP_SKILL_ROOT>/scripts/check_loop_integrity.py" "<loop-dir>"` — at THREE moments; a nonzero exit means enter a recovery subgraph, do NOT advance:

- at session start, before picking a node;
- after every node completion;
- after every state mutation.

Then advance per node through the same three v1 Mode B phases:

**ORIENT (read-only): reconstruct the decision context without changing any
artifact.** Re-read the goal contract at the mandatory dispatch read point;
recompute the frontier from `requires` + `node_states` instead of trusting the
stored `ready_set`; apply parallel dispatch and priority ordering; choose the
node; read its contract and the ledger. Do not write or acquire a claim here.

**WORK (engineering): perform and verify the real work under the idempotency
bracket.** Acquire the per-node claim/lease when claims are in use. Append
`pre_effect` before the side effect with its `idempotency_key`; skip execution
when that key is already recorded. Execute the node. Before any plan edit,
re-read the goal contract at the mandatory mutation read point, append its typed
`mutation` event, then edit. Append `post_effect` after the side effect with
`outcome` + `result_hash`. Re-read the goal contract at the mandatory
verification read point, then evaluate the gate by semantic review, never from
a filled field or validator result alone.

**COMMIT (append-only, then regenerate; persistent v1 only): record each fact
once and derive the resume projection.** Append the evidence-ledger entry and commit the status
transition from it; append a `dissent` event only when R48 requires one. Re-read
the goal contract at the mandatory termination read point before declaring
`done_when`, then recompute the frontier. Regenerate the complete
`checkpoint.yaml` from the plan, event log, and ledger, and write it LAST by
temporary file plus atomic rename; reconcile counters from the event log. A
mutation-free, dissent-free advance mandates four control-state writes: the
`pre_effect`, `post_effect`, and evidence appends, plus atomic checkpoint
regeneration. COMMIT performs at most three appends before regeneration.

Follow the skill's Mode B loop exactly. Never improvise plan changes — route
scope/plan changes through the skill's replan path.
