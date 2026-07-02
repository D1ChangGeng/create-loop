---
description: Show a create-loop status snapshot — goal, current node, ready set, blockers, next action (read-only).
agent: build
---

Use the create-loop skill to produce a read-only **status snapshot** for a loop.

Optional loop id or directory: $ARGUMENTS

Report, reading only from the durable state (do NOT execute or mutate anything):

1. Top-level `goal` and current phase.
2. The current active node (from `.agents/loops/INDEX.yaml` `current_active_node`)
   and the latest checkpoint (selected by highest `checkpoint_seq`).
3. The ready set, and blocked nodes with their reasons.
4. Pending approvals (any node in `waiting_user` with an open decision).
5. The next recommended action.

Source the snapshot from the loop's `checkpoint.yaml`, the loops `INDEX.yaml`, and
`evidence.ledger.yaml`. If no loop exists yet, say so and suggest `/loop-new`.
