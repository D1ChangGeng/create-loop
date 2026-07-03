# Live Loop Semantics: Evidence-Driven Completeness Growth

> Live Loop is not scope creep. It is **evidence-driven completeness growth**.

> Stable Goal + Invariant Control Graph + Live Runtime Subgraphs + Evidence Gates.

*Diataxis type: **reference + explanation**. This document defines the
runtime natural-growth mechanism of a `loop.plan`. It explains **why** a
running plan is allowed to extend downward in response to evidence it
discovers while executing, and **how** that extension stays bounded,
auditable, and aligned with the design-time invariants already locked in
[`concepts.md`](./concepts.md), [`loop_plan_spec.md`](./loop_plan_spec.md),
[`state_model.md`](./state_model.md), and [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode).
It does not redefine fields, statuses, gate kinds, or ladder rungs. Those
are owned by their canonical documents. This doc only specifies *when*
and *how* Live Loop growth may use them.*

---

## 1. Definition

During execution, the loop continuously reads environment feedback:
artifacts, verification results, failures, defect records, dependency
changes, and any new evidence produced by the work that has already
completed. When that evidence reveals an **omission, contradiction,
redundancy, quality defect, or insufficient implementation path** in
the original plan, the loop does NOT mechanically continue the old plan
and does NOT immediately ask the user to redesign it. It spawns an
**exploration, diagnostic, repair, or completion subgraph** and resolves
the gap autonomously, in keeping with [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)
Autonomy-First and the bounded escalation ladder in
[`exception_handling.md` §3](./exception_handling.md#3-the-bounded-escalation-ladder).

This mechanism is called **Live Loop**.

Evidence-driven growth defaults into a lightweight **`subgraph`** first — the inline `subgraph` mechanism hosted by the owning node
([`subgraph_subloop_policy.md` §2](./subgraph_subloop_policy.md#2-what-a-subgraph-is)). If the gap's governance complexity crosses the **Promotion Gate** — for example, cross-session persistence, independent checkpoint or recovery, complex evidence, many artifacts, parallel isolation, elevated risk, multi-node impact, may recurse, or needs an independent closeout — the subgraph is **promoted** to a directory-materialized **`subloop`**, the **child loop** of [`recursive_loops.md`](./recursive_loops.md). The full gate is defined in [`subgraph_subloop_policy.md` §5](./subgraph_subloop_policy.md#5-promotion-gate-subgraph--subloop); Live Loop enters as a subgraph first and promotes only when that gate closes behind the inline choice.

> The top-level control skeleton is stable, but the execution path is alive.

A `loop.plan` is NOT a frozen, one-shot checklist. It is a **control
system** built from three layered concerns:

| concern | character |
|---------|-----------|
| top-level goal | stable across the whole run |
| governance skeleton (`design_invariant: true` top-level nodes) | stable across the whole run |
| execution path (subgraphs inside `mapper` / `allow_subgraph: true` nodes) | alive, grown from evidence as the run progresses |

Growth is NOT adding new requirements (NOT scope creep). Growth is
absorbing evidence, exposing defects or omissions, and converting work
that is **necessary for the original goal to truly hold** into
controlled subgraphs. The goal stays put. The skeleton stays put. The
execution path lives.

---

## 2. Core principle

> **The top-level goal stays stable; the execution graph grows naturally from evidence.**

Concretely:

- Live Loop is neither blind requirement injection nor unbounded task
  expansion.
- Only **naturally-exposed, goal-necessary** work enters the controlled
  plan-evolution mechanism.
- Every admitted growth event traces a causal link back to the
  original `goal` / `true_intent` and the relevant `design_invariant`
  skeleton node that owns it.
- The `loop.plan` is **true at authoring time** and **stable across the
  whole run**; it never needs rewriting, only *extending downward* via
  subgraphs (the rule recorded in
  [`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes)).

The principle is the runtime counterpart to the design-time rule that
"the top-level graph holds only design-time-invariant nodes": just as
the planner refused to enumerate future leaves at v0 (it could not
honestly know them), the runner refuses to silently freeze the leaves
that earlier planning under-specified, and it grows them under the same
control contract.

---

## 3. Triggers: what may spawn a Live Loop subgraph

A Live Loop subgraph may be admitted when the runner observes any of
the following signals during execution. These are the categories of
"completeness gaps" that evidence can expose; they are categorisations
of a discovery signal, not free-form prose, and a given gap is matched
against the list below by its closest pattern.

1. **A discovered defect that does not block basic operation but
   significantly harms final effect, quality, reliability, or UX.**
   The product runs, but a feature or behavior is materially below the
   `success_criteria` or would damage the user's stated outcome if
   shipped as-is.
2. **A logic omission, hole, contradiction, redundancy, or wrong
   assumption in the original requirements analysis, architecture,
   feasibility study, or task decomposition**, found while a node is
   running. The plan's shape conflicts with reality; continuing the old
   plan would compound the error.
3. **Extra work not in the initial plan but clearly NECESSARY for the
   final goal's completeness, verifiability, maintainability, or
   delivery quality.** A path, test, integration step, or cleanup that
   the original plan under-specified, and whose absence would render
   the deliverable non-functional in a way the user would object to.
4. **A verification or evidence gate reporting the current artifact is
   formally "done" but cannot adequately satisfy the
   `success_criteria`.** The `verdict` is `pass` on the contract at
   hand, but the underlying claim is weaker than the goal requires;
   broadening the verification surface is part of completing the work.
5. **State, evidence, or dependency changes that would make continuing
   the old plan produce low-quality results, rework, or wrong
   direction.** Upstream artifacts change, dependencies disappear, an
   `assumption` resolves to false, or a contract renegotiates and the
   old path is no longer the right path.
6. **A node that fails its evidence gate where the cause is NOT a
   simple execution error but needs re-analysis, re-decomposition,
   completion, or upstream design repair.** This is the `local_patch`
   / `replan` ladder rung reached through Live Loop rather than through
   a mechanical exception; see
   [`exception_handling.md` §3](./exception_handling.md#3-the-bounded-escalation-ladder).

Categories 1, 2, 3 are "evidence of a completeness gap." Categories 4,
5, 6 are "evidence the running contract is insufficient." All six feed
the same admission gate (§6 below) and the same controlled subgraph
mechanism (§8 below).

---

## 4. Default response flow

The Live Loop flow is **autonomy-first**, NOT ask-user-first. It runs
inside the existing governance, gate, and persistent-state machinery.
The orchestrator follows this sequence:

```
live growth detected (§3 trigger)
  -> judge whether the candidate is a necessary growth item (§6 admission criteria)
  -> enter as a lightweight subgraph inside the owning node — the default tier
  -> gather evidence; assess impact / cost / risk / necessity
  -> if governance complexity crosses the Promotion Gate
       (any canonical criterion in
        [recursive_loops.md §8](./recursive_loops.md#8-sub-loop-admission-gate)
        — that section is the single source of truth for admission and
        promotion criteria; the Promotion Gate is the same rule observed at
        this live-growth tier)
     -> promote_to_subloop — materialize a directory-materialized child loop
  -> otherwise, complete the subgraph inside the parent
  -> update loop.plan / evidence.ledger / decision.log
     (+ child_loops[] for any promoted subloop)
  -> continue advancing the original goal
```

Three consequences follow:

1. **Autonomy is the default rung.** The first three rungs of the
   `local_retry` → `local_patch` → `replan` → `escalate` ladder
   (`exception_handling.md` §3) are the autonomous rungs. Live Loop
   uses them by default. The user is consulted only when the gap's
   resolution would cross one of the autonomy boundaries listed in
   [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)
   and detailed in [`human_approval.md` §6](./human_approval.md#6-what-must-be-user-approved-by-default).
2. **Existing artifacts are the medium of admission.** Admission writes
   to `loop.plan` (the `subgraph` field of the owning node, plus its
   `parent_ref`) for the inline-subgraph path; when a subgraph is
   promoted to a subloop, the same admission writes the parent node's
   `child_loops[]` reference to the new directory-materialized
   **child loop** under `_loops/`
   ([`recursive_loops.md` §5–§10](./recursive_loops.md)). Either path
   records the new `evidence.ledger` entries and appends a
   `decision.log` line. No hidden in-memory growth; nothing sits
   outside the durable contract.
3. **Advancing the original goal is the success condition.** Live Loop
   does not pause the loop to grow. It grows in order to keep the loop
   moving toward the original goal.

---

## 5. Boundaries: what Live Loop MUST NOT do

Live Loop is a **bounded natural-growth mechanism**, not an
unconstrained expansion right. The following prohibitions are absolute;
each one corresponds to a structural rule already locked in the
canonical documents, so a violation is detectable from artifacts on
disk.

- **MUST NOT change the top-level `goal` or `true_intent` without
  confirmation.** Per [`human_approval.md` §6](./human_approval.md#6-what-must-be-user-approved-by-default)
  and [`exception_handling.md` §2.12](./exception_handling.md#212-goal_changed),
  a `goal_changed` exception MUST NOT be silently accepted. A fresh
  Loop is required when the goal itself moves.
- **MUST NOT dress up weakly-related ideas as necessary work.** What
  "looks useful" is not a trigger (§3 categories 1 through 6 name the only
  legitimate triggers). Work that fails the admission gate in §6 stays
  out of the graph.
- **MUST NOT let local optimisation inflate the task without bound.**
  Growth is bounded by `termination.max_iterations`,
  `termination.max_cost_units`, and `termination.max_wall_clock_hours`
  ([`loop_plan_spec.md` §1.2](./loop_plan_spec.md#12-termination-object)).
- **MUST NOT bypass budget, permission, risk, or external-side-effect
  boundaries.** Anything on the
  [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)
  boundary list still requires the user, even if a Live Loop subgraph
  could in principle handle it.
- **MUST NOT promote unverified guesses directly into formal tasks.**
  Every admission is gated by evidence (§8). A `subgraph` whose gate
  has `verdict != pass` cannot become part of the plan.
- **MUST NOT let a local subgraph break the top-level governance
  structure.** A Live Loop subgraph lives inside the `subgraph` field
  of its parent node, not at the top level (the
  [`design_invariant`](./loop_plan_spec.md#5-design-time-invariant-vs-runtime-discovered)
  rule). It MUST carry `parent_ref`.
- **MUST NOT lower the original `success_criteria` just because
  execution got hard.** When a goal looks unreachable through honest
  growth, the loop either `escalate`s or surfaces a `goal_changed`
  proposal to the user; it never quietly relaxes the bar.

The full escalation boundary list is not restated here. See
[`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)
and [`human_approval.md` §6](./human_approval.md#6-what-must-be-user-approved-by-default)
for the authoritative list; Live Loop inherits it without modification.

---

## 6. Admission criteria: when a candidate enters the graph

A candidate Live Loop subgraph is admitted only if **at least one** of
the following holds. Each criterion expresses a specific way the
original goal would fail to hold if the candidate were left out.

1. Not doing it makes some evidence gate impossible to pass (the gate
   cannot be written without the candidate; closing the gap is on the
   critical path of verification).
2. Not doing it clearly lowers the final deliverable's quality below
   what the `success_criteria` would recognise as complete.
3. Not doing it leaves a known bug, logic hole, design contradiction,
   or wrong assumption in the deliverable.
4. Not doing it causes downstream rework, duplication, or wrong
   direction in the rest of the execution graph.
5. Not doing it leaves the result "runnable" but not complete,
   reliable, verifiable, or maintainable.
6. The work has a clear **causal link** to the original goal, not
   merely "looks useful."

> The essence: Live Loop is NOT scope expansion. Live Loop is
> **goal-integrity maintenance**.

Criteria 1 and 6 are the structural ones: they identify the candidate
as work the goal's own definition requires. Criteria 2 through 5 are
the experiential ones: they identify the candidate as work whose
absence would break the user's eventual experience of the deliverable.
At least one must hold; in practice a well-formed Live Loop subgraph
satisfies two or three at once.

When none holds, the candidate stays out of the plan. If the runner
suspects it should be in but cannot make the link explicit, it records
an `open_assumption` and (if the gap is irreducible and crosses a user
boundary) routes to an `approval` node, not to a Live Loop subgraph.
This is the structural distinction between Live Loop and silent
"polishing": Live Loop admits only what the goal forces.

---

## 7. Three classes of change

Every change observed during a run falls into exactly one of three
classes. Each class has its own handling rule, anchored to the
canonical documents.

| change class | handling |
|--------------|----------|
| **top-level goal change** | MUST request user confirmation; create a new Loop if needed. Goal sovereignty belongs to the user. ([`human_approval.md` §6](./human_approval.md#6-what-must-be-user-approved-by-default), [`exception_handling.md` §2.12](./exception_handling.md#212-goal_changed)) |
| **top-level governance-skeleton change** | Allowed ONLY when a NEW design-time invariant is discovered (a node that, in retrospect, was always mandatory for this task class but the planner missed). MUST be performed as a `replan` on the affected fragment with a new `plan_version`, per the immutable-plan-per-version rule ([`loop_plan_spec.md` §1](./loop_plan_spec.md#1-top-level-loopplan-fields), [`loop_plan_spec.md` §6.2](./loop_plan_spec.md#62-on_failure--the-escalation-ladder)). MUST record the rationale (`decision.log`). |
| **execution-path natural growth** | The system may autonomously create subgraphs and admit them after verification. This is Live Loop. Handled entirely through the parent's `subgraph` field with `parent_ref`, per [`loop_plan_spec.md` §7](./loop_plan_spec.md#7-subgraph-recursion) and [`concepts.md` §4](./concepts.md#4-why-recursion-isomorphic-subgraphs). No `replan` is required at the top level. |

The three classes are mutually exclusive but collectively exhaustive
of what a run can do to its own plan. They differ in **who holds the
authority**:

| class | authority held by | mechanism | cost |
|-------|-------------------|-----------|------|
| top-level goal change | the user | `goal_changed` exception + new Loop | confirmation, new `plan_version` |
| top-level governance-skeleton change | the runner, under the structural test | `replan` of the affected fragment | new fragment `plan_version`, nodes `→ deprecated` |
| execution-path natural growth | the runner, under the admission gate | Live Loop subgraph inside the owning node | none beyond the parent's existing budget |

A Live Loop growth event is NEVER a `replan` at the top level. If the
runner thinks the top-level skeleton itself is wrong, the correct path
is **not** to absorb the change into a subgraph; it is to `replan`
the fragment and record the rationale. This separation is what keeps
governance auditable: the top-level skeleton stays one consistent
shape, and every "the skeleton itself was wrong" event is visible as a
discrete `plan_version` bump.

---

## 8. How growth stays controlled, auditable, and recoverable

Every Live Loop growth event is a **subgraph** admitted under the
existing structural contract. The mechanics that keep growth
controlled, auditable, and recoverable are not new mechanisms; they
are the existing artifacts, applied to Live Loop as a recognisable
case.

| property | how Live Loop satisfies it |
|----------|-----------------------------|
| **trackable** | inline path: the parent node's `subgraph` field carries the fragment, and the fragment carries `parent_ref`. promoted path: the parent node's `child_loops[]` field carries the subloop reference, and the subloop links back via `loop.meta.yaml.parent.parent_node_id` ([`loop_plan_spec.md` §7](./loop_plan_spec.md#7-subgraph-recursion), [`recursive_loops.md` §10](./recursive_loops.md#10-the-child_loops-node-field-locked-schema-decision), [`subgraph_subloop_policy.md` §12](./subgraph_subloop_policy.md#12-the-promotion-procedure)). |
| **verifiable** | every node in the admitted subgraph carries its own `gate`; the parent's `gate` still must pass for the parent to be `completed` ([`loop_plan_spec.md` §4](./loop_plan_spec.md#4-evidence-gates), [`evidence_gates.md`](./evidence_gates.md)). |
| **immutable-per-version** | the Graph Harness rule applies: the plan for a given `plan_version` is immutable. A Live Loop admission writes a new fragment under the existing `plan_version`; structural changes outside Live Loop would `replan` to a new one ([`concepts.md` §7](./concepts.md#7-why-durability-primitives), [`loop_plan_spec.md` §1](./loop_plan_spec.md#1-top-level-loopplan-fields)). |
| **recorded** | the admission appends to `evidence.ledger` ([`state_model.md` §evidence.ledger](./state_model.md#evidence-ledger)) and writes a `decision.log` line with the trigger, the criteria (§6) that were satisfied, the impact / cost / risk / necessity assessment, and the `parent_ref` of the admitted fragment. |
| **resumable** | a fresh session sees the grown graph by reading the durable artifacts (`loop.plan`, `checkpoint`, `evidence.ledger`, `event_log`) exactly as it sees the original graph. No in-memory growth is load-bearing ([`state_model.md` §resume](./state_model.md#resume-from-a-blank-session), [`concepts.md` §9](./concepts.md#9-why-it-must-resume-from-a-blank-session)). |

> Live Loop growth is **lossless under a session crash**. The next
> agent reads the same fragment through the same contract; nothing
> about the growth depended on the previous session's memory.

> **Promotion.** When a Live Loop subgraph crosses the Promotion Gate,
> it is materialized as a **`subloop`** — a directory-materialized
> **child loop** under the parent loop's `_loops/`. The promotion
> records in `decision.log.md` the originating `subgraph_id`, the
> Promotion Gate condition(s) that held, and the new child `loop_id`;
> the parent node's `child_loops[]` field carries the directory
> reference. From that point the subloop is independently recoverable
> and auditable
> ([`recursive_loops.md` §5–§8](./recursive_loops.md),
> [`subgraph_subloop_policy.md` §12](./subgraph_subloop_policy.md#12-the-promotion-procedure)).

**Worked examples** (default subgraph, promote only at the gate). An
unverifiable acceptance criterion defaults to a subgraph and promotes
to a subloop only if investigation reveals a systemic requirement
problem. A leftover bug materially harming effectiveness defaults to a
subgraph and promotes only if the fix demands architecture change,
data migration, or coordinated multi-module work. See
[`subgraph_subloop_policy.md` §10](./subgraph_subloop_policy.md#10-relationship-to-live-loop)
for both examples in full.

The `evidence.ledger` entry for an admitted subgraph follows the
standard shape ([`state_model.md` §evidence.ledger](./state_model.md#evidence-ledger)):
`entry_id`, `node_id`, `gate_kind` (one of the eight kinds in
[`loop_plan_spec.md` §4.2](./loop_plan_spec.md#42-gate-kinds)),
`verdict` (`pass`, `fail`, or `inconclusive`), `score` (or `null`),
`artifact_path`, `rationale`, `recorded`, `verifier` (`agent`,
`subagent`, `user`, `script`). The `rationale` field is where the
trigger (§3), the satisfied admission criterion (§6), and the
parent-child relationship are made explicit; this is what a reviewer
or a future session uses to reconstruct why the growth happened.

---

## 9. Relationship to the other principles

Live Loop is one component in a multi-part decomposition. The others
are documented in their own canonical references; this section
only states what each of them is responsible for and how Live Loop
composes with it.

```
design-time invariants = top-level control skeleton
Live Loop              = runtime natural-growth mechanism
Autonomy-first         = default: system explores and judges autonomously
Evidence gates         = prevent growth from becoming random requirement-adding
Human approval         = only for goal / permission / risk / responsibility boundaries
Three-tier model      = action (leaf) / subgraph (lightweight, default) / subloop (materialized child loop); Live Loop promotes subgraph → subloop at the Promotion Gate
Recursive planning ⇄ immersive execution = the rhythm that switches between whole-graph planning and per-node execution, descends into a subgraph/subloop on local complexity, and writes results back to the parent
```

| component | owns | reference |
|-----------|------|-----------|
| design-time invariants | what may live at the top level of a plan | [`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes), [`loop_plan_spec.md` §5](./loop_plan_spec.md#5-design-time-invariant-vs-runtime-discovered) |
| Live Loop | how the top level extends downward under evidence | this document |
| Autonomy-first | how decisions are routed by default | [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode), [`human_approval.md` §1](./human_approval.md#1-autonomy-first-approval-is-a-bounded-exception) |
| Evidence gates | how growth is verified before it counts | [`concepts.md` §5](./concepts.md#5-why-evidence-gates), [`loop_plan_spec.md` §4](./loop_plan_spec.md#4-evidence-gates), [`evidence_gates.md`](./evidence_gates.md) |
| Human approval | the boundary conditions where autonomy hands off | [`human_approval.md`](./human_approval.md), [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode) |
| Three-tier model | the action → subgraph → subloop ladder Live Loop growth climbs (default: subgraph; promote to subloop at the Promotion Gate) | [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md), [`recursive_loops.md`](./recursive_loops.md) |
| Recursive planning ⇄ immersive execution | the runtime rhythm that switches between the whole-graph planning view and the per-node execution view, descends a level when a node proves complex, and writes the descent's results back to the parent | [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md) |

The components share the same vocabulary: they all speak in
terms of the locked field set, the 15-status enum, the 8 node kinds,
the 8 gate kinds, the 4-value escalation ladder, and the
3-value `risk` enum ([`loop_plan_spec.md` §Glossary](./loop_plan_spec.md#glossary)).
Live Loop introduces no new statuses, kinds, gates, or ladder rungs.
It is a usage pattern over the existing machinery.

> Stable Goal + Invariant Control Graph + Live Runtime Subgraphs +
> Evidence Gates.

---

## See also

- [`concepts.md`](./concepts.md). The **why**: top-level invariant rule (§3), isomorphic subgraph recursion (§4), evidence-gate rationale (§5), bounded ladder (§6), durable primitives (§7), interview-as-Layer-0 (§8), resume from blank session (§9).
- [`loop_plan_spec.md`](./loop_plan_spec.md). The authoritative field dictionary: top-level `loop.plan` shape (§1), node object (§2), `design_invariant` / runtime-discovered rule (§5), `subgraph` recursion and `parent_ref` (§7), the canonical **Glossary** enumerating the locked node kinds, gate kinds, statuses, ladder steps, and `risk` / `assignee` / `verdict` / `verifier` enums.
- [`state_model.md`](./state_model.md). The 15-status enum, the state transition table, the **checkpoint** / **node.contract** / **evidence.ledger** field sets, and the §"Resume from a blank session" algorithm that makes Live Loop growth safe across session boundaries.
- [`exception_handling.md`](./exception_handling.md). The exception taxonomy, the bounded `local_retry` → `local_patch` → `replan` → `escalate` ladder, the per-exception response table, and the three-layer Graph Harness framing that Live Loop composes with.
- [`human_approval.md`](./human_approval.md). Autonomy-first as a bounded exception (§1), decision authority tiers (§2), what MUST be user-approved by default (§6), and the cross-session handoff schema (§5).
- [`evidence_gates.md`](./evidence_gates.md). The eight gate kinds and how they are chosen; the appendix on a `risk: high` node's requirement that the `verifier` MUST NOT be the producing `agent`.
- [`recovery_protocol.md`](./recovery_protocol.md). The operational procedure for running Live Loop in practice (when to admit, when to surface, when to roll back).
- [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode). The Autonomy-First Control Principle that Live Loop inherits without modification.
- [`execution_intelligence_policy.md`](./execution_intelligence_policy.md). The High-Ceiling Execution temperament that decides *when* to admit growth: Bounded Maximalism, deepening triggers, materiality, and the Goal Alignment Check that keeps growth goal-serving.
- [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md). The **three-tier execution model** (`action` / `subgraph` / `subloop`), the **Promotion Gate** that escalates a lightweight `subgraph` to a directory-materialized `subloop`, and the two worked examples (acceptance-criteria and effectiveness-bug) that illustrate the default-then-maybe-promote rule.
- [`recursive_loops.md`](./recursive_loops.md). The directory-materialized **child loop** spec — the substrate a promoted `subloop` is built on: directory shape, `loop.meta.yaml`, `child_loops[]` reference, `return_contract` / `closeout.md`, child-checkpoint additions, and the Sub-loop Admission Gate.
- [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md). The execution rhythm Live Loop growth runs inside: switching between the whole-graph planning view and the per-node immersive view, descending into a subgraph/subloop on local complexity, and writing results back to the parent.
