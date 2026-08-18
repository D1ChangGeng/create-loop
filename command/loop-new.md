Use the create-loop skill to admit and create a Loop.

Arguments: $ARGUMENTS

Resolve `CREATE_LOOP_SKILL_ROOT` to the directory containing the create-loop
`SKILL.md` loaded for this command. Do not assume a repository-relative path:
an installed copy may live under `.agents/skills/create-loop/` or
`.claude/skills/create-loop/`. Treat every skill-relative path below as relative
to that root, and fail clearly if no single root can be identified.

Parse an optional `--protocol v1|v2`. During the transition, v1 is the default;
v2 is used only when explicitly selected. Reject conflicting or repeated
selectors. The remaining arguments are the user's goal.

Read `SKILL.md` §"Protocol selection" before acting. Apply the admission rule
first: if the task is short, low risk, single-session, and needs no durable
recovery or dependency control, do not create `.agents/loops` files. Explain
briefly that direct execution is cheaper. Every created Loop must record one
auditable admission reason.

### v2 opt-in path

When `--protocol v2` is present, load these files completely before writing:

- `references/protocol_v2.md`;
- `schemas/goal.schema.json` and `schemas/plan.schema.json`;
- `templates/goal.json`, `templates/plan-v1.json`, and, for a persistent or
  governed Loop, `templates/journal.jsonl` and `templates/resume.json`.

Choose `lightweight`, `persistent`, or `governed` from the protocol's admission
boundaries without a score. Enable only modules triggered by actual risk.
Allocate the next `L<seq>-<slug>` under `.agents/loops/`, then atomically write
immutable `goal.json` and `plans/plan-v1.json`; hash the exact bytes written.
For persistent/governed mode, append the initial `plan_activated` record to
`journal.jsonl` and generate `resume.json` with `render_resume.py`. Lightweight
mode must not create journal or resume files.

Before declaring the Loop usable, run:

- `python "<CREATE_LOOP_SKILL_ROOT>/scripts/validate_loop_dir.py" "<loop-dir>"`;
- for persistent/governed mode,
  `python "<CREATE_LOOP_SKILL_ROOT>/scripts/render_resume.py" "<loop-dir>" --check`.

Do not create any v1 YAML runtime artifact on this path.

### v1 compatibility path

For the default v1 path, load these skill files before acting — they are the
source of truth. Read them; do not restate them from memory:

- `SKILL.md` §3 (Autonomy-First Control Principle) and §9 (Mode A steps) — the mode contract you are executing.
- `references/layered_execution_chain.md` — the Top-level Loop layer (§2.1): `loop.plan v0` is the **control skeleton only**. It must avoid BOTH failure modes — **over-expansion** (exhausting execution detail up front → a rigid, unadaptable plan) and **under-control** (a bare goal with no gates, failure criteria, recovery, or human boundaries). Build the invariant governance layer; do not pre-plan the runtime work.
- `references/recursive_planning_immersive_execution.md` — the global / planning view you author v0 in: identify the design-invariant gates, real `produces/requires` dependencies, what is parallel vs serial, and the risk / permission / human-decision boundaries to control up front.
- `templates/interview_brief.md` — the Charter interview protocol. Obey §2 (adaptive rules), §3 (**What the interview MUST NOT ask** — never ask vendors/stack/files/tests/compliance up front; route them to `research_questions` with an `owner_node`), and §5 (**Stop condition** — do not stop the interview until every bullet holds).
- `templates/task_profile.yaml` — the control-profile artifact you populate as the interview's audit trail.
- `references/loop_plan_spec.md` §1 (top-level `loop.plan` fields) and §2 (the `node` object — every node carries all its required fields; use the locked enums exactly as defined there).
- `references/recursive_loops.md` — the per-loop directory layout you must materialise.
- `references/evidence_gates.md` §5 (Choosing a gate kind) — pick each node's gate from the defined set; do not invent gates.

Then run v1 Mode A in order:

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

- `python3 "<CREATE_LOOP_SKILL_ROOT>/scripts/validate_loop_plan.py" "<plan>"` — the plan MUST pass before it goes live.
- `python3 "<CREATE_LOOP_SKILL_ROOT>/scripts/validate_checkpoint.py" "<checkpoint>" --plan "<plan>"` — after writing the initial checkpoint; the plan linkage MUST also pass.

Follow the skill's Mode A steps and validators exactly. Do not improvise fields.
