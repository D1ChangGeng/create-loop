# create-loop — Concepts

*Diataxis type: **explanation**. This document explains **why** `create-loop` is
shaped the way it is. It does not define fields (see
[`loop_plan_spec.md`](./loop_plan_spec.md)) or state transitions (see
[`state_model.md`](./state_model.md)). Read this to build a mental model; read
the two reference documents to build a schema.*

---

## 1. What create-loop is

`create-loop` is a **meta-skill**. You give it a short goal for a complex,
long-running, multi-session task — the kind of task that cannot finish in one
sitting, spans many tool calls, and will be picked up and dropped repeatedly by
AI agents that share no memory between sessions. `create-loop` does two things:

1. **Runs a Loop Startup (Charter) interview** to build a *control profile* —
   surfacing the true intent behind the stated goal, the deliverable class, the
   non-goals, the measurable success/failure criteria, the risk and approval
   boundary, the platform capabilities, and the state-persistence requirements.
   This interview is deliberately **not** an omniscient requirements gathering:
   it collects only the design-time invariants needed to emit a top-level plan.
   Anything that can only be known through later research, feasibility, or
   implementation is recorded as an `unknown`/`assumption`/`research_question`
   and routed to an owner node — never demanded of the user up front. See
   [§8, The interview is Layer 0](#8-the-interview-is-the-first-node-not-an-external-step).
2. **Generates a `loop.plan v0`** — a recursive execution-control DAG plus an
   evidence-gate protocol plus a persistent state contract that AI agents
   execute across sessions. `v0` contains only the design-time-invariant
   top-level governance nodes; concrete vendors, tech stacks, files, test cases,
   defects, and compliance details are discovered at runtime and generated as
   subgraphs inside the owning node.

The output is not documentation about the task. It is a machine-executable
control artifact: a plan whose nodes carry verification gates and whose progress
is recorded in a durable checkpoint, so that any fresh agent — with zero prior
chat memory — can read the state, verify what is true, and pick the next thing
to do.

## 2. Why a DAG and not a checklist

A checklist encodes **habit**: the order a human happens to do things. A
`loop.plan` encodes **dependency**: what genuinely cannot start until something
else has produced the artifact it needs.

We borrow this distinction directly from build systems. In
[GNU Make and Bazel](./research_dags_multiagent.md) a dependency edge means "this
target consumes the *artifact* that target produces" — an mtime/content
dependency, not "I usually build this one first". `create-loop` adopts the same
rule: an edge is a **produces/requires artifact dependency**. A node models its
incoming edges as a `requires: [<node_id>...]` list, and the node is only
allowed to become `ready` once every id in `requires` has reached `completed`.

Two consequences fall out of this, and they are the whole reason we prefer a DAG:

- **Parallelism is free and correct.** Any two nodes that do not (transitively)
  depend on each other can run at the same time. Because readiness is computed
  from real artifact dependencies rather than authored order, the scheduler can
  dispatch every ready node without the plan author having to reason about
  concurrency.
- **Resumability is free and correct.** A fresh agent does not need to know what
  the previous agent *intended* to do next. It recomputes the ready set from the
  dependency graph plus the recorded statuses. There is no hidden "cursor".

The four control-flow shapes we need on top of plain dependency edges are mapped
from [LangGraph's edge vocabulary](./research_dags_multiagent.md):

| control-flow vocabulary | LangGraph primitive        | how create-loop expresses it                    |
|-------------------------|----------------------------|-------------------------------------------------|
| fixed                   | `add_edge`                 | a `requires` entry (a static dependency edge)   |
| conditional             | conditional edge / router  | a `branch` node                                 |
| command                 | `Command(update=…, goto=…)`| a node that updates state *and* routes in one return |
| fanout                  | `Send` / map-reduce        | a `fanout` node dispatching parallel work, merged by a `join` node |

The exact node kinds (`milestone`, `gate`, `mapper`, `branch`, `fanout`,
`join`, `approval`, `compensation`) are defined in
[`loop_plan_spec.md` §node kinds](./loop_plan_spec.md#node-kinds).

## 3. Why the top-level graph holds only design-time-invariant nodes

The single most important structural rule in `create-loop` is what is allowed to
live at the top level of a plan.

The top-level graph contains **only design-time-invariant nodes**. A node is
design-time-invariant when it is:

- **known at design time** (we can name it before running anything), **and**
- **invariant for the task class** (it is mandatory and its existence does not
  change based on research findings, vendor choices, implementation details, or
  runtime discoveries).

Everything else — work whose *existence or shape* is only knowable after you
start running — is **runtime-discovered**, and it must not pollute the top-level
graph. Instead it is generated as a **subgraph inside the node that owns it**.

The distinction is subtle and easy to get wrong, so state it precisely:

> The rule is **not** "will this definitely happen? → top level". The rule is
> "is this **known at design time AND invariant for the task class**? → top
> level."

A task might *definitely* involve writing tests, but *which* tests only becomes
known once you have read the code. So "verification exists" is design-time
invariant (top level), while "the specific tests written" is runtime-discovered
(a subgraph inside the verification node).

| type | example | goes in top-level graph? |
|------|---------|--------------------------|
| **design-time invariant** (known + unchanging for the task class) | goal clarification, discovery, risk screen, verification, handoff, recovery protocol | **YES** |
| **runtime-discovered** (only knowable after running) | which vendors were compared, which files changed, which tests were written, which defects were found | **NO** — generate as a subgraph inside the owning node |

Why enforce this? Because a plan authored before any work is done cannot
honestly know its own leaves. If we forced the author to enumerate every future
task up front, the plan would be fiction. By restricting the top level to
invariants, the plan is **true at authoring time** and **stable across the whole
run** — it never needs rewriting, only *extending downward* via subgraphs.

## 4. Why recursion (isomorphic subgraphs)

When a node starts running and discovers it is too big, too dark (poorly
understood), or too complex to complete as a single milestone, it does not fail
and it does not improvise. It **generates an isomorphic subgraph** and recurses.

*Isomorphic* means the subgraph is the same shape as a top-level plan: it is a
`loop.plan` fragment with its own nodes, its own dependency edges, its own gates,
and its own state. The only structural difference is a `parent_ref` pointing back
at the node that spawned it. This is how a `mapper` node (or any node with
`allow_subgraph: true`) turns "this is bigger than I thought" into ordinary,
schedulable, verifiable work — without ever touching the top-level graph.

The recursion is bounded by the same machinery as everything else: each subgraph
node carries its own gate and its own retry budget, and its completion is a
precondition for its parent's completion. This mirrors the dynamic task mapping
of [Airflow, Prefect, Dagster, and Argo](./research_dags_multiagent.md), where a
node expands into a runtime-determined fan of child tasks that are collected back
before the parent proceeds.

This structural recursion is exercised at runtime as a deliberate rhythm — the
runner switches between a whole-graph planning view and an inside-one-node
execution view, descending a level when a node proves complex and writing results
back when it closes; see
[`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md).

## 5. Why evidence gates

A milestone is not "done" because an agent said so. It is done because
**evidence says so**. Every non-trivial node carries a `gate` — an explicit,
recorded verification with a defined kind, an optional numeric threshold, an
optional rubric, and a pointer to the evidence produced. A node cannot transition
to `completed` until its gate passes; a gate that fails sends the node to
`verification_failed`.

The gate kinds are drawn from the verification literature summarised in the
[DAG/multi-agent research](./research_dags_multiagent.md):

- `automated_check` — a deterministic scripted check (lint, schema-validate).
- `test` — code tests as evidence, run in a sandbox (CodeAct / eval-driven TDD).
- `llm_judge` — LLM-as-a-judge scoring against a rubric (Zheng et al. 2023).
- `self_consistency` — sample several times and require agreement (Wang et al. 2022).
- `evaluator_optimizer` — a generate→critique→revise loop (Anthropic's
  evaluator-optimizer pattern).
- `step_verifier` — step-level / process-reward verification (PRMs).
- `human_approval` — a human sign-off.
- `artifact_exists` — the cheapest gate: the required artifact is present.

The full field shape of a gate is defined in
[`loop_plan_spec.md` §evidence gates](./loop_plan_spec.md#evidence-gates), and the
gate's outcome is written to the evidence ledger defined in
[`state_model.md`](./state_model.md#evidence-ledger). Evidence is *external and
re-readable*: this is what lets a fresh session trust the plan without trusting a
previous agent's word.

## 6. Why a bounded escalation ladder

Agents fail. The interesting question is what happens next, and the wrong answer
is "retry forever" or "give up silently". `create-loop` defines a single,
bounded, ordered escalation ladder:

```
local_retry  ->  local_patch  ->  replan  ->  escalate
```

- **`local_retry`** — try the same node again, under its `retry_policy`
  (`max_attempts`, `backoff_base_seconds`, `jitter`).
- **`local_patch`** — apply a small, local correction and retry (fix the obvious
  thing).
- **`replan`** — the node's approach was wrong; regenerate its subgraph.
- **`escalate`** — hand off to a human via an `approval` node.

Each node declares where on this ladder it goes with `on_failure`. The single
most important property of the ladder is this:

> **Guards read persistent state, never in-memory state.** The retry budget is
> evaluated against the checkpoint on disk, so it survives a crash. An agent that
> dies mid-retry and is re-invoked in a fresh session sees the true attempt count,
> not zero.

This is why the ladder lives in the durable contract and not in the running
agent's head. The escalation vocabulary is locked in
[`loop_plan_spec.md` §escalation ladder](./loop_plan_spec.md#escalation-ladder);
the transitions it drives are in
[`state_model.md`](./state_model.md#state-transition-table).

## 7. Why durability primitives

The plan has to survive process death, session boundaries, and hosts that lack
fancy runtimes. `create-loop` therefore leans on a small set of durability
primitives, every one of which is **filesystem-mappable** — because the lowest
common denominator host has nothing but files. These primitives come from the
[durable-execution research](./research_durable_loops.md) and the
[DAG/multi-agent research](./research_dags_multiagent.md):

- **run-id directory = idempotency key.** A run is a directory whose creation is
  the single-flight start signal. Create it with `O_CREAT | O_EXCL` semantics —
  the create either succeeds (you own the run) or fails (someone already started
  it). This is the filesystem form of an idempotency key
  ([durable-execution research §1.6](./research_durable_loops.md)).
- **`cache_key = hash(inputs + prompt + model + config)`.** If a node's cache key
  matches a recorded success, skip the work and reuse the result — the Bazel-style
  action-cache idea ([DAG research §1.6](./research_dags_multiagent.md)).
- **Event-sourced append-only log + deterministic replay.** Record every
  side-effect in an append-only log; on resume, re-run the plan deterministically
  and, before each side-effect, check the log and skip anything already recorded.
  This is the Temporal / Restate / Azure Durable Functions model
  ([durable-execution research §1.1, §1.3, §1.5](./research_durable_loops.md)).
- **`workflow` vs `activity` split.** A *workflow* step is a deterministic plan
  decision (safe to replay). An *activity* is a side-effecting tool call (must be
  logged, must never be blindly replayed). Keeping the two separate is what makes
  replay safe.
- **`continue_as_new` = phase rollover.** When the event log grows too large,
  carry the essential state forward into a fresh log and bump the `phase`
  counter, so the history stays bounded
  ([durable-execution research §1.5](./research_durable_loops.md)).
- **Saga compensation.** Each side-effecting node may pair with a `compensation`
  node that undoes it, so partial failure can be rolled back cleanly (the saga
  pattern, [durable-execution research §1.7](./research_durable_loops.md)).
- **Graph Harness (three independent layers).** Following the Structured Graph
  Harness (arXiv 2604.11378, [DAG research §0.1](./research_dags_multiagent.md)),
  the plan for a given version is *immutable*, and **planning**, **execution**,
  and **recovery** are three separate layers. You never mutate a running plan;
  you produce a new `plan_version` and recover against it.

## 8. The interview is the first node, not an external step

A tempting mistake is to treat the interview as an omniscient, up-front
requirements-gathering pass that pins down every task, vendor, file, and test
before any work starts. That directly contradicts the rule in §5: the top-level
graph may contain **only design-time invariants**. If the interview tried to
extract the concrete solution, it would either block on questions the user
cannot yet answer, or bake runtime-discovered detail into the top level where it
does not belong.

So `create-loop` splits the work into three layers:

| Layer | Artifact | Job |
|-------|----------|-----|
| **Layer 0** | Loop Startup (Charter) interview | Establish the *control profile*: task type, end-state, success/failure criteria, risk & approval boundary, permission scope, platform capability, persistence & recovery requirements. |
| **Layer 1** | `loop.plan v0` | The design-time-invariant governance DAG — e.g. discovery, risk screening, feasibility, requirements baseline, architecture, verification, implementation, review, handoff, recovery. |
| **Layer 2** | node runtime subgraphs | Inside a specific node, generate the dynamic tasks, branches, parallel work, and artifacts that only become knowable once that node runs. |

The interview is therefore **the loop's first governance node** (`N0 Charter /
Control-Profile Gate`), not something that happens outside the loop:

```
short goal input
  → N0 Charter / Control-Profile interview
  → control profile / charter (task_profile.yaml)
  → loop.plan v0  (design-invariant top-level nodes only)
  → N1 Discovery, N2 Risk Screening, N3 Feasibility, …
  → runtime subgraphs generated inside each node from real findings
```

The rule for what the interview asks is sharp: **if the answer should be
produced by later research, feasibility, implementation, or verification, it is
not a startup precondition.** Such items are recorded in the charter as
`unknowns` / `assumptions` / `research_questions`, each routed to an
`owner_node`, and resolved when that node runs. The interview asks only what
changes the *shape of the top-level control graph*: what the goal and boundary
are, what may not be done autonomously, what evidence counts as done, how state
persists, and when the user must be consulted. The protocol lives in
[`templates/interview_brief.md`](../templates/interview_brief.md); its output
schema is [`templates/task_profile.yaml`](../templates/task_profile.yaml).

## 9. Why it must resume from a blank session

The defining constraint: a brand-new session, with **no prior chat memory**, must
be able to continue the work correctly. The design achieves this by making the
checkpoint the *only* source of truth. On startup a fresh agent:

1. reads state (the checkpoint),
2. verifies evidence and internal consistency,
3. identifies the ready nodes from the dependency graph,
4. picks the next node.

Nothing depends on the previous agent's memory, intentions, or "cursor". The full
ordered procedure is specified in
[`state_model.md` §resume-from-blank-session](./state_model.md#resume-from-a-blank-session).

## 10. Why it must degrade safely

Not every host gives us background execution, subagents, a durable runtime, or
lifecycle hooks. `create-loop` is designed so that the *rich* features are
optimisations, not requirements. When the host lacks them, the plan degrades to
the primitives that always exist:

| missing capability | fallback |
|--------------------|----------|
| background execution | persistent files + explicit checkpoints written at each transition |
| subagents | the single agent executes nodes serially; `assignee` collapses to `agent` |
| durable runtime | the run-id directory + event log + checkpoint on the filesystem *is* the runtime |
| lifecycle hooks | a **handoff doc** at each stop + **manual re-invocation** + a **startup recovery** step that runs the resume algorithm |

Because every durability primitive in §7 is filesystem-mappable, "degraded mode"
is not a second implementation — it is the same contract with fewer conveniences.
This is the practical payoff of grounding the whole design in files, evidence,
and an explicit state machine rather than in a live process's memory.

---

## See also

- [`loop_plan_spec.md`](./loop_plan_spec.md) — the authoritative field dictionary
  for `loop.plan` and its nodes, plus the canonical **Glossary** of every locked
  token.
- [`state_model.md`](./state_model.md) — the authoritative status enum, state
  transition table, checkpoint / node-contract / evidence-ledger field sets, and
  the resume-from-blank-session algorithm.
- [`./research_durable_loops.md`](./research_durable_loops.md) — durable
  execution, agentic loops, checkpoint/recovery sources.
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) — DAG
  engines, multi-agent orchestration, evidence gates, state machines.
- [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md) — the runtime rhythm that moves through the isomorphic recursion this document motivates: global planning view ⇄ local immersive execution, with write-back to the parent.
