# Failure-Mode Tests — one bad-input fixture per rejection rule

*Diataxis type: **reference test doc**. This document is the authoritative
rejection contract for the `create-loop` validators. It is written
**test-first**: `scripts/validate_loop_plan.py` and
`scripts/validate_checkpoint.py` are authored afterwards to reject exactly the
inputs below. Each rule `R1`–`R18` has **one** minimal fixture that is complete,
well-formed YAML and valid in every respect **except the single defect** that
rule targets. A correct validator exits **nonzero** on each fixture and prints a
message naming the violated rule.*

Rules `R1`–`R8` cover the base plan/checkpoint schema. Rules `R9`–`R17` cover the
recursive directory-materialized child-loop / three-tier feature added by
[`references/recursive_loops.md`](../references/recursive_loops.md) and
[`references/subgraph_subloop_policy.md`](../references/subgraph_subloop_policy.md):
they exercise the new `--kind loop_meta`, `--kind loops_index`, and
`--kind node_runtime` validator kinds, plus the new required `child_loops` node
field on `loop.plan.yaml`.

All field names and enum values are copied verbatim from
[`references/loop_plan_spec.md`](../references/loop_plan_spec.md),
[`references/state_model.md`](../references/state_model.md),
[`references/recursive_loops.md`](../references/recursive_loops.md), and
[`references/subgraph_subloop_policy.md`](../references/subgraph_subloop_policy.md).
All paths are relative to `/root/create-loop/create-loop/`.

## The rules under test

| rule | defect | validator check | script |
|------|--------|-----------------|--------|
| `R1` | dependency cycle | graph: cycle detection | `validate_loop_plan.py` |
| `R2` | dangling dependency | graph: `requires` id no node defines | `validate_loop_plan.py` |
| `R3` | missing evidence gate | graph/schema: non-trivial node with `gate: null` | `validate_loop_plan.py` |
| `R4` | bad status enum | schema: value outside the 15-status enum | `validate_loop_plan.py` |
| `R5` | missing required field | schema: node missing `id` | `validate_loop_plan.py` |
| `R6` | plan/checkpoint inconsistency | consistency: `node_states` key absent from plan | `validate_checkpoint.py --plan` |
| `R7` | bad gate kind | schema: value outside the 8-gate-kind enum | `validate_loop_plan.py` |
| `R8` | bad on_failure enum | schema: value outside the 4-step ladder | `validate_loop_plan.py` |
| `R9` | bad loop_id | schema: `loop_id` not matching `L<seq>` / `L<seq>.<seq>` | `validate_loop_plan.py --kind loop_meta` |
| `R10` | bad slug | schema: `slug` not lowercase-kebab-≤32 (caps/underscore/space/len) | `validate_loop_plan.py --kind loop_meta` |
| `R11` | missing return_contract | schema: `loop.meta.yaml` omits required `return_contract` | `validate_loop_plan.py --kind loop_meta` |
| `R12` | bad loop.meta type | schema: `type` outside `root_loop` \| `child_loop` | `validate_loop_plan.py --kind loop_meta` |
| `R13` | bad child_loops ref | schema: a node's `child_loops[]` entry missing `path` | `validate_loop_plan.py` |
| `R14` | bad subgraph status | schema: `runtime_subgraph` status outside the 8 subgraph statuses | `validate_loop_plan.py --kind node_runtime` |
| `R15` | subgraph status crossover | schema: subgraph uses a NODE status (`verification_failed`), not a subgraph status | `validate_loop_plan.py --kind node_runtime` |
| `R16` | bad INDEX shape | schema: index has BOTH `loops` and `children` keys (violates oneOf) | `validate_loop_plan.py --kind loops_index` |
| `R17` | child_loop with no parent | schema: `type: child_loop` but `parent` is null/absent | `validate_loop_plan.py --kind loop_meta` |
| `R18` | bad human_intervention_policy | schema: optional `human_intervention_policy.default_mode` outside its enum | `validate_loop_plan.py` |

Canonical enums exercised (verbatim):

- **Node statuses (15):** `undiscovered`, `discovered`, `needs_clarification`,
  `pending`, `ready`, `running`, `waiting_external`, `waiting_user`, `blocked`,
  `verifying`, `verification_failed`, `retry_pending`, `completed`, `cancelled`,
  `deprecated`. (`R4` uses `done`, which is **not** in this set. `R15` uses
  `verification_failed` — a valid *node* status but **not** a subgraph status.)
- **Gate kinds (8):** `automated_check`, `test`, `llm_judge`,
  `self_consistency`, `evaluator_optimizer`, `step_verifier`, `human_approval`,
  `artifact_exists`. (`R7` uses `vibes_check`, not in this set.)
- **`on_failure` ladder (4):** `local_retry`, `local_patch`, `replan`,
  `escalate`. (`R8` uses `give_up`, not in this set.)
- **Subgraph statuses (8):** `proposed`, `admitted`, `running`, `blocked`,
  `completed`, `failed`, `promoted_to_subloop`, `cancelled`. These are a separate,
  lighter enum from the 15 node statuses and never overlap in scope. (`R14` uses
  `done` — in neither enum; `R15` uses `verification_failed` — a node status, not
  a subgraph status.)
- **`loop.meta.yaml.type` enum (2):** `root_loop`, `child_loop`. (`R12` uses
  `superloop`, not in this set.)
- **`loop_id` pattern:** `L<seq>` (top-level, `seq` 3-digit zero-padded) and
  `L<seq>.<local-seq>` / `L<seq>.<local-seq>.<local-seq>` (child / grandchild,
  each `local-seq` 2-digit zero-padded); e.g. `L001`, `L001.02`, `L001.02.01`.
  (`R9` uses `loop-1`, which matches no form.)
- **Slug rule:** lowercase, kebab-case, English only, 2–5 words, ≤ 32 characters,
  no status, no date, no punctuation except the hyphen. (`R10` uses
  `This_Is A Very Long Slug With Caps`, which breaks case, separators, and length.)
- **`loop.meta.yaml` required fields (12):** `loop_id`, `slug`, `title`, `type`,
  `parent`, `root`, `status`, `created_at`, `created_by`, `depth`, `scope`,
  `return_contract`. (`R11` omits `return_contract`.)
- **`child_loops[]` reference fields (5):** `loop_id`, `path`, `spawn_reason`,
  `status`, `closeout`. (`R13` omits `path`.) `child_loops` itself is a **required
  node field** on every `loop.plan.yaml` node; its empty sentinel is `[]`.

---

## R1 — dependency cycle

**What's wrong:** node `a` requires `b` and node `b` requires `a`. Every field is
present and in-enum; the sole defect is a `requires` cycle, so no topological
order exists. The validator's cycle detector must reject.

```yaml
schema_version: "1.0.0"
plan_id: fixture_cycle
goal: "demonstrate a requires cycle"
true_intent: "isolate cycle detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "plan is acyclic"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: ["b"]
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
  - id: b
    kind: milestone
    title: Node B
    design_invariant: true
    status: pending
    requires: ["a"]
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/b.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_cycle.yaml
```

**Expected:** exit **nonzero**; message mentions a **cycle** (rule `R1`).

---

## R2 — dangling dependency

**What's wrong:** node `a` requires `node_x`, but no node with `id: node_x` is
defined anywhere in `nodes`. The dependency dangles. Everything else is valid.

```yaml
schema_version: "1.0.0"
plan_id: fixture_dangling
goal: "demonstrate a dangling requires"
true_intent: "isolate dangling-dependency detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every requires id resolves to a defined node"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: ["node_x"]
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_dangling.yaml
```

**Expected:** exit **nonzero**; message mentions a **dangling dependency**
(the unresolved `requires` id `node_x`) (rule `R2`).

---

## R3 — missing evidence gate

