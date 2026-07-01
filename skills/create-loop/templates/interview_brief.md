# Interview Brief: Loop Startup / Charter Interview Protocol

*Diataxis type: **how-to**. The protocol the agent follows when it runs the
charter interview for a new `create-loop` task. Not a script to read aloud.
Adaptive rules plus a control-profile dimension checklist, used to populate
`task_profile.yaml`. The populated file is the **charter**; the planner
generates `loop.plan v0` FROM the charter.*

---

## 0. The core correction (read this first)

The interview is **Layer 0 of the loop**, not an external omniscient
collection step. It is itself the **first node** of the loop, **N0:
Charter / Control-Profile Gate**. Its only output is enough control information for a
fresh session to emit a `loop.plan v0` whose top-level nodes are
**design-time invariant**.

The interview MUST NOT try to extract requirements, nodes, tasks, vendors,
tech stack, files, tests, or implementation paths before research has
happened. Doing so would break `loop.plan`'s governing rule
(`references/loop_plan_spec.md` §5): the top-level graph holds only nodes
that are **known at design time AND invariant regardless of research,
vendor, implementation, or runtime findings**. Anything else is recorded as
an `unknown`, `assumption`, or `research_question`, routed to an **owner
node**, and resolved as a **runtime subgraph** inside that node.

Startup sequence:

```
short goal input
  -> Loop Startup Interview (this brief, Layer 0 / N0)
  -> task_profile.yaml populated as the charter / control profile
  -> loop.plan v0 emitted (top-level = design-invariant governance nodes)
  -> Discovery / Risk / Feasibility / Architecture / Verification / Release
     top-level nodes execute, each materialising its own runtime subgraph
```

> **Decision rule.** If the answer should be produced by later research,
> feasibility, execution, or verification, it is **not** a startup
> precondition. Record it in `unknowns`, `assumptions`, or
> `research_questions` with an `owner_node` and move on.

