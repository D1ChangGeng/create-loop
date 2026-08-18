# Design Brief: Executable Technical Design for a Node

*Diataxis type: **how-to**. This is the artifact the runner writes when a node
or sub-loop is about to ship a non-trivial implementation. It records the
design in a form that another agent (or a fresh session) can read, critique,
and execute against — without re-discovering the reasoning. The full policy
this template implements is
[`references/execution_intelligence_policy.md` §3.9](../references/execution_intelligence_policy.md)
("Produce an executable design before building"). The template is the
**artifact**; §3.9 is the **procedure** that fills it.*

---

## 0. Why this artifact exists (read first)

A design brief is what turns "we are going to build X" into a commitment that
the runner can actually execute against and that a fresh session can pick up
without re-deriving the same reasoning. It is the *file* the next agent opens
when they ask "what was this design and why is it shaped this way?".

It is **not** documentation for the user. It is a working artifact for the
loop. It sits next to the plan, the checkpoint, and the decision log; it is
referenced by the node's `produces` list and read by whoever executes the
implementation.

> **The hard split.** This template enforces the **structure** of a design
> brief. It does **not** certify that the design is good, complete, correct,
> or that it will work. That is the runner's judgement
> ([`SKILL.md` §17](../SKILL.md)) — a validator can read that the brief
> exists and that the three required sections are filled in; only the runner
> can read that the interfaces are *clean*, the data flow is *sound*, and the
> assumptions are *actually falsifiable*. A filled-in brief is a prerequisite
> for design review, not the review itself. Nothing here changes the
> validator/runner division of labor.

---

## 1. When to write a design brief

Write a fresh design brief whenever any of the following holds:

- A node is about to produce non-trivial code, configuration, or schema
  changes (`mapper`, `milestone`, or `gate` with `risk: med|high`).
- A discovery or architecture subgraph is being collapsed into a concrete
  plan and the runner must record what was decided and why.
- A `replan` event is in progress and the new design must be committed to
  before the old one is retired.
- A `human_approval` gate is requested and the human needs more than a one-line
  rationale to sign off.
- A child subloop is being promoted to a sub-loop and the parent needs the
  child's design before integrating it.

Do **not** write a design brief for trivial work (a single-file edit, a
one-line bug fix, a comment clean-up). The brief is overhead proportional to
the design's complexity; for trivial work the effort is pure waste.

---

## 2. Header

The header binds the brief to the owning loop and node.

- **loop_id / plan_id / plan_version** — verbatim from the owning plan.
- **owning_node_id** — the node whose `produces` list names this brief.
- **success_criteria_ids** — which `success_criteria[].id` values (e.g. `sc-2`,
  `sc-5`) this design serves. The brief must trace to *at least one*; if it
  traces to none, the design is not actually serving the goal and the brief
  should be rejected at draft time.
- **status** — `draft | reviewed | approved | superseded`. A brief is
  `approved` only when a runner (or human) has judged its three sections
  pass muster; `draft` until then.
- **written_at / written_by** — ISO-8601 timestamp and the agent / session id.
- **supersedes** — path to the previous brief this one replaces, if any.

> **Citation rule.** Every design element (interface, data-flow edge,
> assumption) **SHOULD** cite at least one `success_criteria_id`. The citation
> is the seam between the design and the goal contract: a design element
> with no traceable citation is either redundant (it serves something not in
> the contract) or unnecessary (it serves nothing). The runner should drop
> untraced elements on review, not bless them.

---

## 3. The three required sections

A complete design brief covers **D1 Interfaces**, **D2 Data Flow**, and
**D3 Falsifiable Assumptions**. All three must be filled in for the brief to
be anything more than a stub. Truncate only the optional `Optional sections`
at the end of this template; never any of D1–D3.

### D1. Interfaces at clean seams

For every module, function, class, or external boundary in the design,
record:

- **what it exposes** — the minimal interface the caller needs. Method
  signatures, type signatures, the entry points through which the rest of
  the system touches this module. Be concrete: parameter names, return types,
  exception modes, ordering constraints.
- **what it hides** — the implementation details the interface deliberately
  does NOT expose. Internal state, helper functions, the choice of data
  structure, the specific algorithm. A deep module hides a lot of behaviour
  behind a small interface; a shallow module exposes its guts.
- **the seam** — the location of the interface between owner and caller.
  Files, classes, packages, network boundaries, IPC channels. The seam is
  where the design draws the line; the interface is what crosses that line.
- **success_criteria_id** — which goal contract this interface serves.

> **Deep-module vocabulary.** A *deep module* has a small interface over a
> substantial implementation — high leverage for callers. A *shallow module*
> has a large interface over a thin implementation — pass-through. When you
> list an interface, ask: "If I delete this module, does the complexity
> disappear from the system, or does it just relocate?" If it disappears,
> the module was a pass-through and the seam should be redrawn. If it
> reappears across N callers, the seam is earning its keep.

Repeat the above for each module. The list is exhaustive of the modules the
design introduces, not a sample.

### D2. Data flow

For every piece of state the design owns, record:

- **what it is** — the data, named precisely (e.g. `parsed_event`,
  `user_session`, `pending_approval`).
- **where it is born** — which module produces it, at which point in the
  flow.
- **where it is transformed** — every step that mutates it, named by module
  and method. Each transformation is an interface in D1 by reference.
- **where it ends** — who consumes it last, or where it is persisted /
  archived. If nothing consumes it, the data is dead weight and the design
  should probably drop it.
