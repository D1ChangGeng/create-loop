---
type: reference
confidence: observed
scope: ["skills/create-loop/"]
sources: [".agents/knowledge/reference/redesign-evidence-round1-2026-07.md", ".agents/knowledge/reference/redesign-execution-plan-2026-07.md"]
last_verified: 2026-07-31
created: 2026-07-30
---

# Subtraction Refactor — Wave-Ordered Plan — `skills/create-loop/`

> **SUPERSEDED (2026-07-30).** This plan was built on a subtraction frame the user
> subsequently reframed, and 6 of its premises were overturned (see
> `redesign-evidence-round1-2026-07.md` §CORRECTIONS). Its implementation-era
> successor, `redesign-execution-plan-2026-07.md`, is now historical too;
> current authority lives in source, executable tests, and
> `skills/create-loop/references/protocol_v2.md`. Kept for its Wave-0
> pointer-checker insight and tombstone rule.


**Status:** planned, NOT executed. Blocked on decision gates DG1–DG4.
**Companion:** [`mechanism-audit-2026-07.md`](mechanism-audit-2026-07.md) — the evidence base. Read it first; this file assumes its findings.
**Budget:** −3,155 subtracted / +353 added = **−2,802 net lines**. `references/` −30.5%.
**Invariant:** the repo is GREEN at every wave boundary.

---

## 0. Constraints

| # | Constraint |
|---|---|
| C1 | `loop.state.yaml` removal, if approved, must sweep all four layers together: template, schema, validator rule R30, and every command/doc reader |
| C2 | Editing `command/` bodies or `manifest.json` ⇒ `node bin/create-loop.js render` + `node test/installer.test.js`, committing `command/` + both rendered dirs together |
| C3 | Green gate = `tests/acceptance_tests.md` full sequence + `node test/installer.test.js` |
| C4 | Any vocabulary change ⇒ its negative fixture in `failure_mode_tests.md` must still reject, in the same commit |

**C3 does not cover Markdown pointer integrity.** Verified: `SKILL.md`'s pointer table has zero dangling links today and exactly two on-disk orphans. Deleting 4 reference files severs 10+ inbound relative links that **no existing gate catches**. A pointer checker is therefore a Wave-0 precondition, not a nicety.

---

## 1. Flagged inconsistencies found while sequencing

The plan verified each target's file-level reality rather than trusting the audit brief. Eight premises were contradicted or incomplete; four escalated to decision gates.

| # | Finding | Resolution |
|---|---|---|
| F1 | `fanout` load-bearing in 3 places (`checks/__init__.py:73`, `control_flow` enum `loop_plan_spec.md:378`, invocation description `SKILL.md:13`); `mapper` named at `SKILL.md:72` | **DG1**, isolated in Wave 6 |
| F2 | D6 mixes risk classes: 3 fields are optional/back-compat, but `next_suggested_action` is schema-**required** | **DG2**, default KEEP |
| F3 | `loop.state` is declared home for `human_decisions[]`, `active_constraints`, `runtime_subgraphs` — none in `checkpoint.schema.json` | **DG3**, name homes first |
| F4 | D1's inbound pointers include 7 citation cells *inside* the gate-kind vocabulary table (`loop_plan_spec.md:160-166`) plus `branching_parallelism.md:17,:382`, `SKILL.md:716` | convert to plain-text attribution ("Zheng et al. 2023") — preserves the claim, kills the dead link |
| F5 | SKILL §6 is a named core principle (commit `3b14159`) whose backing doc is the deletion target; `layered_execution_chain.md:28` self-declares as its "structural companion" | **D3 and K2 are one task**, same wave |
| F6 | Renumbering after R30's removal would invalidate every pinned fixture ID across 2,617 lines | leave a **tombstone**; never renumber |
| F7 | This plan does **not** reach the 500-line ceiling: 803 → ~760 | the only remaining lever is disclosing §5/§6/§8 principle prose behind pointers — **out of scope**, named so it is not mistaken for delivered |
| F8 | 2 of 3 research files are *already* unreachable from `SKILL.md` | only `research-sources.md` needs a row removed |

