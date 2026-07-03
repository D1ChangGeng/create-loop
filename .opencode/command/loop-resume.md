---
description: Resume a create-loop from its checkpoint in a fresh session after interruption (Mode C).
agent: build
---

Use the create-loop skill and run **Mode C (Resume from a blank session)**.

Optional loop directory: $ARGUMENTS

This requires no prior chat memory — the checkpoint and event log are the only
sources of truth.

**Load these skill files BEFORE you advance — they are the source of truth. Read them; do not restate their contents from memory, and do not paste their vocabulary into your output.**

- `skills/create-loop/references/state_model.md` §"Resume from a blank session" — the authoritative resume algorithm and the per-node claim/lease disambiguation.
- `skills/create-loop/references/recovery_protocol.md` §2 (the resume-from-blank-session algorithm, step by step) and §6 (Consistency repair, incl. §6.0 State Authority Order — the event log wins when files disagree).
- `skills/create-loop/templates/claim.yaml` — the claim/lease schema that tells you whether a `running` node is live, crashed, or delegated.

Run the integrity gate FIRST, before advancing anything —
`python3 skills/create-loop/scripts/check_loop_integrity.py <loop-dir>`. A nonzero
exit means enter a recovery subgraph (recovery_protocol.md §6), NOT normal work.

Then resume:

1. Locate the loop directory ($ARGUMENTS, or discover it via
   `.agents/loops/INDEX.yaml`).
2. Read the latest `checkpoint.yaml`.
3. Reconcile from the `event_log` (primary source of truth) — replay events over
   the checkpoint.
4. Honor claim/lease: skip nodes that are live or delegated.
5. Rebuild the ready set, pick the next node, and continue.

Once the ready set is rebuilt and the next node is chosen, hand off to **Mode B**
(`/loop-run`), which loads its own reference block for execution.

Follow the skill's Mode C resume algorithm exactly.
