# Exception Handling — Taxonomy, Ladder & Recovery Mechanics

*Diataxis type: **reference**. This document catalogues how a `loop.plan`
recognises, classifies, and recovers from things going wrong at run time. It
defines the exception taxonomy, the bounded escalation ladder, the
`retry_policy` math, the saga-compensation and idempotency machinery, and the
per-exception response table. It does not redefine fields — see
[`loop_plan_spec.md`](./loop_plan_spec.md) for every field's type and the
canonical Glossary, and [`state_model.md`](./state_model.md) for the status
enum and transition table.*

*For the operational *protocol* (when to look at what, in what order), see the
companion [`recovery_protocol.md`](./recovery_protocol.md). For the gate-side
counterpart, see [`evidence_gates.md`](./evidence_gates.md).*

Conventions follow the foundation docs: all tokens are **lowercase
snake_case**; all 15 node statuses are spelled exactly as in
[`state_model.md` §node status enum](./state_model.md#node-status-enum); the
four ladder steps are spelled exactly as in
[`loop_plan_spec.md` §6.2](./loop_plan_spec.md#62-on_failure--the-escalation-ladder).

---

## 1. Why exception handling is a planning concern, not an ad-hoc one

Every failure a node can encounter is, in principle, predictable — and
therefore **planned**. `create-loop` treats recovery as a first-class layer of
the control plane, on par with planning and execution. This is the Structured
Graph Harness commitment from arXiv 2604.11378: an execution plan is
**immutable per `plan_version`**, and **planning**, **execution**, and
**recovery** are three independent layers with well-defined interfaces
([`./research_dags_multiagent.md` §0.1](./research_dags_multiagent.md)).
The recovery layer's invariants are: a **bounded** escalation protocol
(`local_retry` → `local_patch` → `replan` → `escalate`) and **strict order**
(no skipping backward), which is why the ladder lives in the contract and not
in the agent's head ([`concepts.md` §6](./concepts.md#6-why-a-bounded-escalation-ladder)).

Three consequences fall out:

1. Every node declares `on_failure` (the rung the ladder starts on for that node)
   and `retry_policy` (the local budget under `local_retry`).
2. The state transitions the recovery layer drives are recorded in the
   authoritative table in
   [`state_model.md` §state transition table](./state_model.md#state-transition-table).
3. The retry guard reads **persistent** state — `node.contract.attempt` on
   disk — never an in-memory counter, so the budget survives crashes and is
   visible to a fresh session ([`state_model.md` §state transition table](./state_model.md#state-transition-table),
   [`concepts.md` §6](./concepts.md#6-why-a-bounded-escalation-ladder)).

---

## 2. The exception taxonomy

A `loop.plan` recognises twelve exception *kinds*. Each is a **categorisation
of a failure signal**, not a free-form description — recovery decisions are
made on the kind, not on the prose. The kinds below exhaust the categories the
recovery layer handles; anything that does not fit is treated as
`inconsistent_result` and routed through `blocked` pending human triage.

For each kind: a one-line **definition**, the **detection signal** the runner
emits when it observes one, and the **response** the recovery layer takes
(retry, patch, replan, escalate, or roll back).

### 2.1 `transient_error`

- **Definition.** A self-resolving external condition (network blip, rate
  limit, temporary unavailability of a downstream API). The work itself is
  correct; the environment wasn't.
- **Detection signal.** The runner catches a known transient exception class
  (HTTP 5xx with `Retry-After`, `429`, socket reset, timeout) and tags it
  `transient_error` in the `event_log`.
- **Response.** Stay on the `local_retry` rung. Honour `retry_policy.backoff_base_seconds`
  with exponential backoff and jitter (see §5). Do **not** patch or replan.

### 2.2 `permanent_error`

- **Definition.** The action is structurally invalid (HTTP 4xx other than
  429/408, schema validation failure against the tool's contract, malformed
  input). The work itself is wrong; retrying unchanged will fail the same way.
- **Detection signal.** The runner emits a permanent-failure tag and the
  `event_log` entry records the tool's diagnostic.
- **Response.** Exhaust the `retry_policy` budget quickly (a single
  `local_retry` is enough to confirm it is permanent), then advance the
  ladder: `local_patch` if a small correction is obvious; otherwise `replan`.

### 2.3 `tool_unavailable`

- **Definition.** The required tool or capability is not available on this
  host (no shell, no browser, no `O_CREAT|O_EXCL` semantics, no Python, etc.).
- **Detection signal.** Capability probe at startup fails; the `event_log`
  records the missing primitive against the affected node.
- **Response.** `replan` — the node's approach has to change because the
  environment lacks the tool the approach assumed. Compensations of any
  already-completed `activity` run.

### 2.4 `insufficient_permission`

- **Definition.** The agent lacks a permission, role, scope, or credential
  required for the action (file outside the project tree, write scope missing,
  API key absent, OAuth scope denied).
- **Detection signal.** The tool call returns a permission-denied class.
- **Response.** `escalate` — the user must grant the permission, approve a
  scope change, or supply the credential. The `approval` node materialises a
  `pending_approvals` entry; downstream nodes move to `blocked`.

### 2.5 `missing_data`

- **Definition.** A required input artifact, schema, environment variable, or
  earlier-produced record is absent from the persistent state.
- **Detection signal.** A `produces/requires` edge resolves to nothing, or the
  referenced `evidence_ref` is unfindable, or a precondition references a
  missing key.
- **Response.** `local_patch` if the artifact can be regenerated by the
  upstream node's idempotent `cache_key` (replay it); otherwise the upstream
  node moves to `discovered` / `pending` and the recovery layer returns to
  recompute readiness. If the upstream node is itself terminal
  (`completed`/`cancelled`/`deprecated`), the missing data is structural —
  `replan` is required.

### 2.6 `inconsistent_result`

- **Definition.** The work *did* complete, but the result is inconsistent
  with the node's `postconditions`, the gate's rubric, or the surrounding
  invariants (the LLM returned prose that doesn't parse; a test passed on the
  wrong fixture; a schema check accepted a payload that contradicts another
  accepted payload).
- **Detection signal.** The `gate` returns `verdict: fail` or `verdict: inconclusive`
  (see [`state_model.md` §evidence-ledger](./state_model.md#evidenceledger)),
  or a postcondition check throws.
- **Response.** The `verifying → verification_failed` transition fires;
  the ladder runs from `on_failure`. `inconclusive` verdicts are treated
  like `fail` for the purposes of the ladder (a non-`pass` verdict is a
  verdict that didn't pass).

### 2.7 `corrupt_state_file`

- **Definition.** A durable state artifact — the checkpoint, a
  `node.contract`, the `evidence.ledger`, or the `event_log` — fails
  integrity validation (truncated JSON, schema mismatch, checksum / signature
  mismatch, deserialisation error).
- **Detection signal.** The loader refuses the file; the
  `resume-from-blank-session` algorithm surfaces the offending path.
- **Response.** Quarantine the bad file (do not delete; move it aside for
  forensics), restore from the last well-formed checkpoint / ledger snapshot,
  and `replan` — the last `plan_version` is consistent, but the run is now a
  resume. **Never** silently overwrite a corrupt state file from in-memory.

### 2.8 `concurrency_conflict`

- **Definition.** Two nodes target the same artifact, identity, or external
  resource and the order of completion would violate a `postcondition` of
  one of them (lost update, write-write race on a unique key, re-entrant
  call, idempotency-key collision).
- **Detection signal.** The runner observes an idempotency-key collision
  (single-flight `run_id_directory` creation fails with `EEXIST`), a unique
  constraint violation, or a tool-reported concurrent-modification error.
- **Response.** The conflicting node moves to `blocked`. The single-flight
  semantics of the `run_id_directory` mean the *earlier* attempt owns the
  resource; the later attempt waits (`waiting_external`) or, if the earlier
  attempt has crashed, resumes by reconciling via the `event_log`. If the
  conflict cannot be ordered, `escalate`.

### 2.9 `no_progress` (stall)

- **Definition.** The node's `iteration` counter (or output similarity,
  receipt of new evidence, new tool calls) has not advanced for a defined
  stall window — the loop is stuck, not failing.
- **Detection signal.** No new entry in the `evidence.ledger`, no new
  `event_log` line, and `node.contract.started` is older than the stall
  window for an active `running` node.
- **Response.** Treat as `local_patch`-eligible: cancel the
  `running`/`verifying` attempt (move to `cancelled`) and restart the node
  under `retry_policy`. Repeated stalls from the same node advance the
  ladder to `replan`.

### 2.10 `budget_exceeded`

- **Definition.** A `termination` bound is reached — `iteration >=
  termination.max_iterations`, or `cost_units_spent >=
  termination.max_cost_units`, or wall-clock elapsed >= `termination.max_wall_clock_hours`.
- **Detection signal.** Checked at the top of every dispatch (see
  [`state_model.md` §resume step 5](./state_model.md#resume-from-a-blank-session));
  the runner increments `iteration` and `cost_units_spent` at each attempt
  boundary; a `failure_criteria` becomes true.
- **Response.** **Stop dispatch.** Mark the offending node `blocked`, run
  compensations for any completed `activity`s of any node, and `escalate` the
  whole loop to the user — there is no `local_retry` that fixes a budget
  cap. See §9 for the table mapping.

### 2.11 `insufficient_context`

- **Definition.** The agent does not have enough information to proceed —
  the user goal is ambiguous, the upstream artifact contradicts an
  `open_assumption`, the schema is undefined, or the `preconditions` cannot
  all be evaluated.
- **Detection signal.** A `preconditions` check returns `unknown`; a
  `needs_clarification` status is the natural carrier (see
  [`state_model.md` §state transition table](./state_model.md#state-transition-table)).
  The runner does **not** immediately surface an open question; that is
  the last rung, not the first (see Response).
- **Response.** **Autonomous recovery first.** The reflex is NOT to set
  `waiting_user`. Spawn a diagnostic `subgraph` that forms an assumption,
  gathers evidence (read upstream artifacts, probe the environment,
  compare analogous cases in the `event_log` / `evidence.ledger`), and
  updates confidence. If the diagnostic resolves the gap, the loop
  continues. If it persists after autonomous recovery is exhausted AND
  the remaining gap is irreducible or crosses a user-boundary, the
  affected node moves to `waiting_user` (or `blocked`); surface the
  question via the `approval` mechanism in
  [`human_approval.md` §1](./human_approval.md#1-autonomy-first-approval-is-a-bounded-exception)
  and `SKILL.md` §3. `waiting_user` is the **last rung**, not the first.
  The diagnostic `subgraph` may itself produce findings that warrant a
  `replan` (new `plan_version`); in that case the structural-change path
  wins over the user-question path.

### 2.12 `goal_changed`

- **Definition.** The user, or a higher-priority signal, changed the top-level
  `goal` / `true_intent` mid-run.
- **Detection signal.** A `decision.log` entry from a tier-3 or higher
  authority (see [`human_approval.md`](./human_approval.md#2-decision-authority-tiers))
  updates `goal` or `true_intent`, **or** a fresh agent observes that the
  running plan no longer advances any `success_criteria`.
- **Response.** The **user** must confirm the change — this is the one
  exception that **must not** be silently accepted by the agent. On
  confirmation, `replan` with a new `plan_version`; the previous plan's
  nodes are marked `deprecated`. Until confirmation, the running loop
  remains on its old `goal` and the change is held as an open
  `open_assumption`.

> **Note on the taxonomy boundary.** These twelve kinds are exhaustive for the
> recovery layer. A failure that does not match one of them is logged with a
> free-form `inconsistent_result` tag and routed to `blocked` so a human
> classifies it before it is acted on. The taxonomy **does not** add new
> statuses, new ladder rungs, or new node kinds; everything below maps onto
> the 15 statuses, the 4 ladder steps, and the 8 node kinds already locked
> in [`state_model.md`](./state_model.md) and
> [`loop_plan_spec.md`](./loop_plan_spec.md).

---

## 3. The bounded escalation ladder

The escalation ladder is a **single, bounded, ordered** sequence of four
rungs. It is identical to the one defined in
[`loop_plan_spec.md` §6.2](./loop_plan_spec.md#62-on-failure--the-escalation-ladder)
and to the rule recorded in [`concepts.md` §6](./concepts.md#6-why-a-bounded-escalation-ladder):

```
local_retry  ->  local_patch  ->  replan  ->  escalate
```

> **Autonomy-first framing.** The first three rungs are **autonomous
> rungs**: `local_retry`, `local_patch`, and `replan`. The loop exercises
> them without consulting the user. The `escalate` rung is the **last**
> rung, reached only after autonomous recovery is exhausted OR the
> failure's resolution would cross a user-boundary (see
> [`human_approval.md` §1](./human_approval.md#1-autonomy-first-approval-is-a-bounded-exception)
> and [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)).
> Escalation is *exhausted-autonomous-recovery*, not a first reflex.

| rung | meaning | when to advance | advance-triggering evidence |
|------|---------|-----------------|-----------------------------|
| `local_retry` | re-run the same node under its `retry_policy`. | `attempt` reaches `max_attempts`, or the failure class is excluded from retry by §2 (see the per-exception table). | `node.contract.attempt == max_attempts`; evidence-ledger entry with `verdict: fail` or `verdict: inconclusive`. |
| `local_patch` | apply a small local correction (edit a prompt, swap a parameter, regenerate one artifact) and retry under `retry_policy`. | `local_retry` has been exhausted and the correction is identifiable without regenerating the subgraph. | the patch and its rationale are recorded in the `event_log`; `node.contract.attempt` is incremented for the new attempt. |
| `replan` | the node's approach is wrong; regenerate its `subgraph` with a new `plan_version` (Graph Harness rule, [`concepts.md` §7](./concepts.md#7-why-durability-primitives), [`./research_dags_multiagent.md` §0.1](./research_dags_multiagent.md)). | `local_patch` has been exhausted and the failure is structural, not environmental. | new `plan_version` written; superseded nodes transition to `deprecated`. |
| `escalate` | hand off to a human via an `approval` node with a `human_approval` gate; the running node moves to `blocked`, a `pending_approvals` entry is added (see [`human_approval.md`](./human_approval.md)). | `replan` has been exhausted, or the failure class bypasses local recovery (e.g. `insufficient_permission`, `goal_changed`, `budget_exceeded`). | `pending_approvals` entry recorded in the checkpoint; `node_states` shows `waiting_user` or `blocked` for the dependent node(s). |

> **Boundedness.** The ladder is **finite** (four rungs, no infinite loops,
> no self-edge) and **monotonic** (never skip backward, never re-enter a
> rung above a higher one already exhausted). Once a rung is exhausted the
> runner advances; it does not cycle within a rung past `max_attempts`. This
> is the Graph Harness strict-escalation invariant
> ([`./research_dags_multiagent.md` §0.1](./research_dags_multiagent.md)).

### 3.1 Mapping ladder outcomes to node statuses

The ladder drives only transitions already in
[`state_model.md` §state transition table](./state_model.md#state-transition-table).
The canonical mapping is:

```
verifying --fail--> verification_failed
    |- on_failure in {local_retry, local_patch}, attempt < max_attempts
    |       -> retry_pending -> ready
    |- on_failure in {local_retry, local_patch}, attempt == max_attempts
    |       -> blocked (ladder advance to local_patch)
    |- on_failure == replan
    |       -> blocked (owning node re-materialises subgraph, new plan_version)
    |       -> superseded node: completed|cancelled -> deprecated
    |- on_failure == escalate (or retries exhausted past replan)
            -> blocked or waiting_user bound to an approval node
            -> pending_approvals entry recorded
```

These arrows are not additions to the transition table — they are the
already-authoritative
[`verifying → verification_failed` row](./state_model.md#state-transition-table),
the `verification_failed → retry_pending | blocked | escalate` row, the
`retry_pending → ready` row, and the `completed | cancelled → deprecated`
row, instantiated against the ladder.

### 3.2 Bounded concurrency

When the ladder advance is `replan` for *one* node inside a subgraph, other
sibling nodes in the plan are unaffected: they keep their recorded statuses
and the runner recomputes `ready_set` from the graph. A
`concurrency_conflict` between two nodes (§2.8) is the *one* case where the
ladder of one node forces a pause on a second.

---

## 4. Guards read persistent state — never memory

The retry guard that enforces `retry_policy` reads the **checkpoint** and the
per-node `node.contract` on disk, **never** an in-memory counter. The
authoritative attempt counter is `node.contract.attempt`
([`state_model.md` §node.contract fields](./state_model.md#nodecontract-fields));
the durable policy object is `node.contract.retry_policy`
([`loop_plan_spec.md` §6.1](./loop_plan_spec.md#61-retry_policy-object)).

This matters because a runner crash mid-retry must not reset the budget. When
a fresh session reads the checkpoint, it reads the true `attempt` — and a
node whose attempts are exhausted cannot quietly re-enter `local_retry` just
because the human (or host) restarted the process. The corresponding
invariant from [`state_model.md` §state transition table](./state_model.md#state-transition-table)
reads: "*retry_pending → ready: `attempt < max_attempts`;
`node.contract.attempt` incremented; guard read from **persistent** state*".

**Implication for `retry_pending`.** A node in `retry_pending` is *not*
guaranteed to re-enter `ready`; the guard evaluates the persistent counter on
each tick. The guard can decide to advance the ladder instead, which moves
the node to `blocked` (or `waiting_user`, if bound to an `approval`).

---

## 5. `retry_policy` and the backoff + jitter math

`retry_policy` is the durable budget the `local_retry` and `local_patch` rungs
share; the rungs differ in *what* they do on each attempt, not in *how often*
they retry.

### 5.1 Fields

| field | type | required | meaning |
|-------|------|----------|---------|
| `max_attempts` | int | yes | maximum number of execution attempts for this node before the ladder advances past `local_retry` (and `local_patch`). |
| `backoff_base_seconds` | number | yes | base interval between attempts, multiplied per attempt for exponential backoff. |
| `jitter` | bool | yes | `true` to add randomised jitter to the backoff. |

These are the fields locked in
[`loop_plan_spec.md` §6.1](./loop_plan_spec.md#61-retry_policy-object), copied
here only to anchor the math. **Do not** duplicate the field dictionary in
schemas or YAML — link to this section instead.

### 5.2 Backoff + jitter formula

Let `n` be the attempt index, zero-based (first retry is `n = 0`).

```
wait_n = backoff_base_seconds * 2^n     (if jitter == false)
wait_n = backoff_base_seconds * 2^n ± jitter  (if jitter == true)
```

The `[` ± jitter `]` is bounded so the wait is never negative. The same
formula appears in
[`./research_durable_loops.md` §1.4](./research_durable_loops.md#1-durable-execution-primitives--their-filesystem-mapping)
attributed to AWS Step Functions (`Retry`: `IntervalSeconds`, `MaxAttempts`,
`BackoffRate`, `JitterStrategy`).

**Worked example.** `max_attempts = 4`, `backoff_base_seconds = 1`,
`jitter = true`. Per-attempt waits (ignoring jitter noise): `n=0 → 1s`,
`n=1 → 2s`, `n=2 → 4s`, `n=3 → 8s`. After four attempts the ladder advances
to `local_patch` (or beyond).

### 5.3 Capped at `max_attempts`

The attempt index is the *current* attempt; the guard fires only while
`attempt < max_attempts`. The increment from `n` to `n+1` is recorded to
`node.contract.attempt` before the next backoff tick begins, so a crash
between attempts cannot lose a tick.

---

## 6. Saga compensation

`create-loop` adopts the saga pattern from
García-Molina & Salem, *Sagas*, 1987
([`./research_durable_loops.md` §1.7](./research_durable_loops.md#1-durable-execution-primitives--their-filesystem-mapping))
and the workflow-engine variants from Temporal Saga and AWS Step Functions.

### 6.1 Pairing

Each **side-effecting** node (a `workflow`-step's child `activity`) may pair
with a `compensation` node. The pairing is recorded on the compensation's
own contract: `node.contract.compensation_of` carries the `node_id` of the
side-effecting node it undoes
([`state_model.md` §node.contract fields](./state_model.md#nodecontract-fields)).
The kind of the undo node is `compensation` (one of the 8 locked node kinds
in [`loop_plan_spec.md` §Glossary](./loop_plan_spec.md#node-kinds)).

A compensation node is not paired with every node — only the side-effecting
ones. The rule of thumb:

- **`activity` → has a `compensation` node.** A node that produced an
  external write, sent a message, performed a payment, created a record, or
  otherwise changed the world.
- **`workflow`-only / read-only → no compensation.** A node whose only output
  is an `evidence_ref` and a `node.contract` mutation does not need one.

### 6.2 Order of execution

On **unrecoverable** failure (the ladder has reached `escalate`, or the loop
terminates because of `budget_exceeded`), compensations run **in reverse
order of completion** — last-in, first-out. This is the standard saga
ordering: the most recent external effect is undone first. The ordering is
computed from the `last_completed` list in the checkpoint and the
`event_log` ([`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields)).

The reverse-order rule is *bounded*: it terminates when either there are no
more compensations or a compensation itself fails. A compensation failure is
its own `inconsistent_result` (or `permanent_error`); the recovery layer
treats it as `insufficient_permission` or `inconsistent_result` and routes
it to `escalate` via an `approval` node (because at that point a human must
clean up external state the runner cannot reach).

### 6.3 What compensation is *not*

A compensation is **not** the same as a `local_patch`. A `local_patch` edits
the *plan* (the prompt, the parameter, the assertion) and tries again. A
`compensation` undoes an *external effect* so the world outside the loop is
back to a consistent state.

---

## 7. Idempotency

A retry, a resume, and a replan all face the same hazard: executing a tool
action twice when it should only run once. `create-loop` defends against
this with two filesystem-mappable primitives.

### 7.1 `run_id_directory` is the idempotency key

The `run_id_directory` is a directory whose **creation** is the
single-flight start signal. The runner creates it with `O_CREAT | O_EXCL`
semantics — the create either succeeds (you own the run) or fails with
`EEXIST` (someone already started it). This is the filesystem form of an
idempotency key, drawn from
[`./research_durable_loops.md` §1.6](./research_durable_loops.md#1-durable-execution-primitives--their-filesystem-mapping).

Practical consequences:

- **One attempt per node per plan run.** A `concurrency_conflict` (two
  schedulers trying to dispatch the same node) becomes a single-flight
  collision on the directory, not a duplicate tool call.
- **Resume is safe by construction.** A fresh session re-creates-or-rejoins
  the same directory and reads the prior `node.contract` — there is no in-
  memory state to lose.
- **Cross-host portability.** The primitive is filesystem-only; it requires
  no broker, no database, no locking service.

### 7.2 `cache_key` prevents duplicate side effects

Every node has a `node.contract.cache_key = hash(inputs + prompt + model +
config)` (Bazel-style, [`concepts.md` §7](./concepts.md#7-why-durability-primitives),
[`./research_dags_multiagent.md` §1.6](./research_dags_multiagent.md)). On a
fresh attempt with the *same* `cache_key` as a recorded successful prior
attempt, the runner may **skip** the side-effect and reuse the result,
provided the side-effect has a stable input→output relationship.

`cache_key` is **stronger than** `run_id_directory` (it survives replans
across `plan_version`s) and **weaker than** single-flight (it permits
multiple reads of cached data but cannot authoritatively resolve a write
conflict between two sessions — that's what `run_id_directory` is for).

### 7.3 Making a tool action safe to retry

Three rules make any `activity` (any side-effecting tool call) safe to retry
under the above primitives:

1. **Idempotency key on the side-effect.** The tool receives a stable id
   derived from `node.contract.cache_key` (a UUID stored in the
   `node.contract.started` lineage). Repeats with the same id are no-ops on
   the side of the world.
2. **Pre-effect log line.** Before the tool call, the runner appends a line
   to the `event_log` describing the intended action. On resume the runner
   scans the log; if the line is already present, the action is **not
   re-executed** (record-then-act pattern, à la Temporal / Restate
   durable promises,
   [`./research_durable_loops.md` §1.1](./research_durable_loops.md#1-durable-execution-primitives--their-filesystem-mapping)).
3. **Cache hit → skip.** If the `cache_key` matches a recorded success, the
   activity is skipped and the recorded evidence/artifact is reused.

If a tool is unsafe to retry even with the above, the node's `on_failure`
**must** be set to `replan` or `escalate` rather than `local_retry`, and the
recovery layer should pair it with a `compensation` node (§6).

---

## 8. Three-layer framing (Graph Harness)

The Structured Graph Harness paper (arXiv 2604.11378) frames agent
execution as three independent layers, each with a narrow interface:

| layer | concern | artifact in `create-loop` |
|-------|---------|---------------------------|
| planning | produce an **immutable** plan for a `plan_version` | `loop.plan`, the DAG of nodes and the subgraph recursion rule ([`loop_plan_spec.md` §7](./loop_plan_spec.md#7-subgraph-recursion)) |
| execution | dispatch ready nodes, evaluate gates, write evidence | `event_log`, `node.contract`, `evidence.ledger` ([`state_model.md` §state transition table](./state_model.md#state-transition-table)) |
| recovery | interpret failures, walk the bounded ladder, run compensations | this document and [`recovery_protocol.md`](./recovery_protocol.md) |

The plan for a given `plan_version` is immutable: recovery never edits a
node's `kind`, `gate`, `retry_policy`, or `on_failure`. When the recovery
layer's action requires a different approach, it produces a new `plan_version`
(`replan`) and transitions the affected nodes to `deprecated` ([`state_model.md` §state transition table](./state_model.md#state-transition-table)).
Source for the framing and the bounded-escalation invariant:
[`./research_dags_multiagent.md` §0.1](./research_dags_multiagent.md).

---

## 9. Per-exception response table

The table below is the recovery layer's contract: for each taxonomy kind, the
default behaviour across the four axes the recovery layer controls. These
defaults can be overridden per node by `retry_policy` and `on_failure`, in
which case the override wins.

| exception kind | auto-retry? | max retries (typical) | backoff | rolls back (saga)? | replans? | requests user? | terminates branch? | terminates loop? |
|----------------|-------------|----------------------|---------|--------------------|----------|----------------|--------------------|------------------|
| `transient_error` | yes | up to `max_attempts` | exponential + jitter (§5) | no | only after exhausted | no | only after exhausted | no |
| `permanent_error` | yes (≤ 1) | 1 | none | no | yes | only via `escalate` | yes (→ `replan`) | no |
| `tool_unavailable` | no | 0 | — | yes (§6) | yes | only via `escalate` | yes | only on `budget_exceeded` |
| `insufficient_permission` | no | 0 | — | yes | only after grant | **yes — gate must be `human_approval`** | no (awaiting grant) | no |
| `missing_data` | no (data is missing) | 0 | — | only if upstream is `activity` | yes if upstream can't regenerate | only if user can supply | yes | no |
| `inconsistent_result` | yes | up to `max_attempts` | exponential + jitter | no | yes after exhausted | only via `escalate` | yes (→ `replan`) | no |
| `corrupt_state_file` | no | 0 | — | only if state corruption hides side-effects | yes (re-`plan_version`) | **yes — quarantine + user confirmation** | yes | only if user abandons |
| `concurrency_conflict` | yes (later attempt waits) | up to `max_attempts` of waiting node | none (single-flight owns) | yes if conflict caused half-done writes | only after manual ordering | **yes — escalate when ordering can't be inferred** | yes (the losing attempt) | no |
| `no_progress` (stall) | yes (cancelled, then restarted) | up to `max_attempts` | none (cancel + retry) | no | yes after repeated stalls | only via `escalate` | yes (→ `replan`) | no |
| `budget_exceeded` | no | 0 | — | yes (§6) | no | **yes — terminal escalation** | yes | **yes** |
| `insufficient_context` | no (not a transient failure) | 0 | — | no | only if diagnostic reveals a structural gap | only after autonomous recovery exhausted AND irreducible / boundary-crossing | yes (paused for input, last rung) | no |
| `goal_changed` | no | 0 | — | yes (§6 in-flight) | yes (new `plan_version`) | **yes — user confirmation required, agent MUST NOT silently change `goal` / `true_intent`** | superseded → `deprecated` | only if user abandons |

**Reading the table.** The four columns on the left (`auto-retry`, `max
retries`, `backoff`, `rolls back`) describe the `local_retry` / `local_patch`
behaviour before the ladder advances. The four columns on the right
(`replans?`, `requests user?`, `terminates branch?`, `terminates loop?`)
describe what happens when the ladder runs out.

Two kinds are *unconditional* `escalate` candidates: `insufficient_permission`
and `budget_exceeded` — retrying these never helps, so the ladder jumps
straight to the `approval` node. `goal_changed` is similar but with an
extra rule: the change is provisional until the user confirms.
`insufficient_context` is **not** in this list. It first routes to a
diagnostic `subgraph` (form an assumption, gather evidence, update
confidence) and only escalates when autonomous recovery is exhausted AND
the remaining gap is irreducible or crosses a user-boundary (see
[`human_approval.md` §1](./human_approval.md#1-autonomy-first-approval-is-a-bounded-exception)
and `SKILL.md` §3). See [`human_approval.md`](./human_approval.md) for how
a `pending_approvals` entry is recorded and how the user decision resumes
the loop.

---

## 10. See also

- [`loop_plan_spec.md` §6.2](./loop_plan_spec.md#62-on_failure--the-escalation-ladder) — the canonical ladder definition.
- [`loop_plan_spec.md` §6.1](./loop_plan_spec.md#61-retry_policy-object) — the canonical `retry_policy` fields.
- [`loop_plan_spec.md` §Glossary](./loop_plan_spec.md#node-kinds) — the locked node-kind, gate-kind, status, and ladder enumerations.
- [`state_model.md` §state transition table](./state_model.md#state-transition-table) — the transitions the ladder drives.
- [`state_model.md` §node.contract fields](./state_model.md#nodecontract-fields) — `node.contract.attempt`, `cache_key`, `compensation_of`.
- [`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields) — `blocked`, `pending_approvals`, `event_log_ref`, `iteration`, `cost_units_spent`.
- [`concepts.md` §6](./concepts.md#6-why-a-bounded-escalation-ladder) — why the ladder is bounded and lives in the contract.
- [`concepts.md` §7](./concepts.md#7-why-durability-primitives) — `run_id_directory`, `cache_key`, `event_log`, `continue_as_new`, saga, Graph Harness.
- [`recovery_protocol.md`](./recovery_protocol.md) — the operational procedure for running this layer.
- [`evidence_gates.md`](./evidence_gates.md) — the gate-side companion.
- [`human_approval.md`](./human_approval.md) — the `approval` node, decision tiers, and handoff schema.
- [`./research_durable_loops.md`](./research_durable_loops.md) — §1.4 (Step Functions retry + jitter math), §1.6 (idempotency keys), §1.7 (saga / García-Molina 1987), §3.x (`interrupt()` and HITL).
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) — §0.1 Graph Harness (arXiv 2604.11378) for the three-layer framing and bounded escalation invariant.
- [`parallel_development_protocol.md`](./parallel_development_protocol.md) — conflict / failure / blocked / rollback for concurrent code development map onto this taxonomy and ladder (a merge conflict is an `inconsistent_result`, a stuck unit is `no_progress`); §8 there is the git rollback ladder.