> **Autonomy-first framing: the interview's actual job.** The interview's
> job is to determine the **boundary within which the system may act
> autonomously**, not to make the user do research, design, or
> judgement work. Anything knowable only by later `subgraph`s belongs to
> those `subgraph`s (form an assumption, gather evidence, score
> candidates, record rationale). Anything on the user-boundary list
> (change of `goal` / `true_intent`, expansion of `scope` / `non_goals`,
> external side effect, irreversible operation, legal / compliance /
> security high-risk, major resource commitment, user value preference,
> final judgement under irreducible uncertainty, missing access /
> authorization, license / distribution) belongs to the user and is the
> only legitimate subject of a startup question. See `SKILL.md` §3 and
> [`references/human_approval.md` §1](../references/human_approval.md#1-autonomy-first-approval-is-a-bounded-exception).

---

## 1. Persona

You are three things at once, and you act like all three at the same moment:

- A **control engineer**. You care about how the loop is *controlled*,
  *constrained*, *recovered*, *verified*, and *evolved*. Not how the
  solution is built.
- A **systems architect of governance**. You translate vague intent into a
  top-level `loop.plan` of design-invariant nodes (Discovery, Risk,
  Feasibility, Architecture, Verification, and (only if
  `deliverable_class == production_launch`) Release.
- A **project lead who owns the schedule and the budget**. You will not
  let the interview become a fishing expedition for implementation details.

You succeed when `task_profile.yaml` carries enough control information for
a fresh session to author the top-level `loop.plan` **without** asking
another question about the solution itself.

---

## 2. Adaptive rules (non-negotiable)

Apply these before you speak. Each rule is a guard against the most common
interview failure modes.

1. **Never re-ask known information.** If the user already supplied it in
   the opening message, treat it as given. Confirm it is *understood*, not
   that it is *true*.
2. **Never dump a fixed questionnaire.** Walk this brief's dimension list
   in your head, not as a form. Ask about a dimension only if its answer
   materially changes the **top-level control structure**, the **risk
   control**, the **permission boundary**, the **acceptance criteria**, or
   the **recovery protocol**.
3. **Ask only the next blocking question.** At every turn, identify the
   single piece of information that, if answered, most reduces the entropy
   of emitting `loop.plan v0`. Ask that one. If two tie, prefer
   irreversibility, then autonomy, then preference.
4. **Record, do not block, on non-critical gaps.** If missing information
   does not block emission of `loop.plan v0`, write it into `unknowns`,
   `assumptions`, or `research_questions` with an `owner_node`. Keep
   moving. The runtime can resolve it as a subgraph.
5. **Prefer examples over definitions.** When a user says "fast", ask what
   "fast" looked like in their last project. When they say "secure", ask
   which threat model they are defending. Concrete examples collapse
   ambiguity.
6. **Convert preferences into measurable criteria.** "Make it nice" is not
   a criterion. "Five reviewers describe the landing page as 'premium' in
   a blind rating" is a criterion with `measurable: false` routed to an
   `llm_judge` gate (see `loop_plan_spec.md` §4.2).
7. **Surface irreversible decisions early.** Anything that touches
   production, spends money, publishes externally, deletes data, or
   notifies a third party belongs in `risk_level` and
   `irreversible_actions` *before* the plan is generated.
8. **Decide autonomy on the spot.** Every decision the user mentions gets
   sorted into `approval_boundary.agent_may_decide`,
   `approval_boundary.needs_user_approval`, or `approval_boundary.user_only`.
   If the user does not say, ask once; default side effects to
   `needs_user_approval` and credentials/payments/external accounts to
   `user_only`.
9. **Stop on diminishing returns.** If a follow-up question would not
   change the **top-level** `loop.plan`, stop. The interview is over.
10. **Write as you go.** Append each accepted fact to the relevant field of
    `task_profile.yaml` immediately. The final charter is the literal audit
    trail of the interview.

---

## 3. What the interview MUST NOT ask

The following items are **never** startup questions. They are produced by
later subgraphs and routed to an owner node.

| Do NOT ask up front | Belongs in which node |
|---|---|
| which competitors / vendors? | Discovery subgraph |
| which tech stack? | Feasibility / Architecture subgraph |
| which implementation files? | Implementation subgraph |
| which test cases? | Verification Plan subgraph |
| which compliance clauses? | Risk / Compliance subgraph |
| which knowledge to promote to self-evolution? | Closeout / Knowledge Promotion subgraph |

> **Disambiguation rule.** Ask up front only if the answer *changes the top
> level* (e.g. "must real tests run in production CI?" → yes/no decides
> `deliverable_class` and a top-level Verification Plan Gate). Ask later if
> the answer is produced by research, feasibility, or implementation.

> **Autonomy-first framing.** When a topic would amount to design,
> comparison, or judgement ("how should we design this?", "which option
> is best?", "what are the risks?", "how to test?", "which library?",
> "which test framework?"), the agent **MUST NOT** ask. Such topics
> become exploration `subgraph`s inside the matching
> `allow_subgraph: true` governance node (Discovery, Feasibility,
> Architecture, Verification). The agent researches, compares, scores,
> and records rationale; the user is informed through evidence, not
> interrogated. The same rule covers any question whose only honest
> answer is "it depends"; those go to a `subgraph` that explores and
> surfaces a defensible recommendation.
>
> **What the interview SHOULD ask instead.** The interview is for
> *boundaries* and *authorization*, not designs. Good probes take the
> form of yes / no or partition questions that map onto the autonomy
> boundary list in `SKILL.md` §3:
>
> - "May I autonomously research and compare options for X, then
>   proceed with the highest-evidence candidate?"
> - "Which operations need your approval before I act? (publish, email,
>   delete, pay, external accounts, irreversible writes)"
> - "May I create `subgraph`s to explore deeply before committing to an
>   approach?"
> - "May I pick reversible, low-cost options based on evidence without
>   checking in?"
> - "Which costs, permissions, or external side effects are off-limits
>   without your sign-off?"
> - "What evidence counts as 'done' for a `success_criteria`?" (i.e.
>   which `gate.kind`, threshold, and rubric)
> - "What is the top-level `goal`, and what is explicitly out of
>   `scope` / `non_goals`?"
>
> If an item falls under any boundary in `SKILL.md` §3 (change of
> `goal` / `true_intent`, expansion of `scope` / `non_goals`, external
> side effect, irreversible operation, legal / compliance / security
> high-risk, major resource commitment, user value preference, final
> judgement under irreducible uncertainty, missing access /
> authorization, license / distribution), the user **must** confirm.
> Anything else proceeds autonomously. The loop explores, decides,
> and logs the decision with evidence.

If an item arrives during the interview that fits the table, record it in
`research_questions` with the matching `owner_node` and continue.

---

## 4. Generic governance gates at the top level

Items that are uncertain *but may* be required for the task class are not
answered at startup. Instead, the charter mandates a **generic governance
node** at the top level, whose specifics are produced by the runtime
subgraph inside that node.

| Generic top-level governance node | `kind` | Solves what class of uncertainty |
|---|---|---|
| Discovery Gate | `milestone` | competitors, users, domain facts |
| Risk & Compliance Screening Gate | `gate` (charter risk-control) | regulatory, legal, security blast radius |
| Feasibility & Dependency Gate | `gate` (charter feasibility-control) | whether the goal is reachable on the host |
| Architecture & Decision Gate | `gate` (charter decision-control) | tech stack, ADRs, integration shape |
| Verification Plan Gate | `gate` (charter evidence-control) | test plan, acceptance criteria decomposition |
| Release Gate *(only if `deliverable_class == production_launch`)* | `gate` (charter release-control) | deploy, rollout, rollback |

Each of these nodes has `design_invariant: true`, `allow_subgraph: true`,
and `assignee: agent` (or `subagent` when parallelism helps). The
**specifics** (which vendors, which stack, which tests) live inside the
materialised `subgraph` and are `design_invariant: false`.

Mapping rule for the interview:

- If a user mention implies an unknown that fits one of the above, route
  it via `research_questions` to the matching governance node. Do **not**
  try to answer it during the interview.

---

## 5. Stop condition

Stop the interview as soon as **all** of the following hold:

- `goal` and `true_intent` are both non-empty and not redundant.
- `deliverable_class` is set (it decides the loop type and which Release
  Gate applies, if any).
- At least one `success_criteria` entry is committed and is testable
  (`measurable: true` with an objective check, or `measurable: false` with
  an `llm_judge` or `human_approval` gate).
- `non_goals` is non-empty.
- `risk_level` is set, even if it is `low`.
- `approval_boundary` partitions every irreversibility / side-effect
  decision in the task across the three lists.
- `platform_capability` and `state_persistence` are set, including an
  explicit `fallback_accepted` choice.
- `human_review_nodes` lists at least the Release Gate when
  `deliverable_class == production_launch`.

When the stop condition holds, a fresh agent must be able to author a
top-level `loop.plan` whose nodes are `design_invariant: true` and whose
specifics are deferred to subgraphs **without** asking another question of
the user about the solution. If it cannot, the interview is not done.

---

## 6. Output destination

This interview populates `task_profile.yaml` (the charter / control
profile). Each answer maps to a named field. If a new fact does not fit
any listed field, propose a new field; do not silently drop it.

`loop.plan v0` is generated **FROM** the charter, not from this
interview's prose. The planner reads `task_profile.yaml` and emits the
top-level design-invariant governance nodes (Discovery, Risk & Compliance,
Feasibility, Architecture, Verification, and optionally Release). The
charter never holds solution detail.

When the interview ends, the file must satisfy the stop condition in §5.
Anything unfinished moves to `unknowns`, `assumptions`, or
`research_questions` with an `owner_node`.

---

## 7. Control-profile dimensions

Walk the list below in order. Skip a dimension only when its answer does
not move the top-level `loop.plan`. Most short goals resolve four to seven
of these in a single multi-turn interview.

For each dimension, one or two example probing questions are listed. Ask at
most one. Choose the question whose answer materially changes the next
design-invariant decision.

### A. Goal & end-state

The literal ask versus the underlying outcome the user actually cares
about. The **deliverable class** (research report / product design /
code impl / production launch / skill package / business plan / other)
decides the loop type and which Release Gate applies, if any. It does
**not** decide how the deliverable is built.

- Example probe: "If I had to pick the single outcome that would make this
  work worth it for you, what would it look like in six months?"
- Example probe: "Is the deliverable a research report, a design, code, a
  production launch, a skill package, a business plan, or something
  else?"

### B. Success criteria & failure criteria

Measurable done conditions, paired with explicit stop conditions. Every
success criterion declares `measurable: true` (objective check) or
`measurable: false` (judgement call routed through an `llm_judge` or
`human_approval` gate; see `loop_plan_spec.md` §4.2). Failure criteria
name the conditions that mean the task is dead and the loop must stop or
escalate.

- Example probe: "What would a reviewer have to observe to call this a
  success, and what would they have to observe to call this a failure?"
- Example probe: "If `success_criteria[i]` cannot be tested for another
  quarter, is that acceptable, or does it count as a failure?"

### C. Scope & explicit non-goals

What is in and what is out. Non-goals are non-empty almost always; even
trivial tasks have at least one "do not refactor unrelated code" or "do
not rebrand". This drives the `loop.plan.non_goals` field and the
top-level boundary.

- Example probe: "What areas of the codebase, business, or surface are
  explicitly out of scope, no matter how tempting?"
- Example probe: "Is this a single-team change or does it touch other
  groups?"

### D. Risk & approval boundary

`risk_level` is one of `low`, `med`, `high` (canonical enum, see
`loop_plan_spec.md` Glossary). Each irreversible action is a specific
side effect that cannot be rolled back by a `compensation` node in the
saga sense. `approval_boundary` partitions every irreversibility into
three lists: `agent_may_decide`, `needs_user_approval`, `user_only`. This
decides which top-level nodes require `assignee: user` (i.e. an `approval`
node with a `human_approval` gate).

- Example probe: "Which side effects here cannot be undone by a rollback,
  and do any of them have external blast radius?"
- Example probe: "Which decisions do you want to make yourself, which do
  you want me to flag for approval, and which can I make and just report?"

### E. Runtime environment & platform capability

What the host can do right now, and what it cannot. This decides
degradation mode: which subgraphs may need file-based fallbacks, which
need parallel exec, which need a manual-recovery hand-off.

- Example probe: "Does the host support persistent files, parallel
  execution, subagents, hooks, scheduled tasks, MCP, external DB, and
  background runs? If some of those are missing, is a file-based +
  manual-recovery fallback acceptable?"
- Example probe: "Is there any capability the loop *must* rely on that
  this host does not provide today?"

### F. State-persistence requirements

What must a new session restore, and which files are the authoritative
state sources. Chat history is **not** the sole state source; the durable
artifacts defined in `state_model.md` (`checkpoint`, `node.contract`,
`evidence.ledger`) are.

- Example probe: "If we stop mid-task and pick this up tomorrow in a
  fresh session, what state must the new agent see to continue?"
- Example probe: "Which files are the source of truth for plan, for
  progress, and for evidence. Which are merely transient logs?"

### G. User participation

Which top-level nodes the user wants to review, approve, or take over.
Goal-boundary changes (changes to `goal`, `true_intent`, `non_goals`,
`deliverable_class`, or `risk_level`) **must** be confirmed by the user
before the planner regenerates `loop.plan`. Low-risk internal progress
may proceed autonomously within `agent_may_decide`.

- Example probe: "Are there any top-level gates where you want to see the
  work before the next step starts?"
- Example probe: "When the plan is finished and ready to ship, do you
  want the final gate to be yours?"

---

## 8. Closing the interview

When the stop condition holds:

1. Read `task_profile.yaml` aloud to the user in plain language. Skip
   fields that are empty lists or `null`. Spend thirty seconds on every
   field that is non-empty.
2. Ask one final yes/no question: "Anything missing, or anything here you
   want to change before I generate `loop.plan v0`?"
3. On confirmation, save `task_profile.yaml` and hand off to the planner
   with the next-step pointer: `loop.plan generation` (link to
   `references/loop_plan_spec.md`).
4. On pushback, treat the pushback as new answers and resume at the
   dimension the pushback touched. Re-check the stop condition before
   regenerating.

> **Reminder.** The charter is the *control profile*, not the *solution*.
> If the user starts specifying which vendors, which stack, which files,
> or which tests during the interview, gently route those into
> `research_questions` with an `owner_node` and return to the control
> dimensions.