**What's wrong:** node `a` is a non-trivial `milestone` that `produces` a real
artifact but carries `gate: null`. Per
[`loop_plan_spec.md` §4](../references/loop_plan_spec.md#4-evidence-gates), every
non-trivial node must carry a gate; `null` is permitted only for trivial nodes.
This node is not trivial (it produces an artifact and is not exempt), so it must
be rejected.

```yaml
schema_version: "1.0.0"
plan_id: fixture_missing_gate
goal: "demonstrate a non-trivial node lacking a gate"
true_intent: "isolate missing-evidence-gate detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every non-trivial node has an evidence gate"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Build the deliverable
    design_invariant: true
    status: pending
    requires: []
    produces: ["artifact/deliverable.md"]
    inputs: []
    preconditions: []
    postconditions: []
    gate: null
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: high
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_missing_gate.yaml
```

**Expected:** exit **nonzero**; message mentions a **missing evidence gate**
(non-trivial node `a` with `gate: null`) (rule `R3`).

---

## R4 — bad status enum

**What's wrong:** node `a` has `status: done`. `done` is not one of the 15
canonical node statuses (the terminal success status is `completed`, not `done`).
Everything else is valid.

```yaml
schema_version: "1.0.0"
plan_id: fixture_bad_status
goal: "demonstrate an out-of-enum status"
true_intent: "isolate bad-status-enum detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every status is one of the 15 canonical values"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: done
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_status.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **status** enum
value (`done` is not one of the 15 statuses) (rule `R4`).

---

## R5 — missing required field

**What's wrong:** node `a` is missing its required `id` field. Every other field
of the node and the plan is present and valid. Schema validation must reject the
node for the absent required key.

```yaml
schema_version: "1.0.0"
plan_id: fixture_missing_field
goal: "demonstrate a node missing its id"
true_intent: "isolate missing-required-field detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every node has an id"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_missing_field.yaml
```

**Expected:** exit **nonzero**; message mentions a **missing required field**
(`id`) (rule `R5`).

---

## R6 — plan/checkpoint inconsistency

**What's wrong:** the checkpoint's `node_states` references a node id (`ghost`)
that is not defined in the plan it is validated against. The plan and the
checkpoint are each individually valid, and their `plan_version` values match
(`1` and `1`), so the **only** defect is the node-id mismatch surfaced by
`validate_checkpoint.py --plan`.

First, the (valid) plan the checkpoint is checked against:

```yaml
schema_version: "1.0.0"
plan_id: fixture_consistency
goal: "demonstrate a checkpoint referencing an unknown node"
true_intent: "isolate plan/checkpoint consistency detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "checkpoint node_states keys are a subset of plan node ids"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

Then the checkpoint whose `node_states` names `ghost` (absent from the plan):

```yaml
schema_version: "1.0.0"
plan_id: fixture_consistency
plan_version: 1
checkpoint_id: ckpt_1
created: "2026-07-01T14:30:00Z"
phase: 0
node_states:
  ghost: pending
ready_set: []
last_completed: []
blocked: []
pending_approvals: []
next_suggested_action: "start node a"
open_assumptions: []
event_log_ref: events/log.jsonl
evidence_ledger_ref: evidence/ledger.json
cost_units_spent: 0
iteration: 0
```

**Command:**

```bash
python3 scripts/validate_checkpoint.py /tmp/fixture_ckpt_inconsistent.yaml \
        --plan /tmp/fixture_consistency_plan.yaml
```

**Expected:** exit **nonzero**; message mentions a **plan/checkpoint
inconsistency** — `node_states` key `ghost` has no matching node id in the plan
(rule `R6`).

---

## R7 — bad gate kind

**What's wrong:** node `a`'s `gate.kind` is `vibes_check`, which is not one of
the 8 canonical gate kinds. Every other field is valid.

```yaml
schema_version: "1.0.0"
plan_id: fixture_bad_gate_kind
goal: "demonstrate an out-of-enum gate kind"
true_intent: "isolate bad-gate-kind detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every gate.kind is one of the 8 canonical kinds"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: vibes_check
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_gate_kind.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **gate kind**
(`vibes_check` is not one of the 8 gate kinds) (rule `R7`).

---

## R8 — bad on_failure enum

**What's wrong:** node `a`'s `on_failure` is `give_up`, which is not one of the 4
ordered escalation-ladder steps. Every other field is valid.

```yaml
schema_version: "1.0.0"
plan_id: fixture_bad_on_failure
goal: "demonstrate an out-of-enum on_failure"
true_intent: "isolate bad-on_failure-enum detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every on_failure is one of the 4 ladder steps"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: give_up
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_on_failure.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **on_failure** enum
value (`give_up` is not one of `local_retry`, `local_patch`, `replan`,
`escalate`) (rule `R8`).

---

## R9 — bad loop_id (loop.meta.yaml)

**What's wrong:** `loop_id: "loop-1"` matches neither the top-level form `L<seq>`
(e.g. `L001`) nor the child form `L<seq>.<seq>` (e.g. `L001.02`). All 12 required
`loop.meta.yaml` fields are present and otherwise valid; the sole defect is the
malformed `loop_id`.

```yaml
loop_id: "loop-1"
slug: create-loop-skill
title: Build the create-loop Agent Skill
type: root_loop
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_bad_loop_id.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **loop_id** pattern
(`loop-1` matches neither `L<seq>` nor `L<seq>.<seq>`) (rule `R9`).

---

## R10 — bad slug (loop.meta.yaml)

**What's wrong:** `slug: "This_Is A Very Long Slug With Caps"` violates the slug
rule on multiple counts (uppercase, underscores, spaces, and length > 32
characters); a slug must be lowercase kebab-case, English only, 2–5 words,
≤ 32 characters, no punctuation except the hyphen. Every other field is valid; the
sole targeted defect is the malformed `slug`.

```yaml
loop_id: L001
slug: "This_Is A Very Long Slug With Caps"
title: Build the create-loop Agent Skill
type: root_loop
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_bad_slug.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **slug** (not
lowercase-kebab / contains caps, underscores, spaces / exceeds 32 chars)
(rule `R10`).

---

## R11 — missing return_contract (loop.meta.yaml)

**What's wrong:** the `loop.meta.yaml` omits the required `return_contract` field.
The other 11 required fields are present and valid; the sole defect is the absent
required `return_contract`.

```yaml
loop_id: L001
slug: create-loop-skill
title: Build the create-loop Agent Skill
type: root_loop
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_missing_return_contract.yaml
```

**Expected:** exit **nonzero**; message mentions a **missing required field**
(`return_contract`) (rule `R11`).

---

## R12 — bad loop.meta type (loop.meta.yaml)

**What's wrong:** `type: "superloop"` is outside the 2-value `type` enum
(`root_loop` | `child_loop`). Every other field is present and valid; the sole
defect is the out-of-enum `type`.

```yaml
loop_id: L001
slug: create-loop-skill
title: Build the create-loop Agent Skill
type: "superloop"
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_bad_type.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **type** enum value
(`superloop` is not one of `root_loop`, `child_loop`) (rule `R12`).

---

## R13 — bad child_loops ref (loop.plan.yaml)

**What's wrong:** node `a` carries a `child_loops[]` entry that is missing the
required `path` field. A `child_loops[]` reference object must have **exactly** the
five fields `loop_id`, `path`, `spawn_reason`, `status`, `closeout`. Everything
else in the plan and node is valid; the sole defect is the incomplete reference.

```yaml
schema_version: "1.0.0"
plan_id: fixture_bad_child_ref
goal: "demonstrate a child_loops entry missing path"
true_intent: "isolate bad-child_loops-ref detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every child_loops entry has loop_id, path, spawn_reason, status, closeout"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: running
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: true
    subgraph: null
    child_loops:
      - loop_id: L001.02
        spawn_reason: "high complexity (Admission Gate #1)"
        status: running
        closeout: _loops/L001.02-design-loop-spec/closeout.md
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fx_bad_child_ref.yaml
```

**Expected:** exit **nonzero**; message mentions a malformed **child_loops**
reference (entry missing required `path`) (rule `R13`).

---

## R14 — bad subgraph status (node.runtime.yaml)

**What's wrong:** the `runtime_subgraphs[]` entry has `status: "done"`. `done` is
in **neither** the 8 subgraph statuses nor the 15 node statuses. A subgraph's
`status` must be one of `proposed`, `admitted`, `running`, `blocked`, `completed`,
`failed`, `promoted_to_subloop`, `cancelled`. Everything else mirrors the
reference's own valid `node.runtime.yaml` example; the sole defect is the
out-of-enum subgraph status.

```yaml
node_id: N4_design_loop_spec
runtime_subgraphs:
  - subgraph_id: SG-N4-001
    title: Compare three state-persistence approaches
    status: "done"
    created_at: 2026-07-01T14:30:00Z
    spawn_reason: >-
      Local decision fan-out: the design node must choose among three
      state-persistence approaches before it can produce design-spec.md.
    scope:
      in:
        - compare checkpoint-only vs event-sourced vs hybrid persistence
      out:
        - implementing the chosen approach (belongs to a later node)
    nodes:
      - id: sg-collect-options
        title: Enumerate the three candidate approaches
        status: completed
        output: artifacts/persistence-options.md
      - id: sg-pick
        title: Record the chosen approach + rationale
        status: pending
        output: null
    edges:
      - [sg-collect-options, sg-pick]
    completion_gate:
      required_outputs:
        - artifacts/persistence-options.md
        - artifacts/persistence-decision.md
      pass_condition: >-
        one approach chosen with a recorded rationale
    outputs:
      - artifacts/persistence-decision.md
    promotion_policy:
      status: not_promoted
      promote_to_subloop_if:
        - the comparison expands into a full multi-phase design effort
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind node_runtime /tmp/fx_bad_subgraph_status.yaml
```

**Expected:** exit **nonzero**; message mentions an invalid **subgraph status**
(`done` is not one of the 8 subgraph statuses) (rule `R14`).

---

## R15 — subgraph status crossover (node.runtime.yaml)

**What's wrong:** the `runtime_subgraphs[]` entry has `status:
"verification_failed"`. That value **is** a valid *node* status (one of the 15),
but it is **not** a subgraph status. A subgraph must never carry a node status;
the two enums are disjoint by design. This fixture proves the two enums do not
bleed into each other. Everything else is valid; the sole defect is the
node-status value used where a subgraph status is required.

```yaml
node_id: N4_design_loop_spec
runtime_subgraphs:
  - subgraph_id: SG-N4-001
    title: Compare three state-persistence approaches
    status: "verification_failed"
    created_at: 2026-07-01T14:30:00Z
    spawn_reason: >-
      Local decision fan-out: the design node must choose among three
      state-persistence approaches before it can produce design-spec.md.
    scope:
      in:
        - compare checkpoint-only vs event-sourced vs hybrid persistence
      out:
        - implementing the chosen approach (belongs to a later node)
    nodes:
      - id: sg-collect-options
        title: Enumerate the three candidate approaches
        status: completed
        output: artifacts/persistence-options.md
      - id: sg-pick
        title: Record the chosen approach + rationale
        status: pending
        output: null
    edges:
      - [sg-collect-options, sg-pick]
    completion_gate:
      required_outputs:
        - artifacts/persistence-options.md
        - artifacts/persistence-decision.md
      pass_condition: >-
        one approach chosen with a recorded rationale
    outputs:
      - artifacts/persistence-decision.md
    promotion_policy:
      status: not_promoted
      promote_to_subloop_if:
        - the comparison expands into a full multi-phase design effort
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind node_runtime /tmp/fx_subgraph_status_crossover.yaml
```

**Expected:** exit **nonzero**; message mentions a **subgraph status** enum
violation — `verification_failed` is a node status, not one of the 8 subgraph
statuses (rule `R15`).

---

## R16 — bad INDEX shape (loops.index)

**What's wrong:** the index file carries **both** the `loops` key (global-index
shape) and the `children` key (local-index shape). The two shapes are mutually
exclusive (a `oneOf`): a global `INDEX.yaml` has `loops[]`; a local
`_loops/INDEX.yaml` has `children[]`. Carrying both is ambiguous. Each entry is
otherwise well-formed; the sole defect is the ambiguous top-level shape.

```yaml
loops:
  - loop_id: L001
    slug: create-loop-skill
    path: L001-create-loop-skill
    status: running
    title: Build the create-loop Agent Skill
    checkpoint: L001-create-loop-skill/checkpoint.yaml
    updated_at: 2026-07-01T15:10:00Z
children:
  - loop_id: L001.01
    slug: research-loop-eng
    path: L001.01-research-loop-eng
    status: completed
    parent_node_id: n-research
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind loops_index /tmp/fx_bad_index_shape.yaml
```

**Expected:** exit **nonzero**; message mentions an ambiguous **INDEX** shape —
both `loops` and `children` present, violating the `oneOf` (rule `R16`).

---

## R17 — child_loop with null/absent parent (loop.meta.yaml)

**What's wrong:** `type: child_loop` but `parent` is `null`. A `child_loop` MUST
carry a `parent` object (`{loop_id, path, parent_node_id, spawn_reason}`); `null`
is permitted for `parent` **only** on a `root_loop`. All 12 required fields are
present; the sole defect is the missing parent relation on a child loop.

```yaml
loop_id: L001.02
slug: design-loop-spec
title: Design the loop spec
type: child_loop
parent: null
root:
  loop_id: L001
  path: ../..
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 1
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_child_no_parent.yaml
```

**Expected:** exit **nonzero**; message mentions a `child_loop` with a missing
**parent** object (`null`/absent `parent` is allowed only for a `root_loop`)
(rule `R17`).

---

## R18 — bad human_intervention_policy (loop.plan.yaml)

**What's wrong:** the OPTIONAL top-level `human_intervention_policy` block is
present but its `default_mode` is `"vibes"`, which is outside the 2-value enum
(`structured_decision_package` | `direct_question`). The
`human_intervention_policy` field is optional (a plan omitting it entirely stays
valid); this fixture proves that **when the block is present**, its enum-typed
members are still checked. Every one of the 12 required top-level fields is
present, `child_loops: []` is set on the node, and every other value is
in-enum — the sole defect is the bad `default_mode`.

```yaml
schema_version: "1.0.0"
plan_id: fixture_bad_hip
goal: "demonstrate an out-of-enum human_intervention_policy default_mode"
true_intent: "isolate bad-human_intervention_policy detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "human_intervention_policy default_mode is one of the 2 modes"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
human_intervention_policy:
  default_mode: "vibes"
  forbid_low_context_questions: true
  require_context_complete_package: true
  require_machine_ingestible_answer: true
  preferred_answer_format: yaml
  decision_package_required_when:
    - top_level_goal_change
    - irreversible_operation
  package_must_include:
    - decision_id
    - required_decision
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate:
      kind: artifact_exists
      threshold: null
      rubric: null
      evidence_ref: evidence/a.json
    retry_policy:
      max_attempts: 3
      backoff_base_seconds: 2
      jitter: true
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py /tmp/fx_bad_hip.yaml
```

**Expected:** exit **nonzero**; message mentions the
**human_intervention_policy** field — `default_mode` `vibes` is not one of
`structured_decision_package`, `direct_question` (rule `R18`).

---

## Materialize fixtures and assert rejection

Copy-paste this block. Run it from `/root/create-loop/create-loop/`. It writes
each fixture above to `/tmp/fixture_<name>.yaml` (byte-identical to the fenced
YAML), then runs each command asserting a **nonzero** exit. The pattern
`<cmd> && echo FAIL || echo PASS-rejected` prints `PASS-rejected` only when the
validator correctly exits nonzero; any `FAIL` line means the validator wrongly
accepted a bad input.

```bash
set -uo pipefail
cd /root/create-loop/create-loop

# ---- R1 cycle ----
cat > /tmp/fixture_cycle.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_cycle
goal: "demonstrate a requires cycle"
true_intent: "isolate cycle detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "plan is acyclic"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: ["b"]
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
  - id: b
    kind: milestone
    title: Node B
    design_invariant: true
    status: pending
    requires: ["a"]
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/b.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R1 cycle: "
python3 scripts/validate_loop_plan.py /tmp/fixture_cycle.yaml && echo FAIL || echo PASS-rejected

# ---- R2 dangling ----
cat > /tmp/fixture_dangling.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_dangling
goal: "demonstrate a dangling requires"
true_intent: "isolate dangling-dependency detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every requires id resolves to a defined node"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: ["node_x"]
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R2 dangling: "
python3 scripts/validate_loop_plan.py /tmp/fixture_dangling.yaml && echo FAIL || echo PASS-rejected

# ---- R3 missing gate ----
cat > /tmp/fixture_missing_gate.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_missing_gate
goal: "demonstrate a non-trivial node lacking a gate"
true_intent: "isolate missing-evidence-gate detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every non-trivial node has an evidence gate"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Build the deliverable
    design_invariant: true
    status: pending
    requires: []
    produces: ["artifact/deliverable.md"]
    inputs: []
    preconditions: []
    postconditions: []
    gate: null
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: high
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R3 missing_gate: "
python3 scripts/validate_loop_plan.py /tmp/fixture_missing_gate.yaml && echo FAIL || echo PASS-rejected

# ---- R4 bad status ----
cat > /tmp/fixture_bad_status.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_bad_status
goal: "demonstrate an out-of-enum status"
true_intent: "isolate bad-status-enum detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every status is one of the 15 canonical values"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: done
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R4 bad_status: "
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_status.yaml && echo FAIL || echo PASS-rejected

# ---- R5 missing required field (node has no id) ----
cat > /tmp/fixture_missing_field.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_missing_field
goal: "demonstrate a node missing its id"
true_intent: "isolate missing-required-field detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every node has an id"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R5 missing_field: "
python3 scripts/validate_loop_plan.py /tmp/fixture_missing_field.yaml && echo FAIL || echo PASS-rejected

# ---- R6 plan/checkpoint inconsistency ----
cat > /tmp/fixture_consistency_plan.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_consistency
goal: "demonstrate a checkpoint referencing an unknown node"
true_intent: "isolate plan/checkpoint consistency detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "checkpoint node_states keys are a subset of plan node ids"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
cat > /tmp/fixture_ckpt_inconsistent.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_consistency
plan_version: 1
checkpoint_id: ckpt_1
created: "2026-07-01T14:30:00Z"
phase: 0
node_states:
  ghost: pending
ready_set: []
last_completed: []
blocked: []
pending_approvals: []
next_suggested_action: "start node a"
open_assumptions: []
event_log_ref: events/log.jsonl
evidence_ledger_ref: evidence/ledger.json
cost_units_spent: 0
iteration: 0
YAML
echo -n "R6 inconsistency: "
python3 scripts/validate_checkpoint.py /tmp/fixture_ckpt_inconsistent.yaml \
        --plan /tmp/fixture_consistency_plan.yaml && echo FAIL || echo PASS-rejected

# ---- R7 bad gate kind ----
cat > /tmp/fixture_bad_gate_kind.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_bad_gate_kind
goal: "demonstrate an out-of-enum gate kind"
true_intent: "isolate bad-gate-kind detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every gate.kind is one of the 8 canonical kinds"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: vibes_check, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R7 bad_gate_kind: "
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_gate_kind.yaml && echo FAIL || echo PASS-rejected

# ---- R8 bad on_failure ----
cat > /tmp/fixture_bad_on_failure.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_bad_on_failure
goal: "demonstrate an out-of-enum on_failure"
true_intent: "isolate bad-on_failure-enum detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every on_failure is one of the 4 ladder steps"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: give_up
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R8 bad_on_failure: "
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_on_failure.yaml && echo FAIL || echo PASS-rejected

# ---- R9 bad loop_id ----
cat > /tmp/fx_bad_loop_id.yaml <<'YAML'
loop_id: "loop-1"
slug: create-loop-skill
title: Build the create-loop Agent Skill
type: root_loop
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
YAML
echo -n "R9 bad_loop_id: "
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_bad_loop_id.yaml && echo FAIL || echo PASS-rejected

# ---- R10 bad slug ----
cat > /tmp/fx_bad_slug.yaml <<'YAML'
loop_id: L001
slug: "This_Is A Very Long Slug With Caps"
title: Build the create-loop Agent Skill
type: root_loop
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
YAML
echo -n "R10 bad_slug: "
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_bad_slug.yaml && echo FAIL || echo PASS-rejected

# ---- R11 missing return_contract ----
cat > /tmp/fx_missing_return_contract.yaml <<'YAML'
loop_id: L001
slug: create-loop-skill
title: Build the create-loop Agent Skill
type: root_loop
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
YAML
echo -n "R11 missing_return_contract: "
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_missing_return_contract.yaml && echo FAIL || echo PASS-rejected

# ---- R12 bad loop.meta type ----
cat > /tmp/fx_bad_type.yaml <<'YAML'
loop_id: L001
slug: create-loop-skill
title: Build the create-loop Agent Skill
type: "superloop"
parent: null
root:
  loop_id: L001
  path: .
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 0
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
YAML
echo -n "R12 bad_type: "
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_bad_type.yaml && echo FAIL || echo PASS-rejected

# ---- R13 bad child_loops ref (missing path) ----
cat > /tmp/fx_bad_child_ref.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_bad_child_ref
goal: "demonstrate a child_loops entry missing path"
true_intent: "isolate bad-child_loops-ref detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "every child_loops entry has loop_id, path, spawn_reason, status, closeout"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: running
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: true
    subgraph: null
    child_loops:
      - loop_id: L001.02
        spawn_reason: "high complexity (Admission Gate #1)"
        status: running
        closeout: _loops/L001.02-design-loop-spec/closeout.md
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R13 bad_child_ref: "
python3 scripts/validate_loop_plan.py /tmp/fx_bad_child_ref.yaml && echo FAIL || echo PASS-rejected

# ---- R14 bad subgraph status ----
cat > /tmp/fx_bad_subgraph_status.yaml <<'YAML'
node_id: N4_design_loop_spec
runtime_subgraphs:
  - subgraph_id: SG-N4-001
    title: Compare three state-persistence approaches
    status: "done"
    created_at: 2026-07-01T14:30:00Z
    spawn_reason: >-
      Local decision fan-out: the design node must choose among three
      state-persistence approaches before it can produce design-spec.md.
    scope:
      in:
        - compare checkpoint-only vs event-sourced vs hybrid persistence
      out:
        - implementing the chosen approach (belongs to a later node)
    nodes:
      - id: sg-collect-options
        title: Enumerate the three candidate approaches
        status: completed
        output: artifacts/persistence-options.md
      - id: sg-pick
        title: Record the chosen approach + rationale
        status: pending
        output: null
    edges:
      - [sg-collect-options, sg-pick]
    completion_gate:
      required_outputs:
        - artifacts/persistence-options.md
        - artifacts/persistence-decision.md
      pass_condition: >-
        one approach chosen with a recorded rationale
    promotion:
      status: not_promoted
      promote_to_subloop_if:
        - the comparison expands into a full multi-phase design effort
YAML
echo -n "R14 bad_subgraph_status: "
python3 scripts/validate_loop_plan.py --kind node_runtime /tmp/fx_bad_subgraph_status.yaml && echo FAIL || echo PASS-rejected

# ---- R15 subgraph status crossover (node status used for subgraph) ----
cat > /tmp/fx_subgraph_status_crossover.yaml <<'YAML'
node_id: N4_design_loop_spec
runtime_subgraphs:
  - subgraph_id: SG-N4-001
    title: Compare three state-persistence approaches
    status: "verification_failed"
    created_at: 2026-07-01T14:30:00Z
    spawn_reason: >-
      Local decision fan-out: the design node must choose among three
      state-persistence approaches before it can produce design-spec.md.
    scope:
      in:
        - compare checkpoint-only vs event-sourced vs hybrid persistence
      out:
        - implementing the chosen approach (belongs to a later node)
    nodes:
      - id: sg-collect-options
        title: Enumerate the three candidate approaches
        status: completed
        output: artifacts/persistence-options.md
      - id: sg-pick
        title: Record the chosen approach + rationale
        status: pending
        output: null
    edges:
      - [sg-collect-options, sg-pick]
    completion_gate:
      required_outputs:
        - artifacts/persistence-options.md
        - artifacts/persistence-decision.md
      pass_condition: >-
        one approach chosen with a recorded rationale
    promotion:
      status: not_promoted
      promote_to_subloop_if:
        - the comparison expands into a full multi-phase design effort
YAML
echo -n "R15 subgraph_status_crossover: "
python3 scripts/validate_loop_plan.py --kind node_runtime /tmp/fx_subgraph_status_crossover.yaml && echo FAIL || echo PASS-rejected

# ---- R16 bad INDEX shape (both loops and children) ----
cat > /tmp/fx_bad_index_shape.yaml <<'YAML'
loops:
  - loop_id: L001
    slug: create-loop-skill
    path: L001-create-loop-skill
    status: running
    title: Build the create-loop Agent Skill
    checkpoint: L001-create-loop-skill/checkpoint.yaml
    updated_at: 2026-07-01T15:10:00Z
children:
  - loop_id: L001.01
    slug: research-loop-eng
    path: L001.01-research-loop-eng
    status: completed
    parent_node_id: n-research
YAML
echo -n "R16 bad_index_shape: "
python3 scripts/validate_loop_plan.py --kind loops_index /tmp/fx_bad_index_shape.yaml && echo FAIL || echo PASS-rejected

# ---- R17 child_loop with null/absent parent ----
cat > /tmp/fx_child_no_parent.yaml <<'YAML'
loop_id: L001.02
slug: design-loop-spec
title: Design the loop spec
type: child_loop
parent: null
root:
  loop_id: L001
  path: ../..
status: running
created_at: 2026-07-01T14:30:00Z
created_by: agent
depth: 1
scope:
  in: []
  out: []
return_contract:
  closeout_file: closeout.md
  required_outputs: []
  parent_updates: []
YAML
echo -n "R17 child_no_parent: "
python3 scripts/validate_loop_plan.py --kind loop_meta /tmp/fx_child_no_parent.yaml && echo FAIL || echo PASS-rejected

# ---- R18 bad human_intervention_policy (optional field, bad default_mode enum) ----
cat > /tmp/fx_bad_hip.yaml <<'YAML'
schema_version: "1.0.0"
plan_id: fixture_bad_hip
goal: "demonstrate an out-of-enum human_intervention_policy default_mode"
true_intent: "isolate bad-human_intervention_policy detection"
non_goals: []
success_criteria:
  - id: sc1
    statement: "human_intervention_policy default_mode is one of the 2 modes"
    measurable: true
failure_criteria: []
termination:
  max_iterations: 10
  max_wall_clock_hours: null
  max_cost_units: null
  done_when: "all success_criteria met and all top-level nodes completed"
constraints: []
human_intervention_policy:
  default_mode: "vibes"
  forbid_low_context_questions: true
  require_context_complete_package: true
  require_machine_ingestible_answer: true
  preferred_answer_format: yaml
  decision_package_required_when:
    - top_level_goal_change
    - irreversible_operation
  package_must_include:
    - decision_id
    - required_decision
nodes:
  - id: a
    kind: milestone
    title: Node A
    design_invariant: true
    status: pending
    requires: []
    produces: []
    inputs: []
    preconditions: []
    postconditions: []
    gate: {kind: artifact_exists, threshold: null, rubric: null, evidence_ref: evidence/a.json}
    retry_policy: {max_attempts: 3, backoff_base_seconds: 2, jitter: true}
    on_failure: local_retry
    priority: 1
    risk: low
    parallelizable: false
    allow_subgraph: false
    subgraph: null
    child_loops: []
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R18 bad_human_intervention_policy: "
python3 scripts/validate_loop_plan.py /tmp/fx_bad_hip.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** eighteen lines, each ending `PASS-rejected` — one per rule
`R1`–`R18`. No `FAIL` may appear.

---

## R19 — non-terminal dead-end (deprecated-dependency deadlock)

**What's wrong:** node `n2` (status `pending`) requires `n1`, but `n1` is
`deprecated` with no superseding rewire. `n2` can never become `ready` — a
retired node silently deadlocks its dependent. The transition table's
deprecated-dependent re-evaluation rule forbids this.

Checkpoint fixture (validated against its plan):

```yaml
schema_version: "1.0"
plan_id: p-deadend
plan_version: 1
checkpoint_id: cp-1
created: "2026-07-02"
phase: 0
node_states:
  n1: deprecated
  n2: pending
ready_set: []
last_completed: []
blocked: []
pending_approvals: []
next_suggested_action: "advance"
open_assumptions: []
event_log_ref: events.jsonl
evidence_ledger_ref: evidence.ledger.yaml
cost_units_spent: 0
iteration: 1
```

Companion plan (minimal, valid): two nodes `n1`,`n2` where `n2` requires `n1`.

**Command:**

```bash
python3 scripts/validate_checkpoint.py /tmp/fx_deadend_ckpt.yaml --plan /tmp/fx_deadend_plan.yaml
```

**Expected:** exit nonzero; message tags `[R19 NON-TERMINAL DEAD-END]` naming `n2`
and its deprecated dependency `n1`.

---

## R20 — `escalate` used as a node status

**What's wrong:** the checkpoint records `node_states.n1: escalate`. `escalate`
is an escalation-ladder rung, NOT one of the 15 node statuses; the only legal
values are the 15 in the status enum (a human escalation is represented as
`waiting_user`).

```yaml
schema_version: "1.0"
plan_id: p-esc
plan_version: 1
checkpoint_id: cp-1
created: "2026-07-02"
phase: 0
node_states:
  n1: escalate
ready_set: []
last_completed: []
blocked: []
pending_approvals: []
next_suggested_action: "resolve"
open_assumptions: []
event_log_ref: events.jsonl
evidence_ledger_ref: evidence.ledger.yaml
cost_units_spent: 0
iteration: 1
```

**Command:**

```bash
python3 scripts/validate_checkpoint.py /tmp/fx_escalate_status.yaml
```

**Expected:** exit nonzero; message tags `[R20 ESCALATE-NOT-A-STATUS]`.

---

## R25 — subgraph fake completion (no evidence)

**What's wrong:** a subgraph-local node has `status: completed` but `output: null`.
A subgraph is held to the same "evidence, not the agent, says done" rule as a
full node — a completed subgraph node MUST record its evidence artifact in
`output`. (Equivalently, a subgraph whose own `status` is `completed` must carry
a `completion_gate.pass_condition`.)

```yaml
node_id: n4_build
runtime_subgraphs:
  - subgraph_id: SG-n4-001
    title: Fix the effectiveness defect
    status: running
    spawn_reason: "local diagnostic + fix"
    scope:
      in: [reproduce the defect]
      out: [redesign the module]
    nodes:
      - id: s1
        title: Reproduce
        status: completed
        output: null
    edges: []
    completion_gate:
      required_outputs: [artifacts/repro.md]
      pass_condition: "defect reproduced"
    outputs: []
    promotion_policy:
      status: not_promoted
      promote_to_subloop_if: []
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind node_runtime /tmp/fx_subgraph_fakecomplete.yaml
```

**Expected:** exit nonzero; message tags `[R25 SUBGRAPH-FAKE-COMPLETION]` naming
the completed local node with the null `output`.

---

## R26 — unapproved (silent) goal change

**What's wrong:** the plan's `goal` was changed but the latest `plan_history`
entry's `goal_hash` was not updated through an approved, provenanced version
bump. The validator recomputes `sha256(normalized goal)` and rejects when it
does not match the recorded hash — a silent goal mutation cannot pass.

Reproduce from the known-good template plan (any valid plan works):

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/loop.plan.yaml"))
d["goal"] = "A completely different, never-approved goal"   # mutate goal only
yaml.safe_dump(d, open("/tmp/fx_silent_goal_change.yaml", "w"), sort_keys=False)
PY
python3 scripts/validate_loop_plan.py /tmp/fx_silent_goal_change.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R26 UNAPPROVED-GOAL-CHANGE]`.

---

## R27 — malformed plan_history

**What's wrong:** a `plan_history` entry is missing `goal_hash` (a required
provenance field), or the entry's `plan_version` does not match the plan's
top-level `plan_version`, or versions are not unique+increasing.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/loop.plan.yaml"))
del d["plan_history"][0]["goal_hash"]   # drop a required provenance field
yaml.safe_dump(d, open("/tmp/fx_bad_plan_history.yaml", "w"), sort_keys=False)
PY
python3 scripts/validate_loop_plan.py /tmp/fx_bad_plan_history.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R27 BAD plan_history]`.

