---
name: create-loop
description: >-
  USE THIS SKILL whenever the user wants to plan, drive, resume, or survive a
  complex long-running task — including: building an execution-control loop or
  `loop.plan` instead of a one-shot prompt; designing multi-session, cross-
  session, durable, resumable, long-horizon agent work; turning a fuzzy goal
  into a recursive task DAG with checkpoints, evidence gates, recovery,
  branches, parallelism, retries, and human-in-the-loop approval nodes; any
  project that spans many sessions, exceeds one context window, must survive
  context loss or session switch or compaction, or needs to be handed off
  between agents; "write the loop not the prompt"; orchestration of multi-step
  work with dependencies, fanout/join, sagas, escalations. TRIGGER on phrases
  like "this is a big task", "this will take many sessions", "I need this to
  survive a crash", "resume the work", "I lost context", "plan the steps",
  "set up an agent loop", "build me a control plan", "we need checkpoints",
  "we need approval gates", "long-running agent task", "durable execution",
  "create a loop", "run the loop", "advance the loop", "resume the loop",
  "loop status", "where are we on the loop", or any time a user wants to drive
  an ambitious multi-step project even if they never say "loop". If the work
  might be picked up tomorrow by a fresh agent with no memory, this applies.
---

# create-loop

A meta-skill. You give it a short goal. It turns that goal into a `loop.plan` — a
recursive execution-control DAG, an evidence-gate protocol, and a persistent
state contract that any fresh agent can resume from a blank session.

It is **not** a prompt generator. It is a control system.

---

## 1. What this is

`create-loop` produces three artifacts together:

1. **`task_profile.yaml`** — the *charter / control profile*, populated by the
   Loop Startup (Charter) interview. Captures goal, true intent, success/failure
   criteria, non-goals, risk class, approval boundary, platform capability, and
   state-persistence requirements.
2. **`loop.plan v0`** — a recursive DAG of `milestone`, `gate`, `mapper`,
   `branch`, `fanout`, `join`, `approval`, and `compensation` nodes, with
   artifact dependency edges (via `requires`), every non-trivial node carrying an
   evidence gate, and a bounded escalation ladder per node.
3. **Persistent state** — a per-loop directory `.agents/loops/L<seq>-<slug>/`
   holding `loop.meta.yaml` + `loop.plan.yaml` + `loop.state.yaml` +
   `checkpoint.yaml` + `evidence.ledger.yaml` + `decision.log.md` + `run.log.md` +
   `handoff.md` + `closeout.md` + `artifacts/` + `_loops/` (+ optional
   `nodes/<node_id>/node.runtime.yaml` for in-node subgraphs). Filesystem-
   mappable so a fresh agent with zero chat memory can resume correctly.

Read [`references/concepts.md`](references/concepts.md) for why the shape is
this way. Read [`references/loop_plan_spec.md`](references/loop_plan_spec.md)
for field definitions and the locked Glossary,
[`references/state_model.md`](references/state_model.md) for statuses,
transitions, checkpoint fields, and the resume algorithm, and
[`references/recursive_loops.md`](references/recursive_loops.md) for the
isomorphic per-loop directory layout and recursion rules.

---

## 2. The three-layer model

The mental model that organises everything else. The interview is **Layer 0**
of the loop — the first governance node — not an external step.

| Layer | Artifact | Job |
|-------|----------|-----|
| **0 — Loop Startup** | Charter interview → `templates/task_profile.yaml` | Establish the *control profile*: goal/end-state, success and failure criteria, non-goals, risk and approval boundary, platform capability, persistence model, HITL nodes. Asks ONLY design-time invariants. |
| **1 — Top-level plan** | `templates/loop.plan.yaml` (`v0`) | Design-time-invariant governance nodes: Discovery, Risk & Compliance, Feasibility, Architecture, Verification, optional Release. No vendor names, no file paths, no test specs at this level. |
| **2 — Runtime subgraphs** | `node.subgraph` of any `mapper` or `allow_subgraph: true` node | Concrete vendors, files, tests, defects, integration steps — generated inside the owning node once research and feasibility actually run. |

The startup sequence is therefore:

```
short goal
  → Layer 0  : Charter / Control-Profile Gate (N0)
  → Layer 1  : loop.plan v0  (design-invariant governance nodes only)
  → Layer 2  : governance nodes execute, each materialising its own subgraph
              from real research, feasibility, and implementation findings
```

The rule is sharp: **if the answer should be produced by later research,
feasibility, execution, or verification, it is NOT a startup precondition.**
Capture it in `unknowns`, `assumptions`, or `research_questions` of
`task_profile.yaml` with an `owner_node` that will own the runtime subgraph
that resolves it. See [`templates/interview_brief.md`](templates/interview_brief.md)
§3 — "What the interview MUST NOT ask."

---

## 3. Autonomy-First Control Principle (read before any mode)

This is the primary design principle of `create-loop`, and it overrides any
instinct to consult the user when a decision, unknown, or blocker appears. The
goal of a `loop.plan` is to **maximise autonomous progress quality, execution
reliability, verification strength, and recoverability** — not to distribute
control evenly between human and agent, and not to make it comfortable for a
human to approve every step.

