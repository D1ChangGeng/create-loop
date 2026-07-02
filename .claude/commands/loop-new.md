---
description: Create a new create-loop control plan from a fuzzy goal — runs the Charter interview and emits loop.plan v0 (Mode A).
argument-hint: "<goal text>"
---

Use the create-loop skill and run **Mode A (Create a loop)**.

The user's goal is: $ARGUMENTS

1. Run the Loop Startup (Charter) interview to build the control profile
   (`task_profile.yaml`) — ask ONLY design-time invariants.
2. Emit `loop.plan v0` — design-invariant governance nodes only (no vendor
   names, file paths, or test specs at this level).
3. Materialise the loop directory `.agents/loops/L<seq>-<slug>/`: `loop.meta.yaml`,
   the initial `checkpoint.yaml`, and the `evidence.ledger.yaml`; register it in
   `.agents/loops/INDEX.yaml`.

Follow the skill's Mode A steps and validators exactly. Do not improvise fields.