---

## R32 — bad checkpoint_seq

**What's wrong:** `checkpoint_seq` is not a non-negative integer (here a string).
Resume selects the latest checkpoint by MAX `checkpoint_seq`, so a non-integer
breaks monotonic ordering.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/checkpoint.yaml"))
d["checkpoint_seq"] = "3"   # must be an int
yaml.safe_dump(d, open("/tmp/fx_bad_checkpoint_seq.yaml", "w"), sort_keys=False)
PY
python3 scripts/validate_checkpoint.py /tmp/fx_bad_checkpoint_seq.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R32 BAD-CHECKPOINT-SEQ]`.

---

## R35 — top-level design_invariant:false

**What's wrong:** a top-level node declares `design_invariant: false`. The
top-level graph holds only design-time invariants; runtime-discovered work must
live in a subgraph or child loop.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/loop.plan.yaml"))
d["nodes"][0]["design_invariant"] = False
yaml.safe_dump(d, open("/tmp/fx_toplevel_invariant_false.yaml", "w"), sort_keys=False)
PY
python3 scripts/validate_loop_plan.py /tmp/fx_toplevel_invariant_false.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R35 TOPLEVEL-INVARIANT-FALSE]`.

---

## R21 — bad claim file

**What's wrong:** a `contracts/<node>.claim` file is missing a required lease
field (here `lease_expires_at`). Without an expiry the lease can neither be
renewed nor reclaimed — single-flight breaks.

