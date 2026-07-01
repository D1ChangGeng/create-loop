# Branching and Parallelism: How a Plan Routes and What Runs at Once

*Diataxis type: **reference + explanation**. This document defines the
four control-flow vocabularies, the rules for serial versus parallel
dispatch, and how merge / cancellation / context isolation work. For
the field shapes, see
[`loop_plan_spec.md` §3.1](./loop_plan_spec.md#31-control-flow-vocabularies-mapped-from-langgraph).
For readiness, see
[`loop_plan_spec.md` §6.3 to 6.5](./loop_plan_spec.md#63-topological-readiness-rule).*

---

## 1. The four control-flow vocabularies

`create-loop` borrows its edge vocabulary from LangGraph's four edge
types
([`./research_dags_multiagent.md` §2.1](./research_dags_multiagent.md)).
Each vocabulary is a label for how an edge or node behaves, not an
extra field. They compose: a single plan can mix all four freely.

| vocabulary | LangGraph primitive | expressed in `loop.plan` as |
|------------|---------------------|------------------------------|
| `fixed` | `add_edge(src, dst)` | a static entry in a node's `requires` list (an unconditional dependency edge) |
| `conditional` | conditional edge / router | a `branch` node that selects among successors based on state |
| `command` | `Command(update=..., goto=...)` | a node whose single return value both updates state and routes to the next node |
| `fanout` | `Send` / map-reduce | a `fanout` node dispatching parallel work, merged by a `join` node |

These four names are locked tokens. They appear in `loop.plan`
narrative and in the cross-cutting vocabulary tables
([`loop_plan_spec.md` §3.1](./loop_plan_spec.md#31-control-flow-vocabularies-mapped-from-langgraph));
the Glossary at the bottom of that document is the canonical list.

---

## 2. Map each vocabulary to a node kind

The vocabulary names describe **how edges behave**. The node kinds
describe **what nodes do**. The mapping is fixed and exhaustive:

- **`fixed`** edges appear as ordinary `requires` entries. They can be
  satisfied by any node kind. A `milestone` node with `requires: [a, b]`
  is the canonical fixed-edge consumer.
- **`conditional`** routing lives inside a `branch` node. The
  `branch` reads the relevant state and emits exactly one successor;
  the others are skipped. The successor is a fixed edge from the
  `branch`'s output.
- **`command`** routing is a node whose return is `{update, goto}`.
  In `create-loop`, any node kind can carry `command: true` to opt
  into the combined update-and-route form. The most common
  application is `mapper` and `branch` nodes.
- **`fanout`** is realised by a `fanout` node dispatching work and a
  `join` node collecting it. The fanout produces multiple successors;
  the join waits for all of them.

`approval`, `compensation`, and `gate` nodes do not change which
vocabulary they participate in; they constrain what is allowed to
transition through them.

---

## 3. Serial versus parallel: the decision rule

The default rule from
[`loop_plan_spec.md` §6.4](./loop_plan_spec.md#64-parallel-dispatch-rule)
is: every node that is `ready` and has `parallelizable: true` MAY be
dispatched concurrently. The scheduler picks `priority` among competing
ready nodes. Whether two specific nodes should actually run in
parallel is a separate question, and the answer is governed by three
checks.

### 3.1 The three checks

Two nodes MAY run in parallel iff **all three** checks pass:

1. **No shared `requires` ancestor that is still `running`.** If node
   B and node C both `requires` node A, and A is still `running`, they
   serialize behind A. If A is `completed`, they may parallelise.
2. **No shared produced artifact.** If B and C both declare the same
   path in their `produces` lists, they share a write target. Two
   writers on the same artifact is forbidden; serialise.
3. **No shared mutable state.** If B and C both read-modify-write a
   piece of state recorded in `node.contract`, they cannot both run.
   The state is whatever the `event_log` records between their two
   `requires` entries; if no such entry exists between them, they may
   parallelise.

The checks are mechanical, not judgemental. The runner applies them
without consulting the LLM. The intent: parallelism is a property of
the dependency graph plus the produced-artifact set, not of how the
plan was authored.

### 3.2 When parallelism is forbidden

Some node kinds and some risk profiles must serialise regardless of
the three checks above:

- A node whose `risk` is `high` and whose `gate` is `human_approval`
  or any side-effecting `activity` (paid API call, file system mutation
  outside the run directory, network call) MUST NOT run in parallel
  with any other node that has overlapping side effects.
- A `compensation` node paired with a side-effecting node MUST run
  serially against that node. No other compensating work runs in
  parallel with it.
- A `branch` node whose decision depends on the `cost_units_spent` or
  `iteration` field MUST serialise behind any node whose completion
  could change those counters.

These are hard constraints. The runner enforces them; the LLM does not
override them.

### 3.3 When parallelism is meaningless

Two nodes may both be `ready` and `parallelizable: true` but still
truly serial in practice: when their combined resource cost exceeds
the host's available concurrency or `termination.max_cost_units`. The
runner honours the budget first, then concurrency. The dispatch order
within the budget is `priority` descending.

---

## 4. Parallelise only if truly independent

The single most important discipline rule for parallelism in
`create-loop` is this: parallel subagents must be **truly independent**.
If they must coordinate mid-task, the parallelism collapses into
expensive serial work. The
[Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
documents the rule explicitly and reports a 90.2% improvement over
single-agent and ~15× token cost when followed.

### 4.1 The three-part rule

A `fanout` may dispatch parallel subagents only when:

1. **Each subagent's task is self-contained.** The subagent prompt
   must include the inputs it needs; it must not depend on intermediate
   state another subagent will produce.
2. **Each subagent has isolated context.** No shared message history,
   no shared scratchpad, no shared memory store. Two subagents that
   share context are not parallel; they are one subagent with split
   attention.
3. **Each subagent has a structured return.** The orchestrator must
   not have to parse free-form prose from subagents; it must validate
   against a fixed schema. The Anthropic four-field schema
   (`summary`, `key findings`, `confidence`, `items to verify`) is the
   production reference.

### 4.2 The fan-out cap

Empirical practice caps parallel subagents at 3 to 5. Beyond that the
synthesis cost dominates the speedup. The
[Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
explicitly uses 3 to 5. `create-loop` inherits the cap. A `fanout`
node whose dispatcher produces more than 5 active subagents must
either batch (run in waves of ≤5) or escalate, not fan out flat.

### 4.3 The collapse signal

If a `join` node receives N branches whose subagent returns contradict
each other and require reconciliation, the cost of reconciliation may
exceed the savings from parallelism. The `join` node's `gate` (if
scored) is the right place to detect this: a low aggregate score or a
low inter-rater agreement is a signal to cancel low-value branches
early and accept partial coverage. See §6 for the cancellation
semantics.

---

## 5. Join and merge semantics

A `join` node is the fan-in: it has multiple entries in `requires`,
one per branch. It becomes `ready` only when **all** of them are
`completed` ([`loop_plan_spec.md` §6.5](./loop_plan_spec.md#65-join-semantics)).
A `join` following a `fanout` collects the fanned-out results before
its successors may proceed.

### 5.1 The reducer

The `join` node declares a `reducer` that determines how the
branch outputs are combined. Three reducers are first-class:

- **`concat`**: ordered concatenation, deterministic, order is the
  order the `fanout` declared the branches.
- **`merge`**: structured merge keyed by branch id, useful when each
  branch contributes a different field of a result object.
- **`vote`**: majority vote or weighted aggregation, used when branches
  are sampling the same question and the `join` is acting as a
  `self_consistency` aggregator.

The reducer choice is part of the plan; it is not negotiated at
runtime.

### 5.2 Conflicting branch outputs

Two branches that disagree are the join's main failure mode. Three
responses are available:

1. **Reconcile deterministically** (when the branches are structured
   and the conflict is local). The reducer does this automatically
   for `merge`; for `concat` it concatenates with explicit conflict
   markers.
2. **Reconcile via gate.** The `join` carries its own `gate`, typically
   `evaluator_optimizer` or `step_verifier`, that resolves the conflict
   in a structured way. The reconciled output is recorded as a new
   ledger entry.
3. **Escalate.** When reconciliation fails after the gate budget is
   exhausted, the `join` transitions to `verification_failed` and the
   node's `on_failure` ladder runs. If `on_failure` is `escalate`, the
   loop surfaces a `pending_approvals` entry to the user with the
   conflicting outputs side by side.

### 5.3 Partial coverage

A `join` whose branches include `cancelled` nodes does not necessarily
fail. The plan author declares whether partial coverage is acceptable
via the `on_partial` field on the `join`. If `on_partial: accept`, the
`join` proceeds with the surviving branches; if `on_partial: fail`,
the `join` transitions to `verification_failed` and the ladder runs.

---

## 6. Cancelling a low-value branch

A `fanout` followed by a long-running branch is sometimes overtaken
by another branch's `completed` result. The remaining branches may
then be cancelled to save cost. The mechanism is the
[`cancelled`](./state_model.md#node-status-enum) terminal status plus
a recorded rationale.

Cancellation rules:

- A branch can only be cancelled after at least one sibling branch is
  `completed` AND the `join`'s `on_partial: accept` is set, OR the
  `join`'s `gate` would never pass given the surviving output.
- The cancellation is recorded in the `event_log` with
  `reason: overtaken_by_sibling` or `reason: gate_will_fail`, plus
  the `node_id` that triggered the cancellation.
- The cancelled branch's `node.contract.attempt` is not refunded, but
  any `activity` it was running that has a partial result can have
  its side effect rolled back by the branch's paired `compensation`
  node, if any.

The runner cancels proactively, not the LLM. The LLM does not get to
silently drop branches.

---

## 7. Context isolation between parallel subagents

Parallel subagents share the filesystem but nothing else. The
isolation rule: each subagent has its own working directory under the
run-id directory, and the subagent's prompt context is built only
from that working directory plus its inputs. Two subagents never see
each other's scratch state.

### 7.1 Where each subagent writes

Each subagent under a `fanout` gets a per-branch working directory:

- `runs/<run-id>/branches/<fanout-id>/<branch-id>/input.json` , the
  subagent's task input, immutable for the subagent's lifetime.
- `runs/<run-id>/branches/<fanout-id>/<branch-id>/output.json` , the
  subagent's structured return, written by the subagent at
  completion.
- `runs/<run-id>/branches/<fanout-id>/<branch-id>/notes.md` , the
  subagent's free-form notes, not consumed by anyone but the
  subagent.

The parent orchestrator reads only `output.json` from each branch.
The branch's working directory is invisible to sibling branches and
to the rest of the plan until the `join` collects them.

### 7.2 Avoiding two writers on the same artifact

The "no shared produced artifact" rule (§3.1 check 2) is enforced by
the runner. Two subagents under the same `fanout` cannot declare the
same `produces` path. If a plan author wrote such a plan, the runner
refuses to dispatch the second subagent until the first is `completed`
and the artifact is sealed (its evidence ledger entry is finalised).

A `compensation` of a side-effecting node is serial with that node,
never parallel. See §3.2.

### 7.3 The cost of losing isolation

If two subagents share context, the parallelism they offer is
illusory. The synthesis step has to merge their narratives, which
takes more tokens than the speedup saved and risks coherence loss
([`concepts.md` §4](./concepts.md#4-why-recursion-isomorphic-subgraphs)).
This is the failure mode the Anthropic multi-agent research system
warns against. `create-loop` enforces isolation structurally through
the per-branch working directory, not by trusting the LLM to
self-isolate.

---

## 8. Concurrency limits and cost bounds

The plan declares its budget in the `termination` object
([`loop_plan_spec.md` §1.2](./loop_plan_spec.md#12-termination-object)):
`max_iterations`, `max_wall_clock_hours`, `max_cost_units`, plus the
`done_when` statement. The first three are hard caps; the runner
stops dispatching when any cap is reached and surfaces an `escalate`
rather than continuing.

The `termination.max_cost_units` cap is the primary budget for
parallelism. Each dispatched node records its cost against
`checkpoint.cost_units_spent`. A `fanout` whose estimated cost would
push the run over the cap is refused; the runner falls back to
serialising the branches, then to dispatching only the highest-priority
branches, then to cancelling the plan and escalating.

Concurrency has a separate cap, which is host-dependent: the runner
honours whatever the host can deliver. The plan does not declare a
parallelism limit of its own; the host's limit plus the cost cap is
the de facto limit. If the plan needs an explicit cap (for example to
prevent an API rate-limit collision), it declares it as a node-level
`parallelism` hint that the runner translates to a host-specific
concurrency primitive.

---

## 9. Summary: when each vocabulary fits

- **`fixed`** for ordinary dependency edges. The default.
- **`conditional`** for routing on state. Use a `branch` node when
  the choice depends on a previous node's output, the ledger, or
  `cost_units_spent`.
- **`command`** for nodes that need to update state and choose the
  next step in one return. Use when the routing decision and the
  state update are tightly coupled.
- **`fanout`** for independent parallel work. Use when the subagents
  are truly independent (§4.1) and the count is ≤ 5.

Mix freely. A plan that uses only `fixed` is a checklist, not a DAG
([`concepts.md` §2](./concepts.md#2-why-a-dag-and-not-a-checklist));
a plan that uses `command` everywhere loses the structural clarity
the DAG gives; a plan that uses `fanout` where `fixed` would do wastes
the cost cap.

---

## See also

- [`concepts.md` §2`](./concepts.md#2-why-a-dag-and-not-a-checklist) explains
  why a DAG with produces/requires edges, not a checklist.
- [`loop_plan_spec.md` §3.1](./loop_plan_spec.md#31-control-flow-vocabularies-mapped-from-langgraph)
  gives the locked control-flow vocabulary table.
- [`loop_plan_spec.md` §6.4 to 6.5`](./loop_plan_spec.md#64-parallel-dispatch-rule)
  define the parallel-dispatch and join rules.
- [`loop_plan_spec.md` §6.6`](./loop_plan_spec.md#66-subgraph-recursion-rule)
  shows how subgraphs participate in the same dispatch rules.
- [`recovery_protocol.md` §2](./recovery_protocol.md#2-the-resume-from-blank-session-algorithm)
  shows how the resume algorithm rebuilds the `ready_set` from the
  dependency graph.
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) covers
  LangGraph edge vocabulary, LangGraph Supervisor, LangGraph Swarm,
  OpenAI Agents SDK handoffs, Anthropic multi-agent research system.