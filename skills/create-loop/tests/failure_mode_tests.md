# Failure-Mode Tests — one bad-input fixture per rejection rule

*Diataxis type: **reference test doc**. This document is the authoritative
rejection contract for the `create-loop` validators. It is written
**test-first**: `scripts/validate_loop_plan.py` and
`scripts/validate_checkpoint.py` are authored afterwards to reject exactly the
inputs below. Each rule `R1`–`R8` has **one** minimal fixture that is complete,
well-formed YAML and valid in every respect **except the single defect** that
rule targets. A correct validator exits **nonzero** on each fixture and prints a
message naming the violated rule.*

All field names and enum values are copied verbatim from
[`references/loop_plan_spec.md`](../references/loop_plan_spec.md) and
[`references/state_model.md`](../references/state_model.md). All paths are
relative to `/root/create-loop/create-loop/`.

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

Canonical enums exercised (verbatim):

- **Node statuses (15):** `undiscovered`, `discovered`, `needs_clarification`,
  `pending`, `ready`, `running`, `waiting_external`, `waiting_user`, `blocked`,
  `verifying`, `verification_failed`, `retry_pending`, `completed`, `cancelled`,
  `deprecated`. (`R4` uses `done`, which is **not** in this set.)
- **Gate kinds (8):** `automated_check`, `test`, `llm_judge`,
  `self_consistency`, `evaluator_optimizer`, `step_verifier`, `human_approval`,
  `artifact_exists`. (`R7` uses `vibes_check`, not in this set.)
- **`on_failure` ladder (4):** `local_retry`, `local_patch`, `replan`,
  `escalate`. (`R8` uses `give_up`, not in this set.)

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
    assignee: agent
    notes: ""
created: "2026-07-01"
plan_version: 1
YAML
echo -n "R8 bad_on_failure: "
python3 scripts/validate_loop_plan.py /tmp/fixture_bad_on_failure.yaml && echo FAIL || echo PASS-rejected
```

**Expected:** eight lines, each ending `PASS-rejected` — one per rule `R1`–`R8`.
No `FAIL` may appear.

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
