---
description: "Show a read-only status snapshot for a detected v1 or v2 create-loop."
argument-hint: "[--protocol v1|v2] [loop-id|loop-dir]"
---

Use the create-loop skill to produce a read-only status snapshot for a Loop.

Arguments: $ARGUMENTS

Resolve `CREATE_LOOP_SKILL_ROOT` to the directory containing the create-loop
`SKILL.md` loaded for this command. Do not assume a repository-relative path.

Parse an optional `--protocol v1|v2`, locate the Loop, and detect the protocol:
`goal.json` with `schema_version: "2.0"` is v2; `loop.plan.yaml` is v1. An
explicit selector must agree. Mixed or ambiguous artifacts are an error.

**This command is strictly READ-ONLY. Do not mutate any file, run a validator,
execute work, acquire a claim, regenerate a projection, or advance a node.**

### v2 snapshot

Read `goal.json` and determine the immutable plan mode first. For
persistent/governed mode, read `journal.jsonl`, the plan selected by the latest
legal `plan_activated` record, and `resume.json` when present. Reconcile in memory:
check the goal/plan hashes, journal sequence/tail, transition chain, evidence
relations, lifecycle/completion/reopen order, and unmatched exact effects.
Treat resume as a cache and label it stale when its source pointers differ.
Report goal and criteria, active plan/mode/modules, Loop status, recomputed node
states/frontier, open context, pending authorization, in-doubt effects, current
evidence conflicts, and the latest next-action decision as advice with
actor/time. Do not create or repair anything.

For a lightweight Loop, read only `goal.json` and `plans/plan-v1.json`; report
the immutable goal, mode, DAG, and declared checks, and state explicitly that
there is no persisted frontier or runtime evidence yet. Absence of journal and
resume is valid in this mode, not corruption.

### v1 snapshot

Read only from these durable files when present:

- `.agents/loops/INDEX.yaml` (or a child loop's `_loops/INDEX.yaml`) to locate the
  loop and obtain index hints;
- the loop's `loop.plan.yaml` for the goal, dependencies, and node contracts;
- the latest `checkpoint.yaml` by highest `checkpoint_seq`;
- `event_log.jsonl` to reconcile node states and ensure the checkpoint sequence
  is not stale;
- `evidence.ledger.yaml` for current verification results;
- active claim files for live/delegated work.

For interpreting node statuses, you may consult
`references/state_model.md` (§"Node status enum") for meaning
only — do not copy the enum into your output.

Report:

1. Top-level goal from the plan and current phase from the reconciled snapshot.
2. The current active node and latest checkpoint sequence, clearly marking any
   stale index/checkpoint hint.
3. The ready set recomputed from plan dependencies and reconciled states, plus
   blocked nodes and reasons.
4. Pending approvals (any node in `waiting_user` with an open decision).
5. The next recommended action.

If no loop exists yet, say so and suggest `/loop-new`.
