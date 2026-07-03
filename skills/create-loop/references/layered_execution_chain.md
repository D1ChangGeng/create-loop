# Layered Execution Chain

*分层执行链路 — the ladder of layers a loop descends through, and the test that
decides when to stop descending and act.*

> A `loop.plan` is neither a single top-level plan that decomposes everything up
> front, nor a pile of complexity dumped straight into child loops. The runner
> descends a **layered chain** — choosing, at each work item, whether to keep
> planning, split locally, build a subgraph, promote to a subloop, write an
> action plan, or **stop and execute** — and writes every layer's verified
> result back up.

```
Top-level Loop
  → Node / Task Stage
  → Subgraph
  → Subloop
  → Action Plan
  → Immersive Action
  → Result Verification
  → Return to Parent Layer
```

*Diataxis type: **explanation + reference**. This document defines the **layers**
of loop execution and the **decision cascade** that routes a work item to the
right one, plus the **leaf-action test** that ends a descent and the **dual
failure mode** (premature execution / over-planning) it exists to prevent. It is
the structural companion to [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md):
that document names the **rhythm** (switch between planning view and execution
view); this one names the **ladder** the rhythm climbs and the **stop condition**
that ends each descent. It defines **no** field, status, gate kind, tier, or
ladder rung — those are owned by [`loop_plan_spec.md`](./loop_plan_spec.md),
[`state_model.md`](./state_model.md), [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md),
and [`recursive_loops.md`](./recursive_loops.md).*

---

## 0. Status of this document (read first)

