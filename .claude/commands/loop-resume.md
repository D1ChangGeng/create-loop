---
description: "Resume a v1 checkpoint loop or v2 journal loop from a blank session."
argument-hint: "[--protocol v1|v2] [loop-dir]"
---

Use the create-loop skill to resume a Loop from a blank session.

Arguments: $ARGUMENTS

Resolve `CREATE_LOOP_SKILL_ROOT` to the directory containing the create-loop
`SKILL.md` loaded for this command. Do not assume a repository-relative path.
Treat every skill-relative path below as relative to that root, and fail clearly
if no single root can be identified.

This requires no prior chat memory. Parse an optional `--protocol v1|v2`, locate
the Loop, and detect its protocol from durable artifacts. `goal.json` with
`schema_version: "2.0"` is v2; `loop.plan.yaml` is v1. An explicit selector must
agree. Never auto-migrate or mix write paths.

### v2 path

Load `SKILL.md` §"Protocol selection" and `references/protocol_v2.md`. Read
`goal.json` and inspect the immutable plan mode first. Run the read-only
whole-loop gate:

`python "<CREATE_LOOP_SKILL_ROOT>/scripts/validate_loop_dir.py" "<loop-dir>"`

If validation identifies a lightweight plan and no journal, report that the
Loop has no durable runtime history by design. Reconstruct only goal, plan, DAG,
and declared checks; do not fabricate prior state or a resume. Continuing in a
new session is itself the upgrade trigger: hand off to `/loop-run`, which must
create the bounded `plan-v1 activation -> control trigger evidence ->
control_mode_upgrade decision -> plan-v2 activation` journal prefix and a
persistent/governed plan version before recording new runtime facts.

For persistent/governed mode, parse `journal.jsonl` through the last complete
legal record, load the latest valid `plan_activated` target, and verify
plan/goal hashes.

Report corruption or an in-doubt effect and enter the protocol's recover path;
never truncate the journal or blindly repeat an effect. Compare `resume.json`
source pointers with a canonical projection. If stale but otherwise valid,
regenerate it atomically with `render_resume.py`, then report goal, active plan,
frontier, open context, pending authorization, in-doubt effects, and the prior
next-action decision with actor/time. Independently judge the next action and
hand off to `/loop-run`. Do not read or create v1 checkpoint/ledger/state files.

### v1 compatibility path

For v1, locate the loop from the durable index, then read the plan, checkpoint,
event log, evidence ledger, and active claims. Use the loaded recovery
protocol's authority order when they differ.

**Load these skill files BEFORE you advance — they are the source of truth. Read them; do not restate their contents from memory, and do not paste their vocabulary into your output.**

- `references/state_model.md` §"Resume from a blank session" — the authoritative resume algorithm and the per-node claim/lease disambiguation.
- `references/recovery_protocol.md` §2 (the resume-from-blank-session algorithm, step by step) and §6 (Consistency repair, incl. §6.0 State Authority Order — the event log wins when files disagree).
- `templates/claim.yaml` — the claim/lease schema that tells you whether a `running` node is live, crashed, or delegated.

Run the integrity gate FIRST, before advancing anything —
`python3 "<CREATE_LOOP_SKILL_ROOT>/scripts/check_loop_integrity.py" "<loop-dir>"`. A nonzero
exit means enter a recovery subgraph (recovery_protocol.md §6), NOT normal work.

Then resume v1:

1. Locate the loop directory ($ARGUMENTS, or discover it via
   `.agents/loops/INDEX.yaml`).
2. Read `loop.plan.yaml`, the latest `checkpoint.yaml`, `event_log.jsonl`,
   `evidence.ledger.yaml`, and any active claim files.
3. Reconcile by replaying the event log and applying the authority order from
   `references/recovery_protocol.md`; verify the checkpoint event sequence is
   fresh before trusting its projections.
4. Honor claim/lease: skip nodes that are live or delegated.
5. Rebuild readiness from the plan dependencies plus reconciled node states,
   pick the next node, and continue.

Once the ready set is rebuilt and the next node is chosen, hand off to **Mode B**
(`/loop-run`), which loads its own reference block for execution.

Follow the skill's Mode C resume algorithm exactly.
