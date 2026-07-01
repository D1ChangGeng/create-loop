# Run Log: Append-Only Execution and Event Log

*Diataxis type: **reference**. This is the per-run execution log emitted by
the `create-loop` runtime. It is the **human-readable companion** to the
machine event log (`event_log_ref` in the checkpoint). It records every
status transition, every action, every evidence write, and every cost
unit spent, in chronological order.*

*The log is **append-only**: never edit, never delete, never reorder. It is
the audit trail that lets a fresh session reconstruct what happened. When
something looks wrong in the machine state, this log is what you read
first.*

---

## Line format

One event per line. Columns are pipe-separated. The format is greppable and
machine-parseable; a downstream tool can rebuild the timeline by sorting
on the timestamp.

```
{ISO datetime} | node_id={id} | status={from}->{to} | action={verb} | evidence={path} | cost={units}
```

Column rules:

- **`{ISO datetime}`**: UTC, ISO-8601 with seconds. Same format as the
  evidence ledger `recorded` field.
- **`node_id`**: the `id` of the node in `loop.plan.nodes`. Use `null`
  (literal text) when the event is plan-level (e.g. a `continue_as_new`
  rollover or a `replan`).
- **`status={from}->{to}`**: the canonical transition, using the 15
  statuses from `references/state_model.md` (e.g.
  `pending->ready`, `ready->running`, `running->verifying`,
  `verifying->completed`, `verifying->verification_failed`,
  `verification_failed->retry_pending`, `retry_pending->ready`,
  `running->waiting_user`, `waiting_user->ready`,
  `running->blocked`). Initial entry into the run uses `null->discovered`
  or `null->pending` per the state model.
- **`action`**: short imperative verb that names what the runtime did
  (e.g. `acquire_run_id`, `schedule_dispatch`, `load_skill`,
  `run_subgraph`, `evaluate_gate`, `write_evidence`, `bump_attempt`,
  `escalate_to_user`, `apply_compensation`).
- **`evidence`**: path to the artifact produced by this event, or
  `null` when no artifact was produced.
- **`cost`**: abstract cost units added by this event, as a decimal
  number. `0` when the event has zero cost.

For an `on_failure` ladder step, add a trailing note on the same line
after a space, e.g.:

```
2026-07-02T14:31:05Z | node_id=n12 | status=verification_failed->retry_pending | action=apply_retry | evidence=null | cost=1.0 ladder=local_retry attempt=2
```

The trailing fields are `key=value` pairs separated by single spaces.
`ladder=<step>` uses the canonical `local_retry | local_patch | replan |
escalate`. `attempt=<n>` records the persistent attempt counter from
`node.contract.attempt`.

---

## Worked example: happy path (pending -> ready -> running -> verifying -> completed)

A single node `publish_landing_page` (assignee = user, gate.kind =
human_approval, risk = high) goes through the green-path lifecycle.

```
2026-07-02T14:00:00Z | node_id=null | status=null->pending | action=plan_generated | evidence=loop.plan.yaml | cost=0
2026-07-02T14:00:01Z | node_id=publish_landing_page | status=null->pending | action=node_enumerated | evidence=null | cost=0
2026-07-02T14:00:05Z | node_id=publish_landing_page | status=pending->ready | action=topological_readiness_check | evidence=null | cost=0
2026-07-02T14:00:10Z | node_id=publish_landing_page | status=ready->running | action=acquire_run_id | evidence=runs/lp-2026-07-02/run_id.lock | cost=0
2026-07-02T14:00:11Z | node_id=publish_landing_page | status=running->waiting_user | action=request_human_approval token=tok-7af1 | evidence=pending_approvals/tok-7af1.json | cost=0
2026-07-02T15:42:00Z | node_id=publish_landing_page | status=waiting_user->ready | action=user_response_captured | evidence=pending_approvals/tok-7af1.json | cost=0
2026-07-02T15:42:05Z | node_id=publish_landing_page | status=ready->running | action=schedule_dispatch | evidence=null | cost=0.1
2026-07-02T15:43:30Z | node_id=publish_landing_page | status=running->verifying | action=execution_finished produces=production_dns_record | evidence=runs/lp-2026-07-02/publish.log | cost=1.2
2026-07-02T15:43:31Z | node_id=publish_landing_page | status=verifying->completed | action=evaluate_gate verdict=pass verifier=user | evidence=evidence/landing_page/human_approval_signed.json | cost=0
```

Notes for the reader:

