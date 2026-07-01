# Closeout: Final Retrospective and Termination Record

*Diataxis type: **explanation**. This is the artifact the `create-loop`
runtime writes when the loop reaches a terminal state. It is the human
record of what happened, what was verified, and what survives the run
as reusable knowledge. It is written exactly once per `plan_version` and
appended to the run directory.*

---

## When to write a closeout

Write a closeout immediately when any of the following is true:

- `termination.done_when` is satisfied. This is the happy-path case.
- The run is cancelled by user or plan. Record `terminated_reason:
  cancelled`.
- A `failure_criteria` line holds. Record `terminated_reason: failed`.
- A budget is hit. Record `terminated_reason: budget_exceeded` and cite
  which budget (`max_iterations`, `max_wall_clock_hours`,
  `max_cost_units`).
- A `replan` ladder step crossed the maximum allowed replan count.
  Record `terminated_reason: replan_exhausted`.

A closeout is written **once** per closeout reason. If a new `plan_version`
starts after the closeout (rare), that version gets its own closeout.

---

## Sections

### C1. Goal restated

Copy `loop.plan.goal` and `loop.plan.true_intent` verbatim. A reader
coming to the closeout cold, with no plan file open, needs to know what
the run was for.

### C2. Deliverables vs success criteria

A pass/fail table. One row per entry in `success_criteria`. Columns:
`id`, `statement` (abbreviated), `measurable`, `gate verdict`,
`outcome` (`pass` | `fail` | `partial`), `evidence_ref`.

If a criterion was `measurable=false`, the verdict column carries the
verifier (`agent` | `subagent` | `user` | `script`) plus a one-line
rationale. If a criterion was `measurable=true`, the verdict column
carries the objective check that ran.

At the bottom of the table, write one sentence on the overall outcome.
A single unpassed criterion that is `measurable=true` disqualifies the
run from the `done_when` path.

### C3. What was verified (evidence summary)

A short narrative of which `gate_kind`s fired (one of: `automated_check`,
`test`, `llm_judge`, `self_consistency`, `evaluator_optimizer`,
`step_verifier`, `human_approval`, `artifact_exists`), how many times,
and the global pass/fail ratio. Reference the `evidence.ledger` by path
and let the reader dig into it for the per-node detail.

If any verdict was `inconclusive`, call it out here. An inconclusive
verdict is not a pass and is not a fail; it means a human must judge
it before the run can be declared done.

### C4. Open items and known limitations

A bullet list. Anything unresolved at termination falls in here: open
`needs_clarification` answers, deferred subgraphs, partially met
`measurable=false` criteria that the user has accepted, external
dependencies still waiting. Each entry names the owning `node_id` and
the resolver if one exists.

### C5. Decisions made (link decision.log)

A one-line pointer to the per-run `decision.log.md`, followed by a
short summary of the load-bearing decisions:

- the count of entries
- the count of `ladder=escalate` entries
- the count of `ladder=replan` entries and the resulting `plan_version` chain
- any decision that materially changed scope, autonomy, or non-goals

The full record is in the decision log; do not duplicate its body here.

### C6. Knowledge candidates for promotion

Findings the run produced that are **re-usable beyond this task**.
Each candidate is a single bullet prefixed by `[LOOP]` (eligible for
the project's self-evolution knowledge base) and explained in one
sentence.

A finding qualifies as `[LOOP]` only when it is:

- specific enough to act on next time, and
- general enough to apply outside this exact task, and
- grounded in evidence recorded in this run, not opinion.

Examples (comments only, not real findings):

- `[LOOP] When a human_approval gate has a 24-hour SLA in practice, the
  initial backoff on retry_pending should be tuned upward to avoid
  thrash. Source: decision log entry DEC-7, evidence
  evidence/landing_page/gate_check.json.`
- `[LOOP] Lighthouse CI is unreliable on staging URLs behind a VPN;
  fall back to a local lighthouse run via the artifact_exists gate.
  Source: evidence/landing_page/lighthouse.json.`

A finding that only applies to this task is not `[LOOP]`; move it to C4.

### C7. Final termination reason

Exactly one of the following enum values, lowercase snake_case:

- `done_when_satisfied`: every `success_criteria` entry passed and
  every top-level node is `completed`.
- `cancelled`: user or plan intentionally stopped the run.
- `failed`: a `failure_criteria` line held; the run is dead and the
  task is not accomplished.
- `budget_exceeded`: `iteration >= termination.max_iterations`,
  `cost_units_spent >= termination.max_cost_units`, or
  `wall_clock >= termination.max_wall_clock_hours`.
- `replan_exhausted`: the ladder crossed the allowed replan count.

Cite the specific evidence (the criterion that fired, the budget that
was exceeded, the user message that cancelled) on a single line beneath
the value.

---

## Worked skeleton

```markdown
# Closeout: {plan_title}

Plan: {plan_id} v{plan_version}
Closed at: {ISO datetime}
Session: {session_id or agent name}

## C1. Goal restated

- goal: {verbatim}
- true_intent: {verbatim}

## C2. Deliverables vs success criteria

| id  | statement (abbrev) | measurable | gate verdict | outcome | evidence_ref |
|-----|--------------------|------------|--------------|---------|--------------|
| SC-1| ...                | true       | pass         | pass    | ...          |
| SC-2| ...                | false      | llm_judge 0.78 | partial | ...         |

Overall outcome: {one sentence}.

## C3. What was verified (evidence summary)

- gates fired: {counts per gate_kind}
- pass / fail / inconclusive ratio: {n} / {n} / {n}
- evidence ledger: {path}
- inconclusive items requiring human judgement: {list or "none"}

## C4. Open items and known limitations

- {open_item_1, node_id, resolver}
- ...

## C5. Decisions made

- decision log: {path to decision.log.md}
- entries: {n}, escalations: {n}, replans: {n}
- material scope changes: {list or "none"}

## C6. Knowledge candidates for promotion

- [LOOP] {finding, evidence ref}
- [LOOP] {finding, evidence ref}
- ...

## C7. Final termination reason

{value from the enum above}.

{one-line citation of the criterion / budget / message that triggered it}
```
