# Three-Tier Execution Model & the Subgraph → Subloop Promotion Gate

*Diataxis type: **reference + explanation**. This document is the authoritative
vocabulary for the **three-tier execution model** — `action`, `subgraph`,
`subloop` — and for the **Promotion Gate** that governs when a lightweight
`subgraph` must be promoted to an independently-governed `subloop`. Downstream
JSON schemas, YAML templates, validator scripts, examples, `SKILL.md`, and tests
key off the tier names, the subgraph status enum, the `node.runtime.yaml` field
set, and the promotion vocabulary defined here. When a spelling is ambiguous, the
[Glossary](#glossary) at the end of this file is canonical.*

*This document does NOT redefine the directory-materialized child loop — it
**reuses** it. A **subloop** IS the directory-materialized **child loop** defined
authoritatively in [`recursive_loops.md`](./recursive_loops.md): the isolated
per-loop directory under a parent's `_loops/`, with its own `loop.meta.yaml`,
`loop.plan.yaml`, `loop.state.yaml`, `checkpoint.yaml`, `evidence.ledger.yaml`,
logs, `artifacts/`, `closeout.md`, and its own `_loops/`. This document adds only
the tier vocabulary, the subgraph's own lighter lifecycle, the subgraph control
fields, the runtime-hosting layout (`node.runtime.yaml`), and the Promotion Gate.
For the plan/node field dictionary and the existing inline `subgraph` /
`allow_subgraph` fields, see [`loop_plan_spec.md`](./loop_plan_spec.md). For the
**15 canonical node statuses**, checkpoint, node.contract, and evidence.ledger
field sets, see [`state_model.md`](./state_model.md). For evidence-driven growth,
see [`live_loop_semantics.md`](./live_loop_semantics.md). For the autonomy
boundary set, see [`human_approval.md`](./human_approval.md).*

Conventions used throughout (identical to the rest of the package):

- All field names and all enum values are **lowercase snake_case**.
- All dates/timestamps are **ISO-8601** strings (e.g. `2026-07-01` or
  `2026-07-01T14:30:00Z`).
- All slugs are **kebab-case**, English only, lowercase.
- `list[T]` = ordered array of `T`. `map[K->V]` = object keyed by `K`.
- `null` is an explicit permitted value where stated; otherwise a field is
  required.
- A **subgraph id** uses the prefix `SG-` (see [§8](#8-subgraph-control-fields)).

---

## 1. The three-tier execution model

`create-loop` distinguishes three execution-unit tiers by **governance need, not
by size**. A ten-line change that must survive a crash and carry an independent
audit trail is a `subloop`; a five-node exploration that lives and dies inside one
parent node is a `subgraph`, however clever. The tier is chosen by *how the work
must be governed*, never by line count.

> **Use `action` for simple single-step work. Use `subgraph` for local
> multi-step work. Use `subloop` for independently governable work.**

> A **subgraph** is a lightweight control structure. A **subloop** is an
> independently managed execution unit.

| tier | essence | own directory? | own state? | recoverable? | typical use |
|------|---------|----------------|------------|--------------|-------------|
| `action` | a single concrete operation with no internal planning (read a file, run a command, write a doc) | no | no | no | one atomic step inside a node — the leaf of all execution |
| `subgraph` | a lightweight runtime task DAG created **inside a parent node** for local exploration / correction / verification / decomposition / necessary live growth | no (lives in parent files) | light state (hosted by the parent) | partially (via the parent) | local multi-step work that the parent node can safely govern |
| `subloop` | a **materialized, independently recoverable & auditable Loop** — the directory-materialized child loop of [`recursive_loops.md`](./recursive_loops.md) | yes | yes (`loop.state.yaml` + `checkpoint.yaml`) | yes (own checkpoint + evidence ledger) | work that needs its own plan, state, evidence, checkpoint, and closeout |

The three tiers form a ladder of increasing governance weight. Start at the
lightest tier that can *safely, clearly, and recoverably* hold the work, and climb
only when the work demands it (the Promotion Gate, [§5](#5-promotion-gate-subgraph--subloop)).

---

## 2. What a subgraph is

A **subgraph** is a **lightweight task topology created inside a single parent
node**. It is the runtime realization of the inline `subgraph` field defined in
[`loop_plan_spec.md` §7](./loop_plan_spec.md#7-subgraph-recursion): an isomorphic
plan fragment, materialised by a `mapper` node or any node with
`allow_subgraph: true`, that expands one node into a small local DAG of
runtime-discovered work.

Precisely, a subgraph:

- is **attached to exactly one parent node** (its `parent_node_id`);
- is **governed BY that parent node** — it inherits the parent's authorization,
  budget, risk envelope, and top-level goal;
- is **hosted by the parent's state, evidence, and logs** — by default it has
  **NO own directory, NO full `loop.plan.yaml`, NO independent `checkpoint.yaml`,
  NO independent `evidence.ledger.yaml`, and NO `closeout.md`**;
- keeps its light state either in the loop's `loop.state.yaml` or in a per-node
  `node.runtime.yaml` ([§6](#6-where-subgraphs-live));
- is **partially recoverable** — a fresh session recovers it only through the
  parent loop's durable artifacts, not through an independent checkpoint;
- is **not another full loop** — it is a control structure *within* a loop, never
  a peer of one.

A subgraph is the same lightweight mechanism that Live Loop uses for
evidence-driven growth ([`live_loop_semantics.md` §8](./live_loop_semantics.md#8-how-growth-stays-controlled-auditable-and-recoverable)):
the parent node's inline `subgraph` fragment carrying a `parent_ref`. This
document names that mechanism the **subgraph tier** and gives it an explicit
lighter lifecycle so downstream tooling can track it without confusing it with a
node or a subloop.

---

## 3. What subgraphs should handle

A subgraph is the right tier for **local, node-bounded, light-governance work**.
The table below is the working scenario list. `YES` means "handle as a subgraph";
`NO → subloop` means "this crosses the Promotion Gate — materialize a subloop
instead" ([§5](#5-promotion-gate-subgraph--subloop)).

| scenario | tier | why |
|----------|------|-----|
| local research of 2–5 questions | **subgraph** YES | small, bounded, resolved inside the node; no independent audit needed |
| compare 2–3 options | **subgraph** YES | a short decision fan-out the parent node can host |
| fix a small design hole | **subgraph** YES | a local correction, tracked by the parent's evidence |
| backfill a small evidence set | **subgraph** YES | a few verification steps feeding the parent's gate |
| a few parallel checks inside a node | **subgraph** YES | local parallelism with no shared-writer contention beyond the parent |
| rewrite a small artifact | **subgraph** YES | one artifact, one node, light state |
| complex implementation module | **NO → subloop** | needs its own plan, phases, and recovery |
| long research task | **NO → subloop** | crosses sessions; needs independent state persistence |
| multi-agent parallel dev | **NO → subloop** | needs isolated workspaces (one writer per file) |
| high-risk compliance review | **NO → subloop** | needs an independent evidence audit and closeout |

The dividing line is always governance, not the apparent effort. A "small" task
that must persist across sessions or carry an independent audit trail is a
subloop; a "large-looking" exploration that the parent node can safely host and
recover is a subgraph.

---

## 4. Subgraph vs subloop: the core difference is GOVERNANCE, not size

The single load-bearing distinction between the two non-`action` tiers is **how
much governance the work needs**, not how big it looks.

**A subgraph is light-governance:**

- lives inside a parent node;
- shares the parent's state, evidence, logs, and budget;
- has no independent checkpoint and no independent closeout;
- is recovered only through the parent loop;
- inherits the parent's authorization and risk envelope unchanged;
- is cheap to create and cheap to discard.

**A subloop is heavy-governance:**

- is a materialized loop directory of its own ([`recursive_loops.md` §5](./recursive_loops.md#5-the-isomorphic-per-loop-directory));
- owns its `loop.plan.yaml`, `loop.state.yaml`, `checkpoint.yaml`,
  `evidence.ledger.yaml`, logs, and `artifacts/`;
- is independently recoverable across sessions and agents;
- carries an independent audit trail (its own evidence ledger);
- communicates with the parent **only** through its `return_contract` and
  `closeout.md` ([`recursive_loops.md` §7](./recursive_loops.md#7-return_contract-and-closeoutmd-the-return-interface));
- may recursively spawn further subloops through its own `_loops/`;
- is admitted only through the Sub-loop Admission Gate
  ([`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate)).

This is exactly the inline-`subgraph` vs directory-materialized-`child_loop`
distinction drawn in
[`recursive_loops.md` §2](./recursive_loops.md#2-two-recursion-mechanisms-coexist).
The subgraph tier is the inline mechanism; the subloop tier is the directory
mechanism. This document does not change either — it names them as tiers and adds
the Promotion Gate that moves work from the first to the second.

---

## 5. Promotion Gate (subgraph → subloop)

The Promotion Gate is the key operating rule of this document.

> **Default to creating a `subgraph` first; promote to a `subloop` ONLY when a
> lightweight subgraph cannot safely, clearly, and recoverably manage the work.**

A subgraph is promoted to a subloop when **at least one** of the same criteria
that drive the Sub-loop Admission Gate holds. The Promotion Gate is the
**tier-level restatement** of the Admission Gate observed at the subgraph tier:
promoting a subgraph and admitting a child loop are the same event seen from the
two tiers.

The full, authoritative criteria list (with sub-signals) lives in
[`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate) — that
section is the **single canonical source of truth** for admission and promotion
criteria across the create-loop package. This section does **not** re-enumerate
the list, to avoid drift; consult §8 for the criteria, sub-signals, and the
verdict-level decision rule. The short summary in this section is: a subgraph
crosses the Promotion Gate when a parent-hosted runtime can no longer
satisfactorily host, recover, or audit it — the same need that, if predictable
up front, would have produced a subloop directly ([§11](#11-the-decision-tree)).

**Simple decision rule (verbatim):**

> **If it needs its own plan / state / checkpoint / evidence / closeout, it is a
> subloop. If it only needs a few nodes and light state, it is a subgraph.**

This is the tier-level restatement of the Sub-loop Admission Gate decision rule
(*"If a problem needs its own plan, state, evidence, checkpoint, or closeout, it
should be a child loop."* — [`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate)).
The two rules are deliberately the same rule: promoting a subgraph and admitting a
child loop are the same event seen from the two tiers.

---

## 6. Where subgraphs live

A subgraph has no directory of its own. Its light state must be hosted somewhere
durable inside the parent loop. There are two options.

**Option A — embedded in `loop.state.yaml`.** All of a loop's subgraphs live in a
single `runtime_subgraphs:` list inside the loop's `loop.state.yaml`.

- *Pro:* simplest; fewer files.
- *Con:* `loop.state.yaml` **bloats** as subgraphs accumulate; every subgraph
  write touches the one hot state file.

**Option B — a per-node `node.runtime.yaml` (RECOMMENDED).** Each node that hosts
runtime subgraphs gets its own `nodes/<node_id>/node.runtime.yaml` under the loop
directory. The `runtime_subgraphs:` list lives there, scoped to that node.

- *Pro:* keeps `loop.state.yaml` lean; localizes subgraph writes to the owning
  node; scales cleanly.
- *Con:* one more file per hosting node.

### 6.1 Recommended directory layout (Option B)

```
L001-create-loop-skill/
  loop.meta.yaml
  loop.plan.yaml
  loop.state.yaml            # the big graph's state — stays lean
  checkpoint.yaml
  evidence.ledger.yaml
  decision.log.md
  run.log.md
  handoff.md
  closeout.md
  artifacts/
  _archive/
  _loops/                    # subloops (child loops) — see recursive_loops.md
  nodes/                     # per-node local runtime state
    N4_design_loop_spec/
      node.contract.yaml     # the per-node execution contract (state_model.md)
      node.runtime.yaml      # this node's runtime_subgraphs[] (THIS document)
      node.notes.md          # free-form local notes
      artifacts/             # node-local artifacts produced by its subgraphs
```

### 6.2 Responsibility split

> **Loop manages the big graph; Node manages local subgraphs; Subloop manages the
> independent graph.**

- The **loop** owns `loop.plan.yaml` (the top-level DAG) and `loop.state.yaml`
  (the graph's status).
- A **node** owns its `node.runtime.yaml` (the local subgraphs it hosts).
- A **subloop** owns its own everything — a full isomorphic loop directory under
  `_loops/` ([`recursive_loops.md` §5](./recursive_loops.md#5-the-isomorphic-per-loop-directory)).

### 6.3 Worked example — `nodes/N4_design_loop_spec/node.runtime.yaml`

```yaml
node_id: N4_design_loop_spec
runtime_subgraphs:
  - subgraph_id: SG-N4-001
    title: Compare three state-persistence approaches
    status: running
    created_at: 2026-07-01T14:30:00Z
    spawn_reason: >-
      Local decision fan-out: the design node must choose among three
      state-persistence approaches before it can produce design-spec.md.
      Light-governance, node-bounded — a subgraph, not a subloop.
    scope:
      in:
        - compare checkpoint-only vs event-sourced vs hybrid persistence
        - pick the approach that satisfies the resume-from-blank requirement
      out:
        - implementing the chosen approach (belongs to a later node)
        - the state-model status enum (owned by state_model.md)
    nodes:
      - id: sg-collect-options
        title: Enumerate the three candidate approaches
        status: completed
        output: artifacts/persistence-options.md
      - id: sg-score-options
        title: Score each option against resume-from-blank + cost
        status: running
        output: null
      - id: sg-pick
        title: Record the chosen approach + rationale
        status: pending
        output: null
    edges:
      - [sg-collect-options, sg-score-options]
      - [sg-score-options, sg-pick]
    completion_gate:
      required_outputs:
        - artifacts/persistence-options.md
        - artifacts/persistence-decision.md
      pass_condition: >-
        one approach chosen with a recorded rationale that satisfies the
        resume-from-blank requirement
    promotion:
      status: not_promoted
      promote_to_subloop_if:
        - the comparison expands into a full multi-phase design effort
        - the decision needs an independent approval + audit trail
        - the work must persist across sessions on its own checkpoint
```

---

## 7. Subgraph lifecycle — its OWN lighter status enum

A subgraph has its **own 8-value status enum**. These statuses are **DISTINCT
from the 15 canonical node statuses** defined in
[`state_model.md` §node status enum](./state_model.md#node-status-enum). A
subgraph is a lighter control structure than a node, so it uses a lighter
lifecycle. **Downstream tooling MUST NOT apply the 15 node statuses to a subgraph,
and MUST NOT apply these 8 subgraph statuses to a node.** The two enums never
overlap in scope.

| subgraph status | meaning |
|-----------------|---------|
| `proposed` | the subgraph has been suggested inside the parent node but not yet admitted; no work has started. |
| `admitted` | the subgraph passed the parent node's local admission check and is part of the node's runtime plan; ready to run. |
| `running` | at least one of the subgraph's local nodes is executing. |
| `blocked` | the subgraph cannot proceed (an unmet local condition or an unresolved local failure); needs intervention or promotion. |
| `completed` | every local node reached a terminal state **and** the `completion_gate` passed. **Terminal.** |
| `failed` | the subgraph could not meet its `completion_gate` and is not being promoted; the parent node handles the gap. **Terminal (locally).** |
| `promoted_to_subloop` | the subgraph crossed the Promotion Gate ([§5](#5-promotion-gate-subgraph--subloop)) and its work was materialized as a subloop; the subgraph itself is closed. **Terminal.** |
| `cancelled` | the subgraph was intentionally abandoned (the work is no longer needed). **Terminal.** |

**Terminal subgraph statuses:** `completed`, `failed`, `promoted_to_subloop`,
`cancelled`.

### 7.1 Example transitions

```
proposed -> admitted -> running -> completed
running  -> blocked  -> promoted_to_subloop
running  -> failed   -> admitted            # a fresh attempt at the same subgraph
running  -> failed   -> cancelled           # the work is dropped
running  -> failed   -> promoted_to_subloop # escalate to a governed subloop
```

- `proposed → admitted → running → completed` is the happy path: a local decision
  or exploration that the parent node hosts to completion.
- `running → blocked → promoted_to_subloop` is the classic promotion: the
  subgraph hits a governance wall (crosses a session, needs an independent
  checkpoint, etc.) and is materialized as a subloop.
- `running → failed → {admitted | cancelled | promoted_to_subloop}` is the
  failure fork: retry the subgraph, drop it, or escalate it to a subloop.

> **Explicit separation.** These are **SUBGRAPH statuses**. They are a separate,
> lighter enum from the **15 node statuses** in
> [`state_model.md`](./state_model.md#node-status-enum). A `subgraph` is never
> `verifying`/`retry_pending`/`deprecated` (those are node statuses); a node is
> never `promoted_to_subloop` (that is a subgraph status). Keeping the two enums
> disjoint is what lets a validator tell a node apart from a subgraph without
> ambiguity.

---

## 8. Subgraph control fields

A subgraph is described by a minimal **8-field set**. Every subgraph carries all
eight.

| field | type | required | description |
|-------|------|----------|-------------|
| `subgraph_id` | string | yes | The subgraph's id. Pattern `SG-<parent-node-id-short>-<seq>` (see below). |
| `parent_node_id` | string | yes | The `id` of the parent node (in `loop.plan.yaml`) that hosts this subgraph. |
| `title` | string | yes | Short human-readable name of the subgraph. |
| `status` | enum | yes | One of the **8 subgraph statuses** ([§7](#7-subgraph-lifecycle--its-own-lighter-status-enum)) — **not** a node status. |
| `spawn_reason` | string | yes | Why the subgraph was created (which local need it serves). |
| `scope` | object | yes | The subgraph's boundary: `{in[], out[]}`. Each list may be empty (`[]`). |
| `nodes` | list[object] | yes | The subgraph's local task nodes (each `{id, title, status, output}`). |
| `edges` | list | yes | Dependency edges as `[from, to]` pairs of local node ids. May be empty (`[]`). |
| `completion_gate` | object | yes | `{required_outputs[], pass_condition}` — the local done condition. |
| `outputs` | list[string] | yes | The artifact paths the subgraph produced. May be empty (`[]`). |
| `promotion_policy` | object | yes | `{status, promote_to_subloop_if[]}` — the local promotion policy (see [§5](#5-promotion-gate-subgraph--subloop)). |

> The `node.runtime.yaml` example in [§6.3](#63-worked-example--nodesn4_design_loop_specnoderuntimeyaml)
> shows these fields in place; there the `promotion_policy` object is written
> under the key `promotion` inside the per-node runtime record, and `outputs` is
> derived from each local node's `output` plus the `completion_gate`. The field
> **names** above are canonical.

**Evidence rule (R25).** A subgraph is lightweight but not evidence-free — it is
held to the same "evidence, not the agent, says done" guarantee as a full node
([`evidence_gates.md` §6](./evidence_gates.md#6-the-non-trivial-node-rule)),
recorded through its compact shape:

- a subgraph-local node MUST NOT be `completed` with a null `output` — the
  `output` artifact path is its evidence;
- a subgraph whose own `status` is `completed` MUST carry a
  `completion_gate.pass_condition` stating how completion was verified.

The `node.runtime` validator enforces both (rule R25), so a subgraph cannot reach
`completed` with nothing to show.

### 8.1 Optional enhancement fields

These MAY be added when a subgraph warrants richer tracking:

`priority`, `risk_level`, `owner_agent`, `created_at`, `updated_at`,
`evidence_refs[]`, `decision_refs[]`, `attempt_count`, `max_attempts`.

### 8.2 `subgraph_id` pattern (LOCKED)

- Pattern: `SG-<parent-node-id-short>-<seq>`.
- Prefix is always `SG-`.
- `<parent-node-id-short>` is a short form of the parent node id (e.g. `N4` for
  node `N4_design_loop_spec`).
- `<seq>` is a 3-digit zero-padded counter, local to the parent node
  (`001`, `002`, …).
- Example: **`SG-N4-001`**.
- A `subgraph_id` is **immutable** once created and is the key referenced by the
  promotion record and any `decision.log.md` line about the subgraph.

---

## 9. Subgraph ↔ parent-node permission table

A subgraph is governed by its parent node and inherits the loop's autonomy
boundaries. The table states what a subgraph may do on its own, what needs a
logged decision, and what it may never do. For the authoritative autonomy
boundary set, see [`human_approval.md`](./human_approval.md) and
[`SKILL.md` §3 Autonomy-First](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode).

| action | permission |
|--------|-----------|
| modify its own light state (`runtime_subgraphs[]` entry, local node statuses) | **allowed** |
| produce a parent-node-local artifact (under `nodes/<node_id>/artifacts/`) | **allowed** |
| supply evidence to a parent node's gate | **allowed** |
| update parent node runtime notes (`node.notes.md`) | **allowed** |
| modify the parent node's `node.contract.yaml` | **needs a logged decision** (`decision.log.md`) |
| modify the parent loop's top-level DAG (`loop.plan.yaml` nodes/edges) | **generally NOT allowed** |
| change the top-level `goal` / `true_intent` | **not allowed** |
| perform external side effects (network, deploy, irreversible writes) | **follow parent authorization policy** ([`human_approval.md`](./human_approval.md), [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)) |
| create a subloop | **only via the Promotion Gate** ([§5](#5-promotion-gate-subgraph--subloop)) |

The boundary set here is the same one Live Loop inherits
([`live_loop_semantics.md` §5](./live_loop_semantics.md#5-boundaries-what-live-loop-must-not-do)):
a subgraph is a Live-Loop-class control structure and MUST NOT break the top-level
governance structure, change the goal, or bypass budget / permission / risk /
external-side-effect boundaries.

---

## 10. Relationship to Live Loop

Live Loop is evidence-driven completeness growth
([`live_loop_semantics.md`](./live_loop_semantics.md)). Its default growth unit
**is a subgraph**: when running evidence exposes a gap, the loop spawns a subgraph
inside the owning node and resolves the gap autonomously. Promotion to a subloop
happens **only when the governance complexity of that growth exceeds the subgraph
threshold** ([§5](#5-promotion-gate-subgraph--subloop)).

Two worked examples:

- **Unverifiable acceptance criteria.** A verification node finds an acceptance
  criterion that cannot be checked as written. The loop spawns a **subgraph** to
  research and draft a checkable restatement — local, node-bounded, light
  governance. *If* investigation reveals a **systemic requirement problem** (the
  criterion reflects a deeper omission spanning many nodes, needs its own evidence
  chain and an independent closeout), **promote to a subloop**.
- **Leftover bug affecting effectiveness.** Evidence shows a bug that does not
  block basic operation but materially harms the final effect. The loop spawns a
  **subgraph** to reproduce and analyze it — a few local steps. *If* the fix turns
  out to require **architecture change, data migration, or coordinated
  multi-module work**, **promote to a subloop** so it gets its own plan, state,
  checkpoint, evidence, and closeout.

In both cases the rule is identical: default into a subgraph; promote only when a
Promotion Gate condition holds. See
[`live_loop_semantics.md`](./live_loop_semantics.md) for the admission criteria,
triggers, and boundaries that govern the subgraph before any promotion is
considered.

### 10.1 Relationship to Recursive Planning ⇄ Immersive Execution

The three tiers are the LEVELS the Planner ⇄ Executor rhythm descends between.
`action` is the leaf the executor runs in place; `subgraph` is a local
re-decomposition the parent node hosts when its work proves complex; `subloop` is
an independently-governed descent with its own plan, state, and closeout. The
rhythm's write-back step is exactly the subgraph `completion_gate` / subloop
`return_contract` — the mechanism by which a descent's products, evidence,
decisions, and state land back in the parent so it can re-plan. See
[`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md).

### 10.2 Relationship to the Layered Execution Chain

The three tiers (`action` / `subgraph` / `subloop`) are the layers the chain's
6-step layer-switch cascade routes work INTO. The Promotion Gate defined in §5
of this document IS the chain's subgraph → subloop decision: when the cascade
reaches "does this need its own governance?" and answers yes, the Promotion Gate
is what executes that step. The chain's "Action Plan" is not a new tier — it is a
`subgraph` of `action` leaves: an ordered list of single-step operations scoped
to one descent, hosted by whichever layer the cascade lands on. See
[`layered_execution_chain.md`](./layered_execution_chain.md).

---

## 11. The decision tree

The criteria that fire the "promote to subloop" branch below are the canonical
Sub-loop Admission Gate criteria in
[`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate) — this
diagram references them rather than re-listing them, to keep the criteria list
single-sourced. Read §8 first; this section is the tier-level navigation aid,
not the criteria source.

```
new work arrives
│
├─ Is it a single, low-risk step (read / run / write, no internal planning)?
│     └─ YES → action
│
├─ Does it need light decomposition, local parallelism, or local verification,
│  and can the parent node safely host and recover it?
│     └─ YES → subgraph
│              │
│              └─ DURING the subgraph, does ANY canonical criterion in
│                 recursive_loops.md §8 become true?
│                     │
│                     ├─ YES (any) → promote to a subloop (Promotion Gate, §5)
│                     └─ NO        → stay a subgraph
│
└─ Otherwise (needs its own plan / state / checkpoint / evidence / closeout
   from the start) → subloop
```

Use this diagram together with the canonical criteria in §8: the diagram routes
the tier choice (`action` / `subgraph` / `subloop`), and §8 supplies the
criteria that decide the subgraph → subloop promotion.

---

## 12. The promotion procedure

When a subgraph crosses the Promotion Gate ([§5](#5-promotion-gate-subgraph--subloop)),
promote it to a subloop with these **10 steps**, in order. Each step reuses the
directory-materialized child-loop machinery of
[`recursive_loops.md`](./recursive_loops.md) verbatim.

1. **Create the child loop directory** under the parent's `_loops/`, named per the
   directory-name pattern (`<parent-id>.<local-seq>-<slug>`,
   [`recursive_loops.md` §3](./recursive_loops.md#3-directory-root--naming-locked)).
2. **Assign a stable child loop ID** (`<parent-id>.<local-seq>`), immutable once
   created ([`recursive_loops.md` §3.3](./recursive_loops.md#33-loop-id-rule-locked)).
3. **Copy or reference the subgraph's current state, evidence, decisions, and
   artifacts** into the new child loop's directory as its starting point.
4. **Create `loop.meta.yaml`** — identity & relation, with `type: child_loop`,
   `parent`, `root`, `scope`, and `return_contract`
   ([`recursive_loops.md` §6](./recursive_loops.md#6-loopmetayaml--exact-field-set-locked)).
5. **Create `loop.plan.yaml`** — the child loop's own DAG.
6. **Create `checkpoint.yaml`** — the child loop's resume entry, including the
   child-checkpoint additions ([`recursive_loops.md` §7.4](./recursive_loops.md#74-child-checkpoint-additions)).
7. **Update the parent node's runtime record** — set the originating subgraph's
   `promotion.status` and add the new child loop to the parent node's
   `child_loops[]` reference ([`recursive_loops.md` §10](./recursive_loops.md#10-the-child_loops-node-field-locked-schema-decision)).
8. **Mark the original subgraph `promoted_to_subloop`** — its terminal status
   ([§7](#7-subgraph-lifecycle--its-own-lighter-status-enum)).
9. **Define the child `return_contract`** — `closeout_file`, `required_outputs[]`,
   `parent_updates[]` ([`recursive_loops.md` §7.1](./recursive_loops.md#71-return_contract-object-locked)).
10. **Record the promotion reason in `decision.log.md`** — the Promotion Gate
    condition(s) that held, the originating `subgraph_id`, and the new child
    `loop_id`.

---

## 13. Formal spec block — Subgraph and Subloop Scope Policy

*This block is the authoritative prose statement of the policy. Downstream authors
treat it as the normative summary of everything above.*

> **Subgraph and Subloop Scope Policy.**
>
> An **action** is a single concrete operation with no internal planning — read a
> file, run a command, write a document. It has no directory, no state, and is not
> recoverable. It is the leaf of all execution.
>
> A **subgraph** is a lightweight runtime task DAG created inside a parent node
> for local exploration, correction, verification, decomposition, or necessary
> live growth. It is governed by the parent node. By default it has no own
> directory, no full `loop.plan.yaml`, no independent checkpoint, no independent
> evidence ledger, and no closeout. Its state lives in the parent (in
> `loop.state.yaml` or a per-node `node.runtime.yaml`). It is partially
> recoverable through the parent.
>
> A **subloop** is a materialized, independently recoverable and auditable Loop —
> the directory-materialized child loop of
> [`recursive_loops.md`](./recursive_loops.md). It has its own directory,
> `loop.meta.yaml`, `loop.plan.yaml`, `loop.state.yaml`, `checkpoint.yaml`,
> `evidence.ledger.yaml`, logs, `artifacts/`, `closeout.md`, and `_loops/`. It
> communicates with its parent through a `return_contract`.
>
> **Default rule:** create a subgraph first; promote to a subloop only when a
> lightweight subgraph cannot safely, clearly, and recoverably manage the work.
>
> **When to use a subgraph:** local research of 2–5 questions; comparing 2–3
> options; fixing a small design hole; backfilling a small evidence set; a few
> parallel checks inside a node; rewriting a small artifact.
>
> **When to use a subloop:** when the work meets at least one criterion of the
> Sub-loop Admission Gate — the canonical list lives in
> [`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate)
> and is **not** re-enumerated here. Common triggers: a complex implementation
> module; a long research task; multi-agent parallel development; a high-risk
> compliance review.
>
> **Subgraphs must not hide work that requires independent governance; subloops
> must not be created for trivial local tasks; start with the lightest sufficient
> structure and promote only when governance needs justify it.**

---

## 14. See also

- [`recursive_loops.md`](./recursive_loops.md) — the authoritative
  directory-materialized child-loop (= subloop) spec: directory root & naming,
  `loop.meta.yaml`, `child_loops[]` reference shape, `return_contract` /
  `closeout.md`, child-checkpoint additions, Sub-loop Admission Gate, the
  isolation rule, and the inline-`subgraph` vs `child_loop` table.
- [`loop_plan_spec.md`](./loop_plan_spec.md) — the plan/node field dictionary, the
  existing inline `subgraph` / `allow_subgraph` fields, the `subgraph` recursion
  rule, and the canonical Glossary.
- [`state_model.md`](./state_model.md) — the **15 canonical node statuses** (which
  the subgraph enum is deliberately distinct from), the state transition table,
  and the checkpoint / node.contract / evidence.ledger field sets.
- [`live_loop_semantics.md`](./live_loop_semantics.md) — evidence-driven growth;
  the default growth unit is a subgraph, promoted to a subloop only when
  governance complexity exceeds the threshold.
- [`human_approval.md`](./human_approval.md) — the autonomy boundary set that a
  subgraph inherits (goal / permission / risk / external-side-effect boundaries).
- [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md)
  — the two-view rhythm that decides, at runtime, which tier a node's work
  descends into and how each descent writes back to the parent.
- [`layered_execution_chain.md`](./layered_execution_chain.md)
  — the layer ladder the tiers here are routed into, the 6-step layer-switch
  cascade, and the leaf-action stop-test that ends a descent.

---

## Glossary

*Canonical spellings of every **new** locked token introduced by this document.
Downstream schemas, templates, validators, examples, `SKILL.md`, and tests MUST
cite these verbatim. Field names are lowercase snake_case; slugs are kebab-case.*

### The three execution-unit tiers (3, NEW)

- `action` — a single concrete operation, no internal planning; no directory, no
  state, not recoverable.
- `subgraph` — a lightweight runtime task DAG inside a parent node; hosted by the
  parent's state/evidence/logs; no own directory; partially recoverable.
- `subloop` — a materialized, independently recoverable & auditable Loop. **REUSED
  token: a subloop IS the directory-materialized child loop of
  [`recursive_loops.md`](./recursive_loops.md); not redefined here.**

### Subgraph statuses (8, NEW — distinct from the 15 node statuses)

`proposed`, `admitted`, `running`, `blocked`, `completed`, `failed`,
`promoted_to_subloop`, `cancelled`.

Terminal subgraph statuses: `completed`, `failed`, `promoted_to_subloop`,
`cancelled`. These are **SUBGRAPH statuses** — a separate, lighter enum from the
15 node statuses in [`state_model.md`](./state_model.md#node-status-enum).

### Subgraph control fields (NEW)

- `subgraph_id` — id with pattern `SG-<parent-node-id-short>-<seq>` (prefix `SG-`,
  3-digit zero-padded `seq`; e.g. `SG-N4-001`), immutable once created.
- `parent_node_id`, `title`, `status`, `spawn_reason`, `scope` (`{in[], out[]}`),
  `nodes` (`{id, title, status, output}`), `edges` (`[from, to]` pairs),
  `completion_gate` (`{required_outputs[], pass_condition}`), `outputs`,
  `promotion_policy` (`{status, promote_to_subloop_if[]}`).
- Optional enhancement fields: `priority`, `risk_level`, `owner_agent`,
  `created_at`, `updated_at`, `evidence_refs[]`, `decision_refs[]`,
  `attempt_count`, `max_attempts`.

### Runtime-hosting tokens (NEW)

- `node.runtime.yaml` — the per-node runtime state file
  (`nodes/<node_id>/node.runtime.yaml`); fields: `node_id`, `runtime_subgraphs[]`.
- `runtime_subgraphs` — the list of subgraphs hosted by a node (or embedded in
  `loop.state.yaml` under the same key in Option A).
- `nodes/<node_id>/` — the per-node directory holding `node.contract.yaml`,
  `node.runtime.yaml`, `node.notes.md`, and node-local `artifacts/`.
- `completion_gate` — a subgraph's local done condition
  (`{required_outputs[], pass_condition}`).
- `promotion_policy` / `promote_to_subloop_if` — the subgraph's local promotion
  policy and its list of promotion conditions.

### Promotion vocabulary (NEW)

- **Promotion Gate** — the rule that promotes a subgraph to a subloop.
- `promoted_to_subloop` — the terminal subgraph status recording a promotion.
- **Simple decision rule (verbatim):** *If it needs its own plan / state /
  checkpoint / evidence / closeout, it is a subloop. If it only needs a few nodes
  and light state, it is a subgraph.*

### Reused (NOT redefined) tokens

- **subloop = child loop** — the directory-materialized child loop; its directory
  shape, `loop.meta.yaml`, `_loops/`, `return_contract`, `closeout.md`,
  child-checkpoint additions, `child_loops[]`, and Sub-loop Admission Gate are
  defined authoritatively in [`recursive_loops.md`](./recursive_loops.md) and are
  **not** redefined here.
- `loop.meta.yaml`, `_loops/`, `artifacts/`, `closeout.md`, `return_contract` —
  from [`recursive_loops.md`](./recursive_loops.md).
- The **15 canonical node statuses** (`undiscovered`, `discovered`,
  `needs_clarification`, `pending`, `ready`, `running`, `waiting_external`,
  `waiting_user`, `blocked`, `verifying`, `verification_failed`, `retry_pending`,
  `completed`, `cancelled`, `deprecated`) — authoritative in
  [`state_model.md`](./state_model.md#node-status-enum); **never** applied to a
  subgraph.
- The existing node fields `subgraph`, `allow_subgraph`, `parent_ref` — from
  [`loop_plan_spec.md`](./loop_plan_spec.md); unchanged.
