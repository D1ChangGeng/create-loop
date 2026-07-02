# Recursive Directory-Materialized Child Loops

*Diataxis type: **reference**. This document is the authoritative, exhaustive
vocabulary for **recursive directory-materialized child loops** — the mechanism
by which a non-trivial child graph is materialized as an **isolated child loop
directory** rather than embedded inline inside a parent plan. Downstream JSON
schemas, YAML templates, validator scripts, examples, `SKILL.md`, and tests copy
these directory patterns, field names, enum values, and reference shapes
**byte-for-byte**. When a spelling is ambiguous, the [Glossary](#glossary) at the
end of this file is canonical.*

*This document does NOT invent new node statuses, gate kinds, or ladder rungs. It
**reuses** the locked vocabulary defined elsewhere and only adds the directory
convention, the `loop.meta.yaml` field set, the `child_loops` node-field
reference shape, the child-checkpoint additions, the INDEX files, and the
Admission Gate. For the plan/node field dictionary and the existing inline
`subgraph` / `allow_subgraph` fields, see
[`loop_plan_spec.md`](./loop_plan_spec.md). For the 15-status enum, checkpoint,
node.contract, and evidence.ledger field sets, see
[`state_model.md`](./state_model.md). For durability primitives and the run-id
directory, see [`concepts.md`](./concepts.md). For evidence-driven growth, see
[`live_loop_semantics.md`](./live_loop_semantics.md). For the transient/durable
boundary against `.agents/knowledge/`, see
[`self_evolution_integration.md`](./self_evolution_integration.md).*

Conventions used throughout (identical to the rest of the package):

- All field names and all enum values are **lowercase snake_case**.
- All dates/timestamps are **ISO-8601** strings (e.g. `2026-07-01` or
  `2026-07-01T14:30:00Z`).
- All slugs are **kebab-case**, English only, lowercase.
- `list[T]` = ordered array of `T`. `map[K->V]` = object keyed by `K`.
- `null` is an explicit permitted value where stated; otherwise a field is
  required. Absence is always explicit (the explicit-sentinel invariant, see
  [§10](#10-the-child_loops-node-field-locked-schema-decision)).

---

## 1. The thesis

Every non-trivial child graph MUST be materialized as an **isolated child loop
directory** — not as an inline nested checklist embedded inside the parent plan.

A **child loop** is a scoped, recoverable, auditable execution unit. It has its
own plan, its own state, its own evidence ledger, its own checkpoint, its own
artifacts, its own logs, its own closeout, and optionally its own nested child
loops. It is **isomorphic** to a top-level loop — the same per-loop directory
shape holds at every level of recursion ([§5](#5-the-isomorphic-per-loop-directory)).

The parent references the child by **path + return contract**, never by
embedding the child graph inline. Child loops may recursively spawn further
child loops using the same directory convention, to arbitrary depth. A child
loop **MUST NOT** mutate parent state directly except through an explicit
merge / return / gate-update protocol — the `return_contract`
([§7](#7-return_contract-and-closeoutmd-the-return-interface)) and the isolation
rule ([§9](#9-isolation-rule-for-parallelism)).

The decision rule, verbatim:

> **If a problem needs its own plan, state, evidence, checkpoint, or closeout, it
> should be a child loop.**

---

## 2. Two recursion mechanisms coexist

The package now has **two** recursion mechanisms, and they are NOT
interchangeable. The [Admission Gate](#8-sub-loop-admission-gate) decides which
applies. The distinction is the load-bearing concept of this document.

| dimension | inline `subgraph` (EXISTING) | directory-materialized `child_loop` (NEW) |
|-----------|------------------------------|-------------------------------------------|
| what it is | a nested `loop.plan` fragment embedded inside a node | an isolated per-loop directory on disk |
| defined in | [`loop_plan_spec.md` §7](./loop_plan_spec.md#7-subgraph-recursion) | this document |
| node field that carries it | `subgraph` (`object \| null`) + `allow_subgraph` (`bool`) | `child_loops` (`list`, NEW — see [§10](#10-the-child_loops-node-field-locked-schema-decision)) |
| weight | lightweight | heavyweight |
| lifetime | **same run**, same session lineage | isolated, independently recoverable across sessions/agents |
| storage | stays inside the parent `loop.plan.yaml` | its own directory under the parent's `_loops/` |
| own checkpoint? | no — shares the parent checkpoint | **yes** — own `checkpoint.yaml` |
| own evidence ledger? | no — shares the parent `evidence.ledger.yaml` | **yes** — own `evidence.ledger.yaml` |
| own closeout? | no | **yes** — `closeout.md` is its return interface |
| typical use | small runtime expansion of one node (Live Loop growth) | non-trivial work: high complexity, parallelism, independent audit, recursive decomposition |
| parent link | `parent_ref` (node_id) inside the fragment | `child_loops[]` reference from the node + `loop.meta.yaml.parent` |
| can spawn grandchildren as directories? | no (would itself trip the Admission Gate) | **yes** — recursion via its own `_loops/` |

Both mechanisms preserve the isomorphism principle
([`concepts.md` §4](./concepts.md#4-why-recursion-isomorphic-subgraphs)): a
`subgraph` is an isomorphic *plan fragment*; a `child_loop` is an isomorphic
*whole loop directory*. The inline `subgraph` remains the default for small,
same-run natural growth ([`live_loop_semantics.md`](./live_loop_semantics.md));
the directory-materialized `child_loop` is the escalation for work that needs its
own plan, state, evidence, checkpoint, or closeout.

---

## 3. Directory root & naming (LOCKED)

### 3.1 Root

- Root of all loops: `.agents/loops/`
  (the canonical `run_id_directory` home from
  [`concepts.md` §7](./concepts.md#7-why-durability-primitives) and
  [`self_evolution_integration.md` §1.1](./self_evolution_integration.md)).

### 3.2 Directory-name patterns

| level | directory-name pattern | example |
|-------|------------------------|---------|
| top-level (root) loop | `L<seq>-<slug>` | `L001-create-loop-skill` |
| child loop (under parent's `_loops/`) | `<parent-id>.<local-seq>-<slug>` | `L001.02-design-loop-spec` |
| grandchild loop (under child's `_loops/`) | `<parent-id>.<local-seq>-<slug>` (append one `.<local-seq>` per level) | `L001.02.01-state-model` |

- `seq` = **3-digit zero-padded** integer at the top level (`001`, `002`, …),
  immutable once created.
- `local-seq` = the child's local counter **assigned by the parent loop**,
  zero-padded to 2 digits (`01`, `02`, …), immutable once created.
- A child directory name **MUST start with the loop_id**, then exactly one short
  slug, joined by a single hyphen after the id.

### 3.3 Loop ID rule (LOCKED)

- Top-level loop id: `L001` (`L` + the 3-digit `seq`).
- Child loop id: `L001.02` (parent id + `.` + 2-digit `local-seq`).
- Nested (grandchild) loop id: `L001.02.01` (append one `.<local-seq>` per
  level of recursion).
- Local seq is assigned **by the parent loop** (the parent owns the counter
  namespace for its direct children).
- **Loop IDs are IMMUTABLE once created.** They are the primary key referenced by
  every path, log line, checkpoint, INDEX entry, and parent-child contract.

### 3.4 Slug rule (LOCKED)

A slug:

- is **lowercase**;
- is **kebab-case** (words joined by single hyphens);
- is **English only**;
- is **2–5 words**;
- is **≤ 32 characters**;
- contains **NO status** (no `-running`, `-done`, `-blocked`);
- contains **NO date** (no `2026-07-01`);
- contains **NO punctuation except the hyphen**.

### 3.5 Directory-name rule (LOCKED)

- A directory name **MUST start with the loop_id**, followed by exactly **one**
  short slug.
- Recommended **maximum directory-name length: 48 characters**.
- A directory is **NEVER renamed** because of status changes (or any other
  mutable property).

### 3.6 Rationale: names carry only "enough to identify + stable to reference"

Directory names carry **only** what is needed to *identify* a loop and to remain
*stable* to reference. Everything else — full semantics, current state,
parent-child relation, spawn reason, return contract, timestamps, ownership —
lives in `loop.meta.yaml` ([§6](#6-loopmetayaml-exact-field-set)) and
`loop.state.yaml`. Two concrete reasons:

- **Truncation hides semantics.** Long names get cut off in file trees, `ls`
  output, path breadcrumbs, and log lines; the cut-off portion is exactly the
  part a reader needs. A short `loop_id + slug` survives truncation.
- **Path operations stay robust.** Agents perform path joins, globs, and
  string comparisons on these names constantly. Short, stable, punctuation-free
  names make those operations deterministic and cheap; long or mutable names make
  them brittle.

### 3.7 Why NOT date-as-primary-id

A date prefix (e.g. `2026-07-01-design-loop-spec`) is rejected because:

- **It eats prefix space.** Ten characters of date push the identifying slug
  past the truncation boundary.
- **Truncation hides semantics.** As above — the date survives, the meaning
  does not.
- **Same-day loops still need a counter.** Two loops created on the same day
  collide, so a sequence counter is required anyway — the date adds nothing the
  counter does not.
- **A date is neither an execution relation nor a topological relation.** The
  loop_id (`L001.02.01`) already encodes parent-child topology; a date encodes
  nothing structural.
- The creation date belongs in `loop.meta.yaml.created_at`, not in the
  directory name.

### 3.8 Why NOT status-in-name

A status suffix (e.g. `L001.02-design-loop-spec-running`, `…-done`) is rejected
because:

- **Status changes.** A directory named `…-running` becomes wrong the moment the
  loop finishes.
- **Renaming breaks references.** Renaming a directory would break **every**
  referencing path, log line, checkpoint reference, INDEX entry, and
  parent-child return contract that points at it.
- Status belongs in `loop.state.yaml` (live status) and `loop.meta.yaml.status`
  (identity-level status), never in the directory name. **Directory names must
  stay stable.**

---

## 4. Directory-name vocabulary: control vs content

Within any loop directory, a naming convention distinguishes **loop control
structure** from **work content**:

| prefix convention | meaning | examples |
|-------------------|---------|----------|
| **underscore-prefixed directory** (`_…`) | loop **control** structure — the recursion / archival machinery | `_loops/`, `_archive/` |
| **non-underscore directory / plain file** | **work content** — what the loop actually produces or records | `artifacts/`, `loop.plan.yaml`, `closeout.md` |

This convention lets an agent (or a `ls` scan) tell at a glance which entries are
scaffolding and which are payload, without opening any file.

---

## 5. The isomorphic per-loop directory

The per-loop directory shape is **IDENTICAL for a top-level loop and for every
child loop** at any depth. This isomorphism is what makes recursion tractable: a
resume, an audit, or a closeout works the same way regardless of level.

```
L001-create-loop-skill/
  loop.meta.yaml          # identity, parent/child relation, spawn reason, slug, title, owner node
  loop.plan.yaml          # this loop's DAG
  loop.state.yaml         # current state
  checkpoint.yaml         # resume entry for a fresh session
  evidence.ledger.yaml    # evidence ledger
  decision.log.md         # decisions
  run.log.md              # run log
  handoff.md              # session handoff
  closeout.md             # result returned to the parent when this loop closes
  artifacts/              # this loop's produced artifacts
  _loops/                 # child loops (recursion)
  _archive/               # deprecated / merged / closed historical items
```

The two most critical files:

- **`closeout.md`** — the **formal return interface** to the parent. When a loop
  reaches a terminal state, its `closeout.md` is the single document the parent
  reads to learn what was solved, what was produced, and what the parent must
  update. It is the *only* sanctioned channel for a child to influence the parent
  (together with the `return_contract`, [§7](#7-return_contract-and-closeoutmd-the-return-interface)).
- **`checkpoint.yaml`** — the **resume entry** for a fresh session. A brand-new
  session with no chat memory reads this file (plus the base checkpoint fields
  from [`state_model.md`](./state_model.md#checkpoint-fields)) to continue the
  loop correctly. For a child loop it carries the additional fields in
  [§7.4 child checkpoint additions](#74-child-checkpoint-additions).

Companion artifacts (`loop.plan.yaml`, `loop.state.yaml`,
`evidence.ledger.yaml`, `decision.log.md`, `run.log.md`, `handoff.md`) map
directly onto the run-scoped artifacts enumerated in
[`self_evolution_integration.md` §1.1](./self_evolution_integration.md) and the
field sets in [`state_model.md`](./state_model.md). Nothing here overrides those
definitions; the child loop simply owns its own copy of each.

---

## 6. `loop.meta.yaml` — EXACT field set (LOCKED)

`loop.meta.yaml` holds a loop's **identity and relation**. It is the file that
carries everything the directory name deliberately omits. Downstream schema
copies this field set **byte-for-byte**.

| field | type | required | description |
|-------|------|----------|-------------|
| `loop_id` | string | yes | The immutable loop id (`L001`, `L001.02`, `L001.02.01`). Primary key. |
| `slug` | string | yes | The kebab-case slug from the directory name (see [§3.4](#34-slug-rule-locked)). |
| `title` | string | yes | Human-readable title of the loop. |
| `type` | enum | yes | One of `root_loop` \| `child_loop`. `root_loop` for a top-level loop; `child_loop` for any materialized child at any depth. |
| `parent` | object \| null | yes | The parent relation. `null` (or absent) **only** for a `root_loop`. For a `child_loop`, an object: `{loop_id, path, parent_node_id, spawn_reason}` — see [§6.1](#61-parent-object). |
| `root` | object | yes | The top-of-tree relation: `{loop_id, path}` pointing at the root loop of this tree. For a `root_loop`, `root` points at itself. |
| `status` | enum | yes | Identity-level status. One of the **15 canonical node statuses** defined authoritatively in [`state_model.md`](./state_model.md#node-status-enum). No new status is invented. |
| `created_at` | string (ISO-8601) | yes | When the loop directory was created. |
| `created_by` | string | yes | Who/what created the loop (agent, subagent, or user identifier). |
| `depth` | int | yes | Recursion depth. `0` for a top-level (`root_loop`); `1` for its direct children; `2` for grandchildren; and so on. |
| `scope` | object | yes | The loop's boundary: `{in[], out[]}` — see [§6.2](#62-scope-object). |
| `return_contract` | object | yes | How this loop returns to its parent: `{closeout_file, required_outputs[], parent_updates[]}` — see [§7](#7-return_contract-and-closeoutmd-the-return-interface). For a `root_loop`, `closeout_file` still points at its own `closeout.md`; `parent_updates` may be empty (`[]`). |

### 6.1 `parent` object

| field | type | required | description |
|-------|------|----------|-------------|
| `loop_id` | string | yes | The parent loop's id (e.g. `L001.02`). |
| `path` | string | yes | Path to the parent loop directory, **relative to this child's own directory** (e.g. `../..`). |
| `parent_node_id` | string | yes | The `id` of the node in the parent's `loop.plan.yaml` that spawned this child loop (the owning node). |
| `spawn_reason` | string | yes | Why this child loop was materialized (which Admission Gate criterion held; see [§8](#8-sub-loop-admission-gate)). |

### 6.2 `scope` object

| field | type | required | description |
|-------|------|----------|-------------|
| `in` | list[string] | yes | What is **in scope** for this loop. May be empty (`[]`). |
| `out` | list[string] | yes | What is explicitly **out of scope** for this loop. May be empty (`[]`). |

### 6.3 Worked example — `L001.02.03-live-policy/loop.meta.yaml`

```yaml
loop_id: L001.02.03
slug: live-policy
title: Live Loop admission policy for the design sub-loop
type: child_loop
parent:
  loop_id: L001.02
  path: ../..
  parent_node_id: n-live-policy
  spawn_reason: >-
    Recursive decomposition: defining the Live Loop admission policy needs its
    own evidence chain and closeout; it produces multiple artifacts and may
    itself spawn grandchildren for edge-case rubrics. Trips Admission Gate
    criteria "independent audit" and "recursive decomposition".
root:
  loop_id: L001
  path: ../../..
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 2
scope:
  in:
    - the admission-gate criteria for Live Loop growth inside the design sub-loop
    - the default response flow when a growth trigger fires
    - the boundaries Live Loop MUST NOT cross
  out:
    - top-level replan policy (owned by L001)
    - the state-model status enum (owned by L001.02.01-state-model)
return_contract:
  closeout_file: closeout.md
  required_outputs:
    - artifacts/live-policy.md
    - artifacts/admission-gate-rubric.md
  parent_updates:
    - node: n-live-policy
      update: mark produces[] artifact live-policy.md satisfied
    - node: n-design-verify
      update: re-verify gate llm_judge once live-policy.md exists
```

---

## 7. `return_contract` and `closeout.md` — the return interface

A child loop influences its parent **only** through its `return_contract` (a
field in `loop.meta.yaml`, [§6](#6-loopmetayaml-exact-field-set)) realized as a
`closeout.md` document. This is the merge / return / gate-update protocol
referenced by the thesis and the isolation rule.

### 7.1 `return_contract` object (LOCKED)

| field | type | required | description |
|-------|------|----------|-------------|
| `closeout_file` | string | yes | Path (relative to this loop's directory) to the closeout document. Conventionally `closeout.md`. |
| `required_outputs` | list[string] | yes | The artifact paths this loop MUST produce before it may close out. Each is an artifact under this loop's `artifacts/` (or another declared path). May be empty (`[]`) only for a loop that produces no artifacts (rare). |
| `parent_updates` | list | yes | The updates the parent must apply once this loop closes: each entry names a parent node and the update to make (e.g. mark a `produces[]` artifact satisfied, re-verify a gate). May be empty (`[]`) for a `root_loop`. |

### 7.2 `closeout.md` — required content

`closeout.md` is the return interface. It MUST document, at minimum:

- **Which parent-node gap this child solved** (which `parent_node_id` and which
  gap in that node's `produces[]` / `postconditions` / `gate`).
- **What artifacts it produced** (concrete paths, matching `required_outputs`).
- **What evidence supports completion** (references into this loop's
  `evidence.ledger.yaml`, i.e. `verdict: pass` entries).
- **Which assumptions were confirmed or refuted** during the loop.
- **Which parent artifacts must be updated** (the concrete `parent_updates`).
- **Which parent gates can be re-verified** now that the child has closed.
- **Whether blockers remain** (open `blocked` items the parent must be aware of).
- **Whether spawning further child loops is advised** (follow-on recursion the
  parent or a sibling should consider).

### 7.3 The merge / return / gate-update protocol

1. The child loop reaches a terminal `status` (`completed`, `cancelled`, or
   `deprecated` per [`state_model.md`](./state_model.md#node-status-enum)) and all
   `required_outputs` exist.
2. The child writes `closeout.md` per [§7.2](#72-closeoutmd--required-content).
3. The parent reads the child's `closeout.md` (located via the `child_loops[]`
   reference's `closeout` field, [§10](#10-the-child_loops-node-field-locked-schema-decision)).
4. The parent applies each `parent_updates` entry: marking `produces[]`
   satisfied, re-running the named gate(s), updating the owning node's `status`
   through the ordinary [state transition table](./state_model.md#state-transition-table).
5. **No direct write** into the parent's `checkpoint.yaml`,
   `evidence.ledger.yaml`, `run.log.md`, or `artifacts/` ever occurs from the
   child — every effect is mediated by the parent applying the contract. This is
   the isolation rule ([§9](#9-isolation-rule-for-parallelism)).

### 7.4 Child checkpoint additions

A child loop's `checkpoint.yaml` **adds** the following fields to the base
checkpoint field set defined in
[`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields). These
additions reconcile with — never replace — the base fields.

| field | type | required | description |
|-------|------|----------|-------------|
| `loop_id` | string | yes | This child loop's id (e.g. `L001.02.03`). |
| `parent_loop_id` | string | yes | The parent loop's id (e.g. `L001.02`). |
| `parent_node_id` | string | yes | The node in the parent plan that owns this child loop. |
| `current_node` | string (node_id) | yes | The node in *this* loop's plan currently in focus for resume. |
| `last_valid_artifacts` | list[string] | yes | Paths of this loop's artifacts confirmed valid at the last checkpoint (safe to reuse on resume). May be empty (`[]`). |
| `next_recommended_action` | string | yes | Advisory hint for the next agent resuming this child loop; never a source of truth over the graph. |
| `open_blockers` | list[object] | yes | Each: `{node_id, reason}`. Blockers currently open in this child loop. May be empty (`[]`). |

> **Note (reconciliation).** The base checkpoint fields (`schema_version`,
> `plan_id`, `plan_version`, `checkpoint_id`, `created`, `phase`, `node_states`,
> `ready_set`, `last_completed`, `blocked`, `pending_approvals`,
> `next_suggested_action`, `open_assumptions`, `event_log_ref`,
> `evidence_ledger_ref`, `cost_units_spent`, `iteration`) still apply verbatim.
> `next_recommended_action` (child-loop addition) and `next_suggested_action`
> (base) are distinct fields and both present; the child addition is scoped to
> the child's own graph.

### 7.5 Worked example — `L001.02.03-live-policy/checkpoint.yaml`

```yaml
# --- base checkpoint fields (state_model.md) ---
schema_version: "1.0.0"
plan_id: plan-L001.02.03-live-policy
plan_version: 2
checkpoint_id: ckpt-L001.02.03-0007
created: 2026-07-01T15:05:00Z
phase: 0
node_states:
  n-collect-triggers: completed
  n-draft-policy: running
  n-edge-case-rubrics: pending
  n-policy-verify: pending
ready_set: []
last_completed:
  - n-collect-triggers
blocked: []
pending_approvals: []
next_suggested_action: "finish n-draft-policy, then dispatch n-edge-case-rubrics"
open_assumptions:
  - "growth triggers list is complete pending n-policy-verify"
event_log_ref: ./event_log.ndjson
evidence_ledger_ref: ./evidence.ledger.yaml
cost_units_spent: 41
iteration: 7
# --- child-loop checkpoint additions (this document, §7.4) ---
loop_id: L001.02.03
parent_loop_id: L001.02
parent_node_id: n-live-policy
current_node: n-draft-policy
last_valid_artifacts:
  - artifacts/triggers.md
next_recommended_action: "complete draft, run llm_judge gate on live-policy.md"
open_blockers: []
```

---

## 8. Sub-loop Admission Gate

A child loop directory is created **ONLY** when at least **one** of the following
criteria holds. If none holds, the work stays as an inline action inside a node,
or as an inline `subgraph`
([`loop_plan_spec.md` §7](./loop_plan_spec.md#7-subgraph-recursion)).

This list is the **canonical source of truth** for admission and promotion
criteria across the create-loop package. The Promotion Gate in
[`subgraph_subloop_policy.md` §5](./subgraph_subloop_policy.md#5-promotion-gate-subgraph--subloop)
and the "promote to subloop" branch in
[`live_loop_semantics.md` §4](./live_loop_semantics.md#4-default-response-flow)
are the same rule observed at two other tiers (subgraph → subloop; live growth
→ subloop); they refer back to this section rather than re-enumerating criteria,
to keep the lists from drifting.

| # | criterion | materialize a `child_loop` because… | sub-signals (any one suffices) |
|---|-----------|-------------------------------------|--------------------------------|
| 1 | **high complexity** | the work is not solvable in a few steps; it needs its own DAG. | - large multi-phase scope (research + design + impl + verify)<br>- needs an independent closeout + return contract |
| 2 | **independent state persistence** | state must persist independently across sessions, across agents, or over a long-running horizon. | - expected to cross sessions (light hosted state is not a durable resume entry)<br>- needs an independent checkpoint / recovery |
| 3 | **independent evidence audit** | the evidence needs its own audit trail — an independent `evidence.ledger.yaml` / evidence chain. | - complex evidence chain |
| 4 | **may run in parallel** | the work may run concurrently with siblings and needs an isolated workspace (no shared-writer contention). | - parallel isolation (subagent / separate executor) |
| 5 | **high risk / uncertainty** | the work needs independent decision-making and independent recovery. | - elevated risk<br>- complex decisions / approvals (own `decision.log.md` and gate history) |
| 6 | **produces multiple artifacts** | the outputs do not fit inside a single parent node's `produces[]`. | - many artifacts |
| 7 | **needs recursive decomposition** | the work may itself spawn grandchildren (its own `_loops/`). | - may recursively spawn further loops |
| 8 | **cross-cutting scope** | the work affects more than one parent node and cannot be owned locally. | - affects multiple parent nodes |

**Decision rule (verbatim):**

> **If a problem needs its own plan, state, evidence, checkpoint, or closeout, it
> should be a child loop.**

Small tasks stay as inline actions or an inline `subgraph`. The Admission Gate is
the single arbiter of subgraph-vs-child_loop. The Live Loop admission gate in
[`live_loop_semantics.md` §6](./live_loop_semantics.md#6-admission-criteria-when-a-candidate-enters-the-graph)
is a **sibling gate** that governs a different question (whether a growth item
enters the graph at all) and is not the same rule.

---

## 9. Isolation rule (for parallelism)

A child loop may write **ONLY its own directory** (its own `loop.*.yaml`,
`evidence.ledger.yaml`, `run.log.md`, `decision.log.md`, `artifacts/`, `_loops/`,
`_archive/`). Writing **parent** state MUST go through the `return_contract`
([§7](#7-return_contract-and-closeoutmd-the-return-interface)) or an explicit
merge gate on the parent side.

**Why:** if two sibling child loops running in parallel could both write the
parent's `evidence.ledger.yaml`, `run.log.md`, or `artifacts/`, they would be
concurrent writers on the same append-only files. That produces interleave
corruption, lost updates, and evidence **drift** — the ledger would no longer be a
faithful, replayable record. Confining each child to its own directory makes
parallelism safe by construction: there is exactly one writer per file. The
parent integrates results **serially**, one `closeout.md` at a time, when it
applies each child's `parent_updates`.

---

## 10. The `child_loops` node field (LOCKED SCHEMA DECISION)

The parent node references its directory-materialized children through a **NEW
node field**, `child_loops`. Downstream authors MUST comply with this shape.

- **Field name:** `child_loops`.
- **Type:** array (`list`).
- **Required:** **yes** — the field is **REQUIRED on every node**.
- **Empty sentinel:** `[]` when the node has no directory-materialized children.
  This mirrors how `subgraph` is **required-but-null**
  ([`loop_plan_spec.md` §2](./loop_plan_spec.md#2-node-object)): every node field
  is present, and **absence is explicit**. This preserves the package's
  explicit-sentinel invariant — an author never has to guess whether a missing
  field means "none" or "not yet considered".

### 10.1 `child_loops[]` reference shape (LOCKED)

Each entry in `child_loops` is a reference object with **exactly** these fields:

| field | type | required | description |
|-------|------|----------|-------------|
| `loop_id` | string | yes | The child loop's immutable id (e.g. `L001.02`). |
| `path` | string | yes | Path to the child loop directory, **relative to the parent loop directory** (e.g. `_loops/L001.02-design-loop-spec`). |
| `spawn_reason` | string | yes | Why this child loop was materialized — which Admission Gate criterion held ([§8](#8-sub-loop-admission-gate)). |
| `status` | enum | yes | The child's current status. One of the **15 canonical node statuses** ([`state_model.md`](./state_model.md#node-status-enum)) — **reused**, not a new enum. |
| `closeout` | string | yes | Path (relative to the parent loop directory) to the child's `closeout.md` — the parent's read entry point for the return contract (e.g. `_loops/L001.02-design-loop-spec/closeout.md`). |

### 10.2 Worked example — a parent node carrying `child_loops`

```yaml
# inside L001-create-loop-skill/loop.plan.yaml, one node:
- id: n-design
  kind: mapper
  title: Design the loop spec
  design_invariant: true
  status: running
  requires:
    - n-research
  produces:
    - artifacts/design-spec.md
  inputs: []
  preconditions: []
  postconditions: []
  gate:
    kind: llm_judge
    threshold: 0.8
    rubric: rubrics/design.md
    evidence_ref: evidence.ledger.yaml
  retry_policy:
    max_attempts: 3
    backoff_base_seconds: 2
    jitter: true
  on_failure: replan
  priority: 5
  risk: high
  parallelizable: false
  allow_subgraph: true
  subgraph: null            # no inline fragment materialised
  child_loops:              # REQUIRED field; directory-materialized children
    - loop_id: L001.02
      path: _loops/L001.02-design-loop-spec
      spawn_reason: "high complexity + recursive decomposition (Admission Gate #1, #7)"
      status: running
      closeout: _loops/L001.02-design-loop-spec/closeout.md
  assignee: agent
  notes: ""
```

A node with no directory-materialized children still carries the field:

```yaml
  child_loops: []           # explicit sentinel: none materialised
```

---

## 11. INDEX files (avoid full-tree scans)

To resume, audit, or schedule without walking the whole tree, each level keeps an
**index**. Agents should **read the index first, not traverse the tree**.

### 11.1 Global index — `.agents/loops/INDEX.yaml`

Lists every top-level loop. Field set per entry: `loops[]` each
`{loop_id, slug, path, status, title, checkpoint, updated_at}`.

```yaml
# .agents/loops/INDEX.yaml
loops:
  - loop_id: L001
    slug: create-loop-skill
    path: L001-create-loop-skill
    status: running
    title: Build the create-loop Agent Skill
    checkpoint: L001-create-loop-skill/checkpoint.yaml
    updated_at: 2026-07-01T15:10:00Z
    current_active_node: n-build
  - loop_id: L002
    slug: migrate-billing
    path: L002-migrate-billing
    status: completed
    title: Migrate billing to the new schema
    checkpoint: L002-migrate-billing/checkpoint.yaml
    updated_at: 2026-06-28T09:42:00Z
    current_active_node: null
```

### 11.2 Local index — `<loop>/_loops/INDEX.yaml`

Lists a loop's direct children. Field set per entry: `children[]` each
`{loop_id, slug, path, status, parent_node_id, current_active_node}`.

```yaml
# L001-create-loop-skill/_loops/INDEX.yaml
children:
  - loop_id: L001.01
    slug: research-loop-eng
    path: L001.01-research-loop-eng
    status: completed
    parent_node_id: n-research
    current_active_node: null
  - loop_id: L001.02
    slug: design-loop-spec
    path: L001.02-design-loop-spec
    status: running
    parent_node_id: n-design
    current_active_node: n-write-spec
  - loop_id: L001.03
    slug: build-skill
    path: L001.03-build-skill
    status: pending
    parent_node_id: n-build
    current_active_node: null
```

> **Rule.** An agent resuming, auditing, or scheduling MUST consult the relevant
> `INDEX.yaml` before traversing the directory tree. The index is the cheap
> lookup; the tree walk is the fallback of last resort. All `status` values in an
> index are drawn from the 15 canonical node statuses
> ([`state_model.md`](./state_model.md#node-status-enum)).

Every index entry carries `current_active_node` — the node currently executing
in that loop (mirroring `loop.state.active_node`), or `null` when idle. This lets
`/loop-status` answer "what is running, tree-wide" from the indexes alone,
without opening each checkpoint.

### 11.3 INDEX ↔ directory reconciliation and archival

The index and the on-disk tree must not drift. The validator enforces this
(rule R37, invoked with `--root <loops-dir>`): **every `path` listed in an
`INDEX.yaml` must exist on disk**, and (by the retirement procedure below) every
live loop directory must be listed. A dangling entry (loop archived/moved but
still indexed) or an unlisted directory is rejected.

**Retirement (`_archive/`).** A loop that reaches a terminal status
(`completed`, `cancelled`, `deprecated`) and is no longer needed for active work
is retired, not deleted:

1. Move the loop directory into its parent's `_archive/` (top-level loops move
   into `.agents/loops/_archive/`).
2. Write a one-line tombstone (`_archive/<loop-id>.tombstone.yaml`:
   `{loop_id, retired_at, reason, final_status}`) so the retirement is auditable.
3. Remove the loop's entry from the live `INDEX.yaml` (it is now under
   `_archive/`, outside the reconciled set).

**Garbage collection.** `_archive/` is bounded by a retention policy — keep the
most recent N retired loops (default 50) or those retired within a retention
window (default 180 days), whichever the project sets; older tombstoned archives
may be pruned. GC never touches a non-terminal loop, and never removes a
tombstone without removing its directory (and vice versa), so the archive itself
stays reconciled.

---

## 12. Complete tree example

A full recursive tree for `L001-create-loop-skill`, showing children,
grandchildren, and the isomorphic per-loop directory at every level:

```
.agents/loops/
  INDEX.yaml                                    # global index (§11.1)
  L001-create-loop-skill/                       # root_loop, depth 0
    loop.meta.yaml
    loop.plan.yaml
    loop.state.yaml
    checkpoint.yaml
    evidence.ledger.yaml
    decision.log.md
    run.log.md
    handoff.md
    closeout.md
    artifacts/
    _archive/
    _loops/                                     # child loops of L001
      INDEX.yaml                                # local index (§11.2)
      L001.01-research-loop-eng/                # child_loop, depth 1
        loop.meta.yaml
        loop.plan.yaml
        loop.state.yaml
        checkpoint.yaml
        evidence.ledger.yaml
        decision.log.md
        run.log.md
        handoff.md
        closeout.md
        artifacts/
        _archive/
        _loops/
      L001.02-design-loop-spec/                 # child_loop, depth 1
        loop.meta.yaml
        loop.plan.yaml
        loop.state.yaml
        checkpoint.yaml
        evidence.ledger.yaml
        decision.log.md
        run.log.md
        handoff.md
        closeout.md
        artifacts/
        _archive/
        _loops/                                 # grandchild loops of L001.02
          INDEX.yaml
          L001.02.01-state-model/               # child_loop, depth 2
            loop.meta.yaml
            loop.plan.yaml
            loop.state.yaml
            checkpoint.yaml
            evidence.ledger.yaml
            decision.log.md
            run.log.md
            handoff.md
            closeout.md
            artifacts/
            _archive/
            _loops/
          L001.02.02-evidence-gates/            # child_loop, depth 2
            loop.meta.yaml
            loop.plan.yaml
            loop.state.yaml
            checkpoint.yaml
            evidence.ledger.yaml
            decision.log.md
            run.log.md
            handoff.md
            closeout.md
            artifacts/
            _archive/
            _loops/
          L001.02.03-live-policy/               # child_loop, depth 2
            loop.meta.yaml
            loop.plan.yaml
            loop.state.yaml
            checkpoint.yaml
            evidence.ledger.yaml
            decision.log.md
            run.log.md
            handoff.md
            closeout.md
            artifacts/
            _archive/
            _loops/
      L001.03-build-skill/                      # child_loop, depth 1
        loop.meta.yaml
        loop.plan.yaml
        loop.state.yaml
        checkpoint.yaml
        evidence.ledger.yaml
        decision.log.md
        run.log.md
        handoff.md
        closeout.md
        artifacts/
        _archive/
        _loops/
```

### 12.1 Abstract recursion form

The general shape at any level — a parent loop containing a `_loops/` directory,
under which each child loop is itself a full isomorphic loop directory that may in
turn contain its own `_loops/`:

```
<parent-loop-dir>/
  loop.meta.yaml
  loop.plan.yaml
  loop.state.yaml
  checkpoint.yaml
  evidence.ledger.yaml
  decision.log.md
  run.log.md
  handoff.md
  closeout.md
  artifacts/
  _archive/
  _loops/
    INDEX.yaml
    <child-loop-dir>/            # dir name = <parent-id>.<local-seq>-<slug>
      loop.meta.yaml            # parent.parent_node_id links back to the owning node
      loop.plan.yaml
      loop.state.yaml
      checkpoint.yaml
      evidence.ledger.yaml
      decision.log.md
      run.log.md
      handoff.md
      closeout.md               # the return interface the parent reads
      artifacts/
      _archive/
      _loops/                   # grandchildren — same shape, recursively
```

The child loop directory is keyed by its own `loop_id`; the owning parent node is
recorded in the child's `loop.meta.yaml.parent.parent_node_id` and mirrored in the
parent node's `child_loops[]` reference ([§10](#10-the-child_loops-node-field-locked-schema-decision)).

---

## 13. See also

- [`loop_plan_spec.md`](./loop_plan_spec.md) — the plan/node field dictionary,
  the existing inline `subgraph` / `allow_subgraph` fields, gate object, retry
  policy, escalation ladder, and the canonical Glossary.
- [`state_model.md`](./state_model.md) — the 15-status node enum, the state
  transition table, and the **checkpoint** / **node.contract** / **evidence.ledger**
  field sets that a child loop reuses.
- [`concepts.md`](./concepts.md) — durability primitives (§7), the run-id
  directory, and the isomorphic-recursion rationale.
- [`live_loop_semantics.md`](./live_loop_semantics.md) — evidence-driven growth
  and the inline-`subgraph` admission gate that the directory-materialized
  Admission Gate parallels.
- [`self_evolution_integration.md`](./self_evolution_integration.md) — the
  transient (`create-loop`) vs durable (`self-evolution`) boundary; a child
  loop's `closeout.md` is the promotion candidate source, never a direct write
  into `.agents/knowledge/`.

---

## Glossary

*Canonical spellings of every **new** locked token introduced by this document.
Downstream schemas, templates, validators, examples, `SKILL.md`, and tests MUST
cite these verbatim. Field names are lowercase snake_case; slugs are kebab-case;
enum reuse of the 15 node statuses is by reference to
[`state_model.md`](./state_model.md#node-status-enum), never redefined here.*

### Directory root & name patterns

- `.agents/loops/` — the root of all loops (the run-id directory home).
- `L<seq>-<slug>` — top-level (root) loop directory-name pattern; `seq` is
  3-digit zero-padded (e.g. `L001-create-loop-skill`).
- `<parent-id>.<local-seq>-<slug>` — child / grandchild loop directory-name
  pattern; `local-seq` is 2-digit zero-padded, assigned by the parent
  (e.g. `L001.02-design-loop-spec`, `L001.02.01-state-model`).
- Loop id forms: `L001` (top-level), `L001.02` (child), `L001.02.01`
  (grandchild) — **immutable** once created.
- `_loops/` — underscore-prefixed control directory holding a loop's child loops
  (recursion).
- `_archive/` — underscore-prefixed control directory holding deprecated /
  merged / closed historical items.
- `artifacts/` — non-underscore work-content directory holding a loop's produced
  artifacts.

### Per-loop files (isomorphic at every level)

- `loop.meta.yaml` — identity & relation.
- `loop.plan.yaml` — this loop's DAG.
- `loop.state.yaml` — current state.
- `checkpoint.yaml` — resume entry.
- `evidence.ledger.yaml` — evidence ledger.
- `decision.log.md` — decisions.
- `run.log.md` — run log.
- `handoff.md` — session handoff.
- `closeout.md` — the return interface to the parent.

### `loop.meta.yaml` fields

`loop_id`, `slug`, `title`, `type` (enum: `root_loop` | `child_loop`), `parent`
(object: `loop_id`, `path`, `parent_node_id`, `spawn_reason`; `null` for a
`root_loop`), `root` (object: `loop_id`, `path`), `status` (one of the 15
canonical node statuses), `created_at`, `created_by`, `depth`, `scope` (object:
`in[]`, `out[]`), `return_contract` (object: `closeout_file`,
`required_outputs[]`, `parent_updates[]`).

### `loop.meta.yaml.type` enum (2)

`root_loop`, `child_loop`

### `return_contract` fields

`closeout_file`, `required_outputs`, `parent_updates`

### Child-checkpoint addition fields (on top of the base checkpoint field set)

`loop_id`, `parent_loop_id`, `parent_node_id`, `current_node`,
`last_valid_artifacts`, `next_recommended_action`, `open_blockers`

### `child_loops` node field (NEW; required; array; empty sentinel `[]`)

`child_loops` — and each `child_loops[]` reference object's fields: `loop_id`,
`path`, `spawn_reason`, `status` (one of the 15 canonical node statuses),
`closeout`.

### INDEX files & fields

- `.agents/loops/INDEX.yaml` — global index; `loops[]` each `{loop_id, slug,
  path, status, title, checkpoint, updated_at}`.
- `<loop>/_loops/INDEX.yaml` — local index; `children[]` each `{loop_id, slug,
  path, status, parent_node_id}`.

### Sub-loop Admission Gate criteria

Canonical list lives in [§8](#8-sub-loop-admission-gate) — do not re-enumerate
here. The eight criterion names are: `high complexity`, `independent state
persistence`, `independent evidence audit`, `may run in parallel`,
`high risk / uncertainty`, `produces multiple artifacts`,
`needs recursive decomposition`, `cross-cutting scope`.

**Admission Gate decision rule (verbatim):** *If a problem needs its own plan,
state, evidence, checkpoint, or closeout, it should be a child loop.*
(Full statement: [§8](#8-sub-loop-admission-gate).)

### Reused (NOT redefined) tokens

- The **15 canonical node statuses** — `undiscovered`, `discovered`,
  `needs_clarification`, `pending`, `ready`, `running`, `waiting_external`,
  `waiting_user`, `blocked`, `verifying`, `verification_failed`, `retry_pending`,
  `completed`, `cancelled`, `deprecated` — authoritative in
  [`state_model.md`](./state_model.md#node-status-enum). Used for
  `loop.meta.yaml.status`, `child_loops[].status`, and all INDEX `status` fields.
- The existing node fields `subgraph`, `allow_subgraph`, `parent_ref`,
  `plan_version` — unchanged; defined in
  [`loop_plan_spec.md`](./loop_plan_spec.md).

## See also

- [`parallel_development_protocol.md`](./parallel_development_protocol.md) — a
  directory-materialized child loop is exactly a **parallel sub-loop** with its
  own isolated workspace and return contract; that protocol adds the
  git-worktree isolation, merge pre-flight, owner-gate, and rollback ladder for
  running several such units concurrently.
- [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) — the tier rules
  that decide when a unit is an inline `subgraph` vs a materialized `subloop`.
- [`state_model.md`](./state_model.md#node-status-enum) — the status enum and the
  per-node claim/lease this layer reuses.