This is a **behavioral principle**, not a schema. It introduces **no new node
kind, no new status, no new gate kind, no new tier, no new ladder rung, and no
validator**. "Descended to the right layer and stopped at the right moment" is
not machine-checkable — the same reason
[`recursive_planning_immersive_execution.md` §0](./recursive_planning_immersive_execution.md#0-status-of-this-document-read-first)
and [`execution_intelligence_policy.md` §0](./execution_intelligence_policy.md#0-status-of-this-document-read-first)
give for being policy, not rules.

Every layer it names is already expressible with machinery that exists. In
particular, **`Action Plan` is not a new tier** — it is a `subgraph` whose nodes
are ordered `action` leaves (or a single node's ordered `action` sequence), used
when a focused local goal still needs several steps but not independent
governance. **`Immersive Action` is executing an `action` leaf.** The chain is a
naming of how the three locked tiers are actually reached and left:

| this layer… | …is which existing machinery | owned by |
|---|---|---|
| **Top-level Loop** | the top-level `loop.plan` — `design_invariant` skeleton only | [`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes), [`loop_plan_spec.md` §1](./loop_plan_spec.md#1-top-level-loopplan-fields), [`SKILL.md` §2](../SKILL.md#2-the-three-layer-model) |
| **Node / Task Stage** | a `loop.plan` node (a stage-level objective) | [`loop_plan_spec.md` §2](./loop_plan_spec.md#2-the-node-object), [`state_model.md`](./state_model.md) |
| **Subgraph** | the inline `subgraph` field / `node.runtime.yaml` `runtime_subgraphs[]`, 8-value subgraph status enum | [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) |
| **Subloop** | a directory-materialized child loop | [`recursive_loops.md`](./recursive_loops.md) |
| **Action Plan** | a `subgraph` of `action` leaves (or a node's ordered `action` list) — a scoped step list, **not** a governed unit | [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md), [`loop_plan_spec.md` §2](./loop_plan_spec.md#2-the-node-object) |
| **Immersive Action** | executing one `action` leaf | [`loop_plan_spec.md` Glossary](./loop_plan_spec.md#glossary) |
| **Result Verification** | the layer's `completion_gate` / evidence-ledger `verdict: pass` | [`evidence_gates.md`](./evidence_gates.md), [`state_model.md`](./state_model.md) |
| **Return to Parent Layer** | subgraph `completion_gate`; subloop `return_contract` / `closeout.md` | [`recursive_loops.md` §7](./recursive_loops.md#7-return_contract-and-closeoutmd-the-return-interface), [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) |

So this document is a **standing instruction to the runner**: recognise the
layer the current work belongs to, descend no further than its clarity /
complexity / risk / dependency / governance need requires, and return a
verified, write-back-ready result. It is not a second execution model beside the
three-tier one — it is how that model is *entered and left*.

---

## 1. The principle

The core of a loop is **not** "decompose the whole task once". It is that the
system, mid-execution of a complex goal, can autonomously judge — from the
current work's **clarity, complexity, risk, dependencies, and governance need** —
whether to:

- keep planning,
- split locally,
- build a subgraph,
- promote to a subloop,
- write an action plan,
- **stop decomposing and enter immersive execution**,
- verify the result and write state back up.

These layers are not a directory shape or a taxonomy. They are the control
mechanism by which a loop does recursive planning, local organisation, parallel
coordination, independent iteration, evidence verification, and write-back inside
one complex goal. The whole mechanism exists to avoid **two symmetric failures**:

```
Premature execution:
  the task is still vague, its dependencies unclear, its output unverifiable —
  and the runner acts anyway.

Over-planning:
  the task is already clear and directly executable — and the runner keeps
  splitting, graphing, or spinning up subloops.
```

So the point of the layers is **not** to add structure mechanically. It is to
give each layer an explicit **trigger, execution rule, completion standard,
evidence requirement, return mechanism, and promotion/demotion rule**, so the
runner can stably switch between whole-goal control, local splitting, structured
organisation, independent iteration, concrete action, evidence verification, and
write-back — and keep driving a complex goal to a high-quality close.

---

## 2. The layers

Each layer answers one governing question. Descend only as far as the answer
forces you to.

### 2.1 Top-level Loop
Owns the **control skeleton** of the whole goal: goal, non-goals, hard
constraints, success/failure criteria, the design-time-known unavoidable gates,
core task stages, inter-node artifact dependencies, evidence gates, recovery
protocol, human-decision boundaries, live-growth rules, plan-mutation rules, and
the global advance strategy. It does **not** exhaust execution detail.
Governing question: *which governance nodes, constraints, evidence gates, and
decision boundaries are design-time-fixed and unbypassable for this goal to hold
at high quality?* Its two failure modes are **over-expansion** (freezing all
detail up front → rigid, unadaptable) and **under-control** (a bare goal with no
gates, failure criteria, recovery, or human boundaries).

### 2.2 Node / Task Stage
A stage-level objective inside a top-level or child loop — research, requirements
baseline, architecture, implementation, verification, release-prep, retro, local
correction, targeted exploration, risk handling, evidence back-fill. Each stage
declares purpose, inputs, outputs, completion condition, evidence requirement,
blocking conditions, the conditions under which it may spawn a subgraph or
promote to a subloop, and how it writes state back up. Governing question: *can
this local objective be executed directly? If not, does it need an action plan, a
subgraph, or a subloop?* A stage is **not necessarily a directly-executable
unit** — if it still hides multiple steps, dependencies, parallel branches,
unresolved decisions, or an unverifiable completion condition, it must keep
splitting.

### 2.3 Subgraph
A lightweight in-node DAG that organises a stage's **local** tasks, dependencies,
branch paths, parallel structure, and local verification chain. Build one when a
stage contains several inter-related steps / branches / parallel paths but does
**not** yet need its own directory, state, evidence ledger, checkpoint, or
closeout. Fits: local multi-step analysis, local option comparison, small-scope
parallel research, local defect fixes, local evidence back-fill, local
verification paths, small live growth, short-lived-but-complex in-node work, and
"several local artifacts jointly satisfy the parent gate". Governing question:
*inside this stage, are there multiple local tasks / dependencies / branches /
parallel paths that must be organised?* If yes, do not write them as vague action
items — build a subgraph. It stays hosted by the parent stage unless rising
complexity trips the subloop promotion criteria; on completion it returns to the
parent stage (see §7.3).

### 2.4 Subloop
A materialized, recoverable, auditable independent local loop. Create or promote
to one when a local objective outgrows the parent node's / subgraph's lightweight
control and needs its **own** plan, state, evidence, checkpoint, closeout,
directory, or executor. Fits: cross-session, high-uncertainty, high-risk,
multi-iteration, complex-implementation, complex-research, subagent-parallel,
many-artifact, independently-recoverable, independent-closeout, may-recurse, or
multi-parent-gate-affecting work. Governing question: *does this local objective
now need independent governance, rather than being handleable as a lightweight
subgraph inside the parent node?* A subloop is **not a bigger subgraph** — a
subgraph solves *local structure organisation*; a subloop solves *independent
governance, recovery, audit, iteration, and write-back*. It returns through its
`return_contract` (see §7.4).

### 2.5 Action Plan
A short-range execution plan **between a local objective and the final
operations**. Write one when a stage / subgraph node / subloop node no longer
needs a subgraph or subloop but still cannot be executed in one shot: the goal
and scope are clear, no independent governance is needed, dependencies are
simple — but several ordered steps are required, order affects the result, inputs
/ outputs need marshalling, tools/files/context must be prepared, or a little
local uncertainty remains. Its purpose is **not** extra planning — it is to split
the local objective down to a directly-executable grain. **The stop condition of
splitting is not "a plan exists"; it is "every leaf action in the plan is clear
enough to execute and verify directly" (§6).** Any action item that stays vague,
too broad, multi-step, or non-executable must split further or be promoted to a
subgraph/subloop. (Structurally, an Action Plan is a `subgraph` of `action`
leaves, or a node's ordered `action` list — not a new tier.)

### 2.6 Immersive Action
The final execution layer. When an action item has a clear goal, clear input,
clear operation, clear output, and clear verification method, the runner **stops
planning** and executes: focus on the one operation, call the needed tools,
create/modify the concrete artifact, keep execution evidence, observe the result,
verify the output, record state, return upward. Governing question: *is this
action item clear enough to complete and verify directly?* If yes → execute now.
If no → return to the action-plan / subgraph / subloop layer and keep splitting.
The runner **must not keep planning once direct execution is possible** — else
the loop degrades from an execution loop into a planning loop.

---

## 3. The layer-switch cascade

Facing any work item, judge in this order and stop at the first match:

```
1. Can it be executed and verified directly?
   yes → Immersive Action.
   no  → continue.

2. Does it just need splitting into a few clear ordered steps?
   yes → write an Action Plan.
   no  → continue.

3. Does it hold multiple local tasks / dependencies / branches / parallel / join?
   yes → build a Subgraph.
   no  → continue.

4. Does it need independent state / recovery / evidence / closeout / directory /
   executor, or multiple iterations?
   yes → create or promote to a Subloop.
   no  → continue.

5. Does it expose a problem in the parent plan / requirements / architecture /
   verification / evidence / control skeleton?
   yes → build a correction subgraph, or raise a Plan Mutation Proposal.
   no  → keep advancing.

6. Does it cross a goal / permission / risk / cost / external-side-effect boundary?
   yes → produce a Human Decision Package.
```

Apply this same cascade uniformly at: loop creation, node execution, subgraph
extension, subloop promotion, live-growth admission, exception recovery,
post-gate-failure correction, plan change, and human-decision triggers. The
cascade is the operational form of the [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)
Autonomy-First routing: steps 1–5 are resolved autonomously by descending; only
step 6 hands off to the user.

---

## 4. Triggers to keep splitting (do NOT enter immersive action while any hold)

```
goal still too large;
input unclear;               output unclear;               operation unclear;
multiple hidden steps;       unresolved decision;          multiple dependencies;
latent parallel branches;    local uncertainty;            risk or quality gap;
completion condition unverifiable;
must analyse before deciding;
several artifacts must jointly support one goal;
one immersive action cannot finish it;
the action contains "handle as appropriate" / vague conditionals;
failure state cannot be recorded;
may cross a permission / cost / risk / external-side-effect boundary.
```

While any of these hold, the work is not a leaf — keep splitting via the §3
cascade. These are the same signals as the deepening triggers in
[`execution_intelligence_policy.md` §4](./execution_intelligence_policy.md#4-deepening-triggers--deepen-selectively-not-everywhere),
read from the "am I allowed to stop?" direction.

---

## 5. Subgraph vs Subloop

Both absorb complexity, but solve different problems.

| dimension | Subgraph | Subloop |
|---|---|---|
| core purpose | organise local task structure | independently govern a local objective |
| lifecycle | short-lived | cross-session, long-running possible |
| state | hosted by parent node | own state |
| evidence | references parent evidence system | own `evidence.ledger` |
| recovery | lightweight (via parent) | own `checkpoint` + recovery |
| closeout | usually none of its own | mandatory own `closeout.md` |
| fits | local dependency, branch, parallel | high complexity, high risk, multi-iteration |
| return | local completion status + evidence | full result via `return_contract` |
| independent executor | no | yes (separate executor / subagent) |

> If the problem is mainly "how are these local tasks organised", use a
> **subgraph**. If it is mainly "this local objective needs independent
> governance and recovery", use a **subloop**.

This is the same decision as the Promotion Gate
([`subgraph_subloop_policy.md` §5](./subgraph_subloop_policy.md#5-promotion-gate-subgraph--subloop))
and the Sub-loop Admission Gate
([`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate)) — the
single canonical criteria list; this table is its at-a-glance form.

---

## 6. The leaf-action test (the real stop condition)

Splitting stops at a **leaf action**, never merely at "a plan exists". A leaf
action MUST satisfy all of:

```
action boundary clear;       input known;             execution method clear;
no extra decision needed;    no hidden branch;        no vague verb;
no multiple hidden steps;    output defined;          verification method defined;
failure state recordable;
does not cross a permission / cost / risk / external-side-effect boundary.
```

**Not a leaf** (each still hides steps, judgement, or an uncertain path — split
or promote it):

```
analyse options and pick the best implementation;
optimise the relevant docs;              fix the issue as appropriate;
research and summarise conclusions;      implement this module;
improve the verification mechanism;      handle all edge cases;
optimise the related content;            back-fill the missing evidence;
check overall quality.
```

**Is a leaf** (clear input / operation / output / verification → execute now):

```
Read `loop.plan.yaml`, extract every node id and edge, write to
  `artifacts/graph_inventory.yaml`.

Check `loop.plan.yaml` for cycles; if any, record them to
  `artifacts/graph_cycle_report.md`.

Mark every subgraph in `node.runtime.yaml` that is `running` past its max
  attempts as `blocked`.

From the `active` entries in `evidence.ledger.yaml`, generate the current
  node's gate-verification summary.

Read every hard constraint in `requirements.baseline.md` and generate
  `artifacts/hard_constraints_checklist.md`.
```

The leaf-action test is what makes "over-planning" and "premature execution"
concretely decidable: a work item that fails the test must not execute (§4); a
work item that passes it must not be split further (§2.6).

---

## 7. Return relations (every layer writes a verified result up)

No layer may return only "done". Each returns a **verifiable, traceable,
write-back-ready** result. Write-back never edits the parent's checkpoint /
ledger / artifacts directly — it flows through the parent gate (subgraph) or the
`return_contract` / `closeout.md` merge protocol (subloop), per the isolation
rule ([`recursive_loops.md` §9](./recursive_loops.md#9-isolation-rule-for-parallelism)).

- **7.1 Immersive Action →** result, artifacts, verification result, failure
  reason, state change, whether more splitting is needed, whether it affects the
  parent gate.
- **7.2 Action Plan →** completed actions, failed actions, remaining actions,
  artifacts, local verification result, blockers, whether a subgraph/subloop is
  now needed.
- **7.3 Subgraph →** subgraph completion status, completed nodes, blocked nodes,
  local artifacts, evidence references, decision records, open issues, whether to
  promote to a subloop, effect on the parent gate.
- **7.4 Subloop →** `closeout.md`, `return_contract`, artifact list, evidence
  list, decision list, risk changes, blockers, suggested parent state updates,
  effect on the parent gate, suggested updates to parent `loop.plan` / state /
  evidence, whether a new subgraph / subloop / plan mutation is needed, residual
  risk + next-step advice.
- **7.5 Node / Task Stage →** node gate result, node artifacts, evidence, state
  update, downstream now-ready nodes, risk changes, assumption changes, whether a
  plan mutation or human decision is needed.
- **7.6 Top-level Loop →** final deliverables, completion evidence, open issues,
  retired items, knowledge-promotion candidates, retro conclusions, follow-up
  loop candidates.

---

## 8. Relationship to the other principles

This principle and [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md)
are a matched pair and are best read together:

| principle | owns | this chain's relation to it |
|-----------|------|-----------------------------|
| **Recursive Planning ⇄ Immersive Execution** ([doc](./recursive_planning_immersive_execution.md)) | the *rhythm*: switch between planning view and execution view | this chain is the **ladder that rhythm descends** and the **stop-test that ends each descent**; the rhythm decides *when* to move levels, this chain defines *what the levels are* and *how far to go* |
| **design-time invariants** ([`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes)) | what may live at the top level | fixes the **Top-level Loop** layer (§2.1) as skeleton-only |
| **Autonomy-First** ([`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)) | how decisions route by default | steps 1–5 of the §3 cascade are autonomous descents; only step 6 escalates |
| **Live Loop** ([`live_loop_semantics.md`](./live_loop_semantics.md)) | how the graph grows under evidence | the chain is the set of layers live growth is admitted *into* (small growth → action; local → subgraph; governed → subloop) without polluting the parent |
| **High-Ceiling Execution** ([`execution_intelligence_policy.md`](./execution_intelligence_policy.md)) | depth-vs-stop temperament | its deepening triggers = §4 "keep splitting"; its diminishing-returns stop = §6 leaf test; its Goal Alignment Check guards every descent and write-back |
| **three-tier model** ([`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md), [`recursive_loops.md`](./recursive_loops.md)) | `action` / `subgraph` / `subloop` + gates | the tiers this chain routes work into; §5 restates the Promotion Gate |

```
too large            → keep splitting
structurally complex → build a Subgraph
needs own governance → create a Subloop
multi-step, no governance needed → write an Action Plan
leaf action clear    → STOP planning, execute immersively
local layer done     → return result + evidence + decisions + state upward
```

This principle adds no new statuses, kinds, gates, tiers, or ladder rungs. Its
final rule: **split when the goal is too large; subgraph when structure is
complex; subloop when a local objective needs independent governance; action-plan
when work needs several steps but not governance; stop planning and act when the
leaf action is clear; and when a local layer closes, return its result, evidence,
decisions, and state accurately to the layer above.** That stable switching —
whole-goal control, local split, structured subgraph, independent subloop, action
plan, immersive execution, evidence verification, structured write-back — is the
core mechanism that keeps driving a complex goal to a high-quality close.

---

## See also

- [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md). The matched-pair principle: the planning ⇄ execution **rhythm** whose descents this chain gives concrete **layers** and a **stop-test** to.
- [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md). The three-tier model (`action` / `subgraph` / `subloop`), the **Promotion Gate** (§5 here restates it), and the subgraph ↔ parent-node permission table — the tiers this chain routes work into.
- [`recursive_loops.md`](./recursive_loops.md). The directory-materialized child loop, the `return_contract` / `closeout.md` write-back interface, the isolation rule, and the Sub-loop Admission Gate — the substrate of the Subloop layer and its return relation (§7.4).
- [`loop_plan_spec.md`](./loop_plan_spec.md). The authoritative field dictionary and **Glossary**: the `action` leaf, the node object, the `subgraph` field, and the locked enums — the machinery every layer here maps onto (§0).
- [`live_loop_semantics.md`](./live_loop_semantics.md). Evidence-driven growth — the mechanism that admits new work *into* one of these layers without bypassing the parent gate (§9 boundary).
- [`execution_intelligence_policy.md`](./execution_intelligence_policy.md). The High-Ceiling temperament: deepening triggers (§4 "keep splitting"), diminishing-returns stop (§6 leaf test), and the Goal Alignment Check that keeps every descent and write-back goal-serving.
- [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode). The Autonomy-First Control Principle: steps 1–5 of the §3 cascade are autonomous, only step 6 escalates.
