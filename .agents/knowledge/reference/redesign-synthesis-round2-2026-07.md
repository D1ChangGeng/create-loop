---
type: reference
confidence: observed
scope: ["skills/create-loop/"]
sources: [".agents/knowledge/reference/redesign-evidence-round1-2026-07.md"]
last_verified: 2026-07-31
created: 2026-07-30
---

# Round 2 Synthesis — 4 independent axes over the Round 1 evidence

> **Historical design evidence (superseded as current-state authority 2026-07-31).**
> Retained for rationale; use current source, executable tests, and
> `skills/create-loop/references/protocol_v2.md` for implemented behavior.
Inputs: Oracle A (answer the 5 questions), Oracle B (clean-slate design), Oracle C (steelman/defend), Artistry D (AI-native role+attention design).
Read with `/tmp/round1-evidence-digest.md`.

## 0. THE USER'S TEST (governs everything)
A mechanism justifies itself only via: records WHAT info -> changes WHAT later judgment/action -> improves WHAT in the result.
Corollary adopted from external evidence (Wen NeurIPS 2024): a check is worth its cost only if its verdict
comes from something OTHER than the thing being checked.

## 1. CONVERGENCE — all 4 axes independently agree (highest confidence)

### C1. Durable core is 4-6 artifacts, not 11 schemas
- Event log = source of truth. Checkpoint = DERIVED CACHE, not a co-equal artifact.
- Consequence: ~38 of 78 per-node writes are projections of data already written.
- Oracle B concrete shape: charter / plan / snapshot / events.jsonl / memory.md / progress.md (+ conditional artifacts, branches, waiting-for-user).
- Oracle A: goal-bearing plan + atomic snapshot + minimal event history + verification receipts.
- IMPORTANT DIVERGENCE FROM EXTERNAL RESEARCH, both Oracles flag it: LangGraph does NOT persist topology
  because CODE holds it. Here there is no code -> `loop.plan` IS the executable program. Topology MUST persist.
  Do not cargo-cult "don't persist topology". DO cargo-cult "don't persist runtime counters/projections".

### C2. Self-attested gates must never authorize completion
- 6 of 8 gate kinds are self-graded; all write the same `verdict: pass`; no reader distinguishes them.
- Required fix (unanimous): an `assurance` axis orthogonal to gate kind —
  `external` (script/test/compiler/tool exit code) | `blind` (independent context, claim withheld) | `self_attested` (advisory only).
- Only `external` and `human_approval` may authorize `completed`. `self_attested` may produce `provisional`.
- Oracle B's sharpest reframe: separate three claims the skill currently conflates —
  WORK WAS PRODUCED vs EVIDENCE SUPPORTS IT vs AN AUTHORIZED SOURCE ACCEPTED IT.

### C3. Goal fields need READERS ADDED, not deletion
- The measured "write-only" status of success_criteria/non_goals/constraints is a MISSING-READER DEFECT,
  and is the mechanical cause of the goal drift the user feels.
- Fix: mandatory re-read of the goal contract at 4 points — dispatch, mutation, verification, termination.
- Oracle A calls this THE most irreplaceable mechanism.

### C4. Kill persona/hat labels; keep isolation + question sets
- "architect/project-lead/layout-designer" vs "executor/researcher/engineer/verifier" and
  "you are three things at once" = 7 hats on 1 head, zero isolation, zero independent verdict.
- What survives: the QUESTION SETS those hats implied (they change what gets examined),
  re-expressed as checklists attached to phases, not as identities.

### C5. Attention budget must be restructured per node advance
- Current: ~78 field-writes / ~8 read back (9:1).
- Target shape (all axes converge): ORIENT (read-only: goal contract + frontier) -> WORK (the actual engineering) -> COMMIT (≤3 appends).
- Nothing may be written twice. Snapshot is regenerated, never hand-maintained field-by-field.