- **who owns it** — the single module whose correctness is broken if the
  data is corrupted. Two owners of one piece of state is a design smell.
- **success_criteria_id** — which goal contract this data flow serves.

Draw the flow as a sequence of arrows (`produced by A → transformed by B →
consumed by C`) or as a small graph (Mermaid if you want it rendered). The
form is not the point; the *exhaustiveness* is. Every state mutation must
appear somewhere in D2 or be hidden in a module whose interface surfaces its
effect.

> **State ownership is the design's hard spine.** If two modules can both
> mutate the same piece of state, the design has not actually drawn a seam
> there — it has drawn a shared global. Either one of them becomes the owner
> and the other gets a read-only view, or the data is split into two
> independently-owned pieces.

### D3. Falsifiable assumptions

For every belief the design depends on — including the implicit ones — record:

- **the assumption** — stated concretely, not as a wish. "Users have stable
  network connections" is not an assumption; "the client may issue up to
  `N` requests per minute and the server must respond within
  `T` milliseconds for the 99th percentile" is.
- **why it could be wrong** — the failure mode. "If the user is on a flaky
  cellular link, this many-retries budget will still drop requests."
- **how it will be verified** — the *concrete* check. A test, a measurement,
  an `evidence.ledger` entry, a manual probe. The verification must be
  possible to perform before the design is shipped; if it can only be done
  after, the assumption is not yet admissible.
- **trigger if wrong** — what the runner does when the verification fails.
  A local patch, a replan, a node redesign, an escalate to user. An
  assumption with no trigger is ungrounded optimism.
- **success_criteria_id** — which goal contract this assumption serves.

> **The admission rule.** An assumption with no verification method is **not
> admissible**. Drop it, rewrite it so it can be verified, or escalate the
> underlying uncertainty to a parent node where it can be resolved. A
> design brief is not a place to hide risks; it is a place to surface them
> with a concrete plan.

---

## 4. Optional sections

Fill these in only when the design has them; truncate freely. None of them
replace D1–D3.

### D4. Risks and rejected alternatives

Major risks the design is taking on, and the alternatives that were
considered and rejected (with the reason). This is the ADR-shaped
counterweight to the design's "happiest path" presentation in D1–D3. One row
per alternative, with the reason a fresh reviewer would accept.

### D5. Evidence plan

How the design will be *verified*. Maps D3's assumptions to the gate kinds
from [`references/loop_plan_spec.md` §4.2](../references/loop_plan_spec.md#42-gate-kinds)
that will catch them. For each gate, name the gate kind, the threshold (if
any), and the rubric / fixture path. The evidence plan is the bridge between
the design brief and the plan's `gate` field.

### D6. Migration / rollback

If the design changes behavior the running system already has, this is how
the change lands and how it reverses. Backwards-incompatible changes
(`success_criteria_id` of the form `sc-<existing>`) must call this out.

---

## 5. Worked skeleton (fill in the values)

```markdown
# Design Brief: {short title}

## Header

- loop_id:           {L<seq>-<slug>}
- plan_id / ver:     {plan_id} v{plan_version}
- owning_node_id:    {node_id}
- success_criteria:  [sc-2, sc-5]
- status:            {draft | reviewed | approved | superseded}
- written_at:        {ISO-8601}
- written_by:        {agent / session id}
- supersedes:        {path or null}

## D1. Interfaces at clean seams

### {module-1 name}
- exposes:  {the minimal interface callers need}
- hides:    {the implementation deliberately not exposed}
- seam:     {where the interface lives}
- serves:   sc-2

### {module-2 name}
- exposes:  {…}
- hides:    {…}
- seam:     {…}
- serves:   sc-5

## D2. Data flow

{state-1} — born in {module-1}, transformed by {module-2}, consumed by {module-3},
owned by {module-1}.  serves: sc-2.

{state-2} — born in {module-2}, transformed by {module-3}, persisted to {path},
owned by {module-3}.  serves: sc-5.

## D3. Falsifiable assumptions

- A.{n}. *Assumption.* {concrete claim}.
  - *Wrong if* {failure mode}.
  - *Verified by* {test / measurement / probe}.
  - *Trigger if wrong* {local_patch | replan | redesign | escalate}.
  - *Serves* sc-2.

- A.{n+1}. *Assumption.* {…}
  - *Wrong if* {…}
  - *Verified by* {…}
  - *Trigger if wrong* {…}
  - *Serves* sc-5.

## D4. Risks and rejected alternatives

| alternative | reason rejected |
|---|---|
| {alternative-A} | {what it traded off} |

## D5. Evidence plan

| assumption | gate kind | threshold | rubric / fixture |
|---|---|---|---|
| A.1 | {gate kind from loop_plan_spec.md §4.2} | {0..1 or null} | {path} |

## D6. Migration / rollback

{how the change lands and how it reverses}
```

---

## 6. Pointers

The brief is committed next to the owning node's artifacts. A reader opens
the following alongside it:

```
- loop.plan:        {path to loop.plan.yaml}
- task_profile:     {path to task_profile.yaml}
- decision_log:     {path to decision.log.md}
- checkpoint:       {path to checkpoint.yaml}
- evidence_ledger:  {path to evidence.ledger.yaml}
- node.contract:    {path to node.contract.yaml}
```

The brief is **referenced** from the owning node's `produces` list as an
artifact path. The node's `gate` is what authorizes the brief's status to
move from `draft` to `approved` — not the act of filling it in.
