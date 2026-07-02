# Human Decision Request — Context-Complete Decision Package

*Diataxis type: **how-to template**. This is the fill-in template a loop
runner emits when an `approval` node transitions `running → waiting_user`
(see [`human_approval.md` §3](../references/human_approval.md#3-the-approval-node)
for the node mechanics and [`human_approval.md` §7](../references/human_approval.md#7-human-decision-request-protocol)
for the protocol). Fill every placeholder before presenting the package to
the decider. Do not abbreviate, do not summarise, do not omit sections.*

> **This package is context-complete — it can be copied into a fresh AI
> session that has no prior history and still be answered systematically.**
> The decider may be the original user, a different human expert, or another
> AI agent. The package is the entire context surface; chat history, prior
> session memory, or implicit plans are NOT part of it.

> **Write-back contract.** The YAML answer returned by the decider is parsed
> and written back into **`decision.log.md`** (new append-only entry naming
> this `decision_id`), **`loop.state.yaml`** (`human_decisions[]` history),
> **`checkpoint.yaml`** (the matching `pending_approvals` entry transitions
> and is removed once approved/rejected), and any affected
> **`loop.plan.yaml`** (a new `plan_version` is recorded when the decision
> changes scope, goal, or topology).

---

## Decision ID

Canonical pattern: **`HD-<loop-id>-<seq>`** (the angle brackets are part of
the format string, not literal fill-ins). When the runner emits this
template, the placeholders are filled as:

`HD-{{loop_id}}-{{seq}}`

- `loop_id` → `<loop-id>`: the **current loop's** immutable id (e.g. `L001`,
  `L001.02`, `L001.02.03`). See
  [`recursive_loops.md`](../references/recursive_loops.md#6-loopstateyaml-schema)
  for the encoding rules.
- `seq` → `<seq>`: a zero-padded sequence number local to this loop,
  assigned in monotonically increasing order. The first decision requested
  by a loop is `seq: 01`; the second is `seq: 02`. Restart counting only
  when the loop is recreated.

---

## Required Decision

State the decision in one sentence, in the form **"The loop must choose
between X, Y, and Z"** or **"The loop needs the user to authorise W"**.
Use the canonical tokens from `loop.plan.yaml` (node_id, gate kind, risk
class) so the decider can grep them back into the DAG.

- **Statement:** {{one-sentence statement of the decision required}}
- **Owning node:** `{{node_id}}` (the `approval` node that triggered the
  request; the node whose `gate.kind == human_approval`)
- **Plan version:** `{{plan_version}}` (from `loop.plan.yaml -> meta.plan_version`)
- **Risk class:** `{{low | med | high}}`
- **Tier:** `{{3 | 4 | 5}}` (per
  [`human_approval.md` §2](../references/human_approval.md#2-decision-authority-tiers))

---

## Why Human Decision Is Required

Tick every category that applies. At least one MUST be ticked — if none
apply, this is not a tier 3+ decision and the runner must NOT emit this
package (see [`human_approval.md` §7](../references/human_approval.md#7-human-decision-request-protocol)
for the rule, and [`human_approval.md` §6](../references/human_approval.md#6-what-must-be-user-approved-by-default)
for the canonical boundary list).

- [ ] **Top-level goal change.** The `goal` or `true_intent` would be revised.
- [ ] **Scope expansion.** A new in-scope item, or a removal of a current
      in-scope item.
- [ ] **Major resource cost.** Significant additional budget, time, compute,
      tokens, external API spend, or human hours beyond the original
      `task_profile.yaml` estimate.
- [ ] **External side effect.** Publishing, sending mail, opening a PR,
      writing to a remote system, paying, deploying, or any action whose
      blast radius extends beyond the local repository.
- [ ] **Irreversible operation.** Delete, overwrite, migrate, public
      release, or anything that cannot be undone by `local_retry` /
      `local_patch`.
- [ ] **Legal / security / compliance / licensing / privacy / safety risk.**
      Touches regulated data, vulnerable populations, license boundaries,
      secrets, or threat surface.
- [ ] **Permission or credential required.** New scope of authority, new
      API key, new repository write, new deployment target.
- [ ] **User value preference.** A choice between alternatives where the
      decider's value judgement (fast vs robust, aggressive vs conservative,
      thorough vs minimal) overrides evidence-based ranking.
- [ ] **No evidence-backed dominant option.** Multiple viable candidates
      with comparable evidence and no rubric that resolves the tie.
- [ ] **Long-term knowledge promotion.** Writing a high-impact conclusion
      into long-term knowledge (a self-evolution promotion, a new ADR, a
      runbook change) that should not happen silently.
- [ ] **Other.** {{free-text description}} — only when none of the above
      fits; explain why the boundary list misses this case.

---

## Current Loop Context

Provide the topology pointers a fresh decider needs to navigate the
repository. Every pointer MUST be a path or a node_id, not a sentence.

| field | value |
|-------|-------|
| **Root loop** | `{{root.loop_id}}` — `{{root.path}}` |
| **Current loop** | `{{loop_id}}` — `{{current_loop.path}}` |
| **Current node** | `{{node_id}}` (the `approval` node waiting on the user) |
| **Parent loop** | `{{parent.loop_id}}` — `{{parent.path}}` (or `none — root loop`) |
| **Parent node** | `{{parent_node_id}}` (or `none — root loop`) |
| **Current status** | `{{status}}` (one of the 15 node statuses; the owning
approval node is `waiting_user`) |
| **Trigger event** | `{{trigger_event}}` — the event that caused the runner to
emit this request (e.g. `evidence.ledger entry: inconclusive at gate
human_approval`, `recovery ladder rung: escalate`, `goal_changed candidate
detected`). |
| **Relevant files** | `{{list of paths to loop.state.yaml, checkpoint.yaml,
loop.plan.yaml, decision.log.md, evidence.ledger.yaml, node.contract.yaml}}` |
| **Relevant artifacts** | `{{list of artifact paths cited by the current node's
requires/produces}}` |
| **Relevant evidence** | `{{list of evidence.ledger.yaml entries (or paths)
that bear on the decision; include the verdict and verifier for each}}` |

---

## Top-level Goal / Non-goals / Hard Constraints

Reproduce verbatim from `task_profile.yaml` (do not paraphrase — the
decider must see the same text the loop was chartered against):

- **Top-level goal:** `{{goal}}`
- **True intent:** `{{true_intent}}`
- **Non-goals:** {{bulleted list}}
- **Success criteria:** {{bulleted list, each with its `id`}}
- **Hard constraints:** {{bulleted list; cite the source field — typically
  `task_profile.yaml -> constraints` or `loop.plan.yaml -> constraints`}}
- **Out-of-scope:** {{bulleted list}}

---

## Evidence Gathered So Far

List the evidence the loop has accumulated that bears on this decision.
Each item is one entry in `evidence.ledger.yaml` plus its source artifact
path. If the loop has not yet gathered any evidence, state `none — this
is a fork before research`.

| # | claim | evidence path | verifier | verdict | confidence |
|---|-------|---------------|----------|---------|------------|
| 1 | {{claim}} | `{{path}}` | `{{gate | subagent | user}}` | `{{pass | fail | inconclusive}}` | `{{high | med | low}}` |
| 2 | {{claim}} | `{{path}}` | ... | ... | ... |

Summarise the epistemic state in one paragraph: what the evidence
collectively argues for, and what it does not resolve.

---

## What Has Already Been Tried

List every action the loop (or a parent loop) has attempted in service of
this decision, including actions that failed. For each, name the negated
path so the decider does not re-suggest it. Cite `decision.log.md`
entries by their ISO timestamp.

| # | attempt | outcome | decision.log entry | why it did not resolve the decision |
|---|---------|---------|--------------------|--------------------------------------|
| 1 | {{action}} | {{result}} | `{{ISO timestamp from decision.log.md}}` | {{reason it left the fork open}} |

If nothing has been tried yet, state `none — this is the first decision
request for this node`.

---

## Candidate Options

Present every viable option the loop has identified. **Show Option A and
Option B fully.** If more options follow, present them with the same
shape — do not abbreviate. Each option block carries nine fields:

### Option A — {{short label}}

- **Description:** {{what this option does, in concrete terms. Cite the
  node_id or plan_version it would produce.}}
- **Pros:** {{bulleted list, each tied to a `success_criteria` id where
  applicable.}}
- **Cons:** {{bulleted list.}}
- **Risks:** {{bulleted list, each tied to a `risk` class and a
  reversibility statement.}}
- **Cost:** {{estimated budget / time / compute / tokens / external spend.
  Cite the source of the estimate.}}
- **Reversibility:** {{`yes — undo path: ...` | `partial — undo path: ...
  with the following cost: ...` | `no — this action cannot be undone
  because: ...`}}
- **Evidence:** {{paths to the artifacts / `evidence.ledger.yaml` entries
  that support this option. Each path MUST be re-readable; see
  [`concepts.md` §5](../references/concepts.md#5-why-evidence-gates).}}
- **Impact on current loop:** {{effect on the current loop's plan_version,
  schedule, and downstream nodes. Cite the affected node_ids.}}
- **Impact on final goal:** {{effect on `success_criteria` and on the
  `goal` / `true_intent` alignment.}}

### Option B — {{short label}}

- **Description:** {{...}}
- **Pros:** {{...}}
- **Cons:** {{...}}
- **Risks:** {{...}}
- **Cost:** {{...}}
- **Reversibility:** {{...}}
- **Evidence:** {{...}}
- **Impact on current loop:** {{...}}
- **Impact on final goal:** {{...}}

### Option C — {{short label, optional}}

- **Description:** {{...}}
- **Pros:** {{...}}
- **Cons:** {{...}}
- **Risks:** {{...}}
- **Cost:** {{...}}
- **Reversibility:** {{...}}
- **Evidence:** {{...}}
- **Impact on current loop:** {{...}}
- **Impact on final goal:** {{...}}

*More options follow the same shape. Do not invent a new field layout.*

---

## System Recommendation

The loop runner's recommended choice. This is **advisory only** — the
decider may override it. The runner MUST NOT collapse a fork it cannot
justify; the recommendation is a summary of the evidence-ranked argument,
not a substitute for the decider's authority.

- **Recommended option:** {{A | B | C}}
- **Rationale:** {{one to three sentences connecting the recommendation
  to the evidence table, the success criteria, and the reversibility
  profile.}}
- **Confidence:** {{`high` — clear evidence winner; `med` — evidence
  leans but a tie-breaker is needed; `low` — opinion-only fallback.}}
- **If confidence is `med` or `low`, name the tie-breaker:** {{what
  additional evidence, user preference, or context would resolve the
  ambiguity.}}

---

## Consequence of No Decision

State what happens if the decider defers, abandons, or does not answer.
Be explicit — the decider must understand the cost of silence.

- **Blocks this node?** `{{yes — the approval node stays waiting_user and
  every downstream pending node remains blocked` | `no — the loop can
  proceed with a degraded plan, but at the following cost: ...`}}
- **Safe to defer?** `{{yes — defer until {{deadline or event}}` | `no —
  deferring loses the following opportunity: ...`}}
- **Degrade gracefully?** `{{yes — the runner will fall back to {{fallback
  policy}}; spec the fallback in the answer's `fallback_policy` field` |
  `no — there is no safe fallback; silence halts the loop indefinitely`}}
- **Affects the final goal?** `{{yes — silence after {{deadline}} causes
  the following failure_criteria to trip: ...` | `no — silence only
  delays this node; the top-level goal is unaffected`}}`

---

## Required Answer Format

The decider returns the answer as the YAML block below. The YAML is the
canonical write-back payload — it is parsed, validated against the keys
below, and written into `decision.log.md`, `loop.state.yaml`,
`checkpoint.yaml`, and any affected `loop.plan.yaml`. Free-form prose
answers are NOT accepted; the runner cannot parse them safely.

```yaml
decision_id: "{{decision_id}}"
selected_option: "<A | B | C | defer | reject | custom>"
approval_status: "<approved | rejected | needs_revision | defer>"
rationale: >
  {{One to four sentences explaining why this option was chosen. Cite the
  evidence entries by their # from the evidence table; cite any
  constraints from the top-level goal section. This rationale is
  appended verbatim to decision.log.md.}}
