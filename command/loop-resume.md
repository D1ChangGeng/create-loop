Use the create-loop skill and run **Mode C (Resume from a blank session)**.

Optional loop directory: $ARGUMENTS

This requires no prior chat memory — the checkpoint and event log are the only
sources of truth.

1. Locate the loop directory ($ARGUMENTS, or discover it via
   `.agents/loops/INDEX.yaml`).
2. Read the latest `checkpoint.yaml`.
3. Reconcile from the `event_log` (primary source of truth) — replay events over
   the checkpoint.
4. Honor claim/lease: skip nodes that are live or delegated.
5. Rebuild the ready set, pick the next node, and continue (hand off to Mode B).

Follow the skill's Mode C resume algorithm exactly.