```yaml
node_id: n7_implementation
owner_id: session-abc
acquired_at: "2026-07-02T14:00:00Z"
phase: 0
heartbeat_at: "2026-07-02T14:05:00Z"
delegated_to: null
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind claim /tmp/fx_bad_claim.yaml
```

**Expected:** exit nonzero; message tags `[R21 BAD-CLAIM]` naming
`lease_expires_at`.

---

## R22 — unclaimed running node (concurrency mode)

**What's wrong:** under **concurrency mode** a checkpoint has a node in status
`running`, but no claim file exists for it in the `contracts/` directory. A
running node MUST hold a claim (single-flight); a crash leaves an *expired*
claim, never none. R22 fires **only** when the loop opts into concurrency via
`--enforce-claims` — in the default single-agent, manual-reentry model a loop has
no claim files and their absence is legitimate, so R22 stays silent (this avoids
false-positives on the skill's default degraded runtime).

Checkpoint fixture (validated with an empty claims dir):

```yaml
schema_version: "1.0"
plan_id: p-r22
plan_version: 1
checkpoint_id: cp-1
checkpoint_seq: 1
created: "2026-07-02"
phase: 0
node_states:
  n1: running
ready_set: []
last_completed: []
blocked: []
pending_approvals: []
next_suggested_action: "advance"
open_assumptions: []
event_log_ref: events.jsonl
evidence_ledger_ref: evidence.ledger.yaml
cost_units_spent: 0
iteration: 1
```

**Command:**

```bash
mkdir -p /tmp/fx_r22_claims_empty
# Default (no concurrency opt-in): absence of a claim is NOT a violation.
python3 scripts/validate_checkpoint.py /tmp/fx_r22_unclaimed.yaml --claims /tmp/fx_r22_claims_empty && echo "default-mode: allowed (correct)"
# Concurrency mode: --enforce-claims makes the unclaimed running node a violation.
python3 scripts/validate_checkpoint.py /tmp/fx_r22_unclaimed.yaml --claims /tmp/fx_r22_claims_empty --enforce-claims && echo FAIL || echo PASS-rejected
```

**Expected:** the default run exits `0` (claims optional); the `--enforce-claims`
run exits nonzero with `[R22 UNCLAIMED-RUNNING]` naming `n1`.

---

## R33 — child-loop checkpoint missing a required field

**What's wrong:** the owning `loop.meta.type == child_loop`, but the checkpoint
omits one of the 7 child-loop fields (here `parent_node_id`). A child-loop
checkpoint must carry all 7 so a fresh session can locate its parent and return
contract.

Reproduce from the shipped child-loop example:

```bash
CH=examples/example_child_loop_tree/L001-example-delivery/_loops/L001.01-fix-effectiveness-bug
python3 - <<PY
import yaml
d = yaml.safe_load(open("$CH/checkpoint.yaml"))
d.pop("parent_node_id", None)
yaml.safe_dump(d, open("/tmp/fx_child_missing_field.yaml", "w"), sort_keys=False)
PY
python3 scripts/validate_checkpoint.py /tmp/fx_child_missing_field.yaml --meta $CH/loop.meta.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R33 CHILD-FIELD-MISSING]`.

---

## R34 — approval node without a human_approval gate

**What's wrong:** a node of kind `approval` has `gate: null` (or a gate whose
kind is not `human_approval`). An approval node is the control point that
suspends on `waiting_user` and records the user's verdict — it must carry a
`human_approval` gate.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/loop.plan.yaml"))
for n in d["nodes"]:
    if n.get("kind") == "approval":
        n["gate"] = None