---

## 2. Wave order

```
Wave 0  additive, zero risk, start immediately
├── 0.1  pointer-integrity checker            (precondition for every deletion)
├── 0.2  baseline green snapshot + revert oracle
├── 0.3  RED resume-contract tests (A1)       (TDD: authored failing, before Wave 5)
└── 0.4  RED attestation tests (A2)

Wave 1  deletions with the largest inert mass
├── 1.1  delete 3 research files (1,826 lines)   [needs 0.1, 0.2]
└── 1.2  repair 10 severed citations             [same commit as 1.1]

Wave 2  kernel extraction (parallel; single pointer custodian)
├── 2.1  K1  execution_intelligence_policy → ~120-170 lines
├── 2.2  K2 + D3  layered_execution_chain kernel + recursive_planning removal  (F5: one task)
├── 2.3  K3  live_loop_semantics kernel
├── 2.4  pointer custodian: SKILL.md / README / command   [after 2.1-2.3; one owner avoids conflict]
└── 2.5  C2 render + installer test                        [after 2.4]

Wave 3  state-artifact excision                              [DG3 must be settled]
├── 3.1  loop.state excision, full C1 sweep
└── 3.2  R30 fixture removal + tombstone (F6)

Wave 4  field-tuple + enum simplification (serial: shared files)
├── 4.1  D5  assignee/notes → optional
├── 4.2  D7  R20 fold + R10 → JSON Schema (only after pattern/maxLength added)
├── 4.3  A4  schema_version + explicit migration rules
└── 4.4  negative-fixture re-pin sweep (C4)

Wave 5  additive enforcement — closes the gaps the audit found
├── 5.1  A1  integrity hardening: load the event log; stop treating ckpt/ledger as optional (D-b)
├── 5.2  A2  attestation gates with assurance levels (DG4)
├── 5.3  A3  "arbitrary depth" vs max_depth repair (D-a)   [independent, may float early]
└── 5.4  crash-resume scenario suite

Wave 6  highest blast radius, gated
└── 6.1  DG1 decision + execution (mapper/fanout)
```

---

## 3. Protected surfaces (do not touch)

`loop.meta.yaml` identity · `loop.plan.yaml` DAG + `requires` · `checkpoint.yaml` core + `next_suggested_action` (DG2) · `event_log` · `evidence.ledger.yaml` + active artifacts · the 5 STRUCTURAL-REAL validators (R1, R2, R3, R6, R19) · the enum guards upheld in audit §4 C1 · the 4 worked examples (90% load-bearing; empty-field tax only ~10%) · `failure_mode_tests.md` fixtures (40/41 runnable; nothing prose-only to delete).

---

## 4. Verification contract

Each wave boundary must show:

| Gate | Command | Expected |
|---|---|---|
| S1 render determinism | `node bin/create-loop.js render && node test/installer.test.js` | exit 0, 15/15 |
| S2 validator integrity | `validate_loop_plan.py` + `validate_checkpoint.py` on all 4 worked examples; `check_loop_integrity.py` on both loop dirs | 10× exit 0 |
| S3 pointer integrity | Wave-0 checker | 0 dangling |
| S4 acceptance gate | `tests/acceptance_tests.md` full green sequence | all pass |
| S5 negative fixtures | every touched R-rule fixture | still rejects (C4) |

Baseline captured pre-refactor: all 10 S2 commands exit 0; `validate_*` print nothing on success; `check_loop_integrity.py` prints `INTEGRITY OK: <dir>`.

---

## 5. What this plan deliberately does not do

- **Does not reach `SKILL.md` < 500 lines** (F7). Ends at ~760.
- **Does not add an eval set.** Anthropic's "build evaluations first" gap stands: mechanism *effectiveness* remains unmeasured, and no amount of file-reading closes it.
- **Does not delete self-graded gates** — it reclassifies them (DG4). Deletion remains the fallback if assurance levels are rejected.
- **Does not renumber any R-rule** (F6).