## 2. DIVERGENCE — genuine design forks, user must arbitrate

### D1. REFACTOR vs REPLACE the state shape
- Oracle B (clean-slate): different SHAPE is correct — 6 files, rolling 3-7-unit horizon, no permanent full-project DAG.
  Rationale: a long static plan is not monitored or revised; short-horizon + replanning outperforms (ReAct/plan-and-solve evidence).
- Oracle C (steelman): refactor in place. BLOCKING CONSTRAINT: do not collapse projections until ONE canonical
  event+snapshot model can demonstrably reconstruct every discarded field. Otherwise you lose transaction evidence,
  provenance, and child return contracts.
- SYNTHESIS: these are compatible if sequenced — build the canonical model FIRST, prove reconstruction, THEN collapse.
  That sequencing is the safe path and should drive wave order.

### D2. THE single highest-value addition
- Artistry D: BLIND ADVERSARIAL VERIFICATION. Information barring (what a reviewer is forbidden to see) is the
  only genuinely AI-unique lever and the only structural fix for self-preference. A blind reviewer's agreement is
  evidence; an informed reviewer's agreement is an echo.
- Oracle A: GOAL-CONTRACT READERS at dispatch/mutation/verify/terminate.
- SYNTHESIS: not mutually exclusive. C3 prevents drift (wrong target); D2 prevents false confidence (wrong result).
  Both are cheap. Recommend both, C3 first (it is a precondition for meaningful verification).

## 3. NEW INVENTIONS worth carrying into the plan (labeled invention, not audit)
- **Information barring** as a first-class primitive: verifier subagent receives artifact + criteria, never the producer's verdict/rationale.
- **Verdict-first ordering**: reviewer writes its verdict file BEFORE reading the producer's claim; file mtime makes independence checkable.
- **Dissent protocol**: a parent overriding a blind reviewer must record why -> rubber-stamping becomes expensive and auditable.
- **Design tournament**: `fanout`/`mapper` reborn as N speculative competing designs with planned casualties.
  NOTE: this resolves open decision DG1 — the dead vocabulary becomes the mechanism that exploits cheap parallel spawn.
- **Attention invoice**: per node, record what was LEARNED / what SURPRISED / what was VERIFIED vs BELIEVED. Replaces field ceremony with signal.
- **Memory inversion**: persist only what cannot be recomputed. Everything derivable is regenerated on demand.

## 4. STANDING SAFETY RULE (from correction C2, verified 3x)
No field may be deleted on the evidence "no validator reads it".
Deletion requires ALL of: no validator reader AND no instruction reader AND no template reader AND no closeout/human reader.
Genuinely ceremonial set that survives this stricter test:
schema_version x5, created_at, created_by, recorded, heartbeat_at, jitter, cache_key, owner_agent, retirement.retired_at.

## 5. PRESERVE (named by multiple axes as the skill's real assets)
- `execution_intelligence_policy.md` §3.2 root-cause classification, §3.5 counterexample review.
- The subagent context-isolation rule (`branching_parallelism.md:142-149`).
- The charter interview (Discovery-vs-Decision routing; "ask only the next blocking question").
- The event log write-ahead bracket (pre_effect/post_effect + idempotency key).
- Generator != verifier for high risk (needs upgrading to blind, not deleting).
- The 4 worked examples (~90% load-bearing).

## 6. STILL-OPEN USER DECISIONS (carried from Round 1, now reframed)
DG1 `mapper`/`fanout`: RESOLVED-BY-DESIGN if design tournament is adopted (they become the tournament primitive).
DG2 `next_suggested_action`: keep (schema-required, tie-break reader exists).
DG3 `loop.state.yaml`: subsumed by D1 — its fate is decided by the canonical-model decision, not separately.
DG4 self-graded gates: RESOLVED — fix via `assurance` axis, not deletion.
NEW DG5: refactor-in-place vs new shape (D1). This is the one real fork the user must call.
