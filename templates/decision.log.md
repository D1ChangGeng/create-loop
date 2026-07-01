# Decision Log: Append-Only Decision Record

*Diataxis type: **reference**. This is the per-run decision log emitted by the
`create-loop` runtime. It is the human-readable companion to the machine
event log and the canonical record of every significant choice the agent
made. It is **append-only**: never edit, never delete, never reorder. To
supersede a decision, write a new entry that names the older one.*

---

## When to log a decision

Log an entry whenever ANY of the following holds:

- A `human_approval` tier 2 decision is acted on: the agent had authority to
  proceed but is required to log the action post hoc. (Tier 1 = announce
  and wait for sign-off; tier 2 = act and log; tier 3 = act silently.)
- An `on_failure` ladder step is taken: `local_retry`, `local_patch`,
  `replan`, or `escalate`. Always log which rung was chosen and why.
- A `replan` is triggered. The new `plan_version` and the reason for
  supersession must appear.
- A scope, requirement, or non-goal is changed mid-run. Cite the
  `task_profile.yaml` field that changed.
- Two or more materially different approaches were considered. Even when
  only one option was picked, log the trade-off so a future agent can
  reverse it.
- An irreversible action fires. The log entry is the audit trail.
- A `blocker` is declared or resolved.
- Any decision the user makes that re-routes the plan.

If unsure, log. The cost of a logged decision is one Markdown heading. The
cost of an unlogged decision is an unrecoverable fork.

---

## Format

Each entry begins with a level-2 Markdown heading. The heading carries the
ISO-8601 timestamp and the decision title. The body carries the structured
fields below, in this order, using the canonical tokens defined in
`references/loop_plan_spec.md` and `references/state_model.md`.

```
## {ISO datetime}: {decision title}

- Context:
- Options considered:
- Decision:
- Rationale:
- Reversible?: yes | no
- Authority: agent | user
- Related node_id:
- Evidence ref:
```

Field rules:

- **Context.** Two to four sentences naming the situation. Cite the
  `node_id` and the `plan_version` it lives in.
- **Options considered.** Bulleted list. At least two options for any
  meaningful fork. Each option names its own trade-off.
- **Decision.** One sentence stating what was done. Use the canonical
  status / kind / gate / ladder terms verbatim.
- **Rationale.** One to three sentences connecting the decision to a
  `success_criteria` id or a `failure_criteria` line.
- **Reversible?.** `yes` or `no`. A reversible decision has a named
  `compensation` node or a trivial undo path. Anything irreversible
  (production writes, external notifications, payments) is `no`.
- **Authority.** `agent`, `user`, or `subagent`. Cite the tier (1, 2, or
  3) in the body if a `human_approval` gate was involved.
- **Related node_id.** The `id` of the owning node in `loop.plan.nodes`.
  `null` only when the decision is plan-level (e.g. choosing the
  `termination.done_when`).
- **Evidence ref.** Path to the artifact (gate verdict, transcript,
  screenshot, evidence-ledger entry) that supports the decision.

---

## Filled example

Below is one complete entry showing the expected shape. New entries go
**below** this example. Do not backfill, do not edit prior entries.

## 2026-07-02T14:30:00Z: Promote draft headline B over A and C

- Context: After three parallel `draft_headline` subgraphs (assignee
  = subagent, parallelizable = true) completed inside the parent
  `build_landing_page` node (plan_id = `lp-2026-07-02`, plan_version =
  1), three candidate headlines were available. The parent node was
  blocked on this choice because the `evaluator_optimizer` gate required
  exactly one picked headline before the `style_polish` subgraph could
  begin.
- Options considered:
  - Headline A ("Ship enterprise deals faster"): strong verb, action
    oriented, but skews toward existing buyers rather than new leads.
  - Headline B ("The quoting layer enterprise sales teams outgrew"):
    challenges the buyer, matches the true intent of validating against
    enterprise CTOs.
  - Headline C ("Built for the way your enterprise actually buys"):
    safe but generic, no differentiator.
- Decision: Promote headline B and archive A and C as alternates in
  `marketing/landing/alternatives.md`.
- Rationale: B is the only candidate that names the buyer
  (`enterprise`) and the pain (outgrew the existing layer) in a single
  read; it directly advances `success_criteria[SC-1]` (page must
  resonate with enterprise CTOs).
- Reversible?: yes. A headline change is one file edit and a re-run of
  the `style_polish` subgraph; no irreversible artifact is touched.
- Authority: agent. Tier 3, no user approval required; selection is
  internal to a reversible creative step. Tier 3 was set in
  `task_profile.yaml -> autonomy.agent_may_decide`.
- Related node_id: `build_landing_page.headline_select`
- Evidence ref: `evidence/landing_page/headline_judge_v2.json` (LLM
  judge score 0.82 against `rubrics/enterprise_voice.md`).