constraints:
  - "{{Any additional constraint this decision imposes on the loop, e.g.
    'must complete before 2026-07-15', 'must not exceed $500 in API spend',
    'must remain compatible with the v2 schema'. If none, return an empty
    list. Each constraint becomes a checkable predicate the runner
    records in loop.state.yaml -> active_constraints.}}"
allowed_actions:
  - "{{Action the runner is now permitted to take that it could not take
    before, e.g. 'write to path X', 'invoke tool Y', 'open PR to branch Z'.
    Each action is matched against the affected node's gate before
    dispatch.}}"
disallowed_actions:
  - "{{Action the runner must NOT take even though the decision is
    approved. Useful when the decider approves a path but wants a
    specific behaviour excluded.}}"
fallback_policy: >
  {{What the runner should do if the chosen option later fails its
  preconditions, e.g. 'fall back to Option B with the same constraints',
  'escalate to user again with HD-{{loop_id}}-{{next_seq}}', 'halt the
  loop and surface the blocker'.}}
additional_notes: >
  {{Any free-form context the decider wants preserved alongside the
  decision (links, references, expected follow-ups, signs of regret to
  watch for). Optional; may be empty.}}
```

### Write-back targets

After the decider returns the YAML, the runner writes it to:

1. **`decision.log.md`** — new append-only entry, header
   `## {ISO}: Human decision HD-{{loop_id}}-{{seq}} — {{selected_option}}`,
   fields filled from the YAML above; references this package path under
   `Evidence ref`.
2. **`loop.state.yaml`** — append to `human_decisions[]`; update the
   `last_decision_at` timestamp; record `active_constraints` from the
   answer's `constraints` list.
3. **`checkpoint.yaml`** — remove the matching `pending_approvals` entry
   (by `node_id` and `token`) once the approval node transitions
   (`verifying → completed` on approved/rejected, or `→ cancelled` on
   reject/abandon).
4. **`loop.plan.yaml`** (if affected) — bump `meta.plan_version` and
   record the new version under `meta.plan_history[]` when the decision
   changes scope, goal, non-goals, node topology, or hard constraints.

> **Reminder to the runner.** The YAML block is the contract. Do not
> invent extra top-level keys; do not omit the listed ones. If the
> decider writes prose, prompt them to re-wrap it as YAML rather than
> parsing the prose yourself.