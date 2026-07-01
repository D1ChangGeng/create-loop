# Human Approval — Decision Authority, `approval` Nodes & Cross-Agent Handoffs

*Diataxis type: **reference**. This document catalogues how a `loop.plan`
decides what an agent may do autonomously, what it must log, and what it must
not do without a human's confirmation. It defines the decision authority
tiers, the mechanics of the `approval` node, the cross-session / cross-agent
handoff schema, and the rules for what *must* be user-approved by default.
It does not redefine fields — see [`loop_plan_spec.md`](./loop_plan_spec.md)
for every field's type and the canonical Glossary, and
[`state_model.md`](./state_model.md) for the status enum and transition
table.*

*For the operational *protocol* (when to ask, when to log, when to escalate),
see [`recovery_protocol.md`](./recovery_protocol.md). For how approval
intersects with the bounded escalation ladder (and which exception classes
unconditionally escalate), see
[`exception_handling.md`](./exception_handling.md#3-the-bounded-escalation-ladder).*

Conventions follow the foundation docs: all tokens are **lowercase
snake_case**; all 15 node statuses are spelled exactly as in
[`state_model.md` §node status enum](./state_model.md#node-status-enum); the
8 node kinds are from
[`loop_plan_spec.md` §Glossary](./loop_plan_spec.md#node-kinds); all 8 gate
kinds, the 3-value `risk` enum, and the 3-value `assignee` enum are locked
in the same Glossary.

---

## 1. Autonomy-first: approval is a bounded exception

The default posture of every `loop.plan` is **tier 1 (autonomous)** (see §2
below). Human intervention is a **bounded exception**, not the default path,
and not a 50/50 split of control between human and agent. The primary
design principle is recorded in `SKILL.md` §3 (read before any mode) and
operates as follows:

- **Branches, unknowns, design choices, implementation blockers, and
  insufficient evidence do NOT route to the user.** They route to an
  exploration or diagnostic `subgraph` that researches and compares candidates
  in parallel, scores them by evidence / risk / cost, picks the clear winner,
  and records its rationale. If no clear winner exists but the choice is
  reversible and low-risk, the loop takes the highest information-gain /
  lowest-cost path and proceeds. Escalation is *exhausted-autonomous-recovery*,
  not a first reflex.
- **Approval nodes exist only for boundary conditions.** An `approval` node, a
  `waiting_user` status, or a tier 3+ decision is reserved for the boundary
  list in `SKILL.md` §3: change of top-level `goal` / `true_intent`; expansion
  of `scope` / `non_goals`; external side effect (publish / email / open a PR /
  delete / pay); irreversible operation (delete / overwrite / migrate /
  public release); legal / compliance / security high-risk; major resource
  commitment; user value preference (fast vs robust, aggressive vs
  conservative); final judgement under irreducible uncertainty; missing
  access / authorization; license / distribution boundary.
- **The mechanism elaborated in §2 through §6 is the *how*, not the *whether*.**
  §2 defines the five decision tiers; §3 through §6 explain how the
  `approval` node, the HITL analog, the cross-boundary handoff, and the
  unconditional boundaries fit together to realise a decision given its
  `risk`, `assignee`, and `gate`. The *policy* (what counts as autonomous
  vs requiring the user) is the boundary list above, owned by `SKILL.md`
  §3.
- **Most decisions sit at tiers 1 and 2 (autonomous / logged-autonomous).**
  Asking the user should be the *exception*, not the floor. Tier 3+ nodes
  appear in a plan only because the action is on the boundary list, not
  because the planner was timid.

**Why this matters.** A human is often the bottleneck on a complex task:
incomplete memory, unstable requirements, snap judgements, no time for deep
comparison, and weaker maintenance of long-horizon state / dependencies /
evidence chains than a file-based protocol. Asking is *friction* to minimise,
not a feature to maximise. The escalation ladder
([`exception_handling.md` §3](./exception_handling.md#3-the-bounded-escalation-ladder))
exhausts the autonomous rungs (`local_retry` → `local_patch` → `replan`)
before it touches `escalate`. The charter interview
([`templates/interview_brief.md`](../templates/interview_brief.md)) extracts
the *boundaries* of autonomy from the user up front, not the designs.
Autonomy here does NOT mean ignoring user boundaries. Boundaries are
absolute. It means not consulting the user about anything that is not on the
boundary list.

---

## 2. Decision authority tiers

Not every decision warrants the same friction. `create-loop` groups decisions
into five ordered tiers. The tiers are *not* separate node kinds — they are a
posture the runner takes based on a node's `risk` (one of `low`, `med`,
`high`), its `assignee` (`agent`, `user`, `subagent`), and the action it is
about to take. Every tier maps onto the locked vocabulary; the tier system
introduces no new statuses, node kinds, or ladder rungs.

| tier | meaning | when it applies | recorded in |
|------|---------|-----------------|-------------|
| **1 — autonomous** | the agent decides and acts without confirmation. | `risk: low`, action is reversible, no policy gates are crossed. | nothing beyond the normal `event_log` and `node.contract`. |
| **2 — logged-autonomous** | the agent decides and acts, but the decision is written down. | `risk: low` or `risk: med` for choices that benefit from auditability (parameter choices, prompt patches, replans at `local_patch` rung). | `decision.log` (one line per decision: `{tier, node_id, action, rationale, ts}`). |
| **3 — pre-approved** | the agent must hold off acting until the user has approved. | `risk: med` or `risk: high`, action is reversible or mildly destructive, or there is a real fork between two valid plans. | an `approval` node's `pending_approvals` entry; user decision recorded before transition. |
| **4 — user-only** | the user is the doer; the agent frames the work and waits. | `assignee: user` on the node itself, or `risk: high` with a side-effect that cannot be staged. | `pending_approvals` entry; the node's status is `waiting_user` (or the user manually reports completion). |
| **5 — escalate-on-risk-threshold** | the agent may iterate freely below a defined threshold; above it, it pauses and hands off. | `risk: high` work where local recovery is known to be bounded and the threshold cost/retry count is part of the policy. | `decision.log` while below threshold; `pending_approvals` entry when crossed. |

### 2.1 Mapping tiers to node fields

The tiers are realised through fields already locked on the node object —
there is no new schema:

| tier | `assignee` | `risk` | `kind` (if a control node) | gate (if any) |
|------|-----------|--------|---------------------------|----------------|
| 1 — autonomous | `agent` \| `subagent` | `low` | (any) | usual `gate` (often `automated_check`, `test`, or `artifact_exists`); no `human_approval`. |
| 2 — logged-autonomous | `agent` \| `subagent` | `low` \| `med` | (any) | usual `gate`; no `human_approval`. The `decision.log` is written in addition. |
| 3 — pre-approved | `agent` \| `subagent` (paused) | `med` \| `high` | `approval` | `human_approval` (a hard gate). |
| 4 — user-only | `user` | `high` | `approval` (or any kind whose `assignee: user`) | `human_approval`; runner cannot dispatch; status is `waiting_user`. |
| 5 — escalate-on-risk-threshold | `agent` \| `subagent` below, then `approval` above | `high` | `approval` once threshold crossed | `human_approval` only after the threshold trips. |

In short: tiers 1–2 are *autonomous* in the canonical schema; they look the
same on the wire and differ only in whether the runner emits a
`decision.log` line. Tiers 3–5 introduce a control node (`approval`) whose
`human_approval` gate is the suspend point.

### 2.2 Tier selection rules

Selection follows a fixed precedence. The runner chooses the *highest* tier
whose preconditions are met:

1. If the action is irreversible or destructive (see §6), the tier is at
   least 3.
2. Else if `risk == high`, the tier is at least 5 (with the threshold recorded
   on the node).
3. Else if `risk == med` and the action would skip a normal `gate`, the
   tier is at least 2.
4. Else the tier is 1.

`goal_changed` (§6) is its own tier-promoter — see §6.

---

## 3. The `approval` node

Approval is a **first-class control node**, planned in advance like every
other kind (`milestone`, `gate`, `mapper`, `branch`, `fanout`, `join`,
`approval`, `compensation`,
[`loop_plan_spec.md` §Glossary](./loop_plan_spec.md#node-kinds)). It is *not*
an ad-hoc question an agent emits when it gets stuck — the kind, the gate,
and the question are all part of the `loop.plan`, just like every other
node.

### 3.1 What it carries on the wire

An `approval` node is a node object (§2 of the foundation spec) with the
following distinctions:

| field | value for an `approval` node |
|-------|--------------------------------|
| `kind` | `approval` |
| `assignee` | `user` (the *user* is the executor of this node — the agent prompts, the user acts) |
| `risk` | matches the risk class of the question (often `high`) |
| `gate` | `kind: human_approval`, `threshold: null`, `rubric: null`, `evidence_ref`: a path where the user response will be persisted |
| `produces` | typically the user decision artifact (e.g. `{decision, rationale, ts}`) plus any artifact the downstream `requires` edges will `produces/requires` |
| `requires` | whatever the decision depends on (the evidence being approved, the alternatives being chosen between) |

### 3.2 How it sets status `waiting_user`

Dispatching the `approval` node moves it through the canonical transition
chain (see
[`state_model.md` §state transition table](./state_model.md#state-transition-table)):

```
ready -> running -> waiting_user
```

The `running → waiting_user` transition is the *only* way `approval` reaches
its suspend state — there is no shortcut status, no special "asking"
status. `waiting_user` is the canonical pause for awaiting the user, and
`approval` is the canonical node kind that uses it.

Downstream nodes whose `requires` includes this `approval` node remain
`pending`. They become `ready` only when the `approval` node reaches a
terminal state (`completed` on user approval, or `cancelled` on user reject /
abandon).

### 3.3 What is written to the checkpoint

The runner appends an entry to `checkpoint.pending_approvals`
([`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields)).

Each entry has the three fields locked in the checkpoint schema:

| field | type | meaning |
|-------|------|---------|
| `node_id` | string (node_id) | the `approval` node waiting on the user. |
| `token` | string | a stable id used by the user's response to identify which approval they are responding to (especially when several are open). |
| `requested` | string (ISO-8601) | when the approval was requested. |

A `pending_approvals` entry is the durable record of the request. The
[`state_model.md` §resume algorithm](./state_model.md#resume-from-a-blank-session)
step 8 makes opening `pending_approvals` a startup action: a fresh session
that finds any must surface them to the user before continuing dependent
work.

### 3.4 The decision resumes the loop

The user's response is one of three:

| response | what it means | how the runner records it |
|----------|---------------|----------------------------|
| **approve** | the action proceeds as proposed, or the user picks option A from a presented choice. | `evidence.ledger` entry with `gate_kind: human_approval`, `verdict: pass`, `verifier: user`; `approval` node transitions `verifying → completed`; downstream `pending` nodes may now become `ready`. |
| **reject** | the user refuses; the action does not run. | `evidence.ledger` entry with `verdict: inconclusive` or `verdict: fail` and `rationale` set to the rejection reason; `approval` node transitions to `cancelled`; downstream nodes remain `pending` (or are `cancelled` themselves on a cascade). |
| **amend** | the user provides a modified prompt, parameter, or constraint; the runner retries the *original* node (or the `approval` node itself) under the amendment. | `evidence.ledger` entry with `verdict: inconclusive` plus `rationale` describing the amendment; the runner applies the amendment as a `local_patch`-class correction under `retry_policy`, then re-enters `verifying`. |

In all three cases the entry is appended to `evidence.ledger` ([`state_model.md` §evidence-ledger](./state_model.md#evidenceledger))
*before* the `node_states` update is written to the checkpoint, so the
checkpoint is never ahead of the evidence it relies on.

---

## 4. Approval as the HITL analog of `interrupt()`

LangGraph's `interrupt()`
([`./research_durable_loops.md` §3.x](./research_durable_loops.md#3-checkpoint-recovery--persistence))
is the canonical HITL primitive the rest of the ecosystem has converged on:
it raises an exception that propagates to the runtime, the runtime saves
state and returns the payload to the caller, and on resume the node is *re-
executed from the start* (any code before the `interrupt()` runs again, but
its result is reused). The `HumanInTheLoopMiddleware`
(`interrupt_on={"write_file": True, "execute_sql": {"allowed_decisions":
["approve", "reject"]}}`) is the same pattern wrapped around tool calls.

`create-loop`'s `approval` node is the **filesystem-mappable equivalent**:

| LangGraph primitive | `create-loop` equivalent |
|---------------------|--------------------------|
| `interrupt()` raising in a node | `approval` node transitioning `running → waiting_user`. |
| Runtime saving state on interrupt | checkpoint + `evidence.ledger` append, with the same atomic ordering. |
| Payload returned to the caller (`__interrupt__` / `stream.interrupts`) | `pending_approvals` entry in the checkpoint (`{node_id, token, requested}`). |
| Resume with `Command(resume=...)` | `evidence.ledger` entry recording the user's `approve` / `reject` / `amend`, followed by a checkpoint write. |

The `approval` node is **a planned control point**, not an ad-hoc
interruption. The same primitive that `interrupt()` exposes at runtime is
*statically declared* in the `loop.plan`. The user knows what they may be
asked and when, because the question is on the page with the rest of the
DAG.

---

## 5. The handoff schema (cross-session / cross-agent)

When work crosses a session boundary, a `user → agent` reassignment, or a
`subagent → parent-agent` boundary, the *context* that crosses is the most
likely thing to drop on the floor. The Wire post "*Why every agent
handoff corrupts your context*" (2026)
([`./research_durable_loops.md` §3.3](./research_durable_loops.md#3-checkpoint-recovery--persistence))
names exactly five categories that compression / summarisation reliably
loses:

1. **what was done** — the actions and their observable results.
2. **why** — the *reasoning*, not just the final decision.
3. **what was tried and didn't work** — the negated paths.
4. **assumptions made** — the things taken on faith.
5. **confidence level** — how sure the producer is in each finding.

The fix the post describes — and that `create-loop` adopts as the canonical
cross-session / cross-agent handoff schema — is a **structured schema with
explicit fields for each**. Anthropic's research handoff (summary /
findings / confidence / verify-before-using) is the production reference.

### 5.1 The four locked fields

Every cross-boundary handoff writes a JSON file with these fields, spelled
exactly as below:

| field | type | meaning |
|-------|------|---------|
| `summary` | string | what was done — the actions taken, in order, with the result of each (the "what"). |
| `findings` | list[object] | each `{claim, evidence, confidence, contradicts?}` — the reasoning, the negated paths, and the assumptions (combining "why", "what was tried", and "assumptions" of the §4 introduction). |
| `confidence` | enum | how confident the producer is overall — one of `high`, `med`, `low` (the same three values as the `risk` enum; the same shape, applied to a producer's epistemic stance rather than to a node's action class). |
| `verify_before_using` | list[string] | the gates or checks the *receiver* must run before treating the findings as ground truth (the "trust-but-verify" rule). |

The schema is named in handoff files as `handoff.schema_version`. The
appendix in
[`./research_durable_loops.md` §3.3](./research_durable_loops.md#3-checkpoint-recovery--persistence)
records this as: "*Every handoff between sub-tasks writes a JSON file with
those four required fields. Schema validation is non-optional.*"

### 5.2 Why this prevents context corruption

Three properties together make the schema robust:

1. **Required fields, not optional.** Each of the five lossy categories
   has an explicit home (`summary` for "what"; `findings[*].claim` for
   "why"; `findings[*].contradicts` for "what was tried that didn't work";
   `findings[*].evidence` for "assumptions" backing the claim;
   `confidence` for confidence; `verify_before_using` for trust). A
   summariser cannot skip a category because the field is required.
2. **Per-claim evidence pointer.** `findings[i].evidence` is a *path* (or
   list of paths) to re-readable artifacts in the run directory — exactly
   the property that makes evidence *external and re-readable* in
   [`concepts.md` §5](./concepts.md#5-why-evidence-gates). The receiver
   can re-open the path; it does not have to trust the prose.
3. **A `verify_before_using` checklist.** The producer lists which gates the
   receiver should run. This is the same posture as the recovery layer
   in [`exception_handling.md`](./exception_handling.md) — never trust a
   prior agent's word; always re-verify.

### 5.3 Where handoff files live

A handoff schema file is written at every well-defined boundary. The
canonical locations are filesystem paths referenced by `node.contract`
(`evidence_ref`, `started`, `finished`) and by `checkpoint.event_log_ref`;
the exact path conventions are owned by the host's filesystem mapping. Two
rules hold regardless of layout:

1. The handoff file is **append-only on production, immutable on read**.
   The producer writes it once; the receiver appends a `received` entry
   (its own review timestamp, optional reconciliation notes) and never
   edits the original.
2. The handoff file is **side-by-side with the artifacts it cites**, not
   in a separate location. The `findings[i].evidence` paths are relative
   to the handoff file.

### 5.4 From schema to resume algorithm

The [`state_model.md` §resume-from-a-blank-session](./state_model.md#resume-from-a-blank-session)
algorithm does not trust handoff prose over evidence — step 3 ("Verify
evidence") re-opens every `evidence_ref` and demotes any node marked
`completed` whose matching `evidence.ledger` entry has gone missing.
Likewise, the resume side of a handoff always re-runs the
`verify_before_using` checklist; the *handoff schema is a discovery aid,
not a substitute for verification.*

---

## 6. What must be user-approved by default

Three classes of decision are *unconditionally* above the autonomous
threshold; they are tier 3 or higher, and the agent's recovery layer treats
them as `escalate` candidates (see
[`exception_handling.md` §9](./exception_handling.md#9-per-exception-response-table)).
The runner must surface an `approval` node (or directly pause a `user`-
assigned node) and wait for human decision.

| class | why it is always above tier 2 |
|-------|---------------------------------|
| **Irreversible or destructive action.** Deleting files outside the project's recovery window, sending real messages, posting publicly, modifying remote state (database writes, configuration changes, infrastructure actions). | The agent cannot *undo* it; the ladder's `local_retry` rung can fix a misstep, but the world cannot. The `risk` marker is always `high`. Tier 3 minimum, typically tier 4. |
| **Anything above the risk threshold.** Any node whose `risk` field is `high`, or whose `gate` has `kind: human_approval` by design, or whose action crosses a policy gate defined in the plan's `constraints`. | `risk: high` is by definition above tier-2 autonomy. The risk threshold is recorded as part of the tier-5 policy (escalate-on-risk-threshold) where applicable. |
| **Changes to top-level `goal` or `true_intent` (the `goal_changed` exception).** Any revision of `goal`, `true_intent`, the `success_criteria`, or the `non_goals`. | The goal is the anchor of every downstream decision; if the agent silently rewrites it, the entire evidence-ledger no longer measures what the user asked for. Per `exception_handling.md` §2.12, `goal_changed` is the *one* exception that the agent **MUST NOT** silently accept — the user must confirm. The new `plan_version` is produced only after confirmation; until then the running loop remains on the old `goal`. |

The third row also pins what `goal_changed` *cannot* do: it cannot change
the goal because an agent reasoned that the goal was suboptimal. It can
only follow a `tier≥3` decision from the user (directly or via an `approval`
node they approved). This is the structural guard against
"agent reorganised my task because it thought it knew better" — the
guard is the `approval` node plus the user-confirmation rule.

---

## 7. Approval is not optional scaffolding

`approval` is a first-class node kind, planned in advance, with its own
`gate`, its own `subgraph` recursion option, and the same readiness and
dispatch rules as every other node (see
[`loop_plan_spec.md` §3, §4, §6](./loop_plan_spec.md#3-edges-are-artifact-dependencies)).
It is not a "best-effort" interrupt the agent emits when it is lost; it is
a *structural* part of the plan and shows up in the DAG like any other
node.

Three corollaries:

1. **The user knows when they may be asked** because the `approval` nodes
   are on the page next to the milestones they gate.
2. **A run without an `approval` node cannot reach tier 3+.** If the plan
   has no `approval` nodes, the agent has *no way* to wait for user
   confirmation — meaning every irreversible / high-risk action must have
   a corresponding `approval` node in the plan, or the plan is missing a
   structural control.
3. **The `human_approval` gate is the only gate whose `verifier: user`
   produces a verdict.** No other gate kind may report `verifier: user`
   ([`state_model.md` §evidence-ledger](./state_model.md#evidenceledger)).
   This guarantees that a verdict that pauses the loop is recognisably a
   user verdict.

---

## 8. See also

- [`loop_plan_spec.md` §2](./loop_plan_spec.md#2-node-object) — the node object and its `assignee`, `risk`, `kind`, `gate` fields.
- [`loop_plan_spec.md` §4](./loop_plan_spec.md#4-evidence-gates) — the `gate` object and the `human_approval` gate kind.
- [`loop_plan_spec.md` §6](./loop_plan_spec.md#6-scheduling--failure-semantics) — readiness, dispatch, retry, escalation.
- [`loop_plan_spec.md` §Glossary](./loop_plan_spec.md#node-kinds) — the locked node-kind, gate-kind, status, and ladder enumerations.
- [`state_model.md` §node status enum](./state_model.md#node-status-enum) — `waiting_user` (the approval-pause status).
- [`state_model.md` §state transition table](./state_model.md#state-transition-table) — `running → waiting_user`, `waiting_user → ready | cancelled`.
- [`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields) — `pending_approvals`, `next_suggested_action`.
- [`state_model.md` §evidence-ledger](./state_model.md#evidenceledger) — `verdict`, `verifier` enums.
- [`state_model.md` §resume algorithm step 8](./state_model.md#resume-from-a-blank-session) — surfacing `pending_approvals` on resume.
- [`concepts.md` §5](./concepts.md#5-why-evidence-gates) — why evidence is external and re-readable.
- [`concepts.md` §6](./concepts.md#6-why-a-bounded-escalation-ladder) — the ladder and how it interacts with `escalate`.
- [`concepts.md` §9](./concepts.md#9-why-it-must-resume-from-a-blank-session) — the resume-from-blank-session rationale that handoff schemas serve.
- [`exception_handling.md`](./exception_handling.md) — the bounded ladder, the per-exception response table, and the saga machinery that approvals often gate.
- [`recovery_protocol.md`](./recovery_protocol.md) — the operational procedure for approvals and escalations.
- [`evidence_gates.md`](./evidence_gates.md) — `human_approval` as one of the 8 gate kinds.
- [`./research_durable_loops.md`](./research_durable_loops.md) — §3.3 (Wire, *Why every agent handoff corrupts your context*; the four-field handoff schema), §3.x (LangGraph `interrupt()`, `HumanInTheLoopMiddleware`, multi-agent handoff).
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) — §0.1 (Graph Harness, three-layer framing) and the DAG research on multi-agent handoff patterns.