Human intervention is a **bounded exception**, not the default path. A human is
often the bottleneck on a complex task: incomplete memory, unstable
requirements, snap judgements, no time for deep comparison, weaker maintenance
of long-horizon state / dependencies / evidence chains than a file-based
protocol. So the default is autonomy; asking the user is reserved for the
boundary conditions in the table below.

**When the loop hits a branch, an unknown, a design choice, an implementation
blocker, or insufficient evidence — do NOT ask the user first.** Instead:

```
branch / choice   → spawn an exploration subgraph → research + compare candidates
                    in parallel → score by evidence/risk/cost → pick the clear
                    winner and record the rationale; if no clear winner but the
                    choice is reversible and low-risk, take the highest
                    information-gain / lowest-cost path and proceed
unknown           → form an assumption → gather evidence → update confidence →
                    escalate only if it stays unresolved AND is load-bearing
blocker / failure → classify → diagnostic subgraph → repair / alternative →
                    minimal reversible fix → verify → only escalate after
                    autonomous recovery is exhausted
```

This is why `on_failure` starts at `local_retry`, not `escalate`; why a node
with `allow_subgraph: true` recurses instead of pausing; and why the interview
(§2) asks for *boundaries*, not designs.

**Escalate to the user ONLY when the decision crosses one of these boundaries:**

| Boundary | Why it needs the user |
|----------|-----------------------|
| Change the top-level `goal` / `true_intent` | Goal sovereignty belongs to the user |
| Expand `scope` / `non_goals` | Alters cost, time, and commitment |
| External side effect (publish, email, open a PR, delete data, pay) | Irreversible impact outside the workspace |
| Irreversible operation (delete, overwrite, migrate, public release) | Cannot be undone by the loop |
| Legal / compliance / security high-risk | The agent cannot assume this responsibility |
| Major resource commitment (time, spend, compute, API cost) | Crosses a budget the user owns |
| User value preference (fast vs robust, aggressive vs conservative) | A taste/values call, not an evidence call |
| Final judgement under irreducible uncertainty | The user must accept the residual risk |
| Missing access / authorization | Only the user can grant it |
| License / distribution boundary | Legal and usage-scope call |

Everything else — decomposition, research depth, architecture *comparison*,
risk *discovery*, test *design*, integration approach, recovery — the loop does
autonomously, records with evidence, and surfaces as a defensible recommendation
rather than an open question. Escalation is **exhausted-autonomous-recovery**,
not a first reflex. The full decision protocol and per-exception routing are in
[`references/human_approval.md`](references/human_approval.md) and
[`references/exception_handling.md`](references/exception_handling.md).

---

## 4. Live Loop Semantics (the plan is alive)

The top-level control skeleton is **stable**; the execution path is **alive**. A
`loop.plan` is not a frozen one-shot checklist. It is a control system with a
stable top-level goal, a stable governance skeleton (the `design_invariant: true`
nodes), and **live runtime execution paths that grow from evidence**.

Growth is not adding requirements. It is **evidence-driven completeness growth** —
converting work that is *necessary for the original goal to actually hold* into
controlled subgraphs.

> Live Loop is not scope creep. It is evidence-driven completeness growth.

**When execution exposes an omission, contradiction, defect, wrong assumption, or
a gate that formally passes but does not truly satisfy `success_criteria`** — do
not mechanically continue the old plan, and (per §3) do not ask the user to
redesign. Instead:

```
anomaly or improvement opportunity detected
  → judge whether it affects whether the original goal holds
  → spawn an exploration / diagnostic / repair / completion subgraph
  → gather evidence
  → assess impact, cost, risk, necessity
  → if within the authorization boundary, autonomously admit it to the graph
  → update loop.plan (new plan_version on the fragment) / evidence.ledger / decision.log
  → continue advancing the original goal
```

**A candidate may enter the Live Loop only if at least one holds:** not doing it
makes a gate impossible to pass; clearly lowers deliverable quality; leaves a
known bug / logic hole / design contradiction / wrong assumption; causes
downstream rework or wrong direction; leaves the result "runnable" but not
complete / reliable / verifiable / maintainable; or it has a clear **causal**
link to the goal (not merely "looks useful").

**Three classes of change — do not confuse them:**

| change type | handling |
|-------------|----------|
| top-level **goal** change (`goal`, `true_intent`, `non_goals`, `deliverable_class`) | request user confirmation (§3); create a new Loop if needed |
| top-level **governance-skeleton** change | allowed only when a NEW design-time invariant is discovered; record the rationale in `decision.log` |
| **execution-path** natural growth | the system autonomously creates subgraphs and admits them after an evidence gate passes |

Every growth event is a `subgraph` with `parent_ref`, passes an evidence gate
before admission, bumps `plan_version` on the affected fragment, and is recorded
in the ledger and decision log — so growth stays trackable, verifiable, and
resumable. The unified model is **Stable Goal + Invariant Control Graph + Live
Runtime Subgraphs + Evidence Gates**. Full spec:
[`references/live_loop_semantics.md`](references/live_loop_semantics.md).

---

## 5. High-Ceiling Execution (behavioral contract — read before Mode B)

