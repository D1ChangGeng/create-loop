# `loop.plan` Specification — Field Dictionary

*Diataxis type: **reference**. This document is the authoritative, exhaustive
field dictionary for the `loop.plan` artifact. Downstream JSON schemas, YAML
templates, validator scripts, and examples copy these field names, types, and
enum values **byte-for-byte**. When a spelling is ambiguous, the
[Glossary](#glossary) at the end of this file is canonical.*

*For the reasoning behind these shapes, see
[`concepts.md`](./concepts.md). For state, transitions, checkpoint, node
contract, and evidence ledger, see [`state_model.md`](./state_model.md).*

Conventions used throughout:

- All field names and all enum values are **lowercase snake_case**.
- All dates/timestamps are **ISO-8601** strings (e.g. `2026-07-01` or
  `2026-07-01T14:30:00Z`).
- `list[T]` = ordered array of `T`. `map[K->V]` = object keyed by `K`.
- `null` is an explicit permitted value where stated; otherwise a field is
  required.

---

## 1. Top-level `loop.plan` fields

A `loop.plan` is a single object with the following fields.

| field | type | required | description |
|-------|------|----------|-------------|
| `schema_version` | string | yes | Version of the `loop.plan` schema this document conforms to (e.g. `"1.0.0"`). Distinct from `plan_version`. |
| `plan_id` | string | yes | Stable unique identifier for this plan. Used as the primary key across the checkpoint, node contracts, and evidence ledger. |
| `goal` | string | yes | The user's stated goal, verbatim. |
| `true_intent` | string | yes | The underlying intent surfaced by the Loop Startup (Charter) interview — what success *really* means, which may be broader or narrower than `goal`. |
| `non_goals` | list[string] | yes | Explicitly out-of-scope outcomes. May be empty (`[]`). |
| `success_criteria` | list[object] | yes | Measurable definitions of done. Each entry: see [§1.1](#11-success_criteria-entry). |
| `failure_criteria` | list[string] | yes | Conditions that mean the task has failed and must stop or escalate. May be empty (`[]`). |
| `termination` | object | yes | Bounds and the done condition for the whole loop. See [§1.2](#12-termination-object). |
| `constraints` | list[string] | yes | Hard constraints the plan and its execution must respect (budget, tech, policy). May be empty (`[]`). |
| `nodes` | list[object] | yes | The DAG. Each entry is a [node object](#2-node-object). Must be non-empty. |
| `created` | string (ISO-8601 date) | yes | Date the plan was created. |
| `plan_version` | int | yes | Monotonic integer, incremented each time the plan is re-generated (`replan`). The plan for a given `plan_version` is immutable (Graph Harness rule, [`concepts.md` §7](./concepts.md#7-why-durability-primitives)). |
| `plan_history` | list | yes | Append-only provenance, one entry per `plan_version`. Each entry is `{plan_version:int, reason:string, superseded_at:string\|null, goal_hash:string, true_intent_hash:string}` where the hashes are `sha256` of the normalized (trim + collapse-whitespace) `goal` / `true_intent` at that version. The latest entry's hashes MUST match the current `goal`/`true_intent`, and its `plan_version` MUST equal the top-level `plan_version` — so a **goal change cannot be made silently**: it requires a new, provenanced, human-approved version bump (validator rules R26 goal-change, R27 malformed history; goal-sovereignty per [`human_approval.md`](./human_approval.md) and SKILL §3). |

### 1.0 Goal-change sovereignty (plan_history)

The top-level `goal` and `true_intent` are the user's to change, not the agent's.
`plan_history` makes this machine-checkable: because the validator recomputes the
normalized hash of the current `goal`/`true_intent` and compares it to the latest
recorded entry, any mutation that was not captured as an approved version bump is
rejected (R26). To legitimately change the goal, add a new `plan_history` entry
(new `plan_version`, a `reason`, fresh hashes) backed by an approved
`human_approval` decision — see [`human_approval.md` §7](./human_approval.md).

### 1.1 `success_criteria` entry

| field | type | required | description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique id of the criterion within the plan. |
| `statement` | string | yes | Human-readable definition of the criterion. |
| `measurable` | bool | yes | `true` if the criterion has an objective, checkable test; `false` if it is a judgement call (which should be gated by `llm_judge` or `human_approval`). |

### 1.2 `termination` object

| field | type | required | description |
|-------|------|----------|-------------|
| `max_iterations` | int | yes | Hard cap on loop iterations (see checkpoint `iteration` in [`state_model.md`](./state_model.md#checkpoint-fields)). |
| `max_wall_clock_hours` | number \| null | yes | Wall-clock budget in hours, or `null` for unbounded. |
| `max_cost_units` | number \| null | yes | Budget in abstract cost units, or `null` for unbounded. Tracked against checkpoint `cost_units_spent`, which is reconciled from the event log (so a crash cannot roll the counter back). One cost unit ≈ one activity / LLM call; each node accrues into `node.contract.cost_units`. |
| `done_when` | string | yes | The single overriding done condition, typically "all `success_criteria` met and all top-level nodes `completed`". |
| `max_depth` | int | yes | Maximum child-loop recursion depth (a top-level loop is depth 0). The validator rejects a plan whose declared `child_loops` nest deeper than this (rule R28) — bounds unbounded recursion. |
| `max_child_loops` | int | yes | Maximum total number of directory-materialized child loops the whole tree may spawn. Enforced statically (R28) and at spawn time against the reconciled counter. |
| `max_active_subgraphs` | int \| null | no | Optional cap on concurrently-active inline subgraphs. |

Together `max_depth` + `max_child_loops` + `max_cost_units` are the **enforced**
growth bounds: the validator rejects a plan whose structure can exceed them, and
a resuming runner refuses to spawn past them using the event-log-reconciled
counters. This closes the "unbounded recursion / declarative-only budget" gap.

---

## 2. `node` object

Each entry in `loop.plan.nodes` is a node. Nodes are the milestones of the DAG;
edges are modelled implicitly through the `requires` field
([§3](#3-edges-are-artifact-dependencies)).

| field | type | required | description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique node identifier within the plan (and within any subgraph fragment). Referenced by other nodes' `requires`. |
| `kind` | enum | yes | One of the [node kinds](#node-kinds): `milestone`, `gate`, `mapper`, `branch`, `fanout`, `join`, `approval`, `compensation`. Default is `milestone`. |
| `title` | string | yes | Short human-readable name. |
| `design_invariant` | bool | yes | `true` if this node is design-time-invariant (belongs at the top level); `false` if it is runtime-discovered (belongs inside a subgraph). See [§5](#5-design-time-invariant-vs-runtime-discovered). |
| `status` | enum | yes | Current status. One of the 15 [node statuses](#node-statuses) defined authoritatively in [`state_model.md`](./state_model.md#node-status-enum). |
| `requires` | list[node_id] | yes | Ids of nodes this node depends on. This node is `ready` only when every id here is `completed`. May be empty (`[]`) for a root node. |
| `produces` | list[string] | yes | Artifact paths or ids this node produces. These are the artifacts that satisfy other nodes' dependencies. May be empty (`[]`). |
| `inputs` | list | yes | Inputs consumed by this node (artifact refs, parameters). Feeds the node's `cache_key`. May be empty (`[]`). |
| `preconditions` | list[string] | yes | Conditions that must hold before the node may run, beyond `requires`. May be empty (`[]`). |
| `postconditions` | list[string] | yes | Conditions guaranteed true after successful completion. May be empty (`[]`). |
| `gate` | object \| null | yes | The evidence gate. `null` only for trivial nodes. See [§4](#4-evidence-gates). |
| `retry_policy` | object | yes | Retry budget. See [§6.1](#61-retry_policy-object). |
| `on_failure` | enum | yes | Where this node starts on the [escalation ladder](#escalation-ladder): `local_retry`, `local_patch`, `replan`, or `escalate`. |
| `priority` | int | yes | Scheduling priority among simultaneously-ready nodes (higher runs first). |
| `risk` | enum | yes | One of `low`, `med`, `high`. |
| `parallelizable` | bool | yes | `true` if this node may run concurrently with other ready nodes. |
| `allow_subgraph` | bool | yes | `true` if this node may materialise a subgraph at runtime when it discovers it is too big/dark/complex. |
| `subgraph` | object \| null | yes | A nested `loop.plan` fragment (see [§7](#7-subgraph-recursion)), or `null` if none has been materialised. |
| `child_loops` | list[child_loop_ref] | yes | List of references to directory-materialized child loops (subloops) spawned from this node. Empty `[]` when the node has no child loops. Each ref is `{loop_id, path, spawn_reason, status, closeout}` where `status` is one of the [15 canonical node statuses](#node-statuses) and `path` is relative to this loop's directory. This is the heavyweight, isolated counterpart to the inline `subgraph` field; see [`recursive_loops.md`](./recursive_loops.md) and [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md). |
| `assignee` | enum | yes | Who executes the node: `agent`, `user`, or `subagent`. |
| `notes` | string | yes | Free-form notes. May be `""`. |

---

## 3. Edges are artifact dependencies

There is **no separate edge object**. An edge is a single entry in a node's
`requires` list, and its type is always **produces/requires** — a real produced
**artifact dependency**, exactly like GNU Make's mtime dependencies
([`concepts.md` §2](./concepts.md#2-why-a-dag-and-not-a-checklist)).

> **Rule.** A `requires` edge MUST represent a real artifact dependency — node B
> `requires` node A **iff** B consumes an artifact that A `produces`. A
> `requires` edge MUST NOT encode habitual execution order, author preference,
> or "I usually do this first". If B does not need A's output, there is no edge,
> and B may run in parallel with A.

### 3.1 Control-flow vocabularies (mapped from LangGraph)

The four control-flow shapes, mapped from
[LangGraph](./research_dags_multiagent.md), are expressed as follows. These are
descriptive labels for how edges/nodes behave, not extra fields.

| control-flow vocabulary | LangGraph primitive | expressed in `loop.plan` as |
|-------------------------|---------------------|-----------------------------|
| `fixed` | `add_edge` | a static entry in `requires` (an unconditional dependency edge) |
| `conditional` | conditional edge / router | a `branch` node that selects among successors |
| `command` | `Command(update=…, goto=…)` | a node that updates state **and** routes to a successor in one return |
| `fanout` | `Send` / map-reduce | a `fanout` node dispatching parallel work, merged by a `join` node |

---

## 4. Evidence gates

Every non-trivial node carries a `gate`. A node **cannot** transition to
`completed` until its gate passes. A failing gate sends the node to
`verification_failed` (see [`state_model.md`](./state_model.md#state-transition-table)).

### 4.1 `gate` object

| field | type | required | description |
|-------|------|----------|-------------|
| `kind` | enum | yes | One of the [gate kinds](#gate-kinds): `automated_check`, `test`, `llm_judge`, `self_consistency`, `evaluator_optimizer`, `step_verifier`, `human_approval`, `artifact_exists`. |
| `threshold` | number (0..1) \| null | yes | Pass threshold for scored gates (e.g. `llm_judge`, `self_consistency`, `step_verifier`). `null` for pass/fail gates (`automated_check`, `test`, `human_approval`, `artifact_exists`). |
| `rubric` | string (path) \| null | yes | Path to a rubric document for judged gates, or `null`. |
| `evidence_ref` | string (path) | yes | Path where this gate's evidence is written. The corresponding evidence-ledger entry is defined in [`state_model.md`](./state_model.md#evidence-ledger). |

### 4.2 Gate kinds

| gate kind | meaning | scored? | source |
|-----------|---------|---------|--------|
| `automated_check` | deterministic scripted check (lint, schema-validate) | no (`threshold: null`) | [DAG research §3](./research_dags_multiagent.md) |
| `test` | code tests run in a sandbox, as evidence | no (`threshold: null`) | CodeAct / eval-driven TDD, [DAG research §3.7–3.8](./research_dags_multiagent.md) |
| `llm_judge` | LLM-as-a-judge scores output against a rubric | yes | Zheng et al. 2023, [DAG research §3.1](./research_dags_multiagent.md) |
| `self_consistency` | sample N times, require agreement | yes | Wang et al. 2022, [DAG research §3.2](./research_dags_multiagent.md) |
| `evaluator_optimizer` | generate → critique → revise loop until acceptable | yes | Anthropic evaluator-optimizer, [DAG research §3.5](./research_dags_multiagent.md) |
| `step_verifier` | step-level / process-reward verification | yes | PRMs, [DAG research §3.6](./research_dags_multiagent.md) |
| `human_approval` | a human signs off | no (`threshold: null`) | HITL, [durable-loops research §3.1](./research_durable_loops.md) |
| `artifact_exists` | required artifact is present (cheapest gate) | no (`threshold: null`) | build-system existence check |

---

## 5. Design-time-invariant vs runtime-discovered

The `design_invariant` boolean on each node encodes the placement rule. It is the
governing structural constraint of a `loop.plan`.

> A node has `design_invariant: true` **iff** it is **known at design time AND
> invariant for the task class** (mandatory, and unchanging regardless of
> research/vendor/implementation/runtime findings). Only `design_invariant: true`
> nodes may appear at the **top level** (`loop.plan.nodes`). All
> `design_invariant: false` (runtime-discovered) nodes MUST live inside a
> [`subgraph`](#7-subgraph-recursion).

The rule is **not** "will it definitely happen? → top level". It is "known at
design time **AND** invariant? → top level".

| type | `design_invariant` | example | placement |
|------|--------------------|---------|-----------|
| design-time invariant | `true` | goal clarification, discovery, risk screen, verification, handoff, recovery protocol | top-level `loop.plan.nodes` |
| runtime-discovered | `false` | which vendors compared, which files changed, which tests written, which defects found | inside a `subgraph` of the owning node |

See [`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes)
for the rationale.

---

## 6. Scheduling & failure semantics

### 6.1 `retry_policy` object

| field | type | required | description |
|-------|------|----------|-------------|
| `max_attempts` | int | yes | Maximum number of execution attempts for this node before escalating past `local_retry`. |
| `backoff_base_seconds` | number | yes | Base backoff between attempts (multiplied per attempt for exponential backoff). |
| `jitter` | bool | yes | `true` to add randomised jitter to backoff. |

> **Durability rule.** The guard that enforces `retry_policy` reads the
> **persistent** state (the checkpoint / node contract on disk), never in-memory
> state, so the retry budget survives a crash. The authoritative attempt counter
> is `node.contract.attempt` in [`state_model.md`](./state_model.md#nodecontract-fields).

### 6.2 `on_failure` — the escalation ladder

`on_failure` names the node's starting rung on the bounded, ordered escalation
ladder:

```
local_retry  ->  local_patch  ->  replan  ->  escalate
```

| ladder step | meaning |
|-------------|---------|
| `local_retry` | re-run the same node under its `retry_policy`. |
| `local_patch` | apply a small local correction, then retry. |
| `replan` | the node's approach is wrong; regenerate its subgraph (new `plan_version` for that fragment). |
| `escalate` | hand off to a human via an `approval` node (`human_approval` gate). |

The ladder is bounded (finite steps) and ordered (never skips backward). The
transitions it drives are defined in
[`state_model.md` §state transition table](./state_model.md#state-transition-table).

### 6.3 Topological readiness rule

A node transitions to `ready` **iff** its `status` is `pending` **and** every
`node_id` in its `requires` list has `status == completed`. A node with
`requires: []` is eligible to become `ready` immediately once `pending`.

### 6.4 Parallel dispatch rule

All nodes that are simultaneously `ready` and have `parallelizable: true` may be
dispatched concurrently. Among competing ready nodes, higher `priority` is
dispatched first. Readiness is recomputed from the dependency graph plus recorded
statuses — never from an authored order.

### 6.5 Join semantics

A `join` node has multiple entries in `requires` (the branches being merged). It
becomes `ready` only when **all** of them are `completed`. A `join` following a
`fanout` collects the fanned-out results (map-reduce collect step) before its
successors may proceed.

### 6.6 Subgraph recursion rule

A node with `kind: mapper` or `allow_subgraph: true` may, at runtime, discover it
is too big/dark/complex and **materialise a child `loop.plan` fragment** into its
`subgraph` field. The child fragment references its parent through `parent_ref`
(see [§7](#7-subgraph-recursion)). The parent node cannot transition to
`completed` until every node in its materialised `subgraph` is in a terminal
state and the parent's own `gate` passes.

---

## 7. `subgraph` recursion

A `subgraph` is an **isomorphic** `loop.plan` fragment: it has the same field
shape as a top-level plan, with one addition. It is materialised by a `mapper`
node or any node with `allow_subgraph: true`.

A `subgraph` fragment object contains:

| field | type | required | description |
|-------|------|----------|-------------|
| `parent_ref` | string (node_id) | yes | The `id` of the parent node in the enclosing plan that owns this subgraph. |
| `schema_version` | string | yes | Same meaning as top-level; the fragment conforms to the same schema. |
| `plan_version` | int | yes | Version of this fragment; incremented on `replan` of the fragment. |
| `nodes` | list[node] | yes | The fragment's nodes. These are typically `design_invariant: false` (runtime-discovered). |

Because a subgraph is isomorphic, every rule in this document (readiness,
parallel dispatch, gates, retry, escalation) applies recursively within it. Only
`design_invariant: true` nodes may appear at the top level; runtime-discovered
work is confined to subgraphs.

### 7.1 `subgraph` vs `child_loops` (subloop): when to use which

The `subgraph` field and the `child_loops` field are NOT interchangeable. They
are the two non-action tiers of the execution model:

- `subgraph` — **inline, lightweight, same-run, node-hosted**. A nested plan
  fragment carried inside the node's own `subgraph` field and recovered through
  the parent loop. Governed by the parent node, and shares its state, evidence,
  logs, and budget.
- `child_loops` (subloop) — **directory-materialized, isolated, recoverable,
  referenced by path + return contract**. Each entry points at an independent
  child loop directory (with its own `loop.plan.yaml`, `loop.state.yaml`,
  `checkpoint.yaml`, `evidence.ledger.yaml`, `artifacts/`, and `closeout.md`)
  reachable via the path-relative `path` field and integrated by the parent via
  its `closeout` file plus the child's `return_contract`.

> Use `action` for simple single-step work, `subgraph` for local multi-step
> work, `subloop` for independently governable work.

The full three-tier model (`action` / `subgraph` / `subloop`), the Promotion
Gate that moves work between tiers, the 8-value subgraph status enum, the
`SG-` subgraph id pattern, and the per-node `node.runtime.yaml` layout are
defined authoritatively in
[`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md). The directory
convention, `loop.meta.yaml` field set, `child_loops[]` reference shape, and
Sub-loop Admission Gate are defined authoritatively in
[`recursive_loops.md`](./recursive_loops.md).

---

## 8. Related persistent state

The `loop.plan` is the *plan*. Its *runtime state* lives in three companion
artifacts defined authoritatively in [`state_model.md`](./state_model.md):

- **checkpoint** — the durable snapshot of progress
  ([fields](./state_model.md#checkpoint-fields)).
- **node.contract** — the per-node execution contract
  ([fields](./state_model.md#nodecontract-fields)).
- **evidence.ledger** — the append-only record of gate verdicts
  ([fields](./state_model.md#evidence-ledger)).

---

## Glossary

*Canonical spellings of every locked token. Downstream schemas, templates,
validators, and examples MUST cite these verbatim. All values are lowercase
snake_case.*

### Node statuses (15) — authoritative set defined in [`state_model.md`](./state_model.md#node-status-enum)

`undiscovered`, `discovered`, `needs_clarification`, `pending`, `ready`,
`running`, `waiting_external`, `waiting_user`, `blocked`, `verifying`,
`verification_failed`, `retry_pending`, `completed`, `cancelled`, `deprecated`

Terminal statuses: `completed`, `cancelled`, `deprecated`.

### Node kinds (8)

`milestone` (default), `gate`, `mapper` (runtime subgraph expansion), `branch`
(conditional route), `fanout` (parallel dispatch), `join` (fan-in / merge),
`approval` (human control node), `compensation` (saga undo)

### Gate kinds (8)

`automated_check`, `test`, `llm_judge`, `self_consistency`,
`evaluator_optimizer`, `step_verifier`, `human_approval`, `artifact_exists`

### Escalation ladder steps (4, ordered)

`local_retry` → `local_patch` → `replan` → `escalate`

### Edge type (1)

`produces/requires` — the sole edge type, modelled via a node's `requires` list.

### `child_loops` node field (required; array; empty sentinel `[]`)

`child_loops` — each entry is a `child_loop_ref` object with fields: `loop_id`,
`path` (relative to this loop's directory), `spawn_reason`, `status` (one of the
[15 canonical node statuses](#node-statuses)), `closeout`. The
directory-materialized child loop itself, the `child_loops[]` reference shape,
the `return_contract`, the `closeout.md` return interface, and the Sub-loop
Admission Gate are defined authoritatively in
[`recursive_loops.md`](./recursive_loops.md). The three-tier execution model
(`action` / `subgraph` / `subloop`) and the Promotion Gate that moves work
between tiers are defined in
[`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md).

### Control-flow vocabularies (4, from LangGraph)

`fixed`, `conditional`, `command`, `fanout`

### `on_failure` enum (4)

`local_retry`, `local_patch`, `replan`, `escalate`

### `risk` enum (3)

`low`, `med`, `high`

### `assignee` enum (3)

`agent`, `user`, `subagent`

### `verdict` enum (3) — defined in [`state_model.md`](./state_model.md#evidence-ledger)

`pass`, `fail`, `inconclusive`

### `verifier` enum (4) — defined in [`state_model.md`](./state_model.md#evidence-ledger)

`agent`, `subagent`, `user`, `script`

### Durability primitives

`run_id_directory` (idempotency key, `O_CREAT|O_EXCL` single-flight),
`cache_key` (`hash(inputs + prompt + model + config)`), `event_log`
(append-only, deterministic replay), `workflow` (deterministic step) vs
`activity` (side-effect), `continue_as_new` (phase rollover), `saga_compensation`
(paired undo node), `graph_harness` (immutable plan per version; planning /
execution / recovery layers).
