# Recursive Planning ⇄ Immersive Execution

*递归规划与沉浸式执行切换 — recursive switching between whole-graph planning and
inside-one-node immersive execution.*

> A `loop.plan` is not decomposed once and then executed in a straight line.
> It is completed by **recursively switching between global planning and local
> immersive execution** — like a high-level team, not a checklist.

> Global decompose → local immersive execute → local re-decompose → deep
> execute + verify → sub-closeout → write back to the parent → parent re-plans
> and advances.

*Diataxis type: **explanation + reference**. This document names the execution
**rhythm** of `create-loop`: how the runner moves between an architect's
whole-graph view and an engineer's inside-one-node view, when a node spawns a
subgraph or a subloop, and how sub-level results are written back so the parent
can re-plan. It explains **when** and **how** to switch levels; it does not
redefine any field, status, gate kind, tier, or ladder rung — those are owned by
their canonical documents ([`loop_plan_spec.md`](./loop_plan_spec.md),
[`state_model.md`](./state_model.md),
[`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md),
[`recursive_loops.md`](./recursive_loops.md)). Like
[`live_loop_semantics.md`](./live_loop_semantics.md) and
[`execution_intelligence_policy.md`](./execution_intelligence_policy.md), it is a
**usage pattern over existing machinery**, and it inherits the boundaries of
[`SKILL.md` §3 Autonomy-First](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode).*

---

## 0. Status of this document (read first)

This is a **behavioral principle**, not a schema. It introduces **no new node
kind, no new status, no new gate kind, no new tier, no new ladder rung, no new
field, and no validator**. There is no rule number for it, because "switched to
the right level at the right time" is not machine-checkable — the same reason
[`execution_intelligence_policy.md` §0](./execution_intelligence_policy.md#0-status-of-this-document-read-first)
gives for the High-Ceiling policy.

Everything it describes is already expressible with machinery that exists:

| This principle uses… | …which is defined authoritatively in |
|---|---|
| the global-view control graph and the design-invariant top level | the three-layer model, [`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes) and [`SKILL.md` §2](../SKILL.md#2-the-three-layer-model) |
| isomorphic recursion (a sub-level is the same shape as the top) | [`concepts.md` §4](./concepts.md#4-why-recursion-isomorphic-subgraphs) |
| the three execution tiers `action` / `subgraph` / `subloop` | [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) |
| promoting a subgraph to a subloop | the Promotion Gate ([`subgraph_subloop_policy.md` §5](./subgraph_subloop_policy.md#5-promotion-gate-subgraph--subloop)) and the Sub-loop Admission Gate ([`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate)) |
| writing sub-level results back to the parent | the `return_contract` / `closeout.md` protocol ([`recursive_loops.md` §7](./recursive_loops.md#7-return_contract-and-closeoutmd-the-return-interface)) |
| growing the graph only when evidence forces it | Live Loop ([`live_loop_semantics.md`](./live_loop_semantics.md)) |
| deciding when to go deep vs stop | the deepening triggers and pre-execution-review / quality-uplift points ([`execution_intelligence_policy.md` §4](./execution_intelligence_policy.md#4-deepening-triggers--deepen-selectively-not-everywhere), [§6](./execution_intelligence_policy.md#6-the-high-ceiling-execution-loop)) |
| keeping recursion goal-serving | the Goal Alignment Check ([`execution_intelligence_policy.md` §3.7](./execution_intelligence_policy.md#37-protect-the-goal-from-drift-goal-alignment-check)) + goal/intent-hash invariant (R26) |

So this document is a **standing instruction to the runner**: it names a rhythm
the runner should recognise and follow, expressed as concrete moves and
boundaries rather than as a validator.

---

## 1. The principle

Facing a systemic, high-complexity, long-horizon goal, the system must not rely
on a single up-front plan, and must not push forward mechanically down a linear
list. Neither extreme completes a hard goal well:

| Failure mode | Why it fails |
|---|---|
| **decompose everything first, then execute linearly** | the plan is fiction — a plan authored before any work is done cannot honestly know its own leaves ([`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes)); it freezes wrong guesses into structure. |
| **execute freely and adjust at random** | no stable control structure, no evidence discipline, no recoverability; local optimisation drifts the work away from the goal. |

The effective way sits between them: **continuously switch between abstraction
levels**. First take the whole-graph view to see the goal's structure, the stage
relationships, the dependency order, and the key evidence gates. Then enter one
concrete node and work it immersively — analyse, design, implement, verify. If
that node is itself complex, generate a **local subgraph** or promote it to a
**child subloop**, and run another round of structured decomposition, execution
planning, and evidence control *inside* it. When the sub-level closes, its
products, evidence, decisions, and state are **written back** to the parent, and
the parent re-evaluates and keeps advancing.

> Loop execution is therefore neither "fully decompose, then execute" nor "adjust
> while wandering". It is a **multi-level nested, continuously recursive,
> evidence-constrained** goal-completion process.

---

## 2. Two working views

Different levels of the work call for different roles. The runner deliberately
adopts the view the current level needs.

| view | role it plays | it focuses on |
|------|---------------|---------------|
| **global / planning view** | architect · project lead · layout designer | Is the top-level goal clear? Which nodes are design-time-invariant, mandatory gates? Are there real produces/requires artifact dependencies between nodes? What can run in parallel; what must be serial? Which nodes need an evidence gate? Which risks, permissions, and human-decision boundaries must be controlled up front? |
| **local / execution view** | executor · researcher · engineer · verifier | What is this node's real purpose? Are its inputs trustworthy enough? How should the work inside it actually be done? Is there an omission, contradiction, hole, weak assumption, or hidden risk? Does it need a light subgraph? Should it be promoted to an independent subloop? Do the outputs satisfy the parent's evidence gate? Should the result be written back to the parent's plan, state, evidence, or decision log? |

The global view builds and maintains the **control structure**; the local view
produces **verified work**. The whole method is switching between them at the
right moments, at every level of the tree.

---

## 3. The recursion rhythm

```
understand the goal
  → build the current level's control graph        (global / planning view)
  → pick an executable ready node
  → enter the node and execute immersively          (local / execution view)
  → discover local complexity, a gap, a risk, or an unknown
  → generate a subgraph, or promote to a subloop
  → inside the sub-level: decompose, plan, execute, verify   (recurse — same rhythm)
  → sub-level closeout: products + evidence + decisions + state
  → write back to the parent                         (return_contract / closeout.md)
  → the parent re-evaluates and keeps advancing
```

This is not "plan once, run once". Each level runs the same loop, and any node
may open another level beneath it. The top-level control skeleton stays stable
(the `design_invariant: true` nodes); the execution path *lives*, growing
downward only as evidence requires ([`live_loop_semantics.md`](./live_loop_semantics.md)).

The recursion is **isomorphic**: a subgraph is an isomorphic *plan fragment* and
a subloop is an isomorphic *whole loop directory*
([`concepts.md` §4](./concepts.md#4-why-recursion-isomorphic-subgraphs),
[`recursive_loops.md` §5](./recursive_loops.md#5-the-isomorphic-per-loop-directory)).
Because every level has the same shape, the runner applies the same two-view
rhythm no matter how deep it is.

---

## 4. Choosing the level of the descent: action / subgraph / subloop

When the local view exposes complexity, the runner does not improvise and does
not pollute the top-level graph. It chooses the **lightest tier that can safely,
clearly, and recoverably hold the work**, and climbs only when governance demands
it. The tiers and the gates that separate them are owned by
[`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md); this section only
maps them onto the rhythm.

| the node is… | descend to a… | governed by |
|--------------|---------------|-------------|
| a single concrete step, no internal planning | `action` (leaf — no descent) | — |
| local multi-step work the parent node can host and recover | `subgraph` (in-node, lightweight) | the parent node |
| independently governable work needing its own plan / state / evidence / checkpoint / closeout | `subloop` (directory-materialized child loop) | its own loop, via the Sub-loop Admission Gate |

The switch from subgraph to subloop is the **Promotion Gate**
([`subgraph_subloop_policy.md` §5](./subgraph_subloop_policy.md#5-promotion-gate-subgraph--subloop)),
which is the tier-level restatement of the Sub-loop Admission Gate
([`recursive_loops.md` §8](./recursive_loops.md#8-sub-loop-admission-gate)) — the
single canonical criteria list. The decision rule, verbatim from that gate:

> **If a problem needs its own plan, state, evidence, checkpoint, or closeout, it
> is a subloop. If it only needs a few nodes and light state, it is a subgraph.**

**A subgraph** carries the parent node's *local re-decomposition*: a bounded
task topology the parent hosts, shares its state/evidence/logs with, and recovers
through. **A subloop** carries *independently governed* sub-work: its own
isolated directory, plan, checkpoint, evidence ledger, and closeout, recoverable
across sessions and agents, communicating with the parent **only** through its
`return_contract`. Together they are what give the system its recursive execution
capability: the top-level control structure stays stable while real execution
absorbs complexity level by level.

---

## 5. Writing back to the parent (the closeout of a descent)

A descent is not complete when the sub-level "runs" — it is complete when its
results are **written back** so the parent can act on them. The write-back
channel depends on the tier, and it is never an ad-hoc edit of the parent.

**From a subgraph (inline).** The subgraph is hosted inside the parent node
(`loop.state.yaml` or a per-node `node.runtime.yaml`,
[`subgraph_subloop_policy.md` §6](./subgraph_subloop_policy.md#6-where-subgraphs-live)).
Its outputs feed the parent node's gate directly; its admission and any live
growth are recorded through the parent's `evidence.ledger` and a `decision.log`
line, and every plan change is a typed `mutation` event (R39). It shares the
parent's budget and authorization; it never edits the top-level graph
([`subgraph_subloop_policy.md` §9](./subgraph_subloop_policy.md#9-subgraph--parent-node-permission-table)).

**From a subloop (directory-materialized).** The child loop writes **only its own
directory** (the isolation rule,
[`recursive_loops.md` §9](./recursive_loops.md#9-isolation-rule-for-parallelism)).
It influences the parent **exclusively** through its `return_contract` realised as
`closeout.md` ([`recursive_loops.md` §7](./recursive_loops.md#7-return_contract-and-closeoutmd-the-return-interface)):

```
child reaches a terminal status + all required_outputs exist
  → child writes closeout.md (what gap it solved, artifacts produced,
                              evidence, confirmed/refuted assumptions,
                              parent_updates, gates the parent may re-verify)
  → parent reads the child's closeout.md (via its child_loops[] reference)
  → parent applies each parent_updates entry:
        mark produces[] satisfied · re-run the named gate(s) ·
        move the owning node's status through the ordinary transition table
  → NO direct write into the parent's checkpoint / ledger / artifacts ever
  → parent re-evaluates readiness and keeps advancing the original goal
```

This is why the write-back keeps recursion **trackable, verifiable, and
recoverable**: the parent integrates children *serially*, one `closeout.md` at a
time, so parallel descents never corrupt shared state, and a fresh session
reconstructs the whole tree from the durable artifacts alone
([`recursive_loops.md` §11 INDEX files](./recursive_loops.md#11-index-files-avoid-full-tree-scans)).

---

## 6. Boundaries: what the rhythm must not do

The recursive descent is powerful, so it is fenced by the same boundaries every
other autonomous mechanism inherits. These prohibitions are absolute.

- **MUST NOT deepen without a trigger.** Open a new level only when the local
  view exposes real complexity, a gap, conflicting evidence, repeated failure, a
  formally-passing-but-weak artifact, or a downstream node that would otherwise be
  weakened — the deepening triggers of
  [`execution_intelligence_policy.md` §4](./execution_intelligence_policy.md#4-deepening-triggers--deepen-selectively-not-everywhere).
  Recursion for its own sake is waste, not rigor.
- **MUST NOT stop at diminishing returns.** When a descent stops producing new,
  material findings, close it out and return. Depth and cost are bounded by
  `termination` ([`loop_plan_spec.md` §1.2](./loop_plan_spec.md#12-termination-object)).
- **MUST NOT let a subgraph edit the top-level graph or change the goal.** A
  descent lives inside its owning node (subgraph) or its own directory (subloop);
  it carries `parent_ref` / `loop.meta.yaml.parent`, and it never mutates the
  `design_invariant` skeleton or the top-level `goal` / `true_intent`
  ([`subgraph_subloop_policy.md` §9](./subgraph_subloop_policy.md#9-subgraph--parent-node-permission-table),
  [`live_loop_semantics.md` §5](./live_loop_semantics.md#5-boundaries-what-live-loop-must-not-do)).
- **MUST NOT let recursion drift the objective.** Before every subgraph spawn,
  subloop promotion, and write-back merge, run the **Goal Alignment Check**
  ([`execution_intelligence_policy.md` §3.7](./execution_intelligence_policy.md#37-protect-the-goal-from-drift-goal-alignment-check)):
  does this still serve the *original* goal, or has a local optimisation become a
  new objective?
- **MUST NOT write back unverified work.** A descent returns to the parent only
  through an evidence-backed closeout (subgraph `completion_gate`; subloop
  `return_contract` + `verdict: pass` ledger entries). Nothing crosses the
  parent boundary on an agent's word alone.
- **MUST NOT escalate before autonomous descent is exhausted.** Per
  [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode),
  a branch / unknown / blocker is resolved by descending into an exploration or
  diagnostic sub-level first; the user is consulted only when the decision crosses
  a genuine boundary (goal, scope, irreversible or external side effect, cost,
  legal, value, authorization).

---

## 7. Relationship to the other principles

This principle is the **rhythm that ties the other four together** — it is *how*
the runner moves through the machinery they define, not a competing mechanism.

| principle | what it owns | how this rhythm uses it |
|-----------|--------------|-------------------------|
| **design-time invariants** ([`concepts.md` §3](./concepts.md#3-why-the-top-level-graph-holds-only-design-time-invariant-nodes)) | what may live at the top level | the *global view* builds and maintains this stable skeleton |
| **Autonomy-First** ([`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode)) | how decisions are routed by default | the reason a branch/unknown becomes a *descent* rather than a user question |
| **Live Loop** ([`live_loop_semantics.md`](./live_loop_semantics.md)) | how the graph extends downward under evidence | the mechanism the *local view* uses when it exposes a goal-necessary gap |
| **High-Ceiling Execution** ([`execution_intelligence_policy.md`](./execution_intelligence_policy.md)) | the temperament for depth vs stop | decides *when* to open a level and *when* to close it (pre-execution review, quality-uplift, deepening triggers, Goal Alignment Check) |
| **three-tier model** ([`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md), [`recursive_loops.md`](./recursive_loops.md)) | action / subgraph / subloop and their gates | the *levels* the descent moves between, and the write-back interface |

```
global planning view  = build/refresh the current-level control graph
local execution view   = immersively work one node and expose its complexity
descend (subgraph/subloop) = open the next level when complexity demands it
write back (closeout)  = return verified products/evidence/decisions to the parent
```

This principle introduces no new statuses, kinds, gates, tiers, or ladder rungs.
It is the disciplined **usage pattern** that lets a stable top-level structure
complete a complex goal through repeated, evidence-constrained descents — the way
a strong team establishes a top structure, sends specialists deep into the hard
parts, spins off workstreams when local work turns complex, and returns results,
evidence, risks, and decisions to the whole plan so it can move forward.

---

## See also

- [`concepts.md`](./concepts.md). The **why** of the shape: the top-level invariant rule (§3) and isomorphic subgraph recursion (§4) this rhythm moves through.
- [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md). The three-tier model (`action` / `subgraph` / `subloop`), the Promotion Gate, and the subgraph ↔ parent-node permission table — the levels the descent chooses between.
- [`recursive_loops.md`](./recursive_loops.md). The directory-materialized child loop, the `return_contract` / `closeout.md` write-back interface, the isolation rule, and the Sub-loop Admission Gate — the substrate of a subloop descent and its write-back.
- [`live_loop_semantics.md`](./live_loop_semantics.md). Evidence-driven completeness growth — the mechanism the local view uses to admit goal-necessary work as a subgraph, promoted to a subloop only at the gate.
- [`execution_intelligence_policy.md`](./execution_intelligence_policy.md). The High-Ceiling temperament that decides when to descend, when to stop (deepening triggers, diminishing returns), and the Goal Alignment Check that keeps recursion goal-serving.
- [`SKILL.md` §3](../SKILL.md#3-autonomy-first-control-principle-read-before-any-mode). The Autonomy-First Control Principle that makes a branch/unknown/blocker a descent, not a user question — the boundary set this rhythm inherits without modification.