yaml.safe_dump(d, open("/tmp/fx_approval_nogate.yaml", "w"), sort_keys=False)
PY
python3 scripts/validate_loop_plan.py /tmp/fx_approval_nogate.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R34 APPROVAL-GATE-REQUIRED]`.

---

## R23 — in-doubt non-idempotent event

**What's wrong:** the event log has a `pre_effect` entry with no matching
`post_effect` and no `idempotency_key`. This is an in-doubt transaction — a crash
after the side effect but before its outcome was recorded. Recovery cannot know
whether the effect happened, and without an idempotency key it cannot safely
re-run.

```yaml
schema_version: "1.0"
entries:
  - seq: 0
    node_id: n7_deploy
    ts: "2026-07-02T14:00:00Z"
    kind: pre_effect
    intent: "post the deploy webhook"
    idempotency_key: null
    outcome: null
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind event_log /tmp/fx_indoubt.yaml
```

**Expected:** exit nonzero; message tags `[R23 IN-DOUBT-NONIDEMPOTENT]`.

---

## R24 — invalid event_log seq

**What's wrong:** `entries[].seq` is negative, or is not strictly increasing
(here 5 then 3). The log uses non-negative, strictly monotonic values so replay
has a total order. Gaps are valid; R24 does not require a contiguous counter.

```yaml
schema_version: "1.0"
entries:
  - {seq: -1, node_id: n1, ts: "2026-07-02T13:59:00Z", kind: note}
  - {seq: 5, node_id: n1, ts: "2026-07-02T14:00:00Z", kind: note}
  - {seq: 3, node_id: n1, ts: "2026-07-02T14:01:00Z", kind: note}
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind event_log /tmp/fx_eventlog_seq.yaml
```

**Expected:** exit nonzero; message tags `[R24 EVENTLOG-SEQ]`.

---

## R28 — recursion/child-loop cap exceeded

**What's wrong:** the plan declares more child loops (or deeper nesting) than
`termination.max_child_loops` / `max_depth` allows — unbounded growth.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/loop.plan.yaml"))
d["termination"]["max_child_loops"] = 0
for n in d["nodes"]:
    if n.get("allow_subgraph"):
        n["child_loops"] = [{"loop_id":"L001.01","path":"_loops/x","spawn_reason":"r","status":"running","closeout":"c"}]
        break
yaml.safe_dump(d, open("/tmp/fx_overcap.yaml","w"), sort_keys=False, width=100)
PY
python3 scripts/validate_loop_plan.py /tmp/fx_overcap.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R28 CAP-EXCEEDED]`.

---

## R29 — node.contract missing cost_units

**What's wrong:** a `node.contract` omits `cost_units`, the per-node cost accrual
that feeds the enforced budget.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/node.contract.yaml"))
d.pop("cost_units", None)
yaml.safe_dump(d, open("/tmp/fx_no_cost.yaml","w"), sort_keys=False)
PY
python3 scripts/validate_loop_plan.py --kind node_contract /tmp/fx_no_cost.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R29 MISSING-COST]`.

---

## R30 — bad loop.state

**What's wrong:** `loop.state.yaml` omits a required field (here `active_node`) or
has a malformed `lease_index`.

```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("templates/loop.state.yaml"))
del d["active_node"]
yaml.safe_dump(d, open("/tmp/fx_bad_loop_state.yaml","w"), sort_keys=False)
PY
python3 scripts/validate_loop_plan.py --kind loop_state /tmp/fx_bad_loop_state.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R30 BAD-LOOP-STATE]`.

---

## R31 — bad event_log kind

**What's wrong:** an event_log entry has a `kind` outside
`{pre_effect, post_effect, note, mutation, dissent}`.

```yaml
schema_version: "1.0"
entries:
  - {seq: 0, node_id: n1, ts: "2026-07-02T14:00:00Z", kind: bogus}
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind event_log /tmp/fx_bad_event_kind.yaml
```

**Expected:** exit nonzero; message tags `[R31 BAD-EVENT-KIND]`.

---

## R36 — self-verified risky side-effecting node

**What's wrong:** a `med`/`high`-risk side-effecting node's evidence-ledger entry
has `verifier: agent`. A risky side-effecting node needs an independent verifier
(user/subagent/script), not self-certification.

Ledger (validated against a plan where node `deploy` is `risk: med` with a
non-empty `produces`):

```yaml
schema_version: "1.0"
entries:
  - entry_id: e1
    node_id: deploy
    gate_kind: automated_check
    verdict: pass
    score: null
    artifact_path: a
    rationale: r
    recorded: "2026-07-02"
    verifier: agent
```

**Command:**

```bash
python3 - <<'PY'
import yaml
ledger = {"schema_version":"1.0","entries":[{"entry_id":"e1","node_id":"deploy","gate_kind":"automated_check","verdict":"pass","score":None,"artifact_path":"a","rationale":"r","recorded":"2026-07-02","verifier":"agent"}]}
yaml.safe_dump(ledger, open("/tmp/fx_self_verify.yaml","w"), sort_keys=False)
plan = yaml.safe_load(open("templates/loop.plan.yaml"))
plan["nodes"][0]["risk"] = "med"
plan["nodes"][0]["produces"] = ["prod.url"]
plan["nodes"][0]["id"] = "deploy"
yaml.safe_dump(plan, open("/tmp/fx_self_verify_plan.yaml","w"), sort_keys=False, width=100)
PY
python3 scripts/validate_loop_plan.py --kind evidence_ledger /tmp/fx_self_verify.yaml --plan /tmp/fx_self_verify_plan.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R36 SELF-VERIFY-RISK]`.

---

## R37 — INDEX↔directory drift

**What's wrong:** an `INDEX.yaml` entry names a `path` that does not exist under
the loops root (a loop was moved/archived without updating the index, or vice
versa), or an entry omits the required `current_active_node`.

```yaml
loops:
  - loop_id: L001
    slug: ghost
    path: L001-ghost
    status: running
    title: A loop with no directory
    checkpoint: L001-ghost/checkpoint.yaml
    updated_at: "2026-07-02T14:00:00Z"
    current_active_node: null
