---
description: Advance an existing create-loop by executing the next ready node(s) (Mode B).
agent: build
---

Use the create-loop skill and run **Mode B (Run / advance a loop)**.

Optional target node or loop: $ARGUMENTS

1. Read the latest `checkpoint.yaml` (plus node contract and evidence ledger).
2. Pick a ready node — respect the readiness rule and the per-node claim/lease
   (skip nodes that are live or delegated).
3. Execute the node.
4. Evaluate its evidence gate.
5. Append evidence to `evidence.ledger.yaml` and the `event_log`.
6. Write the new `checkpoint.yaml` LAST (durable snapshot, never in-memory).

Follow the skill's Mode B loop exactly. Never improvise plan changes — route
scope/plan changes through the skill's replan path.
