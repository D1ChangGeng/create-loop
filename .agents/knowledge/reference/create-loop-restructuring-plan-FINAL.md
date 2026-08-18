---
type: reference
confidence: observed
scope: ["skills/create-loop/"]
sources: ["skills/create-loop/references/protocol_v2.md", ".agents/knowledge/reference/redesign-execution-plan-2026-07.md"]
last_verified: 2026-07-31
created: 2026-07-30
---

# `create-loop` — Final System-Level Restructuring Plan

**Status:** historical design input, partially implemented and superseded as current-state
authority on 2026-07-31. The live contract is the repository source, executable tests, and
`skills/create-loop/references/protocol_v2.md`; this plan remains the rationale and rollout record.
It superseded `subtraction-plan-2026-07.md` and conflicting parts of
`redesign-execution-plan-2026-07.md` at the time it was written.
**Baseline verified 2026-07-30:** SKILL.md 803 lines · references/ 20 files 9,704 lines ·
templates/ 19 files 2,344 lines · schemas/ 11 · scripts/checks/ 14 modules · tests/ 2,954 lines ·
examples/ 4 loop dirs · **total 22,849 lines** · rules R1–R41 (next free: **R42**) ·
15 node statuses · 8 node kinds · 8 gate kinds · installer 15/15 green.

---

## THE GOVERNING TEST

Every mechanism that survives must complete this chain:

> **records/processes WHAT information → changes WHAT later judgment or action → improves WHAT in the delivered result**

Two corollaries, both earned from evidence:

