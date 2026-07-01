# State Model — Node Status, Transitions & Persistent State

*Diataxis type: **reference**. This document is the authoritative definition of
the node **status enum**, the **state transition table**, and the persistent
state artifacts — **checkpoint**, **node.contract**, and **evidence.ledger**.
Downstream `checkpoint.schema`, `node.contract.schema`, and
`evidence.ledger.schema` copy these field sets **byte-for-byte**.*

*For field shapes of the plan itself, see
[`loop_plan_spec.md`](./loop_plan_spec.md). For the reasoning, see
[`concepts.md`](./concepts.md).*

Conventions: all statuses and enum values are **lowercase snake_case**; all
timestamps are **ISO-8601**; `plan_id` / `plan_version` / `node_id` cross-key the
`loop.plan` defined in [`loop_plan_spec.md`](./loop_plan_spec.md).

---

## Node status enum

These 15 values are the canonical, complete set of node statuses. Every
downstream schema enum uses exactly these values, spelled exactly this way.

| status | meaning |
|--------|---------|
| `undiscovered` | the node's existence is implied but it has not yet been enumerated (e.g. a subgraph leaf not yet materialised). |
| `discovered` | the node has been enumerated but not yet analysed for clarity or dependencies. |
| `needs_clarification` | the node cannot be planned without answering an open question (interview / user input required). |
| `pending` | fully specified, but at least one `requires` dependency is not yet `completed`. |
| `ready` | all `requires` dependencies are `completed`; eligible for dispatch. |
| `running` | actively executing. |
| `waiting_external` | paused awaiting an external system/event (non-human). |
| `waiting_user` | paused awaiting user input or action. |
| `blocked` | cannot proceed due to an unmet condition or an unresolved failure; needs intervention. |
| `verifying` | execution finished; the node's `gate` is being evaluated. |
| `verification_failed` | the `gate` did not pass. |
| `retry_pending` | scheduled to retry under `retry_policy` after a failure. |
| `completed` | executed **and** gate passed. **Terminal.** |
| `cancelled` | intentionally abandoned (by user or plan). **Terminal.** |
| `deprecated` | superseded by a newer plan/version and retired. **Terminal.** |

**Terminal statuses:** `completed`, `cancelled`, `deprecated`. No transition
leaves a terminal status except `completed`/`cancelled` → `deprecated` on a
`replan` that supersedes the node (see table).

### Subgraph lifecycle is a SEPARATE, lighter 8-status enum

A `subgraph` (the lightweight runtime control structure inside a parent node)
uses its **own 8-value status enum** — `proposed`, `admitted`, `running`,
`blocked`, `completed`, `failed`, `promoted_to_subloop`, `cancelled`. These are
**DISTINCT from the 15 canonical node statuses defined above**. A subgraph is a
lighter control structure than a node, so it carries a lighter lifecycle;
downstream tooling MUST NOT apply the 15 node statuses to a subgraph, and MUST
NOT apply these 8 subgraph statuses to a node. The two enums never overlap in
scope.

