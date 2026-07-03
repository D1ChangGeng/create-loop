---
description: Create a new create-loop control plan from a fuzzy goal — runs the Charter interview and emits loop.plan v0 (Mode A).
argument-hint: "<goal text>"
---

Use the create-loop skill and run **Mode A (Create a loop)**.

The user's goal is: $ARGUMENTS

**Load these skill files BEFORE you act — they are the source of truth. Read them; do not restate their contents from memory, and do not paste their vocabulary into your output.**

- `skills/create-loop/SKILL.md` §3 (Autonomy-First Control Principle) and §9 (Mode A steps) — the mode contract you are executing.
- `skills/create-loop/references/layered_execution_chain.md` — the Top-level Loop layer (§2.1): `loop.plan v0` is the **control skeleton only**. It must avoid BOTH failure modes — **over-expansion** (exhausting execution detail up front → a rigid, unadaptable plan) and **under-control** (a bare goal with no gates, failure criteria, recovery, or human boundaries). Build the invariant governance layer; do not pre-plan the runtime work.
- `skills/create-loop/references/recursive_planning_immersive_execution.md` — the global / planning view you author v0 in: identify the design-invariant gates, real `produces/requires` dependencies, what is parallel vs serial, and the risk / permission / human-decision boundaries to control up front.
- `skills/create-loop/templates/interview_brief.md` — the Charter interview protocol. Obey §2 (adaptive rules), §3 (**What the interview MUST NOT ask** — never ask vendors/stack/files/tests/compliance up front; route them to `research_questions` with an `owner_node`), and §5 (**Stop condition** — do not stop the interview until every bullet holds).
- `skills/create-loop/templates/task_profile.yaml` — the control-profile artifact you populate as the interview's audit trail.
- `skills/create-loop/references/loop_plan_spec.md` §1 (top-level `loop.plan` fields) and §2 (the `node` object — every node carries all its required fields; use the locked enums exactly as defined there).
- `skills/create-loop/references/recursive_loops.md` — the per-loop directory layout you must materialise.
- `skills/create-loop/references/evidence_gates.md` §5 (Choosing a gate kind) — pick each node's gate from the defined set; do not invent gates.

Then run Mode A in order:

1. Run the Loop Startup (Charter) interview to build the control profile
   (`task_profile.yaml`) — ask ONLY design-time invariants (interview_brief.md §3),
   and stop only when the §5 stop condition holds.
2. Emit `loop.plan v0` — design-invariant governance nodes only (no vendor
   names, file paths, or test specs at this level), every node carrying all fields
   from loop_plan_spec.md §2. This is the Top-level Loop layer (skeleton only):
   do NOT decompose runtime work here — that is over-planning. Leave concrete
   steps to be grown later as subgraphs/subloops per the layered execution chain.
3. Materialise the loop directory `.agents/loops/L<seq>-<slug>/`: `loop.meta.yaml`,
   the initial `checkpoint.yaml`, and the `evidence.ledger.yaml`; register it in
   `.agents/loops/INDEX.yaml`.

Validate before declaring v0 live (do NOT skip):

- `python3 skills/create-loop/scripts/validate_loop_plan.py <plan>` — the plan MUST pass before it goes live.
- `python3 skills/create-loop/scripts/validate_checkpoint.py <checkpoint>` — after writing the initial checkpoint.

Follow the skill's Mode A steps and validators exactly. Do not improvise fields.
