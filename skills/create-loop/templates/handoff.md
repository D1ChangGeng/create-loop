# Handoff: Cross-Session / Cross-Agent Handoff Document

*Diataxis type: **how-to**. This is the artifact a session writes when it
must stop (budget exhausted, session timed out, an `escalate` ladder step
fired, or simply a planned hand-off). A brand-new session reads exactly
this document plus the durable checkpoint to continue. The handoff is the
**first** thing the next agent reads.*

---

## When to write a handoff

Write a fresh handoff whenever any of the following is true:

- The session is about to die (timeout, forced exit, context exhausted).
- The `escalate` ladder step fires and a human `approval` node needs
  attention.
- The plan is being passed from one specialized subagent to another.
- A checkpoint rollover (`continue_as_new`, per
  `references/concepts.md` §7) is in progress.
- A `replan` has just produced a new `plan_version` and the next session
  needs to know what changed.

Do not write a handoff for ordinary intra-session pauses. Pause-and-resume
inside the same session is handled by the checkpoint alone.

---

## Field set

Each section below corresponds to a required or optional part of the
handoff. The first four (H1 through H4) implement the canonical handoff
schema (`summary`, `findings`, `confidence`, `verify_before_using`). The
remaining sections (H5 through H12) are the runtime-state bridge to the
checkpoint defined in `references/state_model.md`. A complete handoff
covers H1 through H12; truncate only H12 (free-form notes), never any
earlier section.

---

### H1. Summary

Two to five sentences. State the current top-level goal, the plan id and
version the work is happening under, and where the run actually is in
the lifecycle. The summary is the **only** part of the handoff a
skim-reader needs. If they read nothing else, they still understand the
shape of the work.

### H2. Findings

Concrete facts the previous session learned. Each finding is a single
bullet, verifiable from a referenced artifact (a file path, an evidence
ledger entry id, a checkpoint field). Findings include surprises, dead
ends, and short-cuts. They do not include speculation or future plans.

### H3. Confidence

A single value: `high`, `med`, or `low`. State the level and the reason
in one sentence. `high` means the handoff is ready to act on without
verification. `med` means the next agent should re-verify before acting.
`low` means treat the work as untrusted and run the resume-from-blank
algorithm with extra skepticism (see `references/state_model.md` §resume).

### H4. Verify before using

A short list of checks the next agent **must** run before acting on the
handoff. Each check names the file or path to read and the expected
result. Examples: "read `checkpoint.yaml`, confirm `ready_set` matches
section H7", "spot-check the three most recent `evidence.ledger` entries
against the gate rubrics".

### H5. Current top-level goal

Verbatim copy of `loop.plan.goal` and `loop.plan.true_intent` for the
plan the checkpoint tracks. The next agent reads these to recover
context that may have drifted in chat history.

### H6. Current phase and iteration

The `phase` counter and the `iteration` counter from the checkpoint, plus
`plan_id` and `plan_version`. These four values together locate the
session in time inside the durability machine; mismatch between any of
them and the on-disk checkpoint means the handoff is stale and the next
agent must roll back to the resume-from-blank procedure.

### H7. Ready set

The list of `node_id`s in the checkpoint's `ready_set`, copied verbatim.
The next agent dispatches from this list and only this list (recomputed
set wins on disagreement per the resume algorithm).

### H8. Blocked list

A copy of every entry in the checkpoint's `blocked` array, each entry
with its `{node_id, reason}`. These are nodes that cannot proceed
without intervention, paired with the reason the previous session
recorded.

### H9. Pending approvals

A copy of every entry in the checkpoint's `pending_approvals` array,
each entry with `{node_id, token, requested}`. These are open human
`human_approval` gates. The next agent surfaces them to the user **before**
dispatching any dependent node.

### H10. Next suggested action

Verbatim copy of `checkpoint.next_suggested_action`. Advisory only.
The next agent treats this as a tie-breaking hint, never as a source
of truth over the graph.

### H11. Open assumptions

Verbatim copy of `checkpoint.open_assumptions`. Each entry is a
verifiable assumption or a `needs_clarification` answer that has not yet
been checked. The next agent either resolves them or carries them
forward into the next handoff.

### H12. Notes (optional)

Free-form. Conventions, traps, things-that-bit-us, pointers to in-progress
chat (if persisted), names of humans to ping. Use this for everything
that does not fit elsewhere. Never put a finding here that should be in
H2; never put an action here that should be in H10.

---

## Required pointer (machine-readable)

At the bottom of every handoff, include a fenced code block titled
"Pointers" containing paths the next agent must open:

```
## Pointers

- checkpoint: {path to checkpoint.yaml}
- evidence_ledger: {path to evidence.ledger.jsonl}
- event_log: {path to event_log.jsonl}
- run_log: {path to run.log.md}
- decision_log: {path to decision.log.md}
- task_profile: {path to task_profile.yaml}
- loop_plan: {path to loop.plan.yaml}
```

Paths are relative to the run directory and must remain valid under the
single-flight `O_CREAT|O_EXCL` rule (no concurrent run on the same
`run_id`).

---

## Worked skeleton (fill in the values)

The skeleton below shows the exact headings a fresh handoff should
carry. Copy this skeleton, fill in the values, and commit it next to
the checkpoint. Do not reorder headings; the next agent greps on
heading names.

```markdown
# Handoff: {plan_title}

Written by: {session_id or agent name}
Written at: {ISO datetime}
Plan: {plan_id} v{plan_version}, phase={phase}, iteration={iteration}

## H1. Summary

{2-5 sentences: goal, intent, lifecycle position}

## H2. Findings

- {finding 1: file path / ledger id / checkpoint field}
- {finding 2}
- ...

## H3. Confidence

{high | med | low}. {one-sentence reason}

## H4. Verify before using

- {check 1: read X, expect Y}
- {check 2}
- ...

## H5. Current top-level goal

- goal: {verbatim from loop.plan.goal}
- true_intent: {verbatim from loop.plan.true_intent}

## H6. Current phase and iteration

- phase: {n}
- iteration: {n}
- plan_id: {id}
- plan_version: {n}

## H7. Ready set

- {node_id_1}
- {node_id_2}
- ...

## H8. Blocked list

- node_id: {id}, reason: {reason}
- ...

## H9. Pending approvals

- node_id: {id}, token: {token}, requested: {ISO datetime}
- ...

## H10. Next suggested action

{verbatim copy of checkpoint.next_suggested_action}

## H11. Open assumptions

- {open_assumption 1}
- ...

## H12. Notes (optional)

{free-form}

## Pointers

- checkpoint: {path}
- evidence_ledger: {path}
- event_log: {path}
- run_log: {path}
- decision_log: {path}
- task_profile: {path}
- loop_plan: {path}
```