The subgraph enum is authoritative in
[`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) (its lifecycle,
transition examples, control fields, and the Promotion Gate that escalates a
`subgraph` to a directory-materialized `subloop`). This file does not redefine
it — only the boundary is named here so the two enums are never conflated.

---

## State transition table

Each row lists a status, its allowed next statuses, the trigger that fires the
transition, and the evidence required to commit it. A transition MUST NOT be
committed to the checkpoint without its stated evidence.

| from | allowed next | trigger | evidence required to commit |
|------|--------------|---------|-----------------------------|
| `undiscovered` | `discovered` | planner enumerates the node | node object written into `loop.plan.nodes` (or a `subgraph`) |
| `discovered` | `needs_clarification`, `pending`, `cancelled` | analysis of clarity + dependencies | dependency (`requires`) analysis recorded; open questions listed if any |
| `needs_clarification` | `pending`, `cancelled` | question answered / node dropped | answer recorded in checkpoint `open_assumptions` or an evidence entry; on drop, cancellation reason |
| `pending` | `ready`, `cancelled`, `blocked` | topological readiness check (see [readiness rule](./loop_plan_spec.md#63-topological-readiness-rule)) | every `requires` id has `status == completed` in `node_states` |
| `ready` | `running`, `blocked`, `cancelled` | scheduler dispatches the node | `run_id` directory acquired (single-flight); `node.contract.started` set |
| `running` | `verifying`, `waiting_external`, `waiting_user`, `blocked`, `cancelled` | execution completes / pauses | `node.contract.finished` set on completion; pause reason recorded on wait |
| `waiting_external` | `running`, `ready`, `blocked`, `cancelled` | external event arrives / times out | event reference or timeout recorded in `event_log` |
| `waiting_user` | `ready`, `cancelled` | user responds / abandons | user response recorded; on abandon, cancellation reason |
| `blocked` | `ready`, `retry_pending`, `cancelled`, `escalate`* | blocker resolved / escalated | resolution note recorded; `pending_approvals` entry if escalated |
| `verifying` | `completed`, `verification_failed` | `gate` evaluated | evidence-ledger entry with `verdict` (`pass` → `completed`, `fail`/`inconclusive` → `verification_failed`) |
| `verification_failed` | `retry_pending`, `blocked`, `escalate`* | apply `on_failure` ladder | failing evidence-ledger entry; ladder decision recorded |
| `retry_pending` | `ready` | backoff elapsed **and** `attempt < max_attempts` | `node.contract.attempt` incremented; guard read from **persistent** state |
| `completed` | `deprecated` | superseded by `replan` | new `plan_version` supersedes the node |
| `cancelled` | `deprecated` | superseded by `replan` | new `plan_version` supersedes the node |
| `deprecated` | — (terminal) | — | — |

\* `escalate` is the [escalation-ladder](./loop_plan_spec.md#62-on_failure--the-escalation-ladder)
terminus, realised as a transition into a `waiting_user`/`blocked` state bound to
an `approval` node with a `human_approval` gate; recorded in `pending_approvals`.

### Failure-path summary (escalation ladder)

Driven by each node's `on_failure` and `retry_policy`
([`loop_plan_spec.md` §6](./loop_plan_spec.md#6-scheduling--failure-semantics)):

```
verifying --fail--> verification_failed
    ├─ on_failure=local_retry / local_patch, attempt<max_attempts --> retry_pending --> ready
    ├─ on_failure=replan                                          --> blocked (owning node re-materialises subgraph, new plan_version)
    └─ on_failure=escalate  (or retries exhausted)                --> blocked/waiting_user bound to approval node (human_approval)
```

The retry guard (`attempt < max_attempts`) is always evaluated against the
**persistent** `node.contract.attempt`, never an in-memory counter, so the budget
survives a crash.

---

## Persistent state artifacts

Three artifacts hold the runtime state. Each is filesystem-mappable and keyed by
`plan_id` (+ `plan_version`).

### checkpoint fields

The durable snapshot of loop progress. A fresh session reads exactly this to
resume.

| field | type | required | description |
|-------|------|----------|-------------|
| `schema_version` | string | yes | Version of the checkpoint schema. |
| `plan_id` | string | yes | The `loop.plan` this checkpoint tracks. |
| `plan_version` | int | yes | The plan version this checkpoint is valid for. |
| `checkpoint_id` | string | yes | Unique id of this checkpoint snapshot. |
| `created` | string (ISO-8601) | yes | When this checkpoint was written. |
| `phase` | int | yes | Phase counter for `continue_as_new` rollover (see [`concepts.md` §7](./concepts.md#7-why-durability-primitives)). |
| `node_states` | map[node_id -> status] | yes | Current status of every node. Statuses are from the [node status enum](#node-status-enum). |
| `ready_set` | list[node_id] | yes | Nodes currently `ready` for dispatch. |
| `last_completed` | list[node_id] | yes | Nodes most recently moved to `completed`. |
| `blocked` | list[object] | yes | Each: `{node_id, reason}`. Nodes currently `blocked`. |
| `pending_approvals` | list[object] | yes | Each: `{node_id, token, requested}` (`requested` is ISO-8601). Open `escalate`/`approval` handoffs. |
| `next_suggested_action` | string | yes | Human-readable hint for the next agent; advisory only, never a source of truth over the graph. |
| `open_assumptions` | list[string] | yes | Assumptions/answers not yet verified; drives `needs_clarification` resolution. |
| `event_log_ref` | string (path) | yes | Path to the append-only event log (deterministic replay). |
| `evidence_ledger_ref` | string (path) | yes | Path to the [evidence.ledger](#evidence-ledger). |
| `cost_units_spent` | number | yes | Cumulative cost, checked against `termination.max_cost_units`. |
| `iteration` | int | yes | Loop iteration counter, checked against `termination.max_iterations`. |

#### Child-loop checkpoint fields

A **child loop's** (`subloop`'s) `checkpoint.yaml` carries the following fields
**in addition to** the base checkpoint field set defined above. These additions
reconcile with — never replace — the base fields; both the base set and these
additions MUST be present in a child loop's `checkpoint.yaml`. The additions
are authoritative in [`recursive_loops.md` §7.4](./recursive_loops.md#74-child-checkpoint-additions).

| field | type | required | description |
|-------|------|----------|-------------|
| `loop_id` | string | yes | This child loop's id (e.g. `L001.02.03`). |
| `parent_loop_id` | string | yes | The parent loop's id (e.g. `L001.02`). |
| `parent_node_id` | string | yes | The node in the parent plan that owns this child loop. |
| `current_node` | string (node_id) | yes | The node in *this* loop's plan currently in focus for resume. |
| `last_valid_artifacts` | list[string] | yes | Paths of this loop's artifacts confirmed valid at the last checkpoint (safe to reuse on resume). May be empty (`[]`). |
| `next_recommended_action` | string | yes | Advisory hint for the next agent resuming this child loop; never a source of truth over the graph. |
| `open_blockers` | list[object] | yes | Each: `{node_id, reason}`. Blockers currently open in this child loop. May be empty (`[]`). |

**Reconciliation note (child-only vs base-set reuse).**

The base checkpoint fields above (`schema_version`, `plan_id`, `plan_version`,
`checkpoint_id`, `created`, `phase`, `node_states`, `ready_set`, `last_completed`,
`blocked`, `pending_approvals`, `next_suggested_action`, `open_assumptions`,
`event_log_ref`, `evidence_ledger_ref`, `cost_units_spent`, `iteration`) still
apply verbatim to a child loop's `checkpoint.yaml`. Of the additions above:

- **Child-only identity fields — no base equivalent:** `loop_id`,
  `parent_loop_id`, `parent_node_id`. The base set carries no parent/child
  identity fields.
- **Child-only resume-hint fields — no base equivalent:** `current_node`,
  `last_valid_artifacts`. The base set has neither a single-node resume focus
  nor an explicit list of confirmed-valid artifact paths.
- **Child-only advisory field, distinct from a base field with similar
  semantics:** `next_recommended_action`. This is a **separate** field from the
  base `next_suggested_action`; both are present in a child loop's checkpoint,
  and the child addition is scoped to the child's own graph.
- **Structural reuse of the base `blocked` field shape:** `open_blockers`
  mirrors the base `blocked` list-of-`{node_id, reason}` shape, scoped to the
  child's own graph; both fields are present.

### node.contract fields

The per-node execution contract, one per node attempt lineage.

| field | type | required | description |
|-------|------|----------|-------------|
| `node_id` | string | yes | The node this contract governs. |
| `plan_id` | string | yes | Owning plan. |
| `cache_key` | string | yes | `hash(inputs + prompt + model + config)`; a matching prior success permits a resumable skip (Bazel-style, [`concepts.md` §7](./concepts.md#7-why-durability-primitives)). |
| `attempt` | int | yes | Persistent attempt counter; the retry guard reads this, never memory. |
| `status` | enum | yes | Current status from the [node status enum](#node-status-enum). |
| `gate` | object | yes | The node's gate (`{kind, threshold, rubric, evidence_ref}`), as defined in [`loop_plan_spec.md` §4.1](./loop_plan_spec.md#41-gate-object). |
| `retry_policy` | object | yes | `{max_attempts, backoff_base_seconds, jitter}`, as in [`loop_plan_spec.md` §6.1](./loop_plan_spec.md#61-retry_policy-object). |
| `on_failure` | enum | yes | Ladder start: `local_retry`, `local_patch`, `replan`, or `escalate`. |
| `evidence_ref` | string (path) | yes | Path to this node's evidence artifact. |
| `started` | string (ISO-8601) \| null | yes | When the current attempt started, or `null`. |
| `finished` | string (ISO-8601) \| null | yes | When the current attempt finished, or `null`. |
| `compensation_of` | string (node_id) \| null | yes | If this is a `compensation` node, the `node_id` it undoes (saga pairing); else `null`. |

### evidence.ledger

An append-only list of gate-verdict entries. Each entry:

| field | type | required | description |
|-------|------|----------|-------------|
| `entry_id` | string | yes | Unique id of the ledger entry. |
| `node_id` | string | yes | The node the verdict is for. |
| `gate_kind` | enum | yes | One of the [gate kinds](./loop_plan_spec.md#42-gate-kinds): `automated_check`, `test`, `llm_judge`, `self_consistency`, `evaluator_optimizer`, `step_verifier`, `human_approval`, `artifact_exists`. |
| `verdict` | enum | yes | `pass`, `fail`, or `inconclusive`. |
| `score` | number (0..1) \| null | yes | Numeric score for scored gates, or `null` for pass/fail gates. |
| `artifact_path` | string | yes | Path to the evidence artifact this entry attests. |
| `rationale` | string | yes | Why the verdict was reached. |
| `recorded` | string (ISO-8601) | yes | When the entry was recorded. |
| `verifier` | enum | yes | `agent`, `subagent`, `user`, or `script`. |

A node may transition `verifying → completed` **only** when its latest ledger
entry has `verdict == pass`. A `fail` or `inconclusive` forces
`verification_failed`.

---

## Resume from a blank session

The defining requirement: a brand-new session with **no prior chat memory** must
continue correctly. The algorithm reads only the persistent artifacts above.
Execute these steps in order.

1. **Acquire / confirm the run.** Locate the `run_id` directory (the idempotency
   key). If none exists this is a fresh start; if one exists, this is a resume.
   Never create a duplicate — respect `O_CREAT|O_EXCL` single-flight semantics
   ([`concepts.md` §7](./concepts.md#7-why-durability-primitives)).
2. **Read state.** Load the latest **checkpoint** (highest `checkpoint_id` /
   `created`) for the current `plan_id` and `plan_version`. Read
   `node_states`, `ready_set`, `blocked`, `pending_approvals`, `iteration`,
   `cost_units_spent`, `phase`, `open_assumptions`.
3. **Verify evidence.** For every node marked `completed` in `node_states`,
   confirm a matching `evidence.ledger` entry with `verdict == pass` exists at
   its `evidence_ref`. Any `completed` node lacking passing evidence is demoted to
   `verifying` (its gate must be re-run) — the checkpoint is not trusted over the
   ledger.
4. **Verify consistency.** Recompute readiness from the graph: for each `pending`
   node, check whether every `requires` id is `completed`
   ([readiness rule](./loop_plan_spec.md#63-topological-readiness-rule)). Rebuild
   `ready_set` from the graph; if it disagrees with the stored `ready_set`, the
   recomputed set wins. Confirm no node is `running` (a `running` node in a fresh
   session means a prior crash — reconcile via the `event_log` and move it to
   `retry_pending` or `verifying`).
5. **Check termination.** If `iteration >= termination.max_iterations`, or
   `cost_units_spent >= termination.max_cost_units`, or any `failure_criteria`
   holds, stop and escalate rather than dispatch.
6. **Identify ready nodes.** Take the recomputed ready set: nodes whose `status`
   is `ready` (all `requires` `completed`).
7. **Pick the next node.** Among ready nodes, honour the
   [parallel dispatch rule](./loop_plan_spec.md#64-parallel-dispatch-rule):
   dispatch `parallelizable: true` nodes concurrently where the host allows,
   otherwise pick the single highest-`priority` node. Consult
   `next_suggested_action` only as a tie-breaking hint.
8. **Handle open handoffs.** If `pending_approvals` is non-empty, surface those
   `approval` nodes (with their `token`) to the user before continuing dependent
   work.
9. **Execute, then checkpoint.** Run the chosen node(s); evaluate the `gate`;
   append the `evidence.ledger` entry; update `node_states`; write a new
   checkpoint. Repeat from step 6 until `termination.done_when` is satisfied.

Every step above reads persistent state only — never memory — which is exactly
what makes a blank session safe (see
[`concepts.md` §9](./concepts.md#9-why-it-must-resume-from-a-blank-session)).

---

## See also

- [`loop_plan_spec.md`](./loop_plan_spec.md) — plan/node field dictionary, gate
  object, retry policy, escalation ladder, and the canonical **Glossary**.
- [`concepts.md`](./concepts.md) — why the model is shaped this way.
- [`recursive_loops.md`](./recursive_loops.md) — directory-materialized child
  loops; defines the child-checkpoint additions added on top of the base
  checkpoint field set in this file (§7.4).
- [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) — the three-tier
  execution model; defines the **8-status subgraph lifecycle** (distinct from
  the 15 node statuses defined here) and the Promotion Gate that escalates a
  `subgraph` to a `subloop`.
- [`./research_durable_loops.md`](./research_durable_loops.md) — checkpoint,
  event-sourced replay, idempotency, saga sources.
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) — state
  machines for agents, evidence gates, DAG readiness sources.
