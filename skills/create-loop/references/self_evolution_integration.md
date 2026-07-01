# Integration Spec — `create-loop` ↔ `self-evolution`

*Diataxis type: **reference**. This document is the authoritative adapter
specification between `create-loop` (transient task-control state) and
`self-evolution` (durable project knowledge). It defines ownership, the
promotion path from transient to durable, the trigger table for capture,
and the failure modes the boundary is designed to prevent.*

*For the field dictionary on the `create-loop` side, see
[`loop_plan_spec.md`](./loop_plan_spec.md) and
[`state_model.md`](./state_model.md). For the reasoning behind the
transient/durable split, see [`concepts.md`](./concepts.md). On the
self-evolution side, see its `SKILL.md` (mode table, inbox format,
confidence ladder) and `references/philosophy.md` (the three gaps,
eight failure modes).*

---

## 1. The boundary — who owns what

The two systems MUST NOT be conflated. They have different lifetimes,
different readers, different consumers, and different failure surfaces.

### 1.1 `create-loop` owns transient task-control state

All run-scoped execution state for ONE complex task lives under
`.agents/loop/<run-id>/` (the canonical `run_id_directory` from
[`concepts.md` §7](./concepts.md#7-why-durability-primitives) and
[`recovery_protocol.md`](./recovery_protocol.md)). This state is
**disposable once the task closes out**. The artifacts in this directory
are:

| artifact | purpose | file |
|---|---|---|
| `loop.plan` (or split fragments per the plan spec) | the DAG the loop executes against | `loop.plan.yaml` per [`loop_plan_spec.md`](./loop_plan_spec.md) |
| `checkpoint` | durable snapshot of node status, ready set, blocked, pending approvals, cost, iteration | [`state_model.md` §checkpoint fields](./state_model.md#checkpoint-fields) |
| `event_log` | append-only event log for deterministic replay | referenced from `checkpoint.event_log_ref` |
| `evidence.ledger` | append-only gate-verdict entries (`verdict: pass\|fail\|inconclusive`) | [`state_model.md` §evidence ledger](./state_model.md#evidence-ledger) |
| `node.contract` | per-node execution contract (gate, retry_policy, attempt counter) | [`state_model.md` §node.contract fields](./state_model.md#node-contract-fields) |
| `decision.log` | append-only record of architectural/operational decisions made mid-run | run-scoped, schema TBD by plan author |

All six are **execution state for one run**. They live and die with the
run. They are NOT project knowledge. They are NOT cross-run memory. They
are NOT scoped, verified, or curated.

### 1.2 `self-evolution` owns durable project knowledge

All cross-run, cross-session, cross-agent project memory lives under
`.agents/knowledge/` (per the `self-evolution` SKILL.md Filesystem
Contract). The canonical structure is exactly these seven
subdirectories — no additions, no omissions:

| directory | what it holds | churn |
|---|---|---|
| `inbox/` | append-only raw observations, timestamped, channel-marked (`[DECISION]`, `[SKILL-IDEA]`, `[DOMAIN-FIX]`, `[SKILL-FIX]`, `[SKILL-COMPAT]`, `[ERROR]`, `[INCIDENT]`) | every session |
| `domains/` | organised working knowledge per task area | weekly |
| `reference/` | low-churn reference documentation | monthly |
| `decisions/` | Architecture Decision Records (ADRs) | on decision |
| `patterns/` | verified reusable conventions that survived 2+ verification cycles | occasionally |
| `crystallized/` | executable best-practice workflows | rarely |
| `archive/` | retired knowledge (preserved, never deleted) | on retirement |

Plus two top-level companions: `manifest.json` (the machine-readable
health dashboard and inventory index, with `confidence` field values
exactly `observed` | `verified` | `canonical`) and `README.md` (the
system's self-description).

The lifecycle hooks under `.agents/hooks/` (`session-end.sh`,
`stop.sh`, `compact-recovery.sh`) plus their tool adapters (Claude
Code JSON, Cursor JSON, **OpenCode native ESM plugin at
`adapters/opencode-plugin.mjs`**, Augment JSON) keep this system
running automatically — they are part of `self-evolution`'s
ownership, not ours.

### 1.3 Why the boundary exists (cite the philosophy)

`self-evolution/references/philosophy.md` enumerates **eight failure
modes** the system is structurally defended against. Two of them are
the reason this spec exists:

- **Garbage accumulation.** "Everything captured, nothing pruned" —
  the inbox is temporary, evolution compresses, archive retires.
  Dumping a run's `checkpoint`, `event_log`, or `evidence.ledger` into
  `.agents/knowledge/` wholesale is *exactly* the failure pattern this
  mode targets: noise piles up faster than compression can drain it,
  signal-to-noise collapses, and a future session cannot tell what
  matters.
- **Zombie knowledge.** "Outdated claims persist silently" — knowledge
  in the knowledge base is implicitly treated as current by every
  consumer. A `checkpoint` snapshot is by definition a frozen past
  state of one run; promoting it to knowledge would resurrect dead
  intermediate state as if it were project fact.

The transient/durable split is not bureaucratic. It is the structural
defense against these two failure modes. Confusing them collapses the
defenses.

### 1.4 Hard rule: what MUST NOT cross

The following MUST NEVER be written from `create-loop` into
`.agents/knowledge/` directly (no copying, no mirroring, no
"snapshot for posterity"):

- `checkpoint` snapshots (whole-file or per-field)
- `event_log` entries (whole or partial)
- `evidence.ledger` entries (whole or partial)
- `node.contract` blobs
- per-node `status` churn (e.g., a transition `ready → running →
  verifying → completed` for one node)
- retry attempt counts, retry timestamps, backoff values
- `cost_units_spent`, `iteration`, `phase` values
- `next_suggested_action` strings
- `pending_approvals` open tokens
- `open_assumptions` entries that were resolved during this run

These belong in `.agents/loop/<run-id>/`. They are not knowledge. They
are execution residue.

---

## 2. The promotion path — transient → durable

Crossing the boundary is a **promotion**, not a write. A promotion is
gated, formatted, scoped, and confidence-tagged. Without the gate, the
promotion does not happen.

### 2.1 The three promotion criteria

A finding from a `create-loop` run may cross into
`.agents/knowledge/` ONLY when **all three** criteria are met:

1. **Verified.** The finding has a recorded `verdict: pass` in the
   `evidence.ledger` (i.e., a `gate` passed). A speculation, an
   observation, a hypothesis, or an unverified claim does NOT
   promote. Note this gate is on the `create-loop` side — it ensures
   the *finding* is real, not that the knowledge is independently
   cross-checked; cross-checking is `self-evolution`'s `verified`
   promotion (Mode 4 Evolve).
2. **Reusable.** The finding generalises beyond this run. A
   run-specific fact (e.g., "the retry policy for node `n47` is
   `local_patch`") is not reusable. A finding like "in this codebase,
   retry-after-patch needs `local_patch`, not `local_retry`, because
   the failure mode is deterministic" IS reusable.
3. **Decision-influencing.** The finding would change a future
   agent's decision. "Cost this run was 312 units" does not change
   a future decision. "Cost exceeded `max_cost_units` only on plans
   where `mapper` nodes ran in parallel — flag `fanout` parallelism
   for cost review" does.

If any criterion fails, the finding stays in the run's
`.agents/loop/<run-id>/closeout.md` and is NOT promoted.

### 2.2 The mechanism — append to the inbox

`create-loop` integrates with `self-evolution` by writing to its
**inbox** — the documented, public capture format from SKILL.md Mode 3
(Capture):

- File path: `.agents/knowledge/inbox/{YYYY-MM}.md`
  (zero-padded month; create the file if it does not exist; respect
  the concurrent-session safety protocol described in SKILL.md §3 —
  temporary file + atomic append, retry once on contention, fallback
  to `.tmp.{random}` if retry fails).
- Entry header format (verbatim from SKILL.md §3):
  `## {date} {time} — {what task you just completed}`
- Bullets: 2–5, in the agent's own words, capturing what surprised
  or wasn't obvious.
- Source line: `[source: ...]` referencing the originating run, e.g.
  `[source: .agents/loop/<run-id>/evidence.ledger.yaml#<entry_id>]`.

### 2.3 Proposed channel marker: `[LOOP]`

`self-evolution` defines optional channel markers as zero-friction
triage aids: `[ERROR]`, `[DECISION]`, `[INCIDENT]`, plus the four
skill-feedback tags `[DOMAIN-FIX]`, `[SKILL-FIX]`, `[SKILL-IDEA]`,
`[SKILL-COMPAT]` (see SKILL.md §3 "Optional channel markers").

We propose adding **`[LOOP]`** as an analogous marker for findings
that originated from a `create-loop` run. The header becomes:

```
## 2026-07-02 14:32 — [LOOP] Evidence gate "evaluator_optimizer" needed two extra cycles for mapper nodes in run 0c4a
```

`[LOOP]` is a *proposal*. `self-evolution` does not currently define
it; adding a channel marker is a self-evolution governance decision,
not a `create-loop` decision. Until accepted, treat `[LOOP]` as an
informal convention that helps Mode 4 (Evolve) cluster loop-originated
captures. Mode 4's clustering logic groups by *what entries are about*,
not by keyword, so the marker is a hint not a routing rule.

### 2.4 What still goes directly to `decisions/`

Per SKILL.md §3 "Recording Architecture Decisions":

> Decisions skip the inbox — they go directly to `decisions/` with
> `confidence: observed` and the context that drove the choice.

A `create-loop` run that records an architectural decision (e.g.,
"we chose event sourcing for the order module") MUST follow the same
rule: write directly to `.agents/knowledge/decisions/` using
`self-evolution`'s `references/templates/decision-template.md`. The
inbox is for *observations and findings*, not decisions.

`create-loop`'s own run-scoped `decision.log` is the source of truth
for decisions made mid-run; the ADR under `.agents/knowledge/decisions/`
is the durable, cross-run record. The ADR cites the `decision.log`
entry as its source.

### 2.5 Confidence handoff

`self-evolution`'s Hard Rule #1 (SKILL.md §Anti-Overconfidence Rules):
"All AI-generated knowledge starts as `observed`. No exceptions."

`create-loop` MUST NOT write `verified` or `canonical` confidence into
`.agents/knowledge/` — not in frontmatter, not in citations, not in
source pointers. Even when an `evidence.ledger` entry shows
`verdict: pass`, the promoted knowledge enters the inbox (or
`decisions/`) as `observed`. The promotion to `verified` is
`self-evolution`'s Mode 4 lifecycle to perform, based on 2+
corroborating sources or cross-checking against code; the promotion to
`canonical` requires human approval. `create-loop` earns the right to
be the *source* of a finding; `self-evolution` alone owns the right
to *grade* it.

### 2.6 Provenance — the source line

Every promoted entry carries a `[source: ...]` line that traces the
finding back to its run-scoped origin. The canonical form is:

```
[source: .agents/loop/<run-id>/evidence.ledger.yaml#<entry_id>]
```

Alternative source shapes, used when the finding's strongest evidence
is elsewhere in the run:

```
[source: .agents/loop/<run-id>/decision.log#L42]
[source: .agents/loop/<run-id>/node.contract.yaml#<node_id>]
[source: .agents/loop/<run-id>/closeout.md#<section>]
```

`self-evolution`'s Mode 4 traceability — "summaries must trace to
details" — is satisfied because the source points at a real
filesystem artifact in the run directory, and `manifest.json`'s
`last_verified` audit can re-read the run directory (until the run is
archived) to confirm the finding still corresponds to recorded
evidence.

---

## 3. Trigger table — which loop events are eligible

Not every event in a `create-loop` run is a knowledge candidate. The
table below is exhaustive for the events we have defined so far.

| event | source artifact | stays in `.agents/loop/` | eligible for `.agents/knowledge/` (marker) |
|---|---|---|---|
| Node transitions to a terminal status (`completed`, `cancelled`, `deprecated`) | `checkpoint.node_states` | yes (always) | no — terminal status is a per-node fact, not project knowledge |
| Node transitions to `verifying → completed` with `verdict: pass` AND finding is reusable and decision-influencing | `evidence.ledger` (pass entry) | yes (the evidence stays) | yes (`[LOOP]`); only the reusable, decision-influencing finding, not the node outcome itself |
| Gate fails (`verdict: fail` or `inconclusive`) and the failure mode is reusable | `evidence.ledger` (fail entry) + `node.contract.on_failure` ladder | yes | yes (`[LOOP]`) — as an anti-pattern / pitfall entry, only if the failure mode generalises |
| Architectural decision recorded mid-run (schema choice, vendor choice, approach pivot) | `decision.log` | yes | yes — **directly to `decisions/`** as an ADR (NOT via inbox), per SKILL.md §3 |
| Discovered invariant ("node `n` requires X to be Y before dispatch") | `node.contract`, `loop.plan` | yes | yes (`[LOOP]`) — only if the invariant is reusable beyond this run |
| Discovered pitfall ("retrying this kind of failure with `local_retry` makes it worse; use `local_patch`") | `evidence.ledger`, `node.contract` | yes | yes (`[LOOP]`) — same gate as invariant, plus it's a candidate for `domains/*/Common Mistakes` once promoted |
| Wrong assumption corrected (e.g., "we assumed X, the code does Y") | `open_assumptions`, `event_log` | yes | yes (`[LOOP]`) — these are high-value corrections |
| New pattern across multiple runs ("every plan that uses `fanout`+`join` for the same mapper problem hits the same gate") | cross-run, observed in `closeout.md` | n/a (this is a cross-run observation) | yes — possibly via `[DOMAIN-FIX]` or `[SKILL-IDEA]` marker after 3+ corroborations, per Mode 7 radar |
| Checkpoint write | `checkpoint` | yes (always) | no — checkpoints are an internal durability primitive |
| `event_log` append | `event_log` | yes (always) | no — event logs are an internal replay primitive |
| `evidence.ledger` append | `evidence.ledger` | yes (always) | no — the ledger is evidence, not knowledge; only a *finding extracted from* a ledger entry promotes |
| Per-node status churn (`ready → running`, `running → verifying`, etc.) | `checkpoint.node_states` | yes (always) | no — status churn is execution detail |
| Retry attempt count change (`attempt: 1 → 2`) | `node.contract.attempt` | yes (always) | no — retry accounting is run-scoped |
| Backoff elapsed, jitter applied | `node.contract`, `event_log` | yes (always) | no — scheduling detail |
| `cost_units_spent` increment | `checkpoint.cost_units_spent` | yes (always) | no — cost accounting is run-scoped, unless a reusable cost-shape finding emerges (then `[LOOP]`) |
| `iteration` increment | `checkpoint.iteration` | yes (always) | no |
| `pending_approvals` open / close | `checkpoint.pending_approvals` | yes (always) | no |
| `next_suggested_action` change | `checkpoint.next_suggested_action` | yes (always) | no — advisory only |
| `open_assumption` resolution | `checkpoint.open_assumptions`, `event_log` | yes | yes (`[LOOP]`) ONLY if the assumption reveals a reusable property of the task class |
| Run closed out (all nodes terminal, termination condition met) | `closeout.md` | yes | no — closeout is run-scoped output |
| Cross-run pattern emerges (3+ runs, same finding) | multiple `closeout.md` files | n/a (cross-run) | yes — eligible for promotion to `patterns/` per SKILL.md Mode 4 promotion criteria; entered via inbox first as `[LOOP]` |

The left column is a closed list of `create-loop` events. The middle
column is "always" by default; the right column is "only if the
finding clears the three promotion criteria in §2.1."

---

## 4. Session startup — two independent recoveries

A fresh agent on a project that has both systems installed performs
**two independent recoveries**. They share no state and have no
dependency on each other.

### 4.1 Recovery 1 — `create-loop` recovers task state

Per [`recovery_protocol.md`](./recovery_protocol.md) §2 and
[`state_model.md` §resume-from-blank-session](./state_model.md#resume-from-a-blank-session),
the recovery algorithm reads ONLY `.agents/loop/<run-id>/` artifacts:

1. Locate the `run_id_directory` (single-flight check).
2. Read the latest `checkpoint`.
3. Verify evidence: every `completed` node must have a matching
   `evidence.ledger` entry with `verdict: pass`; demote otherwise.
4. Verify consistency: `node_states` vs `loop.plan.nodes`, every
   `evidence_ref` resolves.
5. Rebuild the ready set from the topological readiness rule.
6. Check termination (`iteration`, `cost_units_spent`,
   `failure_criteria`).
7. Identify ready nodes and dispatch.

**This recovery MUST NOT depend on `.agents/knowledge/`**. It MUST
NOT read `AGENTS.md`, `manifest.json`, `domains/*.md`, or any other
`self-evolution` artifact. The reason is the same as the rule that
the resume algorithm reads only durable run state: if the knowledge
base is corrupted, missing, partially initialised, or stale, the loop
must still continue.

### 4.2 Recovery 2 — `self-evolution` provides project knowledge

Independently, the agent (or the host session) loads
`self-evolution`'s public surface — `AGENTS.md` (router),
`manifest.json` (index), and (if present) `domains/` and
`patterns/`. This gives the agent:

- where to look for module-specific conventions,
- which patterns the project has promoted,
- what recurring themes exist in `inbox/`,
- which decisions are recorded.

### 4.3 Independence property

The two recoveries are independent:

| failure | effect on `create-loop` recovery | effect on `self-evolution` recovery |
|---|---|---|
| `.agents/loop/<run-id>/` corrupted or missing | resume fails; loop escalates to `blocked` and surfaces a `pending_approval` | none |
| `.agents/knowledge/` corrupted or missing | none — `create-loop` does not depend on it | `self-evolution` rebuilds from filesystem per SKILL.md Mode 4 manifest recovery |
| Both missing | fresh start (loop from `pending`, knowledge from empty) | fresh start |
| Only one present | the present one works normally | the present one works normally |

Losing one does NOT corrupt the other. Each system can be
re-initialised independently. The boundary is the value of the
boundary.

### 4.4 create-loop does not write task state into knowledge

`create-loop` MUST NOT, at any point in recovery or execution,
write `node_states`, `ready_set`, retry counters, `event_log`
entries, `evidence.ledger` entries, `cost_units_spent`, or
`iteration` into `.agents/knowledge/`. This is the same rule as
§1.4 restated for the recovery path: even the temptation to "snapshot
the checkpoint for future reference" is forbidden — that's what
`.agents/loop/<run-id>/` already is.

---

## 5. Degradation — self-evolution is optional

The integration is an **adapter layer**, not a hard dependency.

### 5.1 When `.agents/knowledge/` is absent

If `.agents/knowledge/` does not exist (project never initialised
`self-evolution`, or the user opted out, or it was deliberately
removed), `create-loop` still works fully. The findings that would
have promoted to the inbox stay in the run's `closeout.md` instead.
The three promotion criteria in §2.1 are still applied — but their
output goes to `closeout.md` (a run-scoped artifact), not to a
cross-run knowledge base.

The check is cheap: `if [.agents/knowledge/ exists]` gates the
promotion step. The check is performed once per closeout, not per
finding.

### 5.2 When `.agents/loop/` is absent

If `.agents/loop/` does not exist, this spec does not apply — there
is no `create-loop` run in progress. The agent either starts a new
run (which creates `.agents/loop/<run-id>/` per the single-flight
rule) or is not using `create-loop`.

### 5.3 No copy of self-evolution internals

`create-loop` integrates by **writing to self-evolution's documented
public surface only** — specifically, the inbox file format (SKILL.md
§3) and the `decisions/` directory. It does NOT:

- copy `init-scaffold.sh`, `scan-project.sh`, or `audit-agents.sh`,
- copy `topic-template.md`, `decision-template.md`,
  `pattern-template.md`, or `crystallized-template.md`,
- embed `session-end.sh`, `stop.sh`, `compact-recovery.sh`, or the
  `opencode-plugin.mjs` adapter,
- import or invoke `self-evolution`'s scripts,
- reimplement Mode 4 (Evolve), Mode 5 (Health Check), Mode 6
  (Crystallize), or Mode 7 (Skill Maintenance).

The integration boundary is "format compliance with the public
contract", not "internal reuse". This is the same posture as a
well-behaved API client: respect the contract, don't reach into the
implementation.

### 5.4 Complementarity with `compact-recovery.sh`

`self-evolution`'s `compact-recovery.sh` hook (SKILL.md §Hooks
Integration) injects a re-read directive after context compaction,
reminding the agent to re-read the knowledge surface.

`create-loop`'s recovery is complementary, not duplicative:

- `compact-recovery.sh` recovers *project knowledge* (what the
  project is, what conventions apply, what past decisions bind
  future work).
- `create-loop`'s resume algorithm recovers *task state* (where this
  run is in its DAG, what nodes are pending, what evidence is
  recorded).

A single agent session that runs `create-loop` in a `self-evolution`-
enabled project experiences both: the project knowledge refreshes on
compact, the task state refreshes on loop resume. Neither subsumes
the other.

---

## 6. Worked example — promotion in practice

A minimal end-to-end example, illustrating all the rules above.

### 6.1 The run

Suppose `create-loop` runs `loop.plan` `p-2026-07-02-001` with
`run_id` `r-0c4a`. Inside the plan, a `mapper` node `n47` runs an
`evaluator_optimizer` gate. The gate fails twice (`verdict: fail`,
attempts 1 and 2), then passes on attempt 3 after the `local_patch`
ladder step adjusts the prompt. The reusable finding is:

> "When the evaluator in an `evaluator_optimizer` gate rates the
> candidate below 0.4 for two consecutive attempts, a `local_patch`
> that increases the rubric specificity by one dimension is more
> effective than another `local_retry`."

### 6.2 The evidence

The finding is grounded in three `evidence.ledger` entries:

- `e-001`: `verdict: fail`, `score: 0.31`, `attempt: 1`,
  `gate_kind: evaluator_optimizer`.
- `e-002`: `verdict: fail`, `score: 0.35`, `attempt: 2`,
  `gate_kind: evaluator_optimizer`.
- `e-003`: `verdict: pass`, `score: 0.82`, `attempt: 3`,
  `gate_kind: evaluator_optimizer`. The `rationale` field records the
  rubric-specificity patch.

### 6.3 The promotion

At closeout, `create-loop` checks the three promotion criteria:

1. Verified? Yes — `e-003` has `verdict: pass`.
2. Reusable? Yes — the failure-and-recovery pattern generalises to
   any `evaluator_optimizer` gate, not just `n47`.
3. Decision-influencing? Yes — a future agent authoring a new
   `evaluator_optimizer` gate node would benefit from starting with
   a more specific rubric instead of waiting for two failures.

All three pass. `create-loop` writes to the inbox:

```markdown
<!-- Appended to .agents/knowledge/inbox/2026-07.md -->

## 2026-07-02 16:48 — [LOOP] Evaluator_optimizer gates recover faster with rubric specificity than with local_retry

- Two consecutive sub-0.4 scores on an evaluator_optimizer gate in
  run r-0c4a: local_retry did not move the score; a local_patch that
  added one rubric dimension lifted the next attempt from 0.35 to
  0.82.
- The threshold "two consecutive <0.4" is now a candidate heuristic
  for choosing the on_failure ladder step at plan-design time.
- [source: .agents/loop/r-0c4a/evidence.ledger.yaml#e-003]
```

The entry uses the channel marker `[LOOP]`. It enters the inbox as
`observed` (the confidence is implicit; SKILL.md does not require
frontmatter on inbox files). The source line traces back to the run
directory.

### 6.4 What does NOT get promoted

For the same run, the following stay in `.agents/loop/r-0c4a/`
only:

- the three `node.contract.attempt` values (`1`, `2`, `3`),
- the `cost_units_spent` after each attempt,
- the `event_log` entries recording the prompts sent,
- the `checkpoint.node_states` transitions for `n47`,
- the full text of `e-001` and `e-002` (the failures — only the
  pass entry `e-003` is cited, because the failures are not
  reusable on their own; the *recovery pattern* is reusable, but the
  failure detail is not).

### 6.5 What `self-evolution` does next

The user later triggers `self-evolution` Mode 4 (Evolve). Mode 4
reads `inbox/2026-07.md`, sees the `[LOOP]` cluster, and (assuming
2+ corroborating entries from other runs) promotes the finding from
`observed` to `verified` and moves it into `domains/gates.md` or
`patterns/evaluator_optimizer-recovery.md`. Mode 4 owns the grade.
`create-loop` only contributed the source.

---

## 7. Failure modes of the boundary itself

The boundary fails in predictable ways. We name them so they can be
detected and corrected.

### 7.1 Leakage — transient state written into knowledge

Symptom: `.agents/knowledge/domains/` or `inbox/` contains a
checkpoint snapshot, a `node.contract` blob, or a status-transition
log.

Detection: `self-evolution` Mode 5 (Health Check) flags a domain
file whose `scope:` field points at `.agents/loop/` (or whose sources
are all run-scoped artifacts). Mode 4 (Evolve) review of new domain
content catches it earlier.

Repair: move the offending content back to `.agents/loop/<run-id>/`,
leave a `[DOMAIN-FIX]` inbox entry explaining the move.

### 7.2 Over-promotion — findings written without the gate

Symptom: a run writes "knowledge" to `.agents/knowledge/` for a
finding whose `evidence.ledger` entry shows `verdict: fail` or
`inconclusive`, or for a finding that is not reusable or not
decision-influencing.

Detection: spot-check in Mode 4 clustering — entries whose source
points at a `fail` ledger entry are flagged.

Repair: remove the entry, log the correction under the project's
correction history, leave a `[DOMAIN-FIX]` note.

### 7.3 Confidence inflation — `verified`/`canonical` written by create-loop

Symptom: an inbox entry or ADR has a `confidence: verified` or
`confidence: canonical` field, written by `create-loop`.

Detection: SKILL.md Hard Rule #1 makes this a hard rule violation;
Mode 4 demotes the confidence to `observed` on next evolution
regardless of who wrote it.

Repair: edit the frontmatter; cite the source gate (`verdict: pass`
in the originating ledger) so Mode 4 can independently promote later.

### 7.4 Marker drift — `[LOOP]` overloaded

Symptom: `[LOOP]` is used for findings that did not originate from a
`create-loop` run, or for findings that are not actually promotion
candidates (status churn, retries).

Detection: spot-check: do `[LOOP]` entries cite a
`.agents/loop/<run-id>/` source path?

Repair: edit or remove the offending entries; reaffirm the marker's
intended meaning at next team sync. (If `[LOOP]` is formally accepted
by `self-evolution` governance, this becomes a `[SKILL-FIX]` against
the marker definition.)

### 7.5 Coupled recovery — create-loop depends on knowledge

Symptom: a future agent modifies `create-loop` to read
`AGENTS.md` or `manifest.json` at startup, treating project knowledge
as part of the resume algorithm.

Detection: code review on `create-loop` resume path; lsp_diagnostics
on import surface; integration test that runs `create-loop` against a
fresh project with no `.agents/knowledge/`.

Repair: revert the dependency; the resume algorithm reads only
`.agents/loop/<run-id>/`.

---

## 8. Open questions

These are questions this spec does NOT resolve and should be raised
in `self-evolution`'s inbox (or its `decisions/`) for governance
attention.

- Should `[LOOP]` be formally adopted as a channel marker in
  `self-evolution` SKILL.md? This spec treats it as a proposal.
  Governance lives in `self-evolution`, not here.
- Should `create-loop`'s `decision.log` schema and
  `self-evolution`'s ADR template be cross-aligned (so a tool can
  mechanically translate one to the other)? Currently they are
  separate; the spec recommends manual translation with cross-citation.
- Should `self-evolution`'s `manifest.json` expose a count of
  `[LOOP]`-marked inbox entries per month, so a project can see
  "this month the loops produced N knowledge candidates"? This would
  require a `self-evolution` schema change; the spec does not
  presume it.
- How should archived runs (`.agents/loop/<run-id>/` moved to a
  long-term archive) affect the `[source: ...]` traceability? The
  source path becomes stale once the run directory is archived or
  pruned. Resolution options: re-point to the archive path, or
  accept that very old entries have stale sources (with `last_verified`
  doing the staleness work).

---

## See also

- [`loop_plan_spec.md`](./loop_plan_spec.md) — plan/node field
  dictionary, gate object, retry policy, escalation ladder.
- [`state_model.md`](./state_model.md) — node status enum, state
  transition table, checkpoint / `node.contract` / `evidence.ledger`
  field sets, resume-from-blank-session algorithm.
- [`concepts.md`](./concepts.md) — why the model is shaped this way
  (durability primitives, degraded mode, DAG vs checklist).
- [`recovery_protocol.md`](./recovery_protocol.md) — the recovery
  algorithm `create-loop` uses; **independent of this integration**.
- `self-evolution` SKILL.md — Filesystem Contract, Mode 3 (Capture),
  Mode 4 (Evolve), Anti-Overconfidence Rules, Hooks Integration.
- `self-evolution` `references/philosophy.md` — the three gaps, the
  ten-stage knowledge lifecycle, the eight failure modes (cited in
  §1.3 and §1.4 above).