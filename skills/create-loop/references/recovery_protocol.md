# Recovery Protocol: Resuming a Loop from Any State

*Diataxis type: **explanation + how-to**. The first half explains why
recovery is a single, ordered, filesystem-mappable algorithm. The second
half is the procedure an agent runs. For the field dictionary this
procedure reads, see [`loop_plan_spec.md`](./loop_plan_spec.md). For the
state machine and status enum, see
[`state_model.md`](./state_model.md).*

---

## 1. The defining constraint

`create-loop` runs across sessions, hosts, and process lifetimes. Any
fresh agent must be able to continue the work correctly without any
prior chat memory, the prior agent's intent, or an in-process "cursor".
The checkpoint on disk is the only source of truth. Every mechanism in
this document exists to make that statement true.

The durability primitives we rely on come from
[`./research_durable_loops.md`](./research_durable_loops.md) (Temporal,
DBOS, Restate, AWS Step Functions, Azure Durable Functions) and the
[`./research_dags_multiagent.md`](./research_dags_multiagent.md) graph
harness work. The crucial property is that none of them require a
runtime beyond the filesystem itself, which is what makes them
"degraded-mode safe" ([`concepts.md` §10](./concepts.md#10-why-it-must-degrade-safely)).

---

## 2. The resume-from-blank-session algorithm

A new session invokes `create-loop` and walks the steps below in order.
Each step reads the durable artifacts, never an in-process variable.
The artifacts live under the `run-id` directory whose creation was the
single-flight start signal.

### Step 1. Locate the run-id directory

The `run_id_directory` is the idempotency key for the whole run. It was
created with `O_CREAT | O_EXCL` semantics on first start. On resume, a
fresh agent confirms the directory exists and reads its `plan_id` /
`plan_version` / `phase`. If no such directory exists, this is a fresh
start, not a resume, and the loop begins from `pending` rather than
`ready`. The single-flight rule forbids two agents claiming the same
run.

### Step 2. Read the latest checkpoint

The checkpoint ([`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields))
is the durable snapshot. Pick the entry with the highest `checkpoint_id`
(or `created` timestamp) for the current `plan_id` and `plan_version`.
Read, in this order:

- `node_states` , current `status` per `node_id`.
- `ready_set` , nodes currently `ready`.
- `blocked` and `pending_approvals` , open failures and open `approval`
  nodes with their `token`.
- `iteration`, `cost_units_spent` , for the termination check in step 5.
- `phase` , for the `continue_as_new` decision in §4.
- `open_assumptions` , open answers that may have resolved.
- `event_log_ref` and `evidence_ledger_ref` , paths to the two
  append-only artifacts the rest of this document depends on.

`next_suggested_action` is advisory. It is not authoritative.

### Step 3. Verify evidence and consistency

For every node marked `completed` in `node_states`, a matching
[`evidence.ledger`](./state_model.md#evidence-ledger) entry must exist
at `node.contract.evidence_ref` with `verdict == pass`. If a `completed`
node lacks passing evidence, demote it to `verifying` so its `gate`
re-runs. The ledger wins over the checkpoint; the checkpoint is not
trusted over recorded evidence.

Then verify internal consistency:

- `checkpoint.node_states` vs `loop.plan.nodes` , every `node_id` in the
  plan should appear in `node_states`, and vice versa.
- Every `evidence_ref` listed under a node's `gate` must point to an
  existing artifact in `evidence.ledger`.

If either check fails, fall into the consistency-repair procedure in
§6.

### Step 4. Rebuild the ready set

Apply the
[topological readiness rule](./loop_plan_spec.md#63-topological-readiness-rule):
a node is `ready` iff its `status` is `pending` AND every `node_id` in
its `requires` list has `status == completed`. A node with
`requires: []` becomes `ready` immediately on `pending`. A `node` with
`requires` listing a `node_id` whose status is anything other than
`completed` (including `undiscovered`, `discovered`,
`needs_clarification`, or `running` from a crashed prior session) is
not `ready`.

The recomputed set always wins. If it disagrees with the stored
`ready_set`, write the recomputed set to the next checkpoint.

#### 2.1 Reconciling a `running` node

A node whose `status == running` in a fresh session is disambiguated by its
**claim** (`contracts/<node-id>.claim`, see
[`state_model.md` → Per-node claim/lease](./state_model.md#per-node-claimlease)):

- **Lease unexpired** — a worker is live on this node. Leave it; do NOT
  re-dispatch (avoids double-execution under concurrency).
- **`delegated_to` set** — the node is delegated to a live child loop. Await
  that child's `closeout`; never re-dispatch the parent node.
- **Lease expired** — the prior owner crashed. Reclaim and reconcile via the
  `event_log`: if the activity already produced a recorded completion, demote to
  `verifying`; otherwise demote to `retry_pending` (subject to
  `retry_policy.max_attempts`; if exhausted, `blocked`).
- **No claim at all** — invalid state; a crash leaves an *expired* claim, not
  none. Rejected by rule R22 (`[R22 UNCLAIMED-RUNNING]`).

### Step 5. Check termination

Compare `iteration` to `termination.max_iterations` and
`cost_units_spent` to `termination.max_cost_units` from
[`loop_plan_spec.md` §1.2](./loop_plan_spec.md#12-termination-object).
If either cap is reached, or any `failure_criteria` evaluates true,
stop and route to a `waiting_user` approval (the escalation-ladder
terminus) rather than dispatching more work.

### Step 6. Pick the next node

Among the recomputed `ready_set`, dispatch by
[`priority`](./loop_plan_spec.md#node-object): higher `priority` runs
first. Apply the
[parallel dispatch rule](./loop_plan_spec.md#64-parallel-dispatch-rule)
where the host allows: nodes with `parallelizable: true` may run
concurrently, subject to `termination.max_cost_units` as a budget cap.

If `pending_approvals` is non-empty, surface those `approval` nodes
(with their `token`) to the user before doing dependent work, since
their outcomes may change the ready set.

### Step 7. Execute, checkpoint, repeat

Run the chosen node(s), evaluate the `gate`, append a ledger entry,
update `node_states`, write a new checkpoint, and repeat from step 4
until `termination.done_when` holds or a terminal state is reached.

This procedure is the same one defined in
[`state_model.md` §resume-from-blank-session](./state_model.md#resume-from-a-blank-session);
the only difference is this document makes the durability machinery
behind each step explicit.

---

## 3. Deterministic replay via the event log

A second kind of "resume" happens inside a single run, when an
activity was interrupted mid-flight. The mechanism is event-sourced
deterministic replay, the same pattern Temporal, Restate, and Azure
Durable Functions use
([`./research_durable_loops.md` §1.1, §1.3, §1.5](./research_durable_loops.md)).

### 3.1 The split

A `workflow` step is a deterministic plan decision: choose the next
node, evaluate a `branch` node, compute a `cache_key`, decide whether
to retry. It is safe to replay because re-running it produces the same
result.

An `activity` step is a side-effecting tool call: write a file, run a
shell command, post a webhook, call a paid API. It must be logged
before execution and must never be blindly replayed, because replay
duplicates the side effect.

The runner classifies each tool call at execution time. Tool calls
classified as `workflow` are replayed freely. Tool calls classified as
`activity` consult the `event_log` first.

### 3.2 The check

### 3.2 Canonical write-ahead ordering

The `event_log` is the **PRIMARY source of truth**; the checkpoint and its
counters are DERIVED. Every node advance writes in this exact order so a crash
at any point is recoverable:

1. Append a **`pre_effect`** entry to the `event_log` (`{seq, node_id,
   from_status, to_status, phase, intent, idempotency_key, ts}`). `seq` is
   strictly monotonic (rule R24).
2. Execute the activity (the side effect).
3. Append a **`post_effect`** entry (`{seq, node_id, outcome, result_hash,
   ts}`).
4. Append the `evidence.ledger` entry for the gate verdict.
5. Write the `checkpoint` **last**, via a temp file + atomic `rename` (+ `fsync`
   where available), so a half-written checkpoint is never observed.

Because the checkpoint is written last and is derived, a crash between any two
steps leaves the log authoritative and the checkpoint at worst one step stale —
never contradictory.

### 3.2.1 The activity check (before every activity)

1. Compute the activity's stable identity from the plan (the node
   `id`, the attempt number from `node.contract.attempt`, and a hash of
   the activity's inputs).
2. Look up that identity in the `event_log`.
3. If a `post_effect` with `outcome == ok` exists, return the recorded
   result without re-executing.
4. If no `pre_effect` exists, execute (following the ordering above).
5. If a `post_effect` with `outcome == fail` exists, apply the node's
   `on_failure` ladder step instead of re-executing.
6. **In-doubt** — a `pre_effect` exists with no matching `post_effect`
   (crash between steps 1 and 3): if the entry carries an
   `idempotency_key`, re-execution is safe, so re-run; otherwise route the
   node to `blocked` for human/compensation resolution — **never blind-replay
   a non-idempotent activity**. Rule R23 rejects an in-doubt entry that has
   neither resolution.

### 3.2.2 Reconciliation on resume

Rebuild the derived state from the log, not the (possibly stale) checkpoint:
replay the `event_log` in `seq` order and recompute `node_states`,
`cost_units_spent`, `iteration`, and each node's `attempt`. If the recomputed
values disagree with the loaded checkpoint, the **log wins** — write the
reconciled values into the next checkpoint. This is why a lost checkpoint write
cannot silently roll back the budget counters (Oracle F8).

### 3.3 Non-determinism is the failure mode

Replay breaks when a workflow step produces a different result the
second time. Common causes:

- Wall-clock time read inside a workflow step. Read it from the
  `event_log` or derive it from a recorded timestamp.
- Random IDs or nonces. Mint them once and record them; reuse the
  recorded value on replay.
- LLM calls inside workflow steps. LLM calls are `activity` not
  `workflow`; classify them as such and let the log absorb the cost.

When a replay mismatch is detected (the equivalent of Temporal's
"non-deterministic workflow" or Restate's `RT0016`), truncate the
`event_log` at the last good entry and resume from there. This is the
analogue of Temporal's "Reset" operation
([`./research_durable_loops.md` §1.1](./research_durable_loops.md)).

---

## 4. Continue-as-new / phase rollover

Append-only logs grow. Temporal terminates a workflow at ~51,200
events or 50 MB. Azure Durable Functions has a similar cap. Step
Functions caps execution history at 25,000 entries. The
`create-loop` equivalent is a budget on the `event_log` and the
`evidence.ledger`.

When the log approaches the budget, the loop does not "lose" history;
it rolls the phase over.

### 4.1 The procedure

1. Archive the current `event_log` and `evidence.ledger` under
   `runs/<run-id>/archive/phase-<N>/` (read-only).
2. Compute the carry-forward state: every `node_id` whose
   `node.contract.status` is terminal (`completed`, `cancelled`,
   `deprecated`), every `cache_key` that already matched a recorded
   success, the open `ready_set`, the open `pending_approvals`, and
   the current `iteration` and `cost_units_spent`.
3. Write a fresh `checkpoint` with `phase: <N+1>`, embedding the
   carry-forward state.
4. Initialize a fresh `event_log` and `evidence.ledger` for phase N+1.
5. Resume the loop, reading the new checkpoint.

The same `plan_id` and `plan_version` carry across phases. Phases are
internal bookkeeping, not plan changes; `plan_version` only bumps on
`replan` (see §6.4).

### 4.2 Why phase and not plan_version

A `plan_version` change implies the plan itself changed and triggers
the Graph Harness rule that the new version is a separate, immutable
artifact. A `phase` change does not. It is a checkpoint-management
operation that preserves the plan's identity. Plan-level replans
still bump `plan_version`; only log rollover bumps `phase`.

---

## 5. cache_key skip

Each `node.contract` carries a `cache_key = hash(inputs + prompt +
model + config)`. This is the Bazel action-cache idea
([`./research_dags_multiagent.md` §1.6](./research_dags_multiagent.md)).

### 5.1 When the skip fires

Before dispatching a node, the runner:

1. Recomputes the `cache_key` from the current `inputs`, prompt,
   `model`, and config.
2. Searches `evidence.ledger` for any prior entry on this `node_id`
   whose `cache_key` matches and whose `verdict == pass`.
3. If a match exists and the matching artifact is still present at
   `artifact_path`, the node is treated as already `completed`: the
   runner copies the cached artifact into the new run's
   `evidence_ref`, records a ledger entry that cites the cache hit, and
   moves on.

The skip is `cache_key`-based, not `node_id`-based. Two nodes may
share an id across `plan_version` boundaries; only identical content
collapses.

### 5.2 When the skip must not fire

A node with `on_failure: replan` or `on_failure: escalate` does not
honour the cache. A node that consumed a `compensation_of` target
that has since been undone does not honour the cache. A node whose
`risk` is `high` and whose `gate` is `human_approval` never reuses a
cached human verdict , humans are not cacheable.

The whitelist of "cache-friendly" combinations mirrors the gate
exemption whitelist in
[`evidence_gates.md`](./evidence_gates.md). Anything below
`artifact_exists` plus trivial formatting is not eligible.

---

## 6. Consistency repair

The checkpoint can be missing, corrupt, or inconsistent with the
ledger. The repair ladder is layered so cheaper recovery runs first
and more expensive recovery runs only when needed.

### 6.0 State Authority Order (who to trust when files disagree)

A resuming agent reads many files; when they disagree it must know which one
wins. The authority order, highest first:

| # | File | Authority role |
|---|------|----------------|
| 1 | `loop.meta.yaml` | Identity and parent/child relation. Never derived from anything else. |
| 2 | `event_log` | **Primary source of truth for what happened.** Append-only; every other state file is a projection of it. |
| 3 | `evidence.ledger.yaml` | Source of truth for gate verdicts (which nodes legitimately passed). |
| 4 | `checkpoint.yaml` | Fast-resume **snapshot** — trusted only when it agrees with the log + ledger; on conflict it is rebuilt from them. Highest `checkpoint_seq` wins between snapshots. |
| 5 | `loop.state.yaml` | Live pointer (active node, ready set, lease index) — a convenience cache, always rederivable. |
| 6 | `loop.plan.yaml` | Structure/DAG. Immutable per `plan_version`; a mismatch triggers §6.4. |
| 7 | `INDEX.yaml` | Path index — reconciled against the tree (R37), never authoritative over it. |
| 8–9 | `decision.log.md`, `run.log.md` | Human-readable narration; never a source of machine truth. |

Conflict handling (run [`check_loop_integrity.py`](../scripts/check_loop_integrity.py)
first; any violation means enter recovery instead of advancing):

| Conflict | Handling |
|----------|----------|
| checkpoint points at a node absent from the plan | recovery mode; rebuild `node_states` from the log/ledger (§6.1) |
| node `completed` but no active passing evidence | degrade the node to `verification_failed` |
| child loop in `INDEX.yaml` but its directory is gone | mark `missing_child_loop`; reconcile the index (R37) |
| evidence `artifact_path` referenced but file missing | mark that evidence `invalid` (R38); re-verify the node |
| `event_log` disagrees with `checkpoint` | rebuild the checkpoint from the log (log wins) |
| `loop.plan` has a cycle / dangling edge | block execution; open a plan-repair subgraph |

### 6.1 Missing node_states, intact ledger

Recompute `node_states` from the `evidence.ledger`:

- For every ledger entry with `verdict == pass`, set the node's status
  to `completed`.
- For every entry with `verdict` in `fail` or `inconclusive`, set the
  status to `verification_failed`.
- For every node in the plan with no ledger entry, set the status to
  `pending`.
- Apply the topological readiness rule (§2 step 4) to derive the new
  `ready_set`.

This produces a checkpoint that agrees with the ledger, which is the
only source of truth.

### 6.2 Missing ledger, intact checkpoint

The checkpoint cannot be trusted alone. Demote every `completed` node
to `verifying` so its `gate` re-runs. The `evidence_ref` artifact
files (if they exist on disk) may be used to short-circuit re-runs for
the cheapest gates, namely `artifact_exists` and `automated_check`,
but any scored gate (`llm_judge`, `self_consistency`,
`evaluator_optimizer`, `step_verifier`) must re-execute and re-record.

### 6.3 Both missing

Hard reset. Treat the run as fresh: every node goes back to `pending`,
the `ready_set` is recomputed, the `event_log` is reinitialised.
Append a `ledger` entry that records the recovery itself, with
`verifier: script` and `verdict: inconclusive` plus a `rationale`
describing the rebuild. This recovery is one-shot; if a second
recovery becomes necessary within the same run, the loop escalates.

### 6.4 Plan-level corruption (plan_version mismatch)

If the current `plan_version` no longer matches the persisted
`loop.plan` artifact, the checkpoint is for a stale plan. Apply the
Graph Harness rule: the old plan is immutable; the recovery layer
materialises the new `plan_version` and the `node_states` map is
reconciled against the new node ids (typically by `requires`
matching, with unmatched old nodes moving to `deprecated`).

---

## 7. Filesystem realisation

Every mechanism above maps to specific files under the `run-id`
directory. The naming is conventional, not enforced by the schema, but
every recovery implementation is expected to use it.

| mechanism | files (relative to `runs/<run-id>/`) |
|-----------|----------------------------------------|
| `run_id_directory` (idempotency key) | the directory itself, created with `O_CREAT \| O_EXCL` |
| `cache_key` skip | `evidence.ledger` lookup by `cache_key` |
| `event_log` (append-only) | `events.jsonl`, one event per line |
| `workflow` vs `activity` split | `events.jsonl` entries tagged `kind: workflow \| activity` |
| `continue_as_new` rollover | `archive/phase-<N>/`, `checkpoint.yaml` with new `phase` |
| evidence verification | `evidence/ledger.yaml`, `evidence/<node-id>/` artifact files |
| node-contract persistence | `contracts/<node-id>.yaml` |
| pending approvals | `approvals/<token>.pending` |
| blocked reasons | `blocked/<node-id>.reason.txt` |
| termination check | `checkpoint.yaml` (`iteration`, `cost_units_spent`) read against `loop.plan.yaml` `termination.*` |

The `event_log` is never truncated by the runner except during an
explicit `continue_as_new` rollover (§4) or a documented recovery
operation (§6). The `evidence.ledger` is never edited; corrections are
new entries that supersede prior ones, recorded with a `supersedes`
field that names the prior `entry_id`.

---

## 8. Degraded-mode safety

Every recovery mechanism in this document works with no background
process, no durable runtime, and no subagents. The `run-id` directory
plus the `event_log` plus the `checkpoint` plus the `evidence.ledger`
on disk are themselves the runtime. If the host has no in-memory
state across a session boundary, the next agent reads the same files
and walks the same procedure.

This is the practical payoff of grounding the whole design in files
and explicit state. Degraded mode is not a second implementation; it
is the same contract with fewer conveniences
([`concepts.md` §10](./concepts.md#10-why-it-must-degrade-safely)).

---

## See also

- [`concepts.md` §7](./concepts.md#7-why-durability-primitives) gives the
  durability primitives in plain prose.
- [`state_model.md` §resume-from-blank-session](./state_model.md#resume-from-a-blank-session)
  gives the same algorithm in compact table form.
- [`loop_plan_spec.md` §6](./loop_plan_spec.md#6-scheduling-failure-semantics) gives
  scheduling and failure semantics, including the escalation ladder.
- [`./research_durable_loops.md`](./research_durable_loops.md) lists
  Temporal, DBOS, Restate, Step Functions, Durable Functions.
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) covers
  graph harness, Bazel-style action cache, Make-style artifact deps.