```

**Command:**

```bash
mkdir -p /tmp/fx_idx_root
python3 scripts/validate_loop_plan.py --kind loops_index /tmp/fx_index_drift.yaml --root /tmp/fx_idx_root && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R37 INDEX-RECONCILE]` (the `L001-ghost`
directory does not exist under the root).

---

## R38 — lifecycle status used to hide evidence

**What's wrong:** an append-only ledger entry carries a mutable inactive status
instead of recording currentness with a newer explicit lifecycle relation. This
would let a newly appended blind failure declare itself `retired` and leave an
older pass current. Evidence observations stay immutable; relations change the
current view.

```yaml
schema_version: "1.0"
entries:
  - {entry_id: E1, node_id: n1, gate_kind: automated_check, verdict: pass, score: null, artifact_path: a, rationale: old, recorded: "2026-07-02T10:00:00Z", verifier: script, assurance: external, status: active}
  - {entry_id: E2, node_id: n1, gate_kind: llm_judge, verdict: fail, score: null, artifact_path: a2, rationale: counterexample, recorded: "2026-07-02T11:00:00Z", verifier: subagent, assurance: blind, status: retired}
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind evidence_ledger /tmp/fx_evidence_lifecycle.yaml
```

**Expected:** exit nonzero; message tags `[R38 EVIDENCE-LIFECYCLE]`. The control
removes `status: retired` from E2 and appends an explicit newer `supersedes`
relation from E2 to E1; then E2 is the current failure.

---

## R39 — untracked plan mutation

**What's wrong:** an `event_log` entry of `kind: mutation` omits a valid
`mutation_type`. A live plan change must be *typed* with one of the locked
mutation types, never an untracked edit — that is the machine-checkable half.
(Whether the change is *well-reasoned* is a behavioral discipline in
`references/execution_intelligence_policy.md`, not a validator rule — a validator
can only check that a `reason` string is non-empty, which is gameable and would
be programmatizing judgment the runner must actually exercise.)

```yaml
schema_version: "1.0"
entries:
  - {seq: 1, node_id: n1, ts: "2026-07-02T10:00:00Z", kind: mutation}
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind event_log /tmp/fx_untracked_mutation.yaml
```

**Expected:** exit nonzero; message tags `[R39 UNTRACKED-MUTATION]` (missing/invalid `mutation_type`).

---

## R40 — retired node without a tombstone

**What's wrong:** a node is `deprecated`/`cancelled` but carries no `retirement`
object (type + reason). Retired work must be tombstoned, not silently left
dangling, so the retirement is auditable and reconcilable.

```bash
python3 - <<'PY'
import yaml, hashlib, re
_WS=re.compile(r"\s+"); h=lambda t:hashlib.sha256(_WS.sub(" ",str(t)).strip().encode()).hexdigest()
def node(nid, **kw):
    d={"id":nid,"kind":"milestone","title":"T","design_invariant":True,"status":"pending","requires":[],"produces":[],"inputs":[],"preconditions":[],"postconditions":[],"gate":{"kind":"artifact_exists","threshold":None,"rubric":None,"evidence_ref":"e"},"retry_policy":{"max_attempts":1,"backoff_base_seconds":1,"jitter":False},"on_failure":"local_retry","priority":1,"risk":"low","parallelizable":False,"allow_subgraph":False,"subgraph":None,"child_loops":[],"assignee":"agent","notes":""}
    d.update(kw); return d
d={"schema_version":"1.0","plan_id":"p","goal":"g","true_intent":"t","non_goals":[],"success_criteria":[{"id":"s1","statement":"s","measurable":True}],"failure_criteria":["f"],"termination":{"max_iterations":50,"max_wall_clock_hours":None,"max_cost_units":None,"done_when":"d","max_depth":2,"max_child_loops":5},"constraints":[],"nodes":[node("n1",status="deprecated"), node("n2")],"created":"2026-07-02","plan_version":1,"plan_history":[{"plan_version":1,"reason":"init","superseded_at":None,"goal_hash":h("g"),"true_intent_hash":h("t")}]}
yaml.safe_dump(d, open("/tmp/fx_retire_no_tombstone.yaml","w"), sort_keys=False, width=120)
PY
python3 scripts/validate_loop_plan.py /tmp/fx_retire_no_tombstone.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** exit nonzero; message tags `[R40 RETIREMENT]`.

---

## R41 — two authoritative artifact versions at one path

**What's wrong:** an `artifacts/INDEX.yaml` lists two entries at the same `path`
that are both in an active status (`draft`..`published`). Exactly one version may
be authoritative; older ones must be `superseded`.

```yaml
schema_version: "1.0"
artifacts:
  - {artifact_id: A1, path: artifacts/spec.md, status: verified}
  - {artifact_id: A2, path: artifacts/spec.md, status: draft}
```

**Command:**

```bash
python3 scripts/validate_loop_plan.py --kind artifact_index /tmp/fx_artifact_authority.yaml
```

**Expected:** exit nonzero; message tags `[R41 ARTIFACT-AUTHORITY]`.

---

## Fixture-to-rule map

| rule | fixture file |
|------|--------------|
| `R1` cycle | `/tmp/fixture_cycle.yaml` |
| `R2` dangling dependency | `/tmp/fixture_dangling.yaml` |
| `R3` missing evidence gate | `/tmp/fixture_missing_gate.yaml` |
| `R4` bad status enum | `/tmp/fixture_bad_status.yaml` |
| `R5` missing required field | `/tmp/fixture_missing_field.yaml` |
| `R6` plan/checkpoint inconsistency | `/tmp/fixture_ckpt_inconsistent.yaml` (+ `/tmp/fixture_consistency_plan.yaml`) |
| `R7` bad gate kind | `/tmp/fixture_bad_gate_kind.yaml` |
| `R8` bad on_failure enum | `/tmp/fixture_bad_on_failure.yaml` |
| `R9` bad loop_id | `/tmp/fx_bad_loop_id.yaml` |
| `R10` bad slug | `/tmp/fx_bad_slug.yaml` |
| `R11` missing return_contract | `/tmp/fx_missing_return_contract.yaml` |
| `R12` bad loop.meta type | `/tmp/fx_bad_type.yaml` |
| `R13` bad child_loops ref | `/tmp/fx_bad_child_ref.yaml` |
| `R14` bad subgraph status | `/tmp/fx_bad_subgraph_status.yaml` |
| `R15` subgraph status crossover | `/tmp/fx_subgraph_status_crossover.yaml` |
| `R16` bad INDEX shape | `/tmp/fx_bad_index_shape.yaml` |
| `R17` child_loop with no parent | `/tmp/fx_child_no_parent.yaml` |
| `R18` bad human_intervention_policy | `/tmp/fx_bad_hip.yaml` |
| `R19` non-terminal dead-end (deprecated-dependency) | `/tmp/fx_deadend_ckpt.yaml` (+ `/tmp/fx_deadend_plan.yaml`) |
| `R20` escalate used as a status | `/tmp/fx_escalate_status.yaml` |
| `R21` bad claim file | `/tmp/fx_bad_claim.yaml` |
| `R22` unclaimed running node | `/tmp/fx_r22_unclaimed.yaml` (+ empty `/tmp/fx_r22_claims_empty/`) |
| `R23` in-doubt non-idempotent event | `/tmp/fx_indoubt.yaml` |
| `R24` non-monotonic event_log seq | `/tmp/fx_eventlog_seq.yaml` |
| `R25` subgraph fake completion | `/tmp/fx_subgraph_fakecomplete.yaml` |
| `R26` unapproved goal change | `/tmp/fx_silent_goal_change.yaml` |
| `R27` malformed plan_history | `/tmp/fx_bad_plan_history.yaml` |
| `R28` recursion/child-loop cap exceeded | `/tmp/fx_overcap.yaml` |
| `R29` node.contract missing cost_units | `/tmp/fx_no_cost.yaml` |
| `R30` bad loop.state | `/tmp/fx_bad_loop_state.yaml` |
| `R31` bad event_log kind | `/tmp/fx_bad_event_kind.yaml` |
| `R36` self-verified risky node | `/tmp/fx_self_verify.yaml` (+ `/tmp/fx_self_verify_plan.yaml`) |
| `R37` INDEX↔directory drift | `/tmp/fx_index_drift.yaml` (+ empty `/tmp/fx_idx_root/`) |
| `R32` bad checkpoint_seq | `/tmp/fx_bad_checkpoint_seq.yaml` |
| `R33` child-loop checkpoint missing field | `/tmp/fx_child_missing_field.yaml` |
| `R34` approval node without human_approval gate | `/tmp/fx_approval_nogate.yaml` |
| `R35` top-level design_invariant:false | `/tmp/fx_toplevel_invariant_false.yaml` |
| `R42` incomplete loop state | `/tmp/fx_r42_incomplete_state/` |
| `R43` self-attested completion | `/tmp/fx_r43_self_attested_completion/` |
| `R44` missing assurance | `/tmp/fx_r44_missing_assurance/` |
| `R45` unresolved goal citation | `/tmp/fx_r45_goal_citation_unresolved/` |
| `R46` allocated and withdrawn | tombstone only; no fixture |
| `R47` blind context not withheld | `/tmp/fx_r47_blind_context/` |
| `R48` missing dissent | `/tmp/fx_r48_missing_dissent/` |
| `R49` checkpoint projection mismatch | `/tmp/fx_r49_projection_mismatch/` (+ control `/tmp/fx_r49_projection_control/`) |

**Fixture readiness:** `R42` is **RED now**; `R43`/`R44`/`R45`/`R47` are
**GREEN**; `R48` remains **PRE-VOCABULARY (blocked on later schema work)**.

---

## R42 — incomplete state

**What's wrong:** the directory contains a valid `loop.plan.yaml`, but has no
checkpoint, evidence ledger, or event log. Those missing state artifacts make
the loop unresumable. The current integrity gate incorrectly treats all three
as optional and certifies this incomplete directory as healthy.

**Materialize and run:**

```bash
rm -rf /tmp/fx_r42_incomplete_state
mkdir -p /tmp/fx_r42_incomplete_state
python3 - <<'PY'
from pathlib import Path

source = Path("templates/loop.plan.yaml")
target = Path("/tmp/fx_r42_incomplete_state/loop.plan.yaml")
target.write_bytes(source.read_bytes())
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r42_incomplete_state
```

**Observed RED (current validator; exit `0`):**

```text
INTEGRITY OK: /tmp/fx_r42_incomplete_state
```

This is the correct RED because the valid plan reaches the missing rule: no
unrelated parse, schema, or reconciliation error masks acceptance of the
unresumable directory.

**Expected after repair:** exit nonzero; message tags
`[R42 INCOMPLETE-STATE]` and names the missing low-level state artifacts.

---

## R43 — self-attested completion

**What's wrong:** node `goal_clarification` is `completed`, and its active
passing `llm_judge` evidence declares `assurance: self_attested`. The evidence
entry is structurally present and resolves to the node, but self-graded opinion
may not authorize completion. This check concerns the declared assurance class;
it does not infer whether the evidence content is adequate.

**Materialize and run:**