The machinery in this skill guarantees a loop runs *safely and reproducibly*. It
does not, alone, guarantee the loop runs *well*. This section is the execution
temperament that closes that gap: **not mechanical checklist completion, but
responsible autonomy** — preserve the goal, actively raise the quality and
completeness of the outcome, within the boundaries the enforceable machinery
already sets.

This is a **behavioral** policy, not a validator. Nothing here has a rule number
or fixture — "found the root cause" is not machine-checkable. It is a standing
instruction to *you, the runner*. Full spec:
[`references/execution_intelligence_policy.md`](references/execution_intelligence_policy.md).

**Governing principle — Bounded Maximalism:** maximize final-outcome quality
under the current goal, evidence, authorization boundaries, risk limits, and
resource budget. *Bounded* is load-bearing: pursue completeness/quality **only
where a gap would materially affect whether the goal holds**, and stop at a
boundary, over budget, or at diminishing returns. Materiality gates both
directions — it licenses work a mechanical runner skips and forbids work an
expansionist runner invents.

**Default disposition:** solve root causes not symptoms; explore autonomously
(spawn an analysis/diagnostic subgraph) before asking a low-context question;
challenge a stale/unverifiable plan and patch it *through the admission gate*;
repair upstream artifacts when downstream work exposes a defect; record material
reasoning; deepen **selectively** (see triggers below); verify before claiming
done.

**Never:** follow a stale plan blindly · treat execution as completion · ignore a
defect because "it still runs" · ask the user to solve what you could explore ·
add optional scope without admission · change the top-level goal without approval
· hide uncertainty or failed attempts · keep deepening past diminishing returns.

**Two judgment points augment the Mode B loop:**

- **Pre-execution review** (before acting on a ready node): is this node still
  relevant? are its inputs current? any known gap? has a plan assumption been
  invalidated? — else you execute stale or ill-founded work.
- **Quality-uplift decision** (after the gate passes): the gate is the *floor*,
  not the ceiling. If the artifact passes but has a **material** weakness and a
  **low-risk, verifiable, in-budget** improvement would substantially help the
  outcome, do it — else you ship the-moment-it-turns-green. Do **not** uplift for
  taste, speculation, or over-budget polish.

**Deepen only when triggered** — ambiguity that materially affects the outcome,
conflicting evidence, repeated failure, formally-passing-but-substantively-weak
artifacts, an implementation-revealed gap, unprovable verification, a
high-leverage low-risk improvement, an invalidated assumption, or a downstream
node that would otherwise be weakened. Do **not** deepen on cosmetic issues,
speculative benefit, over-budget work, goal-altering changes, boundary-crossing
actions, or after diminishing returns.

**Node completion** under this policy needs more than output: gate passed +
artifacts current + material gaps resolved-or-admitted-or-deferred-with-reason +
material quality defects handled + state/evidence/checkpoint transactionally
updated.

**Goal Alignment Check** — before every subgraph spawn, subloop promotion, major
change, or branch merge: does this still serve the *original* goal, or has an
optimization become a new objective? (Backed enforceably by the goal/intent-hash
invariant, R26.) The full deepening triggers, root-cause protocol, counterexample
review, quality-uplift policy, execution profiles
(`conservative` / `balanced` / `high_ceiling` (default) / `research_max`), and the
anti-risk table are in
[`references/execution_intelligence_policy.md`](references/execution_intelligence_policy.md).

---

## 6. Execution units: action / subgraph / subloop

Three tiers, distinguished by **governance need, not size**. Start at the
lightest tier; promote only when governance demands it (Promotion Gate below).

| tier | essence | own directory? | recoverable? | use when |
|------|---------|----------------|--------------|----------|
| `action` | a single concrete op (read, run, write) | no | no | one atomic step inside a node — the leaf of all execution |
| `subgraph` | lightweight in-node DAG for local exploration / correction / verification / decomposition | no (hosted in parent) | partial (via parent) | local multi-step work the parent node can safely govern |
| `subloop` | materialized child loop directory (per `references/recursive_loops.md`) | yes | yes (own checkpoint + evidence ledger + closeout) | independently governable work that needs its own plan / state / evidence / closeout |

> **Use `action` for a single step, a `subgraph` for local multi-step work, a
> `subloop` for independently governable work.**

A `subgraph` is either the inline `subgraph` node field (per
`references/loop_plan_spec.md`) or a per-node `node.runtime.yaml`
(`nodes/<node_id>/node.runtime.yaml`) holding that node's `runtime_subgraphs[]`.
It uses its **own 8-value status enum** (`proposed`, `admitted`, `running`,
`blocked`, `completed`, `failed`, `promoted_to_subloop`, `cancelled`) —
**distinct from the 15 node statuses** in `references/state_model.md`. A node
never takes subgraph statuses; a subgraph never takes node statuses.

A `subloop` is a directory-materialized child loop:
`.agents/loops/L<seq>-<slug>/` holding a `loop.meta.yaml` + `loop.plan.yaml` +
`loop.state.yaml` + `checkpoint.yaml` + `evidence.ledger.yaml` + logs +
`artifacts/` + `_loops/` + `closeout.md`. The parent node references it via the
**`child_loops` field** (REQUIRED on every node, empty sentinel `[]`) by path +
a `return_contract` realized as `closeout.md`. Subloops recurse via their own
`_loops/` and are indexed by `.agents/loops/INDEX.yaml` (global) and
`<loop>/_loops/INDEX.yaml` (local). The isomorphic per-loop directory and
directory-name rules are locked in `references/recursive_loops.md`.

