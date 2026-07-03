---
description: Show a create-loop status snapshot — goal, current node, ready set, blockers, next action (read-only).
argument-hint: "[loop-id]"
---

Use the create-loop skill to produce a read-only **status snapshot** for a loop.

Optional loop id or directory: $ARGUMENTS

**This command is strictly READ-ONLY. You MUST NOT mutate any file, MUST NOT run
validators or the integrity gate, MUST NOT execute, claim, or advance any node.**
Read only from the durable state and report.

Source the snapshot ONLY from these files (read, never write):

- `.agents/loops/INDEX.yaml` (the loops index, per `skills/create-loop/templates/loops.index.yaml`) — for `current_active_node`. For a child loop, read its own `_loops/INDEX.yaml`.
- the loop's `checkpoint.yaml` — select the latest by highest `checkpoint_seq`.
- the loop's `evidence.ledger.yaml`.

For interpreting node statuses, you may consult
`skills/create-loop/references/state_model.md` (§"Node status enum") for meaning
only — do not copy the enum into your output.

Report:

1. Top-level `goal` and current phase.
2. The current active node (`current_active_node`) and the latest checkpoint
   (highest `checkpoint_seq`).
3. The ready set, and blocked nodes with their reasons.
4. Pending approvals (any node in `waiting_user` with an open decision).
5. The next recommended action.

If no loop exists yet, say so and suggest `/loop-new`.