```bash
if [ -e /tmp/fx_r43_self_attested_completion ]; then
  mv /tmp/fx_r43_self_attested_completion "/tmp/fx_r43_self_attested_completion.previous.$$"
fi
mkdir -p /tmp/fx_r43_self_attested_completion/evidence
python3 - <<'PY'
from pathlib import Path
import json
import yaml

root = Path("/tmp/fx_r43_self_attested_completion")
plan = yaml.safe_load(Path("templates/loop.plan.yaml").read_text())
checkpoint = yaml.safe_load(Path("templates/checkpoint.yaml").read_text())
node_id = plan["nodes"][0]["id"]
checkpoint["plan_id"] = plan["plan_id"]
checkpoint["plan_version"] = plan["plan_version"]
checkpoint["node_states"] = {node["id"]: "pending" for node in plan["nodes"]}
checkpoint["node_states"][node_id] = "completed"
checkpoint["ready_set"] = []
checkpoint["last_completed"] = [node_id]
checkpoint["event_log_ref"] = "event_log.jsonl"
checkpoint["evidence_ledger_ref"] = "evidence.ledger.yaml"
ledger = {
    "schema_version": "1.0.0",
    "entries": [{
        "entry_id": "ev-r43", "node_id": node_id, "gate_kind": "llm_judge",
        "verdict": "pass", "score": 0.9,
        "artifact_path": "evidence/r43-review.txt",
        "rationale": "producer's own judgment", "recorded": "2026-07-30T10:00:00Z",
        "verifier": "agent", "status": "active", "assurance": "self_attested",
    }],
}
(root / "loop.plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
(root / "checkpoint.yaml").write_text(yaml.safe_dump(checkpoint, sort_keys=False))
(root / "evidence.ledger.yaml").write_text(yaml.safe_dump(ledger, sort_keys=False))
(root / "event_log.jsonl").write_text(json.dumps({
    "seq": 0, "node_id": node_id, "ts": "2026-07-30T09:59:00Z",
    "kind": "note", "outcome": "fixture state prepared",
}) + "\n")
(root / "evidence/r43-review.txt").write_text("self-attested verdict\n")
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r43_self_attested_completion
```

**Observed GREEN (exit `1`):**

```text
[R43 SELF-ATTESTED-COMPLETION] node 'goal_clarification' is 'completed' but has no active passing entry whose declared assurance is 'external' or whose declared gate_kind is 'human_approval'; this checks only those literal ledger fields and does not license any conclusion about evidence adequacy, correctness, or whether the node is genuinely done

INTEGRITY GATE FAILED (1 violation(s)) for /tmp/fx_r43_self_attested_completion.
Do NOT advance normal work — enter a recovery subgraph (references/recovery_protocol.md).
```

**Exact command:** `python3 scripts/check_loop_integrity.py
/tmp/fx_r43_self_attested_completion`. Expected tag:
`[R43 SELF-ATTESTED-COMPLETION]`.

---

## R44 — missing assurance

**What's wrong:** the active evidence entry omits `assurance`, so its provenance
class is not recorded. The other required evidence fields are present and its
artifact path exists. Rejection establishes field presence only; it does not
claim that any evidence content is adequate.

**Materialize and run:**

```bash
if [ -e /tmp/fx_r44_missing_assurance ]; then
  mv /tmp/fx_r44_missing_assurance "/tmp/fx_r44_missing_assurance.previous.$$"
fi
mkdir -p /tmp/fx_r44_missing_assurance/evidence
python3 - <<'PY'
from pathlib import Path
import json
import yaml

root = Path("/tmp/fx_r44_missing_assurance")
plan = yaml.safe_load(Path("templates/loop.plan.yaml").read_text())
checkpoint = yaml.safe_load(Path("templates/checkpoint.yaml").read_text())
node_id = plan["nodes"][0]["id"]
checkpoint["plan_id"] = plan["plan_id"]
checkpoint["plan_version"] = plan["plan_version"]
checkpoint["node_states"] = {node["id"]: "pending" for node in plan["nodes"]}
checkpoint["ready_set"] = []
checkpoint["last_completed"] = []
checkpoint["event_log_ref"] = "event_log.jsonl"
checkpoint["evidence_ledger_ref"] = "evidence.ledger.yaml"
ledger = {
    "schema_version": "1.0.0",
    "entries": [{
        "entry_id": "ev-r44", "node_id": node_id, "gate_kind": "test",
        "verdict": "pass", "score": None,
        "artifact_path": "evidence/r44-test.txt",
        "rationale": "record with no assurance field", "recorded": "2026-07-30T10:00:00Z",
        "verifier": "script", "status": "active",
    }],
}
(root / "loop.plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
(root / "checkpoint.yaml").write_text(yaml.safe_dump(checkpoint, sort_keys=False))
(root / "evidence.ledger.yaml").write_text(yaml.safe_dump(ledger, sort_keys=False))
(root / "event_log.jsonl").write_text(json.dumps({
    "seq": 0, "node_id": node_id, "ts": "2026-07-30T09:59:00Z",
    "kind": "note", "outcome": "fixture state prepared",
}) + "\n")
(root / "evidence/r44-test.txt").write_text("test output\n")
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r44_missing_assurance
```

**Observed GREEN (exit `1`):**

```text
[INTEGRITY:evidence] ledger invalid:
[R44 MISSING-ASSURANCE] ledger entry[0]: declared assurance field is absent; this establishes field absence only and does not license any conclusion about evidence adequacy or correctness
[jsonschema] entries/0: 'assurance' is a required property
error: /tmp/fx_r44_missing_assurance/evidence.ledger.yaml is invalid (2 problem(s))

INTEGRITY GATE FAILED (1 violation(s)) for /tmp/fx_r44_missing_assurance.
Do NOT advance normal work — enter a recovery subgraph (references/recovery_protocol.md).
```

**Exact command:** `python3 scripts/check_loop_integrity.py
/tmp/fx_r44_missing_assurance`. Expected tag: `[R44 MISSING-ASSURANCE]`.

---

## R45 — goal citation unresolved

**What's wrong:** evidence entry `ev-r45` cites `success_criteria` id
`sc-does-not-exist`, but the plan defines no criterion with that id. This is
strictly a reference-validity check: resolution proves only that an id exists,
never that the criterion is satisfied or that the evidence content is adequate.

**Materialize and run:**

```bash
if [ -e /tmp/fx_r45_goal_citation_unresolved ]; then
  mv /tmp/fx_r45_goal_citation_unresolved "/tmp/fx_r45_goal_citation_unresolved.previous.$$"
fi
mkdir -p /tmp/fx_r45_goal_citation_unresolved/evidence
python3 - <<'PY'
from pathlib import Path
import json
import yaml

root = Path("/tmp/fx_r45_goal_citation_unresolved")
plan = yaml.safe_load(Path("templates/loop.plan.yaml").read_text())
checkpoint = yaml.safe_load(Path("templates/checkpoint.yaml").read_text())
node_id = plan["nodes"][0]["id"]
checkpoint["plan_id"] = plan["plan_id"]
checkpoint["plan_version"] = plan["plan_version"]
checkpoint["node_states"] = {node["id"]: "pending" for node in plan["nodes"]}
checkpoint["ready_set"] = []
checkpoint["last_completed"] = []
checkpoint["event_log_ref"] = "event_log.jsonl"
checkpoint["evidence_ledger_ref"] = "evidence.ledger.yaml"
ledger = {
    "schema_version": "1.0.0",
    "entries": [{
        "entry_id": "ev-r45", "node_id": node_id, "gate_kind": "test",
        "verdict": "pass", "score": None,
        "artifact_path": "evidence/r45-test.txt",
        "rationale": "citation-resolution fixture", "recorded": "2026-07-30T10:00:00Z",
        "verifier": "script", "status": "active", "assurance": "external",
        "success_criteria_id": "sc-does-not-exist",
    }],
}
(root / "loop.plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
(root / "checkpoint.yaml").write_text(yaml.safe_dump(checkpoint, sort_keys=False))
(root / "evidence.ledger.yaml").write_text(yaml.safe_dump(ledger, sort_keys=False))
(root / "event_log.jsonl").write_text(json.dumps({
    "seq": 0, "node_id": node_id, "ts": "2026-07-30T09:59:00Z",
    "kind": "note", "outcome": "fixture state prepared",
}) + "\n")
(root / "evidence/r45-test.txt").write_text("test output\n")
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r45_goal_citation_unresolved
```

**Observed GREEN (exit `1`):**

```text
[INTEGRITY:evidence] ledger invalid:
[R45 GOAL-CITATION-UNRESOLVED] ledger entry[0] success_criteria_id 'sc-does-not-exist': cited criterion id does not exist in loop.plan.success_criteria[].id; this checks exact-id reference validity only and does not license any conclusion that a criterion is satisfied, met, or demonstrated
error: /tmp/fx_r45_goal_citation_unresolved/evidence.ledger.yaml is invalid (1 problem(s))

INTEGRITY GATE FAILED (1 violation(s)) for /tmp/fx_r45_goal_citation_unresolved.
Do NOT advance normal work — enter a recovery subgraph (references/recovery_protocol.md).
```

**Required GREEN:** exit nonzero, the failure message contains
`[R45 GOAL-CITATION-UNRESOLVED]`, and it says `cited criterion id does not
exist`. It must make no claim about criterion satisfaction.

---

## R46 — allocated and withdrawn (tombstone; no fixture)

`R46` was allocated and withdrawn before implementation. It would have enforced
`score >= threshold` on judged gates. That design was cancelled because a score
on a judged gate is an LLM's opinion; comparing that opinion with a threshold
would give a fabricated number deterministic authority over node completion.
The absence of this threshold check is correct, not a validator gap. `R46` must
never be reused for another rule because R-numbers are pinned by fixture IDs
throughout this document.

---

## R47 — blind assurance without withheld producer claim

**What's wrong:** evidence declares `assurance: blind`, but its explicit review
manifest says the producer claim was `available` (or `unknown`). Only
`producer_claim_access: withheld` establishes the deterministic isolation fact;
role labels and filesystem mtimes do not prove blindness.

**Materialize and run:**