**Promotion Gate.** Start with the lightest structure; promote a `subgraph` to a
`subloop` only when it needs its own plan / state / checkpoint / evidence /
closeout — i.e. when any of: cross-session, independent checkpoint, complex
evidence chain, many artifacts, parallel isolation (subagent / separate
executor), high risk, large multi-phase scope, may recurse into grandchildren,
or needs an independent `return_contract`.

**Isolation rule.** A child loop writes **ONLY its own directory**. Parent state
changes go through the `return_contract` / `closeout.md` merge protocol — never
direct writes into the parent's checkpoint, evidence ledger, or artifacts.

Full spec: [`references/recursive_loops.md`](references/recursive_loops.md) and
[`references/subgraph_subloop_policy.md`](references/subgraph_subloop_policy.md).

---

## 7. Mode A — Create a loop

Use this mode when the user is starting fresh or is restarting with a new goal.

Run these in order. Do not skip.

1. **Run the Charter interview.**
   Follow [`templates/interview_brief.md`](templates/interview_brief.md) and
   populate [`templates/task_profile.yaml`](templates/task_profile.yaml) as
   the audit trail. Walk the seven dimensions (A–G). Ask only the single next
   blocking question. Stop when the interview_brief.md §5 stop condition holds.
   - Capture: goal, true_intent, deliverable_class, success_criteria,
     failure_criteria, scope, non_goals, risk_level, irreversible_actions,
     approval_boundary (three lists), platform_capability (incl.
     fallback_accepted), state_persistence, human_review_nodes,
     quality_requirements, evidence_requirements.
   - **MUST NOT ask up front:** which vendors, which tech stack, which
     implementation files, which test cases, which compliance clauses. Those
     go to `research_questions` with an `owner_node`.

2. **Emit `loop.plan v0`.**
   Build [`templates/loop.plan.yaml`](templates/loop.plan.yaml) from the
   charter. Top level contains **only `design_invariant: true` governance
   nodes**. Typical set per `deliverable_class`:
   `goal_clarification` → `discovery` → `risk_compliance_gate` →
   `feasibility_gate` → `architecture_gate` → `verification_plan_gate` →
   `release_gate` (only if `production_launch`) → `closeout`, with
   `final_approval` where `human_review_nodes` require it.
- Every node MUST carry all 21 fields per
      [`references/loop_plan_spec.md`](references/loop_plan_spec.md) §2
      (the 21st is `child_loops` — the directory-materialized child-loop
      reference list; see §6).
   - Edges go in `requires` (a `produces/requires` artifact dependency,
     not habitual order).
   - Each `mapper` / `allow_subgraph: true` node has `subgraph: null` and
     will fill it at runtime.
   - Use `gate.kind` from the 8-value enum; use `on_failure` from the
     4-value ladder; use `assignee` from `agent | user | subagent`; use
     `risk` from `low | med | high`.