- `running->waiting_user` is correct because the gate is
  `human_approval` and the user had not yet signed off.
- `waiting_user->ready` returns the node to the ready set, then the
  scheduler redispatches (`ready->running`) on the next loop turn.
- `verifying->completed` only happens because the evidence-ledger entry
  has `verdict = pass`. Anything else forces `verification_failed`.
- `cost` accumulates; the total for this node here is `0 + 0 + 0 + 0 + 0
  + 0.1 + 1.2 + 0 = 1.3` cost units, which is added to
  `checkpoint.cost_units_spent`.

---

## Worked example: failure path (verification_failed -> retry_pending -> ready)

The same node `publish_landing_page` (assignee = user, gate.kind =
human_approval, `on_failure = local_retry`, `retry_policy.max_attempts =
3`) goes through the failure path because the gate verdict is `fail`.

```
2026-07-02T15:00:00Z | node_id=publish_landing_page | status=null->pending | action=node_enumerated | evidence=null | cost=0
2026-07-02T15:00:05Z | node_id=publish_landing_page | status=pending->ready | action=topological_readiness_check | evidence=null | cost=0
2026-07-02T15:00:10Z | node_id=publish_landing_page | status=ready->running | action=acquire_run_id | evidence=runs/lp-2026-07-02/run_id.lock | cost=0
2026-07-02T15:00:15Z | node_id=publish_landing_page | status=running->waiting_user | action=request_human_approval token=tok-7af1 | evidence=pending_approvals/tok-7af1.json | cost=0
2026-07-02T15:01:00Z | node_id=publish_landing_page | status=waiting_user->ready | action=user_response_captured | evidence=pending_approvals/tok-7af1.json | cost=0
2026-07-02T15:01:05Z | node_id=publish_landing_page | status=ready->running | action=schedule_dispatch | evidence=null | cost=0.1
2026-07-02T15:02:30Z | node_id=publish_landing_page | status=running->verifying | action=execution_finished produces=staging_dns_record | evidence=runs/lp-2026-07-02/publish.log | cost=1.2
2026-07-02T15:02:32Z | node_id=publish_landing_page | status=verifying->verification_failed | action=evaluate_gate verdict=fail verifier=script rationale=staging_url_did_not_resolve_404 | evidence=evidence/landing_page/gate_check.json | cost=0.05
2026-07-02T15:02:33Z | node_id=publish_landing_page | status=verification_failed->retry_pending | action=apply_retry | evidence=null | cost=0 ladder=local_retry attempt=2
2026-07-02T15:02:48Z | node_id=publish_landing_page | status=retry_pending->ready | action=backoff_elapsed | evidence=null | cost=0
2026-07-02T15:02:50Z | node_id=publish_landing_page | status=ready->running | action=schedule_dispatch | evidence=null | cost=0.1
2026-07-02T15:04:10Z | node_id=publish_landing_page | status=running->verifying | action=execution_finished produces=staging_dns_record | evidence=runs/lp-2026-07-02/publish.log | cost=1.2
2026-07-02T15:04:12Z | node_id=publish_landing_page | status=verifying->completed | action=evaluate_gate verdict=pass verifier=script | evidence=evidence/landing_page/gate_check.json | cost=0.05
```

Notes for the reader:

- The transition `verifying -> verification_failed` is forced by the
  evidence-ledger entry whose `verdict` is `fail`. The state model forbids
  any path to `completed` from `verifying` unless the latest ledger
  entry's verdict is `pass`.
- `verification_failed -> retry_pending` is allowed because
  `on_failure = local_retry` and `node.contract.attempt` (read from the
  persistent checkpoint, never memory) is below `retry_policy.max_attempts`.
- The trailing `ladder=local_retry attempt=2` makes the escalation-ladder
  decision auditable. If `attempt` ever reaches `max_attempts`, the next
  line will be `verification_failed -> blocked` with `ladder=escalate`
  and a `pending_approvals` entry pointing at the user.
- On a `replan` ladder step, the trailing note would read
  `ladder=replan plan_version=2` instead, and a fresh `loop.plan` would
  land in the run directory.

---

## How to read this log

- Sort by timestamp to get the timeline.
- Filter by `node_id=<id>` to see one node's full lifecycle.
- Filter by `status=verifying->completed` to count successful gates.
- Filter by `ladder=escalate` to find every escalation point.
- Sum the trailing `cost=` field per node to recover per-node spend,
  then compare against `checkpoint.cost_units_spent` to detect drift.