```bash
if [ -e /tmp/fx_r47_blind_context ]; then
  mv /tmp/fx_r47_blind_context "/tmp/fx_r47_blind_context.previous.$$"
fi
mkdir -p /tmp/fx_r47_blind_context/evidence
python3 - <<'PY'
from pathlib import Path
import json
import yaml

root = Path("/tmp/fx_r47_blind_context")
plan = yaml.safe_load(Path("templates/loop.plan.yaml").read_text())
checkpoint = yaml.safe_load(Path("templates/checkpoint.yaml").read_text())
node_id = plan["nodes"][0]["id"]
checkpoint["plan_id"] = plan["plan_id"]
checkpoint["plan_version"] = plan["plan_version"]
checkpoint["node_states"] = {node["id"]: "pending" for node in plan["nodes"]}
checkpoint["ready_set"] = []
checkpoint["last_completed"] = []
checkpoint["event_log_ref"] = "event_log.jsonl"
checkpoint["evidence_ledger_ref"] = "evidence.ledger.yaml"
verdict = root / "evidence/reviewer-verdict.txt"
ledger = {
    "schema_version": "1.0.0",
    "entries": [{
        "entry_id": "ev-r47", "node_id": node_id, "gate_kind": "llm_judge",
        "verdict": "pass", "score": 0.9,
        "artifact_path": str(verdict),
        "review_context": {
            "review_id": "review-r47",
            "delivered_context_sha256": "a" * 64,
            "producer_claim_access": "available",
        },
        "rationale": "blind-context fixture", "recorded": "2026-07-30T10:01:00Z",
        "verifier": "subagent", "status": "active", "assurance": "blind",
    }],
}
(root / "loop.plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
(root / "checkpoint.yaml").write_text(yaml.safe_dump(checkpoint, sort_keys=False))
(root / "evidence.ledger.yaml").write_text(yaml.safe_dump(ledger, sort_keys=False))
(root / "event_log.jsonl").write_text(json.dumps({
    "seq": 0, "node_id": node_id, "ts": "2026-07-30T09:59:00Z",
    "kind": "note", "outcome": "fixture state prepared",
}) + "\n")
verdict.write_text("reviewer verdict\n")
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r47_blind_context
```

**Observed GREEN (exit `1`):**

```text
[INTEGRITY:evidence] ledger invalid:
[R47 BLIND-CONTEXT-MISSING] ledger entry[0] for node 'goal_clarification': assurance 'blind' requires explicit review_context {review_id, delivered_context_sha256, producer_claim_access: withheld}; available/unknown access, role labels, and filesystem mtimes are not proof of blindness
error: /tmp/fx_r47_blind_context/evidence.ledger.yaml is invalid (1 problem(s))

INTEGRITY GATE FAILED (1 violation(s)) for /tmp/fx_r47_blind_context.
Do NOT advance normal work — enter a recovery subgraph (references/recovery_protocol.md).
```

**Required GREEN:** exit nonzero, the failure message contains
`[R47 BLIND-CONTEXT-MISSING]`, and it reports that `available`/`unknown` cannot
support `assurance: blind`. The control changes the access value to `withheld`
and passes this invariant.

---

## R48 — missing dissent

**What's wrong:** blind review entry `ev-r48-negative` records a negative
verdict, the checkpoint records the reviewed node as `completed`, and the event
log contains no `dissent` event corresponding to that review. The fixture checks
for the explicit override record only. It does not infer whether either verdict
or the completed design is correct.

**Materialize and run:**

```bash
rm -rf /tmp/fx_r48_missing_dissent
mkdir -p /tmp/fx_r48_missing_dissent/evidence
python3 - <<'PY'
from pathlib import Path
import json
import yaml

root = Path("/tmp/fx_r48_missing_dissent")
plan = yaml.safe_load(Path("templates/loop.plan.yaml").read_text())
checkpoint = yaml.safe_load(Path("templates/checkpoint.yaml").read_text())
node_id = plan["nodes"][0]["id"]
checkpoint["plan_id"] = plan["plan_id"]
checkpoint["plan_version"] = plan["plan_version"]
checkpoint["node_states"] = {node["id"]: "pending" for node in plan["nodes"]}
checkpoint["node_states"][node_id] = "completed"
checkpoint["ready_set"] = []
checkpoint["last_completed"] = [node_id]
checkpoint["event_log_ref"] = "./event_log.jsonl"
checkpoint["evidence_ledger_ref"] = "evidence.ledger.yaml"
ledger = {
    "schema_version": "1.0.0",
    "entries": [
        {
            "entry_id": "ev-r48-negative", "node_id": node_id,
            "gate_kind": "llm_judge", "verdict": "fail", "score": 0.2,
            "artifact_path": "evidence/r48-negative.txt",
            "rationale": "blind negative verdict", "recorded": "2026-07-30T10:00:00Z",
            "verifier": "subagent", "status": "active", "assurance": "blind",
        },
        {
            "entry_id": "ev-r48-override", "node_id": node_id,
            "gate_kind": "human_approval", "verdict": "pass", "score": None,
            "artifact_path": "evidence/r48-override.txt",
            "rationale": "parent proceeded", "recorded": "2026-07-30T10:05:00Z",
            "verifier": "user", "status": "active", "assurance": "external",
            "overrides_entry_id": "ev-r48-negative",
        },
    ],
}
event = {
    "seq": 0, "node_id": node_id, "ts": "2026-07-30T10:05:00Z",
    "kind": "note", "outcome": "proceeded without a dissent event",
}
(root / "loop.plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
(root / "checkpoint.yaml").write_text(yaml.safe_dump(checkpoint, sort_keys=False))
(root / "evidence.ledger.yaml").write_text(yaml.safe_dump(ledger, sort_keys=False))
(root / "event_log.jsonl").write_text(json.dumps(event) + "\n")
(root / "evidence/r48-negative.txt").write_text("negative verdict\n")
(root / "evidence/r48-override.txt").write_text("override verdict\n")
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r48_missing_dissent
```

**Observed GREEN (exit `1`):**

```text
[R48 MISSING-DISSENT] ledger entry[0] 'ev-r48-negative' for completed node 'goal_clarification' is an active blind failure, but the event log has no dissent event for that node; this checks record absence only and does not license any conclusion that the override was wrong or unjustified, or that either verdict or the completed design is correct

INTEGRITY GATE FAILED (1 violation(s)) for /tmp/fx_r48_missing_dissent.
Do NOT advance normal work — enter a recovery subgraph (references/recovery_protocol.md).
```

**Required GREEN:** exit nonzero, the failure message contains
`[R48 MISSING-DISSENT]`, and it identifies the negative review entry lacking a
corresponding `dissent` event.

---

## R49 — checkpoint projection mismatch

**What's wrong:** the event log projects node `goal_clarification` to `running`,
while the checkpoint records it as `completed`. The ledger contains valid active
external passing evidence, but the canonical projection applies a ledger verdict
only to a node left at `verifying`, so it does not alter the replayed `running`
status. This fixture establishes a snapshot/projection disagreement only; it does
not establish that the loop is broken, work is incomplete, evidence is
inadequate, or the node is or is not done.

**Materialize and run (mismatch plus passing control):**

```bash
rm -rf /tmp/fx_r49_projection_mismatch /tmp/fx_r49_projection_control
mkdir -p /tmp/fx_r49_projection_mismatch/evidence /tmp/fx_r49_projection_control/evidence
python3 - <<'PY'
from pathlib import Path
import json
import yaml

roots = (
    (Path("/tmp/fx_r49_projection_mismatch"), "completed"),
    (Path("/tmp/fx_r49_projection_control"), "running"),
)
for root, recorded_status in roots:
    plan = yaml.safe_load(Path("templates/loop.plan.yaml").read_text())
    checkpoint = yaml.safe_load(Path("templates/checkpoint.yaml").read_text())
    node_id = plan["nodes"][0]["id"]
    for node in plan["nodes"]:
        node["status"] = "pending"
    checkpoint["plan_id"] = plan["plan_id"]
    checkpoint["plan_version"] = plan["plan_version"]
    checkpoint["node_states"] = {node["id"]: node["status"] for node in plan["nodes"]}
    checkpoint["node_states"][node_id] = recorded_status
    checkpoint["ready_set"] = []
    checkpoint["last_completed"] = [node_id] if recorded_status == "completed" else []
    checkpoint["event_log_ref"] = "event_log.jsonl"
    checkpoint["evidence_ledger_ref"] = "evidence.ledger.yaml"
    ledger = {
        "schema_version": "1.0.0",
        "entries": [{
            "entry_id": "ev-r49", "node_id": node_id, "gate_kind": "test",
            "verdict": "pass", "score": None,
            "artifact_path": "evidence/r49-test.txt",
            "rationale": "projection fixture", "recorded": "2026-07-30T10:00:00Z",
            "verifier": "script", "status": "active", "assurance": "external",
        }],
    }
    event = {
        "seq": 0, "node_id": node_id, "ts": "2026-07-30T09:59:00Z",
        "kind": "post_effect", "from_status": "pending", "to_status": "running",
        "outcome": "ok",
    }
    (root / "loop.plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
    (root / "checkpoint.yaml").write_text(yaml.safe_dump(checkpoint, sort_keys=False))
    (root / "evidence.ledger.yaml").write_text(yaml.safe_dump(ledger, sort_keys=False))
    (root / "event_log.jsonl").write_text(json.dumps(event) + "\n")
    (root / "evidence/r49-test.txt").write_text("test output\n")
PY
python3 scripts/check_loop_integrity.py /tmp/fx_r49_projection_mismatch
python3 scripts/check_loop_integrity.py /tmp/fx_r49_projection_control
```

**Observed RED before R49 (mismatch exits `0`):**

```text
CROSS-FILE REFERENCES OK: /tmp/fx_r49_projection_mismatch
```

**Observed GREEN after R49 (mismatch exits `1`):**

```text
[R49 CHECKPOINT-PROJECTION-MISMATCH] node 'goal_clarification': projected status 'running' disagrees with checkpoint.node_states recorded status 'completed'; this establishes a replayed-projection/recorded-snapshot consistency disagreement only and does not license any conclusion that the loop is broken, work is incomplete, evidence is inadequate, or the node is or is not done

INTEGRITY GATE FAILED (1 violation(s)) for /tmp/fx_r49_projection_mismatch.
Do NOT advance normal work — enter a recovery subgraph (references/recovery_protocol.md).
```

**Observed passing CONTROL after R49 (exit `0`):**

```text
CROSS-FILE REFERENCES OK: /tmp/fx_r49_projection_control
Checks run:
- canonical checkpoint node_states projection consistency (R49)
```

**Required GREEN:** the mismatch exits nonzero with
`[R49 CHECKPOINT-PROJECTION-MISMATCH]` and names both exact statuses; the control
exits zero and lists the R49 check. Neither result licenses a semantic conclusion
about completion, adequacy, correctness, or the next action.