3. **Set up the per-loop directory and durable state.**
   Create `.agents/loops/L<seq>-<slug>/` (the run-id / idempotency key).
   Materialise `loop.meta.yaml` ([`templates/loop.meta.yaml`](templates/loop.meta.yaml)),
   the plan, initialise
   [`templates/checkpoint.yaml`](templates/checkpoint.yaml) (one entry per
   plan node in `node_states`, every node `pending` or `ready), start the
   append-only event log, stand up
   [`templates/evidence.ledger.yaml`](templates/evidence.ledger.yaml), and
   create an empty `artifacts/` + `_loops/` (register `.agents/loops/INDEX.yaml`
   if this is the first loop). See
   [`references/recursive_loops.md`](references/recursive_loops.md) for the
   full layout.

4. **Validate before declaring v0 live.**
   - `python3 scripts/validate_loop_plan.py <plan>` — schema + graph rules
     (R1–R5/R7/R8).
   - `python3 scripts/validate_checkpoint.py <checkpoint>` — initial
     `node_states` coverage and linkage to `plan_id` + `plan_version`.
   - `python3 scripts/render_dag.py <plan>` (optional sanity render).
   - The optional JSON Schemas live in [`schemas/`](schemas/) and validate
     field types against the locked enum values.

Schema and dictionary are locked, byte-for-byte, in
[`schemas/loop.plan.schema.json`](schemas/loop.plan.schema.json),
[`schemas/checkpoint.schema.json`](schemas/checkpoint.schema.json),
[`schemas/node.contract.schema.json`](schemas/node.contract.schema.json),
and [`schemas/evidence.ledger.schema.json`](schemas/evidence.ledger.schema.json).

---

## 8. Mode B — Run / advance a loop

Use this mode when `loop.plan v0` exists and the loop is in motion. Execute
this loop **per node**, until `termination.done_when` holds. Run it with the
§5 High-Ceiling temperament — a **pre-execution review** before acting and a
**quality-uplift decision** after the gate passes bracket the raw loop:

```
for the chosen ready node:
  acquire claim           (contracts/<node>.claim, O_CREAT|O_EXCL — single-flight)
  read state              (checkpoint, contract, ledger)
  append pre_effect        (event_log — the primary source of truth)
  execute                 (workflow vs activity; skip if idempotency_key already recorded)
  append post_effect       (event_log: outcome + result_hash)
  evaluate gate           (verdict pass | fail | inconclusive)
  append evidence         (evidence.ledger entry with verifier + rationale)
  transition status       (commit requires an evidence entry)
  write new checkpoint    (LAST: temp file + atomic rename; counters reconcile from event_log)
  decide next             (recompute ready_set from the graph)
```

Hard rules:

- **Autonomy-first at every decision point (§3).** When a node hits a branch,
  an unknown, a design choice, or a blocker, the default is to spawn an
  exploration or diagnostic subgraph and resolve it with evidence — NOT to ask
  the user. Escalate only when the decision crosses a §3 boundary
  (goal/scope/irreversible/external side effect/cost/legal/value/authorization).
- A node transitions to `completed` **only** when its latest ledger entry has
  `verdict: pass`. Anything else routes to `verification_failed`.
- **Evidence has a lifecycle.** An entry marked `superseded`/`stale`/`invalid`/
  `retired` must NOT keep `verdict: pass` — inactive evidence can never back a
  gate (R38). Re-verify, or degrade the node.
- **Every live plan change is a typed, reasoned `mutation` event** appended to
  the `event_log` (`kind: mutation` with `mutation_type` + `reason`, R39) — never
  an untracked edit. This is what keeps live growth from becoming scope creep.
- **A retired node is tombstoned, not deleted** (R40): a `deprecated`/`cancelled`
  node carries a `retirement{type, reason}`; `superseded`/`merged` names its
  replacement. Deleting it would dangle every reference that points at it.
- **Run [`check_loop_integrity.py`](scripts/check_loop_integrity.py) at every
  session start, after every node completion, and after every mutation.** A
  cross-file violation (checkpoint↔plan↔ledger↔index, completed-without-evidence,
  missing artifact) means enter a recovery subgraph — do NOT advance normal work.
- A node that discovers it is too big/dark/complex and has
  `allow_subgraph: true` **must** materialise an isomorphic `subgraph` (a
  `loop.plan` fragment with `parent_ref`) and recurse — never improvise, never
  pollute the top-level graph with `design_invariant: false` nodes.
- The retry guard (`attempt < max_attempts`) reads the **persistent**
  `node.contract.attempt`, never in-memory state. The budget survives a
  crash.
- Among simultaneously-ready nodes, `parallelizable: true` ones dispatch
  concurrently; otherwise pick by highest `priority`. Readiness is
  recomputed from `requires` + `node_states`; the stored `ready_set` is
  advisory.

Full control-flow vocabularies (`fixed`, `conditional`, `command`, `fanout`),
join semantics, and parallel-dispatch rules live in
[`references/branching_parallelism.md`](references/branching_parallelism.md).
Gate selection (which of the 8 to assign to which node) is in
[`references/evidence_gates.md`](references/evidence_gates.md).

Per-node intent and resulting artifact templates:
[`templates/node.contract.yaml`](templates/node.contract.yaml),
[`templates/handoff.md`](templates/handoff.md),
[`templates/run.log.md`](templates/run.log.md),
[`templates/decision.log.md`](templates/decision.log.md).

---

## 9. Mode C — Resume from a blank session

Use this mode when a fresh agent with no chat memory takes over a half-finished
loop. The checkpoint is the only source of truth.

Run the algorithm from [`references/state_model.md`](references/state_model.md)
§"Resume from a blank session", in order:

1. Acquire / confirm the run (locate `.agents/loops/L<seq>-<slug>/` and its
   `_loops/` children via `INDEX.yaml`; respect `O_CREAT|O_EXCL` single-flight
   per loop directory).
2. Read state — latest `checkpoint.yaml` for current `plan_id` +
   `plan_version`.
3. Verify evidence — every node marked `completed` must have a matching
   `evidence.ledger` entry with `verdict: pass`. Mismatches demote the node
   to `verifying` so the gate re-runs.
4. Verify consistency — recompute readiness from the graph (every
   `pending` node's `requires` all `completed`). The recomputed `ready_set`
   wins on conflict. A `running` node in a fresh session means a prior
   crash — reconcile via the event log.
5. Check termination against `termination.max_iterations`,
   `termination.max_cost_units`, and `failure_criteria`.
6–9. Identify ready → pick next → handle open handoffs in
`pending_approvals` → execute → checkpoint. Repeat.

Rationale, edge cases, and the cross-agent hand-off schema are in
[`references/recovery_protocol.md`](references/recovery_protocol.md).

---

## 10. Exceptions & escalation

Every node declares `on_failure` — its starting rung on the bounded, ordered
ladder:

```
local_retry  ->  local_patch  ->  replan  ->  escalate
```

Read [`references/exception_handling.md`](references/exception_handling.md)
for: exception taxonomy, retry-policy math (`max_attempts`,
`backoff_base_seconds`, `jitter`), saga `compensation` pairing, and the
per-exception response table. A `replan` increments `plan_version` and
spawns a fresh subgraph; an `escalate` produces a `pending_approvals` entry
on an `approval` node with a `human_approval` gate.

---

## 11. Human approval

Approval is a **bounded exception**, not a routine step (see §3). It is planned
in advance, never improvised as a first reaction to a branch or blocker. Two
principles:

- Build `approval` nodes (with `assignee: user` and `gate.kind:
  human_approval`) into `loop.plan v0` for each row in
  `task_profile.yaml:human_review_nodes` and each irreversible action in
  `needs_user_approval` / `user_only`.
- **Goal-boundary changes** (changes to `goal`, `true_intent`,
  `non_goals`, `deliverable_class`, or `risk_level`) require user
  confirmation before any `replan`. Internal progress within
  `agent_may_decide` proceeds autonomously.

Decision-authority tiers, the cross-session handoff token, and the
"what-must-be-user-approved-by-default" rules are in
[`references/human_approval.md`](references/human_approval.md).

When you must ask the user to decide, never ask a bare question. Emit a
**Human Decision Package** — a context-complete, copy-pasteable, YAML-answerable
brief (goal, constraints, evidence, options with trade-offs, a recommendation,
and the answer schema) so a fresh reader or another AI can answer systematically
and the reply can be written straight back into `decision.log.md` /
`loop.state.yaml` / `checkpoint.yaml`. A plan may declare a
`human_intervention_policy` block to make this mandatory. Template:
[`templates/human_decision_request.md`](templates/human_decision_request.md);
protocol in [`references/human_approval.md`](references/human_approval.md) §7.

---

## 12. Knowledge promotion

Verified, reusable findings may be promoted from transient loop state to
durable project knowledge (the `self-evolution` skill). The boundary is
strict: transient plan/checkpoint/ledger state stays local; only findings
that have passed an evidence gate and survive a `closeout` decision become
candidates. Promotion ships as a tagged inbox entry; never as an in-place
mutation of the run.

Full adapter spec, ownership, the trigger table, and failure modes the
boundary is designed to prevent are in
[`references/self_evolution_integration.md`](references/self_evolution_integration.md).

Loop closeout itself produces
[`templates/closeout.md`](templates/closeout.md).

---

## 13. Platform capability & degradation

Do **not** assume the host provides background execution, subagents, a
durable runtime, or lifecycle hooks. When any are missing, degrade to the
filesystem primitives that always exist:

| missing capability | fallback |
|--------------------|----------|
| background execution | persistent files + explicit checkpoints written at every transition |
| subagents | the single agent runs nodes serially; `assignee: subagent` collapses to `assignee: agent` |
| durable runtime | the `.agents/loops/L<seq>-<slug>/` directory tree + event log + checkpoint on the filesystem *is* the runtime (see [`references/recursive_loops.md`](references/recursive_loops.md)) |
| lifecycle hooks | a handoff doc per stop + manual re-invocation + the §9 resume algorithm at startup |

Probe via `task_profile.yaml:platform_capability`. Set
`fallback_accepted` before emitting `loop.plan v0`. "Degraded mode" is the
same contract with fewer conveniences — not a second implementation.

---

## 14. Reference map (progressive disclosure index)

Every link below points to a real file. Read it when its row says to. Most
rows only matter in their respective modes.

### References — `references/`

| File | Read when |
|------|-----------|
| [`concepts.md`](references/concepts.md) | You want the *why* of the shape (DAG not checklist, top-level invariant rule, recursion, evidence gates, durable primitives, three-layer model, §8 interview as Layer 0). |
| [`live_loop_semantics.md`](references/live_loop_semantics.md) | The execution path grew, a gate exposed an omission/defect, or you must decide whether new work is goal-necessary growth vs scope creep. Triggers, admission criteria, and the three-classes-of-change table. |
| [`execution_intelligence_policy.md`](references/execution_intelligence_policy.md) | You are *running* a loop (Mode B) and want the high-ceiling execution temperament: Bounded Maximalism, root-cause protocol, deepening triggers, quality-uplift vs the gate floor, Goal Alignment Check, counterexample review, execution profiles, and the anti-risk table. Behavioral policy (no schema), backs SKILL §5. |
| [`loop_plan_spec.md`](references/loop_plan_spec.md) | You need the authoritative field dictionary for `loop.plan`, node kinds, gate kinds, `retry_policy`, the escalation ladder, control-flow vocabularies, subgraphs, or the locked **Glossary**. |
| [`state_model.md`](references/state_model.md) | You need the 15-status enum, the state transition table, **checkpoint** / **node.contract** / **evidence.ledger** field sets, or the §"Resume from a blank session" algorithm. |
| [`recursive_loops.md`](references/recursive_loops.md) | You need the isomorphic per-loop directory layout, `loop.meta.yaml` field set, `child_loops[]` reference shape, `return_contract` / `closeout.md`, child-checkpoint additions, the Sub-loop Admission Gate, the isolation rule, or the INDEX files. Read when promoting to or working inside a **subloop**. |
| [`subgraph_subloop_policy.md`](references/subgraph_subloop_policy.md) | You need the action / subgraph / subloop three-tier model, the **Promotion Gate** (when a subgraph must be promoted to a subloop), the 8-value subgraph status enum, `node.runtime.yaml` hosting, or the subgraph ↔ parent-node permission table. |
| [`branching_parallelism.md`](references/branching_parallelism.md) | You are dispatching nodes, wiring `fanout`/`join`, choosing serial vs parallel, or designing `branch` / merge / cancellation. |
| [`evidence_gates.md`](references/evidence_gates.md) | You are picking which of the 8 gate kinds to assign to a node, or deciding between `llm_judge` vs `human_approval` vs `evaluator_optimizer`. |
| [`exception_handling.md`](references/exception_handling.md) | A node fails, the ladder fires, a saga needs compensation, or you need retry-policy math / per-exception response table. |
| [`human_approval.md`](references/human_approval.md) | You are deciding what an agent may do autonomously, scoping an `approval` node, or writing a cross-session handoff token. |
| [`recovery_protocol.md`](references/recovery_protocol.md) | You are resuming mid-flight, handling a stale `running` node, reconciling event-log drift, or building the handoff doc. |
| [`self_evolution_integration.md`](references/self_evolution_integration.md) | You are promoting verified findings from loop state to durable project knowledge, or stopping cross-boundary leakage. |
| [`command_system.md`](references/command_system.md) | You want the `/loop-new`, `/loop-run`, `/loop-resume`, `/loop-status` slash commands (OpenCode + Claude Code) that map to Modes A/B/C + status, how to install them, and the natural-language fallback. |
| [`research-sources.md`](references/research-sources.md) | You want the underlying durable-execution and DAG/multi-agent citations the design is grounded in. |

### Templates — `templates/` (copy and fill)

| File | Read when |
|------|-----------|
| [`interview_brief.md`](templates/interview_brief.md) | Mode A: you are about to run the Charter interview — load it for the adaptive rules, dimensions A–G, stop condition, and the **MUST NOT ask** table. |
| [`task_profile.yaml`](templates/task_profile.yaml) | Mode A: the charter / control profile you populate during the interview. |
| [`loop.meta.yaml`](templates/loop.meta.yaml) | Mode A: identity & relation for the new loop directory (`loop_id`, `parent`, `scope`, `return_contract`, etc.). |
| [`loop.plan.yaml`](templates/loop.plan.yaml) | Mode A: the `loop.plan v0` template — every node carries all 21 fields (incl. `child_loops`). |
| [`loops.index.yaml`](templates/loops.index.yaml) | Mode A / Mode C: the global `.agents/loops/INDEX.yaml` (and the per-loop `_loops/INDEX.yaml`) — read the index before traversing the directory tree. |
| [`checkpoint.yaml`](templates/checkpoint.yaml) | Modes B/C: the durable snapshot you read on resume and rewrite after every transition. |
| [`evidence.ledger.yaml`](templates/evidence.ledger.yaml) | Mode B: the append-only record of gate verdicts a node needs to reach `completed`. Each entry carries a lifecycle `status` — only `active` evidence may back a gate (R38). |
| [`node.contract.yaml`](templates/node.contract.yaml) | Mode B: per-node execution contract (`cache_key`, `attempt`, gate copy, evidence pointer). |
| [`node.runtime.yaml`](templates/node.runtime.yaml) | Mode B: per-node runtime hosting for in-node `subgraph`s (`nodes/<node_id>/node.runtime.yaml`, the `runtime_subgraphs[]` list). |
| [`claim.yaml`](templates/claim.yaml) | Mode B: the per-node claim/lease (`contracts/<node-id>.claim`) that makes `ready → running` single-flight — acquire before executing, on resume it says whether a `running` node is live, crashed, or delegated. |
| [`event_log.yaml`](templates/event_log.yaml) | Modes B/C: the append-only, primary-source-of-truth event log (pre/post-effect entries) the checkpoint counters are reconciled from. Also hosts `kind: mutation` events — the typed, reasoned record of every live plan change (R39). |
| [`loop.state.yaml`](templates/loop.state.yaml) | Mode B: the live pointer file (active node, ready set, lease index) — cheap "what is running now" without replaying the log. |
| [`artifact.index.yaml`](templates/artifact.index.yaml) | Any mode: the `artifacts/INDEX.yaml` registry — one authoritative version per path via lifecycle status + supersedes chain (R41). |
| [`handoff.md`](templates/handoff.md) | Modes B/C: when the session ends mid-node, this is the handoff the next session reads first. |
| [`human_decision_request.md`](templates/human_decision_request.md) | You must ask the user to decide: fill this context-complete Human Decision Package (options, trade-offs, recommendation, YAML answer schema) instead of a bare question. |
| [`run.log.md`](templates/run.log.md) | Mode B: human-readable per-node run narrative (not a source of truth). |
| [`decision.log.md`](templates/decision.log.md) | Mode B: ADR-style log of major plan/scope decisions. |
| [`closeout.md`](templates/closeout.md) | Mode B / after done: the closeout summary — also the **return interface** for a child loop to its parent. |

### Schemas — `schemas/` (locked JSON Schema; validators are authoritative)

| File | Read when |
|------|-----------|
| [`loop.plan.schema.json`](schemas/loop.plan.schema.json) | You need structural validation of `loop.plan.yaml` against the locked field set. |
| [`loop.meta.schema.json`](schemas/loop.meta.schema.json) | You need structural validation of a `loop.meta.yaml` (top-level loop or child-loop identity / relation / return_contract). |
| [`loops.index.schema.json`](schemas/loops.index.schema.json) | You need structural validation of `.agents/loops/INDEX.yaml` (global) or `<loop>/_loops/INDEX.yaml` (local). |
| [`node.runtime.schema.json`](schemas/node.runtime.schema.json) | You need structural validation of a `nodes/<node_id>/node.runtime.yaml` (the per-node `runtime_subgraphs[]` list). |
| [`checkpoint.schema.json`](schemas/checkpoint.schema.json) | You need structural validation of `checkpoint.yaml` field types. |
| [`node.contract.schema.json`](schemas/node.contract.schema.json) | You need structural validation of a node's execution contract. |
| [`evidence.ledger.schema.json`](schemas/evidence.ledger.schema.json) | You need structural validation of an evidence-ledger entry. |
| [`claim.schema.json`](schemas/claim.schema.json) | You need structural validation of a per-node `contracts/<node>.claim` (lease fields). |
| [`event_log.schema.json`](schemas/event_log.schema.json) | You need structural validation of the append-only `event_log` (monotonic `seq`, pre/post-effect entries). |
| [`loop.state.schema.json`](schemas/loop.state.schema.json) | You need structural validation of the live `loop.state.yaml` pointer file. |
| [`artifact.index.schema.json`](schemas/artifact.index.schema.json) | You need structural validation of an `artifacts/INDEX.yaml` registry (lifecycle status + supersedes chain; one authoritative version per path). |

### Scripts — `scripts/` (run before v0 goes live and after every transition)

| File | Use when |
|------|----------|
| [`validate_loop_plan.py`](scripts/validate_loop_plan.py) | Validates `loop.plan` + hand-rolled graph/provenance/cap/lifecycle rules (R1–R41). Required gate at v0 and after any `replan` or mutation. `--kind loop_plan \| node_contract \| evidence_ledger \| loop_meta \| loops_index \| node_runtime \| claim \| event_log \| loop_state \| artifact_index`; `--plan` (ledger R36), `--root` (index R37). Covers evidence lifecycle (R38), node retirement (R40), artifact authority (R41), plan-mutation events (R39, via `event_log`). |
| [`validate_checkpoint.py`](scripts/validate_checkpoint.py) | Validates checkpoint schema + `--plan` consistency (R6), transition-closure (R19/R20), `--claims` single-flight (R22), `--meta` child-loop fields (R33). |
| [`check_loop_integrity.py`](scripts/check_loop_integrity.py) | **Whole-loop-directory anti-corruption gate.** Composes the per-file validators AND the cross-file reconciliation (checkpoint↔plan↔ledger↔index, completed-needs-active-evidence, evidence-artifact-exists). Run at every session start, after every node completion, and after every mutation; a violation means enter recovery instead of advancing. |
| [`render_dag.py`](scripts/render_dag.py) | Optional DAG render for human inspection. |

### Examples — `examples/`

| File | Read when |
|------|-----------|
| [`example_research_project/`](examples/example_research_project/) | End-to-end worked example for a research deliverable (`research_report`). |
| [`example_product_delivery/`](examples/example_product_delivery/) | End-to-end worked example for a product/code deliverable (`code_impl`). |
| [`example_child_loop_tree/`](examples/example_child_loop_tree/) | End-to-end worked example for **recursive child loops** — a top-level loop with a `child_loops[]`-referenced child and its own `_loops/INDEX.yaml`. Use when you need a model for `subloop` directory layout, `loop.meta.yaml`, `child_loops[]`, and the return-contract merge. |

Each example directory contains a `README.md`, `loop.plan.yaml`, and `checkpoint.yaml` (plus, for `example_child_loop_tree/`, a `loop.meta.yaml`, a global `INDEX.yaml`, and a child loop with its own `closeout.md`).

### Tests — `tests/`

| File | Read when |
|------|-----------|
| [`acceptance_tests.md`](tests/acceptance_tests.md) | You want the acceptance gate for a generated `loop.plan` before declaring v0 live. |
| [`failure_mode_tests.md`](tests/failure_mode_tests.md) | You want the catalog of named failure modes (stale `running`, missing evidence, circular `requires`, ladder exhaustion) and their expected responses. |

---

## Quick orientation for the model running this skill

1. Did the user hand you a short goal with no plan? → **Mode A** (§7).
2. Did the user hand you an existing `.agents/loops/L<seq>-<slug>/` or
   `loop.plan.yaml` and ask you to continue? → **Mode B** if `loop.plan v0`
   exists and work was in progress; **Mode C** (§9) if the session is blank
   and you must recover. When unsure, run the §9 resume algorithm first — it is
   read-only and safe.
3. Did the user describe a goal that *might* need a loop but is small enough
   to do in one shot? Then you don't need this skill — say so and do the task.
   But: if it spans more than a couple of tool calls, may need a decision
   gate, may be dropped and resumed, or mentions "session" / "resume" /
   "checkpoint" / "durable" / "long-running", stay in this skill.

Run `python3 scripts/validate_loop_plan.py <plan>` and
`python3 scripts/validate_checkpoint.py <checkpoint>` before you claim a
`loop.plan v0` is ready. Never edit `loop.plan.yaml` and `checkpoint.yaml`
independently — both must agree on `plan_id`, `plan_version`, and every
`node_id`.