1. **A check is worth its cost only if its verdict comes from something other than the thing being checked.** (Chen arXiv:2504.03846 — self-preference persists at ~86% on MATH500 specifically when the model's own answer is objectively wrong.)
2. **Programs verify determinable low-level facts. The model judges what those facts mean and what to do next.** A validator may prove only the condition it actually inspected and may never extrapolate to a high-level goal.

Success is not structural completeness. It is whether the agent makes better judgments, takes
more valuable actions, and delivers more professional systems.

---

## 1. CURRENT-STATE DIAGNOSIS

Five structural problems, each measured rather than asserted.

### 1.1 Attention inversion (the root defect)

Advancing ONE node `todo → in_progress → done` mandates **~78 field-writes across 7 files**. A
blank-session resume reads back **~8**. Ratio **9:1**. For a 20-node loop: ~1,560 mandated
field-writes.

`checkpoint.yaml` is a **full rewrite** on every advance — every node's state re-emitted even when
unchanged. `node.contract.yaml` changes 4 fields and copies 9 verbatim. The protocol's own State
Authority Order (`recovery_protocol.md:340`) declares the event log primary and "every other state
file is a projection of it" — then mandates ~38 projection writes per advance anyway.

The per-node sequence (`SKILL.md:503-515`) is structurally **a write pipeline with execution
sandwiched inside it**. It should be execution with a write at the end. This is the mechanical
cause of the reported symptom: the agent's visible objective becomes field maintenance.

### 1.2 Authority contradiction on the most critical path

- `recovery_protocol.md:340` + `:183` + `event_log.schema.json:5` — the event log is **PRIMARY**; everything else is a projection.
- `SKILL.md:577` — opening line of **Mode C, the blank-session resume path**: *"The checkpoint is the only source of truth."*
- `state_model.md`'s 9-step resume algorithm **never replays the log** (0 mentions).

So the two documents a resuming agent actually reads contradict the authority order the protocol
declares. A stale checkpoint is *believed* on exactly the path where staleness is most likely.

Compounding it: the checkpoint has **no `last_event_seq`** field (verified absent), so freshness is
not checkable — which is *why* the resume path quietly opts for blind trust.

### 1.3 Assurance collapse

Of 8 gate kinds, only 2 produce a verdict from outside the agent: `automated_check`/`test` (exit
code) and `human_approval` (external party). `artifact_exists` is externally grounded but proves
only existence. The remaining four — `llm_judge`, `self_consistency`, `evaluator_optimizer`,
`step_verifier` — are the agent grading its own work.

All 8 write the same `verdict: pass` into the same field. **No reader distinguishes them.** A
node completes identically whether a test passed or the model liked its own output.

R36 (generator≠verifier) exists but is **semantically unfalsifiable**: the ledger carries no
producer/verifier/session/model identity, only one of four role strings, so a producing agent can
label its own verdict `verifier: subagent`.

### 1.4 Missing readers on the goal contract

`success_criteria`, `failure_criteria`, `non_goals`, `constraints`, `scope` are written at charter
time and **never re-read at dispatch**. `SKILL.md:506` has the runner read `checkpoint, contract,
ledger` — never the goal.

This is a **missing-reader defect, not a useless-field defect**, and it is the mechanical cause of
goal drift. (Partial exception verified: `failure_criteria`, `max_iterations`, `max_cost_units` ARE
read at `state_model.md:321-328` step 5, and `open_assumptions` at `:308`. The termination check
exists; the *dispatch* check does not.)

### 1.5 Over-extrapolation: programs deciding semantic questions

Three proven instances:

- **R5 is presence-only.** `checks/nodes.py:28` is literally `if field not in node`. A node with all 21 required fields present but `title: ""` and `preconditions: []` **passes** (constructed and confirmed). R5 proves *filled-in*; the docs read a passing plan as structurally sound. 字段完整 ≠ 信息充分.
- **`score` is a semantic judgment wearing a number's clothes.** `llm_judge` = "A separate LLM scores the node's output against a rubric" (`evidence_gates.md:126`). No validator compares `score` to `threshold` — **and that absence is correct.** Adding the comparison would grant a fabricated opinion deterministic authority over completion.
- **`INTEGRITY OK` over-claims in its name.** It verifies cross-file reference consistency; the string asserts whole-loop integrity. Empirically: a directory containing only `loop.plan.yaml` — no checkpoint, no ledger, no event log — prints `INTEGRITY OK` and exits 0. It certifies an unresumable loop as healthy.

### 1.6 Secondary findings

- 1,509 lines of shipped **raw agent transcripts** (`research_dags_multiagent.md`, `research_durable_loops.md`) opening with `Task ID: bg_...` / `Duration: 10m 52s`. They carry **54 inbound citation links** from 8 reference files, 7 inside the locked gate-kind table. (`research-sources.md`, 317 lines, is a clean cited report — **preserve**.)
- `self_evolution_integration.md` — 690 lines, 0 validators, 0 schema fields.
- Persona/hat labels in 2 places: "architect · project lead · layout designer" vs "executor · researcher · engineer · verifier" (`recursive_planning_immersive_execution.md:93-94`), and "You are three things at once" (`interview_brief.md:60-76`). Same agent, same context, no independent verdict.
- `mapper` and `fanout`: **0 instances** across all 4 worked examples.
- `recursive_loops.md:52` "to arbitrary depth" contradicts `termination.max_depth` (R28, enforced at `caps.py:41`).
- Only **R1–R18** have a runnable fixture script; R19–R41 are prose-only.
- The green acceptance gate never exercises 6 of the 11 artifact kinds it nominally validates.

---

## 2. TARGET ARCHITECTURE

### 2.1 The shape

```
                    ┌─────────────────────────────────────────┐
   CHARTER  ────────▶  goal · success · constraints · non-goals · authority
   (stable)          └──────────────┬──────────────────────────┘
                                    │ re-read at every dispatch, mutation,
                                    │ verification, termination  ◀── the fix for §1.4
                                    ▼
   PLAN     ────────▶  executable topology + real dependencies
   (revisable)         MUST persist: no code holds it — the plan IS the program
                                    │
                                    ▼
   ┌────────────────── THE LOOP (one node advance) ──────────────────┐
   │  ORIENT   read charter + frontier + memory        (writes: 0)   │
   │  DECIDE   name the highest-value next action      (writes: 0)   │
   │  WORK     research · design · implement · verify   (the point)  │
   │  EVIDENCE gather from a source outside the work                 │
   │  JUDGE    model decides: done? progressed? next?   ◀── semantic │
   │  COMMIT   ≤3 appends, nothing written twice                     │
   └─────────────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
   EVENT LOG (truth)      LEDGER (verdicts +      MEMORY (facts · failures ·
   append-only            assurance provenance)   decisions · assumptions)
              │                     │                     │
              └─────────▶ CHECKPOINT (derived cache + last_event_seq) ◀──┘
                          PROGRESS (cold-start, human-readable)
```

### 2.2 The three authorities, permanently separated

| Authority | Owns | May conclude | May NEVER conclude |
|---|---|---|---|
| **Program** | determinable facts | "this field is absent", "this path does not resolve", "exit code was 1", "seq is not monotonic" | anything about sufficiency, correctness, progress, or completion |
| **Tool** | external reality | "the API returns X", "the test failed at line N", "the build produced this artifact" | what the observation implies for the design |
| **Model** | meaning + direction | done? progressed? sufficient? risk resolved? next action? change course? | that its own opinion constitutes verification |

**The load-bearing rule:** a program may prove only the condition it inspected. Passing never
propagates upward into a goal claim.

### 2.3 What replaces "the checkpoint is the only source of truth"

The event log is truth. The checkpoint is a **freshness-checkable cache**:

- add **`last_event_seq`** (absent today) — the log position the snapshot incorporates;
- on resume: `last_event_seq == max(log.seq)` ⇒ cache provably fresh, skip replay; else replay the **tail only**;
- the checkpoint is written at **boundaries**, not on every advance.

**But the checkpoint cannot become derived-only.** The event log has exactly 4 event kinds
(`pre_effect`, `post_effect`, `note`, `mutation`) and **no approval or blocked event**. §3.2.2
lists only `node_states`, `cost_units_spent`, `iteration`, `attempt` as recomputable. Therefore
`pending_approvals`, `blocked`, and `open_assumptions` are **not reconstructible by replay** — a
pure-log design would silently lose pending human approvals across a session boundary, the single
worst loss available, because a human is waiting on exactly that state.

---

## 3. MECHANISM AUDIT

### KEEP UNCHANGED — proven value, intact causal chain

| Mechanism | Chain | Why untouchable |
|---|---|---|
| Charter interview: Discovery-vs-Decision routing | records who can answer a question → routes research to subgraphs and authority to the user → prevents both low-context interrogation and unauthorized decisions | The one role mechanism in the skill that works, because it routes by *who can answer*, not by job title |
| `assignee: user` | records that a decision needs external authority → blocks until answered → prevents unauthorized irreversible action | Real capability gap; `human_approval` is the only gate whose `verifier: user` may produce a verdict |
| `assignee: subagent` + context isolation | records an independent execution context → its finding is evidence not echo → catches what the main line missed | *"Two subagents that share context are not parallel; they are one subagent with split attention"* — the sharpest line in the skill |
| Write-ahead bracket (`pre_effect`/`post_effect` + `idempotency_key`) | records intent before a side effect → resume can tell done from in-doubt → prevents duplicate irreversible effects | The only crash-safety primitive; loss is unrecoverable |
| Root-cause classification (`execution_intelligence_policy.md:146-167`) | records which of 7 things is actually wrong → fixes cause not symptom → prevents green-by-patching | Strongest behavioral instruction in the skill |
| Counterexample review (`:198-211`) | records boundary conditions and hidden dependencies → design changes before code exists | Second strongest; both survived a metric that nearly deleted them |
| Live Loop admission criteria | records why discovered work is necessary → admits only goal-advancing growth → distinguishes completeness growth from scope creep | Mature feedback-correction machinery, ~135 lines, procedure-specified |
| 4-rung escalation ladder | records failure severity → selects retry/patch/replan/escalate → bounds thrash | Bounded, enforceable, real behavioral branch |
| Child-loop return contract + closeout | records the delta crossing an isolation boundary → parent applies results → recursion rejoins correctly | Only channel across the boundary; isolation is meaningless without it |
| Tombstone rule for retired nodes | records why work vanished → later readers distinguish superseded from cancelled → prevents silent history loss | Cheap, and R-numbers are pinned to fixtures |
| 4 worked examples | ~90% load-bearing (empty-field tax ~10%) | Verified: not ceremony |

### SIMPLIFY — right mechanism, wrong cost

| Mechanism | Now | Becomes | Why |
|---|---|---|---|
| `checkpoint.yaml` | 17-18 fields, **full rewrite every advance** | + `last_event_seq`; written at **boundaries** (approval requested, node blocked, phase rollover, session end) + periodic | Removes the single largest hot-path write; log already holds truth |
| `node.contract.yaml` | 12 fields, 9 copied verbatim per advance | reference the plan; keep only `attempt`, `status`, `started`, `finished` | 9 fields are a projection of immutable plan data |
| `claim` | 7 fields, every advance | 2-3 (`owner`, `lease_expires_at`, `delegated_to`), **and only in concurrency mode** | `state_model.md:147` already exempts single-agent mode; claims are pure tax there |
| 15 node statuses | all 15 always | audit each transition's reader; retain those with a distinct behavioral branch (~8 expected: `pending`, `ready`, `running`, `blocked`, `waiting_user`, `verifying`, `completed`, + terminal) | Several discovery/verification microstates have no distinct reader |
| Human Decision Package | 15 sections mandatory | **risk-scaled**: 5 sections default, full 15 only for irreversible/high-risk | 15 sections + 8-key YAML + 4 write-back targets for every approval is disproportionate |
| `handoff.md` | 12 sections (H1–H12) | **resume block**: where state lives · what was mid-flight · next command | The state contract IS the handoff; 12 sections duplicate it |
| `self_evolution_integration.md` | 690 lines in the operational surface | ~80-line optional adapter, moved out of the core read path | 0 validators, 0 schema fields, optional by its own admission |

### MERGE — duplicate homes for one fact

| Merge | Into | Evidence |
|---|---|---|
| `loop.state.yaml` (10 fields/advance) | `checkpoint.yaml` | `state_model.md:289-291` calls it "a convenience cache, always reconcilable"; `recovery_protocol.md:344` ranks it #5 below the artifacts it projects. The resume algorithm reads `checkpoint.ready_set`, not `loop.state.ready_set`. |
| `run.log.md` narrative | `progress.md` **surprise register** | `recovery_protocol.md:347` — "never a source of machine truth". What survives is the unexpected, which no artifact captures |
| `decision.log.md` | `memory.md` § Decisions | Most entries are projections of git + event log; only *rejected options* are unrecomputable |
| `node.runtime.yaml` | plan subgraph / node-local task list | A second 10-field graph system for the same purpose |
| `artifact.index.yaml` | conditional module, activate only on competing versions | Git + explicit node `produces` cover ordinary work |
| `loops.index.yaml` | generated on demand by `/loop-status` | Accelerates discovery; does not determine correctness |

### REBUILD — mechanism must change shape

| # | Rebuild | From → To |
|---|---|---|
| **B1** | **Gate assurance** | 8 gate kinds all writing identical `verdict: pass` → add an **`assurance` axis orthogonal to gate kind**: `external` (exit code / tool observation / real system) · `blind` (independent context, claim withheld) · `self_attested` (model opinion). Only `external` and `human_approval` may authorize `completed`. `self_attested` yields `provisional` and must be re-grounded before it can close a criterion. **Gate kinds are NOT deleted and the enum is NOT extended** (R7's fixture depends on it). |
| **B2** | **Goal-contract readers** | written-never-read → mandatory re-read at **dispatch · mutation · verification · termination**. Programs check only that a cited criterion id **resolves**; whether it is *satisfied* is the model's judgment. |
| **B3** | **Authority contract** | `SKILL.md:577` "checkpoint is the only source of truth" → "the event log is the source of truth; the checkpoint is a cache trusted only where `last_event_seq` proves it fresh". Add `last_event_seq`. Make replay tail-only. |
| **B4** | **R5's claim** | message implies completeness → message states presence only, and the docs state *presence is not sufficiency; content adequacy is a semantic judgment the runner must make and record*. **Do NOT add a non-empty check** — a non-empty `preconditions` is not a *correct* `preconditions`; that relocates the same error one level up. |
| **B5** | **`INTEGRITY OK`** | over-claiming name → `CROSS-FILE REFERENCES OK`, enumerating what ran. Also: require checkpoint + ledger + event log to exist, and **load** the log (currently never opened). |
| **B6** | **Independence proof** | `verifier` role string a producer writes about itself → **information barring**: the reviewer receives artifact + criteria, never the producer's verdict or rationale. Verdict written **before** the producer's claim is read; mtime proves **ordering only** — never blindness. Plus a **dissent record**: overriding a blind reviewer costs an explicit entry, making rubber-stamping auditable. |
| **B7** | **`mapper`/`fanout`** | 0 instances of dead vocabulary → the **design tournament**: N competing designs in isolated contexts with planned casualties, selected by blind review. Exploits cheap parallel spawn — a real AI/human-team asymmetry. Resolves the dead-vocabulary question by giving it a job. |
| **B8** | **Per-node sequence** | 10-step write pipeline → **ORIENT / DECIDE / WORK / EVIDENCE / JUDGE / COMMIT** (§6). `command/loop-run.md:20-40` mirrors this and must move in the same commit. |

### DELETE — fails the 4-reader test (no validator AND no instruction AND no template AND no closeout/human reader)

| Delete | Evidence | Rollback |
|---|---|---|
| Persona/hat labels (2 sites) | No validator, no schema field, no template field. The *question sets* live in the same tables and are **preserved** as phase checklists — the questions were the value, the titles the costume | Prose-only, zero coupling; single-commit revert |
| `runtime_subgraphs[].owner_agent` | 0 script hits; 1 descriptive mention as an "optional enhancement field" | One commit per field |
| `retirement.retired_at` | 0 script hits; audit-only, no consumer (the `reason` stays) | One commit per field |
| Audited `schema_version` instances | Delete **only** instances with no required-tuple reader; keep where one exists | Per-instance |
| 2 research transcripts (1,509 lines) | Raw `Task ID:` / `Duration:` transcripts, no normative instruction | **Requires 54-link citation repair in the same commit** — convert each to text attribution, never touch the gate-kind enum values |

**EXPLICITLY NOT DELETED** (each has a verified live reader — I claimed otherwise and was wrong):
`recorded` (required tuple, `validate_loop_plan.py:196`) · `cache_key` (`CONTRACT_REQUIRED`,
`checks/__init__.py:89`) · `jitter` (backoff formula, `exception_handling.md:337-361`) ·
`created_at`/`created_by` (`LOOP_META_REQUIRED`, `:99`) · `heartbeat_at` (`CLAIM_REQUIRED`
+ lease mechanism) · `research-sources.md` (clean cited report) ·
`execution_intelligence_policy.md` (strongest behavioral instructions in the skill).

**CANCELLED, NOT DELETED — the threshold check.** Enforcing `score >= threshold` would grant a
fabricated model number deterministic authority over completion. The absence is **correct** and
`evidence_gates.md` must say why, so a later maintainer does not "fix" it back.

---

## 4. MINIMUM NECESSARY SCHEMA

### 4.1 Four core + two conditional

| Schema | Verdict | Holds | Consumer + moment | Loss if absent |
|---|---|---|---|---|
| `loop.plan.yaml` | **CORE, slim down** | goal contract + executable topology + real dependencies | runner at every dispatch | No decomposition; **topology must persist — no code holds it here** |
| `event_log.jsonl` | **CORE, extend kinds** | append-only causal history + effect brackets | resume reconciliation; in-doubt detection | Cannot distinguish done from in-doubt ⇒ duplicate irreversible effects |
| `evidence.ledger.yaml` | **CORE, add `assurance`** | verdict + **who produced it** + artifact pointer | completion decision; resume verification | Completion rests on assertion |
| `checkpoint.yaml` | **CORE, add `last_event_seq`** | frontier cache + the 3 non-reconstructible fields | resume orientation | Full replay every resume; **pending approvals lost** |
| `loop.meta.yaml` | **CONDITIONAL** — recursion only | identity + parent relation + return contract | child→parent rejoin | Child results can't find their parent node |
| `claim` | **CONDITIONAL** — concurrency only | lease | second worker | Duplicate dispatch (only if concurrent) |

Merged away: `loop.state`, `node.contract`, `node.runtime`, `artifact.index`, `loops.index`.
**11 → 4 core + 2 conditional.**

### 4.2 Node fields: 21 → 10 required

**REQUIRED** (each names its consumer):

| Field | Consumer + moment | Decision changed |
|---|---|---|
| `id` | graph validation; every cross-reference | identity |
| `kind` | `GATE_REQUIRED_KINDS`; tier behavior | whether a gate is mandatory |
| `title` | human reading the plan cold | orientation (human reader is a legitimate consumer) |
| `status` | dispatch; resume | whether it may run |
| `requires` | readiness recompute | dispatch order |
| `gate` | completion | what evidence is needed |
| `on_failure` | escalation ladder | which rung fires |
| `risk` | verifier-independence rule; gate selection | whether blind review is mandatory |
| `assignee` | authority routing | agent vs user vs subagent |
| `design_invariant` | top-level governance rule | whether it may live at top level |

**OPTIONAL-WHEN-APPLICABLE** — present when they carry information, **absent when they do not**
(this is what kills the empty-sentinel tax at its source): `produces`, `inputs`, `preconditions`,
`postconditions`, `retry_policy`, `priority`, `parallelizable`, `allow_subgraph`, `subgraph`,
`child_loops`, `notes`, `retirement`.

The 21-field mandate is what makes example plans 662 lines and makes R5's presence check look like
completeness. Removing the empty-sentinel requirement removes both problems without deleting a
single semantically useful field.

### 4.3 Field retention test — all 8 must pass

1. what information does it hold? 2. who consumes it, at what moment? 3. what decision changes?
4. what is the observable loss without it? 5. does an equivalent source exist? 6. is it worth
generate+read+update+maintain cost? 7. model-generated, program-generated, or tool-provided?
8. must it persist, or does it only belong in the current reasoning context?

---

## 5. MODEL / PROGRAM / TOOL AUTHORITY MATRIX

### 5.1 Program — determinable facts only

| Program verifies | It proves ONLY | It must NOT conclude |
|---|---|---|
| required field present | the key exists | the content is adequate |
| type / format / enum valid | the value is well-formed | the value is correct |
| path / reference resolves | the target exists | the target is right |
| numeric bound satisfied | the number is in range | the budget was well spent |
| test exit code | the command's exit status | the design is correct |
| `seq` strictly monotonic | ordering integrity | causal correctness |
| cited criterion id resolves | the id exists | the criterion is satisfied |
| file exists at artifact path | a file is there | the artifact is valid evidence |
| verdict-file mtime ordering | which was written first | that the reviewer was blind |

### 5.2 Tool — external reality (the only source of `assurance: external`)

Documentation and primary sources · real API behavior · test/build/type-check results · runtime
observation · git state · the user's literal answer.

**These are the only verdict producers that cannot flatter the work.**

### 5.3 Model — meaning and direction (never delegable to a program)

Is the task actually complete? · Does the deliverable meet the goal? · Is the analysis sufficient
and did it find the core problem? · Is the approach sound? · Is the risk substantively resolved? ·
Should the status change? · What is the highest-value next action? · Must direction, assumption, or
technical path change? · **Is this work formally complete but actually ineffective?**

### 5.4 Collaboration

```
Program: "field absent" · "path unresolved" · "exit 1" · "seq gap"
              ↓ reliable signal, bounded claim
Tool:    "the API returns 404" · "test failed at line 88" · "build produced X"
              ↓ external evidence, no self-interest
Model:   interprets → judges progress → decides next action → records why
              ↓
State:   changes ONLY on the model's recorded judgment, never on a field flip
```

**No status transition may be triggered by a surface field.** Any status change affecting resource
allocation, direction, or completion requires the model's semantic review of actual results, and
that judgment is recorded. A validator returning "pass" never ends the model's independent analysis.

---

## 6. THE NEW EXECUTION LOOP

```
ORIENT   (read-only — writes NOTHING)
  read the charter: goal · success criteria · constraints · non-goals · authority
  read the frontier: what is done, blocked, waiting, in doubt
  read memory: confirmed facts · failed approaches · decisions · open assumptions
  GATE: state in one sentence which success criterion the next action advances.
        Cannot state it ⇒ re-read the charter. This is the missing reader from §1.4.

DECIDE   (writes NOTHING)
  name the largest current uncertainty or blocker
  choose the action that most reduces it, unblocks work, or directly advances the goal
  prefer: resolve unknown > remove blocker > advance criterion > improve quality
  if key facts are unknown, the action IS research — do not plan past uncertainty

WORK     (the point — the overwhelming majority of the advance)
  research (external sources for external facts) · design · implement · test · iterate
  before an irreversible effect: confirm authority, record intent + idempotency key
  spawn an isolated perspective only when: decision-relevant AND parent-suspect
      AND no cheaper external ground exists
  ordering: script/tool > blind subagent > informed subagent > self-check

EVIDENCE (from outside the work)
  run the declared verification; record what was ACTUALLY executed or observed
  stamp assurance: external | blind | self_attested — never launder the third as the first
  no objective verifier available ⇒ produce a verification packet, resolve objections,
      obtain human acceptance OR proceed explicitly provisional with a falsification trigger

JUDGE    (semantic — the model, never a validator)
  did this actually progress the goal, or only change fields?
  is the result sufficient, or merely formally complete?
  is the risk substantively resolved?
  should the status change — and on what factual basis?
  did anything surprise me? (surprise is the trigger for replanning)

COMMIT   (≤3 appends — nothing written twice)
  1. one event-log line (truth)
  2. one ledger entry IF a gate ran (verdict + assurance + artifact pointer)
  3. one progress line: what changed · what's next · what surprised me · verified vs believed
  checkpoint is NOT written here — only at boundaries or periodically
  then: continue · adjust · replan · escalate · finish
```

**The write quota, stated so the agent can self-audit without seeing its token budget:** *a node
advance that writes more state than it produced work product is a failure mode, not diligence.
Editing control files a third time in one advance means you are bookkeeping.*

Target: **~78 writes → ~20**, with the freed attention going to WORK.

---

## 7. LONG-HORIZON MECHANISMS

### 7.1 `memory.md` — the only durable knowledge store

Four sections, each with a trigger that makes it actionable:

```
## Confirmed Facts      — fact · evidence pointer · implication · recheck-when
## Failed Approaches    — attempt · failure evidence · do-not-retry-unless
## Decisions            — decision · rejected alternatives · evidence · revisit-when
## Open Assumptions     — assumption · decision it supports · discriminating check
```

Each earns its place: confirmed facts prevent re-research and constrain design; failed approaches
prohibit unchanged retries; decisions prevent accidental reversal while remaining revisable; open
assumptions carry a *falsification test*, not a worry. **No deliberation transcripts, no raw tool
output, no reasoning traces** — write only what cannot be recomputed or re-read.

### 7.2 Cold-start recovery

`progress.md` is the human-readable projection: charter summary · state through event N ·
demonstrated criteria with evidence · current horizon · next action · blocked/waiting · provisional
claims · what changed since last horizon.

**The test:** if a human reading it cold cannot tell what happens next, neither can an agent.
Structured state wins on conflict; `progress.md` is regenerated.

### 7.3 Context compression and direction correction

- **Compression:** context loss becomes a deliberate boundary, not only a failure — a fresh agent reading a curated charter + progress + memory can outperform an exhausted one carrying a huge transcript.
- **Phase rollover:** archive log + ledger, carry forward terminal states and open frontier (§4 already specifies this — keep).
- **Direction correction:** Live Loop admission (KEEP) turns discovered facts into plan changes; the JUDGE step's surprise question is the trigger; replan bumps `plan_version`.
- **Goal sovereignty:** the charter changes only on explicit user confirmation.

---

## 8. MIGRATION

**Principles:** every wave ends green · instrumentation before change · repair before restructure ·
**subtraction last** (highest blast radius, least value) · one irreversible decision, deferred as
late as possible.

| Wave | Content | Boundary gate |
|---|---|---|
| **0 — instrument** | pointer-integrity checker (**precondition for every deletion** — no gate sees Markdown links today) · baseline green script + revert anchor · RED fixtures R42–R45, R47–R48 · reconstruction-proof harness | all new files; production untouched; fixtures documented RED with captured output |
| **1 — repair** (parallel) | B5 integrity checker loads the log + requires state files + honest name · R28 depth contradiction · duplicate R36 statement · example R34 contradiction · **B3 authority fix + `last_event_seq`** | R42 RED→GREEN; all 4 examples still validate; 2× cross-file OK |
| **2 — additive core** | **B2 goal-contract readers** (reference-validity checks only) · **B1 assurance axis** (orthogonal; enum untouched) · **B4 R5 claim bounded** · **write the deterministic/semantic boundary into the skill** | R43/R44/R45 GREEN; **R7 still rejects** (proves orthogonality); R1–R41 unchanged |
| **3 — the two real gaps** | external-knowledge acquisition procedure (currently NAMED-ONLY, RANK 1) · executable-design procedure (NAMED-ONLY, RANK 2) · **B6 blind verification + dissent** | R47/R48 GREEN; isolation rule preserved verbatim |
| **4 — attention budget** | **B8 ORIENT→COMMIT** + `command/loop-run.md` in the same commit + `render` + installer · **de-persona, question sets preserved 1:1** · attention invoice | write count stated and reduced; render byte-identical; installer 15/15 |
| **5 — measure, then decide** | run the reconstruction proof · **DECISION POINT: which fields are provably rebuildable from the log** | 100% field coverage; non-reconstructible set enumerated (already known to include `pending_approvals`, `blocked`, `open_assumptions`) |
| **6 — collapse + tournament** | merge `loop.state` → checkpoint; strip `node.contract` copies; claims conditional on concurrency mode · **B7 design tournament** | 0 reconstruction regressions; fan-out cap + isolation preserved |
| **7 — subtraction** | 3 verified-clean fields (**one commit each**) · 2 transcripts + **54-link citation repair in the same commit** · `self_evolution_integration.md` → optional adapter | **0 dangling pointers**; gate-kind enum byte-identical; `research-sources.md` intact |

**Compatibility:** loops mid-flight under the old contract keep working — Waves 0–4 are additive or
repair-only. Waves 6–7 need a one-time state migration, gated on Wave 5's evidence.

**Avoiding one-shot risk:** each wave is independently revertible; subtraction is one commit per
field; the fork is a single named decision resolved by measurement rather than argument.

---

## 9. VERIFICATION AND ACCEPTANCE

Structure checks are necessary and **insufficient**. Acceptance runs **real development tasks**
before and after, and compares.

### 9.1 Structural floor (necessary, proves nothing about quality)

Full `tests/acceptance_tests.md` sequence · `node test/installer.test.js` 15/15 · pointer checker 0
dangling · every R1–R48 fixture behaves · `render` byte-identical.

### 9.2 Real-task acceptance — the actual gate

Run ≥3 tasks of different shapes (a multi-session feature; a research-then-design task; a
bug-with-unknown-cause) on both old and new, and measure:

| # | Metric | How observed | Target |
|---|---|---|---|
| 1 | **bookkeeping share** | field-writes per advance ÷ total actions | 9:1 → ≤2:1 |
| 2 | **high-value action share** | advances containing research/design/implement/verify vs state-only advances | materially up |
| 3 | **time to first real action** | advances before the first goal-advancing action | down |
| 4 | **risk-discovery latency** | when architectural contradictions surface (design vs post-implementation) | earlier |
| 5 | **next-action quality** | blind review of chosen action vs available alternatives at that state | more defensible |
| 6 | **deliverable quality** | code/design/test review by an independent reviewer, old vs new | up |
| 7 | **goal drift** | completed nodes traceable to a success criterion | ↑ toward 100% |
| 8 | **false completion** | nodes marked complete whose criterion was not met | down, especially mechanically-caused |
| 9 | **escape rate** | defects found after a gate passed | down |
| 10 | **assurance distribution** | share of completions on `external` vs `self_attested` | `external` up |
| 11 | **mechanism cost** | mechanisms, schemas, fields, lines — vs metrics 1-10 | fewer mechanisms, better outcomes |

**Acceptance rule:** metrics 1, 2, 7, 8, 10 must improve; 6 must not regress; 11 must show fewer
mechanisms for equal-or-better results. **Structural greenness alone is not acceptance.**

### 9.3 Falsification drills

Kill the session mid-advance and resume cold — no duplicated effect, no lost approval · corrupt
the checkpoint and confirm the log wins · plant a `self_attested` verdict on a high-risk node and
confirm it cannot close it · delete a reference file and confirm the pointer checker catches it.

---

## 10. RISKS AND COUNTER-EFFECTS

| # | Risk this plan introduces | Lightweight control (no new process) |
|---|---|---|
| **1** | **Over-reliance on model judgment** — removing mechanical gates removes floors | The `assurance` axis is the floor: high-risk completion requires `external` or `human_approval`. That is one field, not a process. |
| **2** | **Too little structure ⇒ context loss** | The 4-core-schema set is chosen by the cold-resume test, and the drill in §9.3 is the check. If a zero-memory agent can resume, structure is sufficient by definition. |
| **3** | **Vague status criteria** — "the model judges" becomes "anything goes" | Each retained status keeps a written *factual basis* requirement: what must be observably true. The model judges whether it is true; it may not skip stating what it relied on. |
| **4** | **Role responsibilities re-overlap** | A perspective is a lever bundle (`sees` / `barred` / `objective` / `tools` / `returns`), never a title. No bundle ⇒ no role. Titles cannot silently return. |
| **5** | **Missing determinism guards** — cutting validators removes real protection | The program keeps every check in §5.1. Nothing determinable is being given up; only over-extrapolation is. |
| **6** | **Plausible-but-unverified conclusions** — the model reasons deeply and is confidently wrong | `provisional` is a first-class outcome with a falsification trigger. A criterion cannot close on `provisional`. This is the counter-effect I consider most likely and it is the reason `provisional` exists rather than being folded into `pass`. |
| **7** | **The blind reviewer becomes a rubber stamp** | Zero disagreements across a long loop is itself the signal; dissent is recorded. If disagreement never appears, the mechanism is not working and is visibly not working. |
| **8** | **Short-horizon replanning fragments architecture** | Every horizon names the criterion it advances; a unit that cannot name one is not admitted. |
| **9** | **This plan's own over-extrapolation** | Standing rule: every validator states the exact fact inspected **and the conclusion it does not license**. A rule whose name implies more than it inspected is a defect even when its logic is correct. |

---

## 11. FINAL-STATE TEST

| Criterion | How this plan satisfies it |
|---|---|
| Fewer mechanisms, each with a clearer role | 11 schemas → 4 core + 2 conditional; 21 node fields → 10 required; 6 merges; 5 deletions |
| Leaner schema, higher decision value | Every retained field names its consumer, moment, and the decision it changes |
| More reliable program validation | Programs keep every determinable check and stop deciding semantic questions; the threshold check is *cancelled*, not added |
| Model holds judgment, bounded by real evidence | Model decides completion/progress/direction; `assurance: external` is the constraint |
| Attention on research, design, implementation, verification | ~78 writes → ~20; ORIENT/DECIDE are read-only; WORK is the bulk |
| State reflects real progress, not field changes | No status transition driven by a surface field; each requires a recorded factual basis |
| Roles produce independent increment | Lever bundles with information barring; org-simulation labels deleted, question sets kept |
| Supports long-horizon system building | Charter + memory + progress + phase rollover + Live Loop correction |
| Professionalism in judgment and delivery | Acceptance measures real-task outcomes, not structural completeness |
| Every complexity justified | Every retained mechanism carries its 3-link chain in §3 |

---

## APPENDIX — calibration record

Six claims of mine were overturned by verification during this analysis, **all six erring toward
deletion**: the 500-line ceiling as a constraint · validators-per-line as a yield metric (nearly
deleted the skill's best behavioral prose) · "79 write-only fields" (excluded prose readers; the
resume algorithm reads three of them) · "9 ceremonial fields" (6 have live readers) · "research
files unreachable" (54 inbound links) · "3 transcripts" (2 transcripts + 1 clean report). A
seventh was self-inflicted: planning to enforce `score >= threshold`, which would have handed a
model's opinion deterministic authority over completion.

**The pattern:** each error came from judging a mechanism with the wrong detector. Any future round
must state which detector it used and apply the 4-reader test before calling anything unread.

---

# AMENDMENT A2 — corrections found while EXECUTING Wave 1 (2026-07-30)

**Authoritative over the plan body and over Amendment A1 where they conflict.**
Written during execution, not planning: every item below is a defect the plan itself contained,
or a repo defect the plan did not know about. Recorded so a future executor does not re-hit them.

## A2.1 — T1.1 as written was UNSATISFIABLE (plan defect, blocking)

T1.1 required BOTH:
- "a loop dir claiming to be resumable MUST have `checkpoint.yaml`, `evidence.ledger.yaml`, and an event log", AND
- "both real examples still print `INTEGRITY OK` (no regression)".

Measured reality at execution time: **no example shipped a ledger or an event log at all.** Each
contained exactly `checkpoint.yaml`, `loop.plan.yaml`, `README.md`. So the two acceptance criteria
were mutually exclusive.

**Root cause was worse than a plan error.** `check_loop_integrity.py` gated the completed-node
evidence check behind `if ledger_p.exists():` with the comment *"no ledger = legal minimal mode,
not corruption; do not remove"*. Under that decision the examples shipped **17 `completed` nodes
with 0 ledger entries** — i.e. the shipped examples taught that a node may be marked complete with
no evidence whatsoever. That is precisely the false-completion pattern this refactor exists to
remove, encoded in the artifacts users copy from.

**Resolution — T1.1b inserted BEFORE T1.1a (new ordering constraint):**
- **T1.1b** (data): backfill all 4 example loops with `evidence.ledger.yaml`, `event_log.jsonl`,
  and per-node evidence artifacts, so every `completed` node has a factual basis. DONE:
  17 completed nodes / 17 backing passing entries / 0 missing; 34 log entries total.
- **T1.1a** (code): only then may the checker require those files.

Any future wave that tightens a validator must check whether the shipped examples can satisfy it.
**Tightening a rule against fixtures that violate it makes the fixtures the blocker, not the rule.**

## A2.2 — Layout contradiction: `state/` vs loop root (repo defect, 4th found)

Four sources disagreed on where the ledger and log live:

| Source | Says |
|---|---|
| `references/recursive_loops.md:234` (canonical isomorphic per-loop tree) | loop **root** — `state/` appears nowhere |
| all other `references/` | 0 mentions of a `state/` subdir |
| `templates/checkpoint.yaml` (before fix) | `state/evidence.ledger.yaml`, `state/event_log.jsonl` |
| `scripts/check_loop_integrity.py:51` | hardcodes `loop_dir / "evidence.ledger.yaml"` — **ignores the checkpoint's own `evidence_ledger_ref`** |

Consequence: an agent following the template writes to `state/`, while the checker reads root. The
only way to satisfy both is to write the file **twice** — which is exactly what happened during
T1.1b (byte-identical duplicate ledgers in 3 loops).

**Resolution:** loop root is canonical (2 template lines lost to 1 canonical reference + the child
example, which already used root and thus contradicted its own parent). Template and all 3 example
checkpoints now declare `./event_log.jsonl` and `./evidence.ledger.yaml`; no `state/` dir remains.

**New requirement added to T1.1a:** the checker must resolve the **declared** `evidence_ledger_ref`
/ `event_log_ref` from the checkpoint, never a hardcoded path. A checker that validates a different
file than the protocol points at is a false-verification defect in the checker itself.

## A2.3 — INCIDENT: destructive cleanup without per-file proof (executor error)

While de-duplicating ledgers I ran `rm -rf <loop>/state`. I had proved the *ledger* copies were
byte-identical, then generalized that proof from the file class to the whole directory. The
**event logs existed only under `state/`** — 32 entries destroyed, untracked (`??`), so
`git` could not restore them.

Recovered in full: the one surviving child log gave the exact line format; the intact ledgers gave
node ids, gate kinds, verifiers, timestamps. All logs regenerated at root (18/12/2/2 entries),
`seq` contiguous from 0, every `pre_effect` matched by a `post_effect`, ALL GREEN. **Net loss: zero.**

**Standing rule adopted:** a destructive command requires proof for **every file it will remove**,
not for the class of file being examined. When de-duplicating, **move, do not delete** — an untracked
file has no undo. This belongs in the skill's own guidance: the loop protocol writes untracked state
files, so any cleanup step inside a loop carries the same hazard.

## A2.4 — Wave 5 unblocked as a side effect

Wave 5's decision point needed a loop dir with a populated event log; none existed (recorded as a
Wave-0 blocker). T1.1b's backfill supplies it. `prove_reconstruction.py` now reads a real log and
reports, for `example_product_delivery`: **2 RECONSTRUCTIBLE** (`phase`, `ready_set`),
**6 NOT-RECONSTRUCTIBLE**, **24 NO-EVENT-SOURCE** — the first measured (not inferred) evidence for
the D1 fork, and it confirms the structural finding that `pending_approvals` / `blocked` /
`open_assumptions` have no event carrying them.

## A2.5 — Verified-clean Wave 1 text repairs

- **T1.2** `recursive_loops.md:52` — "to arbitrary depth" → bounded by `termination.max_depth` (R28).
- **T1.3** `evidence_gates.md` — duplicate verifier-independence rule de-duplicated; **union preserved**
  (`step_verifier` + `threshold >= 0.7` from the second copy survive in the canonical statement at :44;
  :262 is now a pointer). Dropping either clause would have been a silent weakening.
- **T1.4** `example_research_project/README.md:78` — the **README was the defect, not the plan**.
  `N9_recommendation_approval` does ship `kind: human_approval`; the README claimed gate-exempt.
  Instructing the agent to read the plan first is what caught this; a "fix the README to match R34"
  instruction would have produced the same text for the wrong reason.
