Task completed in 16m 23s.

Agent: plan
Model: zeo-claude/claude-opus-5-max

---

# Systemic Redesign of `skills/create-loop/` — Wave-Ordered Execution Plan

## Context

### What is being changed
`/home/changgeng/create-loop/skills/create-loop/` (22,849 lines) is a Markdown-defined Agent Skill that instructs a coding agent how to run long-horizon, multi-session, context-loss-surviving engineering work using filesystem state. **There is no runtime, no daemon, no scheduler — the agent reading the Markdown IS the runtime.** `loop.plan.yaml` is therefore not config; it is the executable program.

### The problem (measured, not inferred)
Advancing ONE node `todo → in_progress → done` mandates **~78 field-writes across 7 files**; a blank-session resume reads back **~8**. Ratio ≈ **9:1 write-to-read**. ~38 of the 78 writes are projections of data already durably written to the event log, which the protocol's own State Authority Order (`recovery_protocol.md` §6.0) declares the source of truth. The agent spends its attention on bookkeeping instead of on understanding goals, acquiring external information, finding risk, deriving design, verifying assumptions, and implementing well.

### The governing test — every task below serves it
> A mechanism is justified only if this chain can be written: **records WHAT information → changes WHAT later judgment or action → improves WHAT in the final result.**

**Adopted corollary (Wen, NeurIPS 2024):** a check is worth its cost only if its verdict comes from something OTHER than the thing being checked.

### Verified baseline — the repo is GREEN right now
Confirmed by direct execution before planning:
- 11 schemas parse + are Draft-07 valid
- 11 templates validate
- 4 example plan/checkpoint validations pass
- 2 `check_loop_integrity.py` runs print `INTEGRITY OK`
- `render_dag.py` prints 3
- `node test/installer.test.js` → **15 passed, 0 failed**
- `SKILL.md` = 803 lines
- All Python compiles

### Five convergences to land (4 independent analysis axes agreed)
- **C1** — Event log is truth; checkpoint is a derived cache. Collapse duplicate projections. **Topology MUST still persist** (unlike LangGraph, where code holds it — here `loop.plan` IS the program). Do not cargo-cult "don't persist topology"; DO cargo-cult "don't persist runtime counters/projections."
- **C2** — Add an `assurance` axis (`external` | `blind` | `self_attested`) orthogonal to the 8 gate kinds. 4 of 8 gate kinds are self-graded; all write the same `verdict: pass`; **no reader distinguishes them.** Only `external` and `human_approval` may authorize `completed`; `self_attested` yields `provisional`.
- **C3** — The goal contract (`success_criteria` / `failure_criteria` / `non_goals` / `constraints` / `scope`) is write-only because **nothing re-reads it**. This is a MISSING-READER defect and the mechanical cause of goal drift. Add readers at 4 points: dispatch, mutation, verification, termination. **Verified**: `SKILL.md:506` reads `checkpoint, contract, ledger` — never the goal.
- **C4** — Remove persona/hat labels; **preserve the question sets** they implied as phase-attached checklists. Keep all 8 perspective-allocating mechanisms.
- **C5** — Restructure per-node attention into **ORIENT (read-only) → WORK (engineering) → COMMIT (≤3 appends)**. Nothing written twice.

### Inventions to land
Information barring · verdict-first ordering · dissent protocol · design tournament (repurposes dead `mapper`/`fanout`) · attention invoice.

### Corrections to the incoming framing (found while verifying; these change the plan)

| # | Framing claim | Verified reality | Plan impact |
|---|---|---|---|
| **E1** | 9 fields are "genuinely ceremonial", safe to delete | **3 have live readers.** `recorded` is in the validator required-tuple at `validate_loop_plan.py:196`; `cache_key` is in `CONTRACT_REQUIRED` at `checks/__init__.py:89`; `jitter` has a behavioral instruction reader — the retry-wait formula at `exception_handling.md §5.2`. Also `created_at`/`created_by` are in `LOOP_META_REQUIRED` (`checks/__init__.py:99`) and `heartbeat_at` is in `CLAIM_REQUIRED` (`checks/claim.py:12`) + is the lease mechanism (`state_model.md:141-145`) | Subtraction re-scoped to the **3 that actually pass**: `owner_agent`, `retirement.retired_at`, and audited `schema_version` instances. Rest deferred to Wave 7 as opt-in. |
| **E2** | Research notes are "unreachable from SKILL.md" | **54 inbound links** from 8 reference files — `loop_plan_spec.md`×8 (7 are citation cells *inside the gate-kind vocabulary table*), `exception_handling.md`×11, `concepts.md`×14, `recovery_protocol.md`×7, `human_approval.md`×5, `evidence_gates.md`×5, `branching_parallelism.md`×2, `state_model.md`×2 | Deletion requires a 54-link citation-repair task in the same commit. Cannot be a cheap Wave-1 win. |
| **E3** | All 3 research files are raw transcripts contradicting the design | `research-sources.md` (317 lines) is a **clean cited report**, not a transcript. Only the other two (1,509 lines) are transcripts. The "16 node kinds / `runs/<run_id>/`" text appears in **descriptions of other systems** (Anthropic progress file, LangGraph session), i.e. prior-art vocabulary — not competing claims about this skill | `research-sources.md` is **PRESERVED**. Deletion scope drops 1,826 → 1,509 lines. |
| **E4** | `check_loop_integrity.py` exit 0 doesn't prove safe resume | **Worse — proved empirically.** A dir containing only `loop.plan.yaml` (no checkpoint, no ledger, no event log) exits **0** printing `INTEGRITY OK`. It actively certifies an unresumable loop as healthy. | Strengthens the Wave-2 repair; gives an exact RED fixture. |
| **E5** | R28 governs `max_depth` | **Correct** — `caps.py:41` emits `[R28 CAP-EXCEEDED]`. Verified because the docstring reads ambiguously. | No change. |
| **E6** | (not stated) | **Only R1–R18 have a runnable fixture script.** R19–R41 are prose-only. Next free rule number is **R42** (R1–R41 contiguous). | Every new rule R42+ must ship a *runnable* fixture, not prose. |

### Hard repo constraints (violating these breaks the build)
- Slash commands: ONE source of truth `command/`. `.opencode/command/` + `.claude/commands/` are RENDERED. Any `command/` or `manifest.json` edit ⇒ `node bin/create-loop.js render` + `node test/installer.test.js`, committing `command/` + both rendered dirs **together**. **`command/loop-run.md:27-33` mirrors the per-node sequence — so C5 triggers this gate.**
- Vocabulary source-of-truth order: `references/` → `schemas/` → `scripts/checks/__init__.py` → `SKILL.md`. Sweep ALL layers in ONE commit.
- Any vocabulary change ⇒ its negative fixture in `tests/failure_mode_tests.md` must STILL REJECT, same commit.
- Green gate = full `tests/acceptance_tests.md` sequence + `node test/installer.test.js`.
- **R-rule numbers are TOMBSTONES — never renumber** (fixture IDs pinned across 2,617 lines).
- **NO existing gate checks Markdown pointer integrity.** A pointer checker is a WAVE-0 PRECONDITION for any file deletion or move.
- Validators need `python3` + `PyYAML`.
- `SKILL.md` ≤ 1000 lines (enforced). Currently 803. **Line count is NOT a goal.**

---

## Task Dependency Graph

| Task | Depends On | Reason |
|------|------------|--------|
| **T0.1** pointer-integrity checker | None | Precondition for every deletion/move; no existing gate covers it |
| **T0.2** baseline snapshot + revert oracle | None | Rollback anchor for all later waves |
| **T0.3** RED fixture: resume-safety (E4) | None | TDD guard authored before the Wave-2 repair |
| **T0.4** RED fixture: assurance axis (C2) | None | TDD guard authored before the Wave-3 change |
| **T0.5** RED fixture: goal-contract readers (C3) | None | TDD guard authored before the Wave-3 change |
| **T0.6** reconstruction-proof harness (C1/D1) | None | Produces the evidence that resolves fork D1 |
| **T1.1** repair integrity checker (E4) | T0.2, T0.3 | Turns T0.3 RED→GREEN; needs revert oracle |
| **T1.2** repair R28 depth contradiction | T0.2 | Independent text repair |
| **T1.3** repair duplicate R36 statement | T0.2 | Independent text repair |
| **T1.4** repair example R34 contradiction | T0.2 | Independent text repair |
| **T2.1** goal-contract readers (C3) | T0.5, T1.1 | Needs RED fixture + trustworthy integrity gate |
| **T2.2** assurance axis (C2) | T0.4, T1.1 | Needs RED fixture; verification must be trustworthy first |
| **T2.3** score-vs-threshold enforcement | T2.2 | `assurance` must exist before scored gates bind to it |
| **T3.1** external-knowledge procedure | T2.1 | New procedure must read the goal contract |
| **T3.2** executable-design procedure | T2.1 | Same |
| **T3.3** blind verification + verdict-first | T2.2 | `blind` assurance level must exist first |
| **T3.4** dissent protocol | T3.3 | Overriding a blind reviewer presupposes blind reviewers |
| **T4.1** C5 ORIENT/WORK/COMMIT | T2.1, T2.2 | Sequence must reference the new readers + gates |
| **T4.2** C4 de-persona | T0.1 | Touches files with inbound pointers |
| **T4.3** attention invoice | T4.1 | Lands inside the COMMIT phase |
| **T4.4** render + installer gate | T4.1 | `command/loop-run.md` changed ⇒ mandatory |
| **T5.1** run reconstruction proof | T0.6, T4.1 | Needs harness + final write set |
| **T5.2** **DECISION POINT D1** | T5.1 | Resolved by T5.1's measured output |
| **T6.1** collapse projections (branch A) | T5.2 | Gated on decision |
| **T6.2** design tournament | T3.3 | Reuses blind-verification primitive |
| **T7.1** subtraction: 3 verified-clean fields | T0.1, T5.2 | Post-decision; needs pointer gate |
| **T7.2** research-file removal + 54-link repair | T0.1 | Needs pointer gate to prove no dangling links |

---

## Parallel Execution Graph

```
Wave 0 — additive only, zero risk, all parallel
├── T0.1  pointer-integrity checker
├── T0.2  baseline snapshot + revert oracle
├── T0.3  RED: resume-safety fixture
├── T0.4  RED: assurance fixture
├── T0.5  RED: goal-contract-reader fixture
└── T0.6  reconstruction-proof harness
        ⇣ GATE G0

Wave 1 — REPAIR, independent files, all parallel
├── T1.1  integrity checker loads event log   (T0.3 RED→GREEN)
├── T1.2  R28 "arbitrary depth" repair
├── T1.3  duplicate R36 statement repair
└── T1.4  example R34 contradiction repair
        ⇣ GATE G1

Wave 2 — ADDITIVE core, 2 parallel then 1 serial
├── T2.1  goal-contract readers  (C3)   ─┐ parallel
├── T2.2  assurance axis         (C2)   ─┘
└── T2.3  score-vs-threshold  [after T2.2]
        ⇣ GATE G2

Wave 3 — ADDITIVE procedures, 3 parallel then 1
├── T3.1  external-knowledge procedure   ─┐
├── T3.2  executable-design procedure    ─┤ parallel
├── T3.3  blind verification             ─┘
└── T3.4  dissent protocol  [after T3.3]
        ⇣ GATE G3

Wave 4 — STRUCTURAL attention budget (serial: shared SKILL.md)
├── T4.1  ORIENT/WORK/COMMIT  (C5)
├── T4.2  de-persona          (C4)   [parallel with T4.1 — different files]
├── T4.3  attention invoice   [after T4.1]
└── T4.4  render + installer  [after T4.1; MANDATORY]
        ⇣ GATE G4

Wave 5 — MEASURE + DECIDE
├── T5.1  run reconstruction proof
└── T5.2  ★ DECISION POINT D1 ★
        ⇣ GATE G5

Wave 6 — branch-dependent
├── T6.1  collapse projections  [branch A only]
└── T6.2  design tournament     [both branches; parallel]
        ⇣ GATE G6

Wave 7 — SUBTRACTION last (highest link blast radius)
├── T7.1  3 verified-clean fields
└── T7.2  research files + 54-link repair
        ⇣ GATE G7
```

**Critical path:** T0.5 → T2.1 → T4.1 → T5.1 → T5.2 → T6.1
**Why subtraction is LAST, not first:** every deletion's blast radius is measured in inbound Markdown links, and the only gate that can see those links is built in T0.1. Deleting early also destroys the reconstruction evidence T5.1 needs to resolve D1.

---

## Tasks

### Wave 0 — Instrumentation and RED fixtures

Precondition: baseline green (verified).

---

#### T0.1 — Pointer-integrity checker
`skills/create-loop/scripts/check_pointers.py` (new): **ADDITIVE**

**For:** the constraint that no gate checks Markdown pointer integrity — a Wave-0 precondition for T7.1/T7.2/T4.2.

Walk every `.md` under the skill root, extract relative Markdown links + `#anchor` fragments, resolve against disk, report dangling. Exit nonzero on any dangling link. Include an `--baseline <file>` mode so pre-existing orphans do not block (2 known on-disk orphans exist).

**Verify by:** `python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt` → exit 0, prints `POINTERS OK: N links, 0 dangling`. Then negative-test it: `python3 scripts/check_pointers.py` against a temp copy with one reference file removed → exit nonzero naming the severed link.

**Delegation:** Category `deep` — one goal, one deliverable, needs autonomous link-graph reasoning. Skills: `programming` (Python, strict types, 250-LOC ceiling).
**Skills Evaluation:** INCLUDED `programming` — new `.py` file, repo mandates it for any Python work. OMITTED `debugging` — no runtime bug to diagnose. OMITTED `ast-grep` — Markdown links, not code AST. OMITTED `tdd` — the acceptance-doc format is the test harness here, covered by T0.2's contract.

**Depends On:** None
**Acceptance:** Exit 0 on clean tree with baseline; exit nonzero + names the file when any reference file is removed; zero new dependencies beyond stdlib + PyYAML.

---

#### T0.2 — Baseline snapshot + revert oracle
`skills/create-loop/tests/baseline_green.md` (new): **ADDITIVE**

**For:** rollback safety for every subsequent wave.

Record the verified-green baseline as a single runnable script + expected output: 11 schemas parse & Draft-07 valid, 11 templates validate, 4 example validations, 2 `INTEGRITY OK` lines, `render_dag.py` → 3, `installer.test.js` → 15 passed, `SKILL.md` = 803 lines. Capture `git rev-parse HEAD` as the revert anchor.

**Verify by:** `bash tests/baseline_green.sh` → exit 0, all assertions pass; re-running twice is idempotent.

**Delegation:** Category `quick` — mechanical capture of already-verified commands. Skills: none.
**Skills Evaluation:** OMITTED `programming` — shell assertions only, no `.py`/`.ts` authoring. OMITTED `tdd` — this records an existing green state rather than driving new behavior.

**Depends On:** None
**Acceptance:** One command reproduces the full green gate; documented `git` SHA to revert to.

---

#### T0.3 — RED fixture: resume-safety (guards T1.1)
`skills/create-loop/tests/failure_mode_tests.md` (append **R42**): **ADDITIVE (test-first)**

**For:** defect E4 — `check_loop_integrity.py` exits 0 on an unresumable loop.

Author fixture **R42 INCOMPLETE-STATE**: a loop dir containing only `loop.plan.yaml`. Must be a **runnable** fixture (heredoc materialization + command + expected output), because R19–R41 are prose-only and that is a known weakness.

**Observe RED:** `python3 scripts/check_loop_integrity.py /tmp/fx_r42/L900-probe` currently → `INTEGRITY OK`, exit 0. **This is the RED state — proved empirically during planning.** Fixture expects exit nonzero tagged `[R42 INCOMPLETE-STATE]`; it therefore fails now.

**Verify by:** running the fixture command and observing exit 0 + `INTEGRITY OK` = documented RED.

**Delegation:** Category `deep` — must design the fixture to fail for the right reason. Skills: `tdd`.
**Skills Evaluation:** INCLUDED `tdd` — this is literally red-green-refactor; the user's environment requires RED→GREEN evidence. OMITTED `programming` — Markdown fixture doc, not source. OMITTED `debugging` — the defect is already diagnosed and proved.

**Depends On:** None
**Acceptance:** Fixture is runnable (not prose); documented as RED with captured actual output; uses R42 (next free number); no existing R-rule renumbered.

---

#### T0.4 — RED fixture: assurance axis (guards T2.2)
`skills/create-loop/tests/failure_mode_tests.md` (append **R43**, **R44**): **ADDITIVE (test-first)**

**For:** C2.

- **R43 SELF-ATTESTED-COMPLETION** — a ledger entry with `gate_kind: llm_judge`, `assurance: self_attested`, `verdict: pass` backing a `completed` node must be REJECTED.
- **R44 MISSING-ASSURANCE** — a ledger entry with no `assurance` field must be REJECTED.

**Observe RED:** `assurance` appears **nowhere** in any script (verified). Both fixtures currently pass validation → exit 0 where nonzero is expected = RED.

**Verify by:** run both fixture commands now; both exit 0. Documented RED.

**Delegation:** Category `deep`. Skills: `tdd`.
**Skills Evaluation:** INCLUDED `tdd` — RED→GREEN discipline. OMITTED `programming` — Markdown. OMITTED `domain-modeling` — vocabulary is already decided by C2; this encodes it, not debates it.

**Depends On:** None
**Acceptance:** Both fixtures runnable; both documented RED with captured output; numbered R43/R44.

---

#### T0.5 — RED fixture: goal-contract readers (guards T2.1)
`skills/create-loop/tests/failure_mode_tests.md` (append **R45**): **ADDITIVE (test-first)**

**For:** C3.

**R45 GOAL-CONTRACT-UNREAD** — a node transitioning to `completed` whose evidence entry does not cite which `success_criteria` it satisfies must be REJECTED. This makes the C3 reader *checkable* rather than merely instructed — otherwise C3 is prose an agent can skip.

**Observe RED:** no schema field links an evidence entry to a `success_criteria` id; fixture passes today → RED.

**Verify by:** run fixture; exits 0 today. Documented RED.

**Delegation:** Category `ultrabrain` — designing a *checkable* goal-contract citation without over-constraining is the genuinely hard logic decision in this plan. Give the goal, not steps. Skills: `tdd`.
**Skills Evaluation:** INCLUDED `tdd` — RED→GREEN mandatory. OMITTED `programming` — Markdown fixture. OMITTED `codebase-design` — no module interface being shaped here.

**Depends On:** None
**Acceptance:** Fixture runnable + documented RED; the citation mechanism it asserts is expressible in the existing evidence-ledger schema shape.

---

#### T0.6 — Reconstruction-proof harness (produces D1's deciding evidence)
`skills/create-loop/scripts/prove_reconstruction.py` (new): **ADDITIVE**

**For:** C1 + fork D1's blocking constraint — *do not collapse any projection until ONE canonical model provably reconstructs every discarded field.*

Given a loop dir, replay `state/event_log.jsonl` and attempt to reconstruct **every field** of `checkpoint.yaml`, `loop.state.yaml`, `node.contract.yaml`, and `artifacts/INDEX.yaml`. Emit a three-way classification per field: `RECONSTRUCTIBLE` / `NOT-RECONSTRUCTIBLE` / `NO-EVENT-SOURCE`. Exit 0 always (it is a **measurement instrument**, not a gate).

**Verify by:** run against `examples/example_child_loop_tree/L001-example-delivery` and both other examples → prints a per-field table; count of `NOT-RECONSTRUCTIBLE` is the number T5.2 decides on.

**Delegation:** Category `ultrabrain` — this is the hardest logic in the plan: deciding what "reconstructible" means per field, and it is the sole evidence resolving the one irreversible fork. Skills: `programming`.
**Skills Evaluation:** INCLUDED `programming` — new Python, strict-typing rules apply. OMITTED `tdd` — a measurement instrument has no pass/fail to drive red-green. OMITTED `deep-research` — inputs are local files, not literature.

**Depends On:** None
**Acceptance:** Runs on all 3 examples; every field of all 4 artifacts classified; output is machine-diffable (stable field order) so T5.1 can re-run and compare.

---

### GATE G0 — must be GREEN before Wave 1
```bash
cd skills/create-loop
bash tests/baseline_green.sh                                    # exit 0
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt   # exit 0
python3 scripts/prove_reconstruction.py examples/example_child_loop_tree/L001-example-delivery  # exit 0
python3 -m py_compile scripts/*.py scripts/checks/*.py          # exit 0
cd ../.. && node test/installer.test.js                          # 15 passed
```
Plus: **R42–R45 all documented RED with captured actual output.** No production file modified in Wave 0 — only new scripts + appended fixtures.

---

### Wave 1 — REPAIR

Precondition: G0 green; R42 RED.

---

#### T1.1 — Integrity checker loads the event log; state files become mandatory
`skills/create-loop/scripts/check_loop_integrity.py`: **REPAIR**

**For:** defect E4 (proved: plan-only dir → `INTEGRITY OK`, exit 0).

Replace the optional `.exists()` guards (lines ~50-74, ~104, ~125, ~132) so that a loop dir claiming to be resumable MUST have `checkpoint.yaml`, `evidence.ledger.yaml`, and `state/event_log.jsonl`. Load and parse the event log (currently **never opened** — verified). Emit `[R42 INCOMPLETE-STATE]` when a required state file is missing. Keep the genuinely-optional ones optional (`INDEX.yaml` for a childless loop).

**Verify by:** `python3 scripts/check_loop_integrity.py /tmp/fx_r42/L900-probe` → exit nonzero, `[R42 INCOMPLETE-STATE]` (**R42 RED→GREEN**), AND both real examples still print `INTEGRITY OK` (no regression).

**Delegation:** Category `deep`. Skills: `programming`, `tdd`.
**Skills Evaluation:** INCLUDED `programming` — modifying `.py`. INCLUDED `tdd` — must flip R42 RED→GREEN with evidence. OMITTED `debugging` — root cause already established empirically. OMITTED `refactor` — behavior change, not restructuring.

**Depends On:** T0.2, T0.3
**Acceptance:** R42 GREEN; both examples still `INTEGRITY OK`; event log actually parsed (assert by pointing at a corrupt JSONL and getting a nonzero exit).

---

#### T1.2 — R28 depth contradiction
`skills/create-loop/references/recursive_loops.md:52`: **REPAIR**

**For:** defect 8 — "to arbitrary depth" contradicts `termination.max_depth` enforced by R28 (`caps.py:41`).

Replace "to arbitrary depth" with a statement bounded by `termination.max_depth`, citing R28.

**Verify by:** `grep -rn "arbitrary depth" references/` → no hits; the R28 fixture still rejects; `check_pointers.py` → 0 dangling.

**Delegation:** Category `quick` — single-line text repair with a known correct target. Skills: none.
**Skills Evaluation:** OMITTED `programming` — Markdown prose only. OMITTED `writing` — one clause, not prose authoring.

**Depends On:** T0.2
**Acceptance:** No "arbitrary depth" claim; R28 fixture still rejects; no R-rule renumbered.

---

#### T1.3 — Duplicate, non-identical R36 statement
`skills/create-loop/references/evidence_gates.md:33-47` and `:262-265`: **REPAIR**

**For:** defect — two NON-IDENTICAL versions of the verifier-independence rule (the second adds `step_verifier` + threshold). Two sources of truth for one rule.

Make `:33-47` canonical; replace `:262-265` with a pointer to it. Preserve the union of both constraints (do not silently drop the `step_verifier`/threshold clause).

**Verify by:** `grep -c` the independence rule → exactly one normative statement; R36 fixture still rejects; `provenance.py` unchanged (this is a doc repair only).

**Delegation:** Category `quick`. Skills: none.
**Skills Evaluation:** OMITTED `programming` — no code. OMITTED `domain-modeling` — de-duplicating an existing rule, not defining a term.

**Depends On:** T0.2
**Acceptance:** Single normative statement; union of constraints preserved; R36 fixture still rejects.

---

#### T1.4 — Example contradicts R34
`skills/create-loop/examples/example_research_project/README.md:78-83`: **REPAIR**

**For:** defect — README claims `N9_recommendation_approval` is "gate-exempt" with `gate: null`, contradicting R34 (`checks/gates.py:24-35`) which requires approval nodes to carry a `human_approval` gate.

Correct the README to match R34 and the shipped `loop.plan.yaml`. **Read the actual plan first** — if the plan also has `gate: null`, the plan is the defect and validation is currently passing something it should reject; report that rather than papering over the README.

**Verify by:** `python3 scripts/validate_loop_plan.py examples/example_research_project/loop.plan.yaml` → exit 0; README statement now matches the plan; R34 fixture still rejects.

**Delegation:** Category `deep` — must determine which of README/plan is wrong rather than assume. Skills: none.
**Skills Evaluation:** OMITTED `programming` — Markdown + YAML data. OMITTED `tdd` — R34 fixture already exists; this is a consistency repair.

**Depends On:** T0.2
**Acceptance:** README and plan agree; R34 fixture still rejects; if the plan was the defect, that is reported explicitly.

---

### GATE G1
```bash
bash tests/baseline_green.sh                    # exit 0 (all 4 examples, 2 integrity)
# R42 GREEN:
python3 scripts/check_loop_integrity.py /tmp/fx_r42/L900-probe   # nonzero + [R42 INCOMPLETE-STATE]
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt   # 0 dangling
grep -rn "arbitrary depth" references/          # no hits
# R28, R34, R36 fixtures still reject
cd ../.. && node test/installer.test.js         # 15 passed
```

---

### Wave 2 — ADDITIVE core (C3 + C2)

Precondition: G1 green; R43/R44/R45 RED.

---

#### T2.1 — Goal-contract readers at 4 points
`references/state_model.md`, `references/evidence_gates.md`, `schemas/evidence.ledger.schema.json`, `scripts/checks/__init__.py`, `scripts/validate_loop_plan.py`, `SKILL.md` §10, `templates/evidence.ledger.yaml`: **ADDITIVE**

**For:** C3 — the most irreplaceable mechanism per Oracle A. Confirmed defect: `SKILL.md:506` reads `checkpoint, contract, ledger`, never the goal contract.

Add a mandatory re-read of `success_criteria` / `failure_criteria` / `non_goals` / `constraints` / `scope` at **dispatch** (before choosing a ready node), **mutation** (before any plan edit), **verification** (before writing a verdict), **termination** (before declaring `done_when`). Make it *checkable* by requiring each evidence entry to cite the `success_criteria` id(s) it bears on — the mechanism designed in T0.5.

**Chain:** records *which criterion a verdict bears on* → changes *whether a node may be marked completed, and what verification targets* → improves *goal adherence; goal drift becomes mechanically detectable rather than a felt symptom.*

**Sweep order (mandatory):** `references/` → `schemas/` → `scripts/checks/__init__.py` → `SKILL.md`. ONE commit.

**Verify by:** R45 RED→GREEN; all 11 templates still validate; all 4 examples still validate (they must be updated to carry the citation, or the field must be additive-optional-with-enforcement-on-completed — decide and state which); `check_pointers.py` 0 dangling.

**Delegation:** Category `ultrabrain` — coordinated 4-layer vocabulary change where the hard part is making a reader enforceable without breaking 4 worked examples. Skills: `programming`, `tdd`, `domain-modeling`.
**Skills Evaluation:** INCLUDED `programming` — edits `.py` validators. INCLUDED `tdd` — R45 must flip RED→GREEN. INCLUDED `domain-modeling` — introduces a durable cross-artifact relationship (evidence→criterion) into locked vocabulary; the skill's source-of-truth discipline is exactly this. OMITTED `codebase-design` — no module seam moving. OMITTED `deep-research` — decision already made by C3.

**Depends On:** T0.5, T1.1
**Acceptance:** R45 GREEN; 11/11 templates + 4/4 examples validate; all 4 read points present in `SKILL.md` §10; all 4 layers swept in ONE commit; no R-rule renumbered.

---

#### T2.2 — The `assurance` axis
`references/evidence_gates.md`, `references/loop_plan_spec.md`, `references/state_model.md`, `schemas/evidence.ledger.schema.json`, `scripts/checks/__init__.py`, `scripts/validate_loop_plan.py`, `templates/evidence.ledger.yaml`, `SKILL.md` §10: **STRUCTURAL**

**For:** C2 — 4 of 8 gate kinds are self-attested; all write identical `verdict: pass`; no reader distinguishes them. Verified: `assurance` appears nowhere in any script.

Add `assurance: external | blind | self_attested` to every evidence entry, **orthogonal** to the 8 gate kinds (do not extend the gate enum — R7's fixture depends on it). Enforce: only `external` and `human_approval` may authorize `completed`; `self_attested` yields `provisional` only. Introduce `provisional` carefully — the 15 node statuses are locked vocabulary, so either map `provisional` onto an existing status or add it through the full sweep and state which.

**Chain:** records *where a verdict came from* → changes *whether that verdict may authorize completion* → improves *result trustworthiness; a model's self-preference (persisting ~86% MATH500 / ~73% MMLU specifically when its own answer is wrong, Chen arXiv:2504.03846) can no longer close a node.*

**Verify by:** R43 + R44 RED→GREEN; **R7 gate-kind fixture STILL REJECTS** (proves the axis is orthogonal, not an enum extension); 11/11 templates; 4/4 examples.

**Delegation:** Category `ultrabrain` — genuinely hard: adding an orthogonal axis to locked vocabulary across 4 layers without disturbing 41 pinned fixtures. Skills: `programming`, `tdd`, `domain-modeling`.
**Skills Evaluation:** INCLUDED `programming` — validator edits. INCLUDED `tdd` — R43/R44 RED→GREEN. INCLUDED `domain-modeling` — new canonical enum entering locked vocabulary; source-of-truth order is the skill's core discipline. OMITTED `refactor` — adding an axis, not restructuring. OMITTED `security-review` — this is verification integrity, not a security boundary.

**Depends On:** T0.4, T1.1
**Acceptance:** R43+R44 GREEN; R7 still rejects; the 8 gate kinds unchanged; `provisional`'s status treatment explicitly documented; 4 layers in ONE commit.

---

#### T2.3 — Make `score` load-bearing
`scripts/validate_loop_plan.py`, `scripts/checks/gates.py`, `tests/failure_mode_tests.md` (**R46**): **REPAIR**

**For:** defect — `score` is required on EVERY ledger entry (verified: `validate_loop_plan.py:196`) but **no validator ever compares it to `threshold`**. `score: 0.0` + `verdict: pass` validates clean. A required field that changes nothing.

Add: for the 4 scored gate kinds, `verdict: pass` requires `score >= threshold`. Also enforce that the ledger's `gate_kind` MATCHES the node's configured gate (verified: never cross-checked today — each is only checked for enum membership).

**Write R46 FIRST and observe RED** (`score: 0.0` + `verdict: pass` + `threshold: 0.7` currently validates), then GREEN.

**Verify by:** R46 RED→GREEN; 11/11 templates; 4/4 examples (fix any example that relied on the inert `score`).

**Delegation:** Category `deep`. Skills: `programming`, `tdd`.
**Skills Evaluation:** INCLUDED `programming` — validator logic. INCLUDED `tdd` — R46 RED→GREEN. OMITTED `domain-modeling` — no new vocabulary; enforcing an existing field.

**Depends On:** T2.2
**Acceptance:** R46 GREEN; scored gates bind `score`↔`threshold`; ledger `gate_kind` cross-checked against the node's gate; 4/4 examples validate.

---

### GATE G2
```bash
bash tests/baseline_green.sh                                     # exit 0
# R43, R44, R45, R46 GREEN; R42 still GREEN
# R7 STILL REJECTS  (assurance is orthogonal, not an enum extension)
# every previously-passing fixture R1-R41 still rejects
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt
cd ../.. && node test/installer.test.js                          # 15 passed
```

---

### Wave 3 — ADDITIVE procedures + blind verification

Precondition: G2 green.

---

#### T3.1 — External knowledge acquisition procedure
`references/execution_intelligence_policy.md` (extend — **PRESERVE asset**), `templates/interview_brief.md:146-156`, `SKILL.md` §16 pointer: **ADDITIVE**

**For:** gap RANK 1 (HIGH) — currently **NAMED-ONLY**, ~15 lines. Research is named but no external-source / real-API verification procedure exists.

Write an actual procedure: when external knowledge is required; how to distinguish a primary source from a recalled one; how to *verify* an API/library claim by executing against it rather than asserting it; how the finding enters evidence with `assurance: external`.

**Chain:** records *a verified external fact + its source* → changes *design decisions that would otherwise rest on model recall* → improves *correctness against real APIs, and prevents confidently-wrong implementation.*

**Verify by:** the procedure names ≥1 concrete verification action producing an `external`-assurance artifact; `SKILL.md` reference map registers any new doc; `check_pointers.py` 0 dangling; full green gate.

**Delegation:** Category `writing` — this is authoring behavioral prose into the skill's strongest existing policy doc; the model choice favors prose quality. Skills: `research`, `context7`.
**Skills Evaluation:** INCLUDED `research` — the task is *defining* a research procedure; the skill encodes primary-source discipline. INCLUDED `context7` — the canonical mechanism for verifying live library/API facts is exactly what this procedure must instruct the agent to use. OMITTED `programming` — Markdown prose. OMITTED `deep-research` — writing a procedure, not conducting a study.

**Depends On:** T2.1
**Acceptance:** Procedure is executable (concrete actions, not exhortation); ties to `assurance: external`; `execution_intelligence_policy.md`'s existing §3.2/§3.5 content untouched; green gate.

---

#### T3.2 — Executable technical design procedure
`references/execution_intelligence_policy.md` (extend), `templates/interview_brief.md:199-211`, new `templates/design_brief.md`, `SKILL.md` §16: **ADDITIVE**

**For:** gap RANK 2 (HIGH) — currently **NAMED-ONLY**, ~30 lines. Architecture and ADRs are named without required interfaces, data flow, or a design artifact.

Require a design artifact with: module interfaces (per the deep-module discipline — a lot of behavior behind a small interface, at a clean seam), data flow, the assumptions the design rests on, and how each will be verified. Design must cite `success_criteria` (composes with T2.1).

**Chain:** records *interfaces + data flow + design assumptions* → changes *implementation from improvisation to executing a stated design, and makes assumptions individually falsifiable* → improves *architectural coherence and catches contradictions before code exists.*

**Verify by:** new template validates if schema-bound (or is prose-only by design — state which); `SKILL.md` reference map registers it; `check_pointers.py` 0 dangling; green gate.

**Delegation:** Category `writing`. Skills: `codebase-design`, `domain-modeling`.
**Skills Evaluation:** INCLUDED `codebase-design` — supplies the exact deep-module/seam/interface vocabulary this procedure must demand. INCLUDED `domain-modeling` — a design brief is where ubiquitous language and ADR-worthiness get decided; the skill defines when an ADR is warranted (hard to reverse + surprising + real trade-off). OMITTED `design-an-interface` — that spawns parallel competing designs; that is T6.2's job, not this one. OMITTED `programming` — Markdown.

**Depends On:** T2.1
**Acceptance:** Design artifact requires interfaces + data flow + falsifiable assumptions; cites `success_criteria`; registered in the reference map; green gate.

---

#### T3.3 — Blind verification + verdict-first ordering
`references/evidence_gates.md`, `references/branching_parallelism.md` (**PRESERVE** the isolation rule at :142-149), `schemas/evidence.ledger.schema.json`, `scripts/checks/provenance.py`, `tests/failure_mode_tests.md` (**R47**), `SKILL.md`: **ADDITIVE**

**For:** invention — information barring; the only genuinely AI-unique lever and the only structural fix for self-preference. Upgrades R36 from "different role string" to real independence. Verified weakness: the ledger carries no producer/verifier/session/model ID, so a producing agent can simply label its own verdict `verifier: subagent`.

Define `assurance: blind`: the verifier subagent receives **artifact + criteria only** — never the producer's verdict or rationale. Verdict-first ordering: the reviewer writes its verdict file BEFORE reading the producer's claim, so **file mtime makes independence checkable**. Add R47 rejecting a `blind` entry whose verdict-file mtime is later than its read of the producer's claim.

**Chain:** records *a verdict formed without seeing the producer's claim, with a checkable timestamp* → changes *agreement from an echo into evidence* → improves *result trustworthiness precisely in the case self-grading fails — when the model's own answer is wrong.*

**Verify by:** R47 RED (no mtime rule today) → GREEN; **R36 fixture still rejects**; 11/11 templates; 4/4 examples.

**Delegation:** Category `ultrabrain` — designing a checkable independence proof from filesystem metadata is subtle logic with an adversarial threat model. Skills: `programming`, `tdd`.
**Skills Evaluation:** INCLUDED `programming` — `provenance.py` edits. INCLUDED `tdd` — R47 RED→GREEN. OMITTED `security-review` — the adversary is a careless agent, not an attacker; a full threat-model orchestration is disproportionate. OMITTED `domain-modeling` — `blind` already enters vocabulary in T2.2.

**Depends On:** T2.2
**Acceptance:** R47 GREEN; R36 still rejects; the isolation rule at `branching_parallelism.md:142-149` preserved verbatim; mtime check does not false-positive on the 4 examples.

---

#### T3.4 — Dissent protocol
`references/evidence_gates.md`, `references/human_approval.md`, `schemas/event_log.schema.json`, `tests/failure_mode_tests.md` (**R48**): **ADDITIVE**

**For:** invention — a parent overriding a blind reviewer must record why, making rubber-stamping expensive and auditable.

Require a typed `dissent` event (overridden verdict, override rationale, who) whenever a parent proceeds against a blind reviewer's verdict. R48 rejects an override with no dissent event.

**Chain:** records *why an independent negative verdict was overridden* → changes *override from free to costly and reviewable* → improves *the signal value of blind review; silently ignoring reviewers stops being the path of least resistance.*

**Verify by:** R48 RED→GREEN; existing event-log fixtures (R23/R24/R31/R39) still reject; green gate.

**Delegation:** Category `deep`. Skills: `programming`, `tdd`.
**Skills Evaluation:** INCLUDED `programming` — schema + validator. INCLUDED `tdd` — R48 RED→GREEN. OMITTED `domain-modeling` — one event kind added within an established pattern.

**Depends On:** T3.3
**Acceptance:** R48 GREEN; R23/R24/R31/R39 still reject; `dissent` follows the existing typed-event convention.

---

### GATE G3
```bash
bash tests/baseline_green.sh
# R47, R48 GREEN; R42-R46 still GREEN; R1-R41 all still reject
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt   # 0 dangling
grep -n "142" references/branching_parallelism.md    # isolation rule intact
cd ../.. && node test/installer.test.js
```

---

### Wave 4 — STRUCTURAL: the attention budget

Precondition: G3 green. **`SKILL.md` is single-writer — T4.1 and T4.3 are serial.**

---

#### T4.1 — ORIENT → WORK → COMMIT
`SKILL.md` §10 (lines 496-570, the `for the chosen ready node:` block at 503-515), `command/loop-run.md:27-33`, `references/state_model.md`, `references/recovery_protocol.md`: **STRUCTURAL**

**For:** C5 — measured 9:1 write-to-read.

Restructure the per-node sequence into three phases:
- **ORIENT (read-only)** — goal contract (T2.1) + frontier. No writes.
- **WORK** — the actual engineering.
- **COMMIT (≤3 appends)** — event-log append, evidence append, snapshot **regenerated** (never hand-maintained field-by-field).

**Nothing may be written twice.** Preserve the write-ahead bracket (`pre_effect`/`post_effect` + idempotency key) — a named PRESERVE asset. Do NOT collapse any projection here; that is T6.1, gated on D1. This wave changes *ordering and duplication*, not *which artifacts exist* — that separation is what keeps Wave 4 safe under both D1 branches.

**Chain:** records *the same facts once instead of ~78 times across 7 files* → changes *where agent attention goes — from field ceremony to engineering* → improves *the actual work product, which is the user's whole complaint.*

**⚠ `command/loop-run.md` is edited ⇒ T4.4 render gate is MANDATORY.**

**Verify by:** count mandated writes in the new sequence < 78 and no fact written twice (state the new count); 4/4 examples validate; 2× `INTEGRITY OK`; `SKILL.md` ≤ 1000 lines.

**Delegation:** Category `ultrabrain` — the central structural change, must preserve crash-safety while removing duplication. Skills: `programming`, `codebase-design`.
**Skills Evaluation:** INCLUDED `programming` — touches validator-adjacent contracts. INCLUDED `codebase-design` — ORIENT/WORK/COMMIT is a seam-placement and interface-depth decision (small interface, behavior hidden). OMITTED `tdd` — no new rule; guarded by existing fixtures + the write-count assertion. OMITTED `refactor` — a designed restructure, not mechanical cleanup.

**Depends On:** T2.1, T2.2
**Acceptance:** Three phases explicit; write count reduced and stated; no fact written twice; write-ahead bracket preserved; `command/loop-run.md` consistent with `SKILL.md`; ≤1000 lines.

---

#### T4.2 — De-persona; preserve the question sets
`references/recursive_planning_immersive_execution.md:93-94`, `templates/interview_brief.md:60-76`: **SUBTRACTION (labels) + ADDITIVE (checklists)**

**For:** C4 — "architect · project lead · layout designer" vs "executor · researcher · engineer · verifier" (same agent, same context, different label) and "You are three things at once" (3 hats, 1 context, no independent verdict). 7 hats on 1 head, zero isolation.

**4-reader evidence licensing the label removal:** the role strings have **no validator reader** (no script matches them), **no schema field**, **no template field**, and **no closeout reader**. They are prose identity only. **Verified: the question sets live in the SAME table** — the `role it plays` column is the label; the `it focuses on` column is the substance. Drop the label column, keep the question column, re-express as a phase-attached checklist.

**Rollback if gate fails:** `git revert` the single commit; both files are prose-only with no schema/validator coupling, so revert is complete and side-effect free.

**KEEP (do not touch):** `assignee: user`, `assignee: subagent`, the context-isolation rule (`branching_parallelism.md:142-149`), generator≠verifier (R36) — all 8 perspective-allocating mechanisms survive.

**Chain:** records *the questions to ask at each phase* → changes *what gets examined, without pretending one context is several people* → improves *examination quality while removing the illusion that a label creates independence.*

**Verify by:** `grep -rn "three things at once\|architect · project lead"` → no hits; every question from the old table present in the new checklists (enumerate them 1:1); `check_pointers.py` 0 dangling; green gate.

**Delegation:** Category `writing` — prose restructuring where fidelity of the preserved question set is the whole risk. Skills: `writing-great-skills`.
**Skills Evaluation:** INCLUDED `writing-great-skills` — directly about converting identity prose into checkable steps and detecting no-ops; this task is exactly that operation. OMITTED `programming` — no code. OMITTED `remove-ai-slops` — targeted prose surgery, not slop cleanup. OMITTED `edit-article` — a skill doc, not an article.

**Depends On:** T0.1
**Acceptance:** Zero persona labels; 1:1 question preservation demonstrated; all 8 perspective mechanisms intact; 0 dangling pointers; green gate.

---

#### T4.3 — Attention invoice
`SKILL.md` §10 COMMIT phase, `templates/node.contract.yaml` or `templates/run.log.md`: **ADDITIVE**

**For:** invention — replace field ceremony with signal.

Per node, record three things: what was **LEARNED**, what **SURPRISED**, what was **VERIFIED vs BELIEVED**. Keep it inside the ≤3 COMMIT appends — this must not become write #79.

**Chain:** records *what actually changed in the agent's understanding, and which beliefs are unverified* → changes *what a resuming session treats as solid vs assumed, and surfaces surprises that should trigger replanning* → improves *long-run design correction — the failure mode where stale assumptions silently persist.*

**Verify by:** total COMMIT appends still ≤3; 4/4 examples validate; green gate.

**Delegation:** Category `deep`. Skills: `writing-great-skills`.
**Skills Evaluation:** INCLUDED `writing-great-skills` — the risk is authoring a no-op the model already does by default; this skill's no-op test is the guard. OMITTED `programming` — template/prose. OMITTED `tdd` — no new rejection rule.

**Depends On:** T4.1
**Acceptance:** Three fields present; ≤3 COMMIT appends preserved; not a no-op (state what behavior changes vs default); green gate.

---

#### T4.4 — Render + installer gate (MANDATORY)
`command/` → `.opencode/command/` + `.claude/commands/`: **REPAIR (build discipline)**

**For:** the hard repo constraint. T4.1 edits `command/loop-run.md`.

```bash
node bin/create-loop.js render
node test/installer.test.js
```
Commit `command/` + BOTH rendered dirs together.

**Verify by:** `installer.test.js` → 15 passed; running `render` twice is byte-for-byte identical (`git status` clean on the second run — determinism is asserted by the test).

**Delegation:** Category `quick`. Skills: `git-master`.
**Skills Evaluation:** INCLUDED `git-master` — the constraint is fundamentally about atomic co-commit of source + rendered artifacts. OMITTED `programming` — running an existing renderer. OMITTED `customize-opencode` — this is the project's own renderer, not opencode config.

**Depends On:** T4.1
**Acceptance:** 15 passed; render idempotent; source + both rendered dirs in ONE commit.

---

### GATE G4
```bash
bash tests/baseline_green.sh
node bin/create-loop.js render && git status --porcelain   # empty ⇒ deterministic
node test/installer.test.js                                # 15 passed
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt
grep -rn "three things at once" skills/create-loop/         # no hits
wc -l skills/create-loop/SKILL.md                          # <= 1000
# R42-R48 GREEN; R1-R41 all still reject
```

---

### Wave 5 — MEASURE, then DECIDE

#### T5.1 — Run the reconstruction proof
`scripts/prove_reconstruction.py` against all 3 examples: **ADDITIVE (measurement)**

**For:** fork D1's blocking constraint.

Produce the per-field table. Explicitly enumerate every field classified `NOT-RECONSTRUCTIBLE` or `NO-EVENT-SOURCE`. Write the result to `.agents/knowledge/reference/` as durable evidence.

**Verify by:** table covers 100% of fields in `checkpoint.yaml`, `loop.state.yaml`, `node.contract.yaml`, `artifacts/INDEX.yaml`; each non-reconstructible field named with the reason.

**Delegation:** Category `ultrabrain` — its output decides the one irreversible fork. Skills: `programming`.
**Skills Evaluation:** INCLUDED `programming` — running/extending the Python harness. OMITTED `tdd` — measurement, not behavior change. OMITTED `deep-research` — local measurement.

**Depends On:** T0.6, T4.1
**Acceptance:** 100% field coverage; non-reconstructible set explicitly enumerated; result persisted.

---

#### T5.2 — ★ DECISION POINT D1 ★ — refactor-in-place vs new state shape

**This is the one fork. It is NOT decided by this plan. It is decided by T5.1's measured output.**

**Position A (refactor in place, steelman):** keep the current artifact set; collapse only provably-redundant projections.
**Position B (new shape, clean-slate):** 6 files — charter / plan / snapshot / events / memory / progress — with a **rolling 3–7-unit execution horizon** instead of a permanent full-project DAG. Rationale: short-horizon plans + observation-driven replanning beat rigid static plans (ReAct, arXiv:2210.03629).

**Why the fork sits HERE and not earlier:** Waves 0–4 are **identical under both branches**. They add readers (C3), an orthogonal assurance axis (C2), procedures (C1 gaps), and reorder attention (C5) — none of which presupposes an artifact set. That is deliberate: it maximizes delivered value before an irreversible choice.

**Exactly what evidence resolves it:** the count and nature of `NOT-RECONSTRUCTIBLE` fields from T5.1.
- **If 0 non-reconstructible** → the canonical event-log model provably reconstructs everything ⇒ **Branch A**: collapse projections (T6.1) is safe, incremental, and reversible.
- **If a small, enumerable set** (e.g. transaction evidence, provenance, child return contracts) → **Branch A with named exceptions**: those fields stay durable; everything else collapses.
- **If large or structural** (the event log cannot express what the artifacts carry) → **Branch B**: refactoring cannot reach the target; the shape itself is wrong. Do NOT execute T6.1; instead scope a new-shape migration as a separate plan with its own reconstruction proof.

**Downstream deltas:**
- **Branch A:** T6.1 executes. `loop.state.yaml`'s fate is decided here (it is subsumed by this decision, not decided separately). Field-level subtraction in T7.1 proceeds.
- **Branch B:** T6.1 is cancelled. Wave 7 subtraction narrows to only the 3 verified-clean fields plus the research files. The 6-file shape requires a fresh reconstruction proof, a migration path for in-flight loops, and a new fixture set — out of scope for this plan.

**Deliverable:** a written decision citing the T5.1 table, recorded as an ADR under `docs/adr/` (hard to reverse + surprising without context + a real trade-off — all three ADR conditions met).

**Delegation:** **NONE — escalate to the user.** This crosses a goal/scope boundary and is irreversible. Present the T5.1 table and the three branch conditions; do not self-authorize.

**Depends On:** T5.1
**Acceptance:** Written decision citing measured evidence; ADR recorded; branch selected by the user, not the agent.

---

### GATE G5
```bash
bash tests/baseline_green.sh          # still green — Wave 5 adds no production change
# T5.1 table exists, 100% field coverage
# D1 decision recorded as an ADR, user-approved
```

---

### Wave 6 — Branch-dependent

#### T6.1 — Collapse duplicate projections  **[BRANCH A ONLY]**
`schemas/checkpoint.schema.json`, `schemas/loop.state.schema.json`, `references/state_model.md`, `references/recovery_protocol.md`, `scripts/checks/loop_state.py` (R30), `scripts/validate_checkpoint.py`: **STRUCTURAL**

**For:** C1 — ~38 of 78 writes are projections of already-durable data; `checkpoint.yaml` is a **full rewrite** per advance (unchanged nodes re-emitted).

Make the checkpoint a **derived cache regenerated from the event log**, not a co-equal hand-maintained artifact. Collapse only fields T5.1 proved reconstructible. **Topology still persists** — `loop.plan` IS the executable program.

If R30 (`loop.state`) is removed: **leave an R-rule tombstone, never renumber.**

**Chain:** records *each fact once in the event log* → changes *snapshot maintenance from ~17 hand-written fields per advance to a regeneration step* → improves *attention available for engineering, and removes projection-drift as a failure mode.*

**Verify by:** every collapsed field re-derivable (re-run T0.6 harness → 0 regressions); 4/4 examples validate; 2× `INTEGRITY OK`; R30 fixture either still rejects or is tombstoned with justification; full green gate.

**Delegation:** Category `ultrabrain` — highest-blast-radius structural change. Skills: `programming`, `tdd`, `codebase-design`.
**Skills Evaluation:** INCLUDED `programming` — schemas + validators. INCLUDED `tdd` — every collapse needs a guard proving reconstruction. INCLUDED `codebase-design` — this is the canonical deep-module move: hide projection behind a regeneration interface. OMITTED `refactor` — semantics change, not mechanical restructuring.

**Depends On:** T5.2 (Branch A)
**Acceptance:** Only proven-reconstructible fields collapsed; reconstruction harness shows 0 regressions; no R-rule renumbered; green gate.

---

#### T6.2 — Design tournament  **[BOTH BRANCHES]**
`references/branching_parallelism.md`, `references/loop_plan_spec.md` (`mapper`/`fanout`), `SKILL.md`: **ADDITIVE**

**For:** invention — resolves the dead-vocabulary question (`mapper` at `SKILL.md:72`; `fanout` load-bearing in 3 places: `checks/__init__.py:73`, the `control_flow` enum at `loop_plan_spec.md:378`, and the invocation description at `SKILL.md:13`) by giving them a real job instead of deleting them.

N competing designs spawned in isolated contexts with **planned casualties** — selection by blind review (T3.3), not by the author. Respect the existing 3–5 fan-out cap.

**Chain:** records *N independent designs + a blind selection verdict* → changes *design from first-idea-wins to compared alternatives chosen by someone who didn't write them* → improves *architecture quality, exploiting cheap parallel spawn — a real AI/human-team difference.*

**Verify by:** `fanout` still passes its enum check (`checks/__init__.py:73` untouched); the 3–5 cap and the context-isolation rule preserved; green gate.

**Delegation:** Category `artistry` — unconventional design mechanism exploiting AI-specific economics. Skills: `design-an-interface`, `codebase-design`.
**Skills Evaluation:** INCLUDED `design-an-interface` — literally "design it twice via parallel sub-agents with planned casualties"; this task generalizes it into the skill. INCLUDED `codebase-design` — supplies the comparison axes (depth, locality, seam placement) that make selection objective. OMITTED `programming` — vocabulary/prose. OMITTED `team-mode` — off by default; the skill's own subagent mechanism is the vehicle.

**Depends On:** T3.3
**Acceptance:** `mapper`/`fanout` have a real mechanism; fan-out cap + isolation rule preserved; existing enum checks unchanged; green gate.

---

### GATE G6
```bash
bash tests/baseline_green.sh
python3 scripts/prove_reconstruction.py <all 3 examples>   # 0 regressions vs T5.1
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt
node test/installer.test.js
# R42-R48 GREEN; R1-R41 all still reject (or tombstoned + justified)
```

---

### Wave 7 — SUBTRACTION (last: highest link blast radius)

#### T7.1 — Delete the 3 fields that actually pass the 4-reader test
`schemas/loop.plan.schema.json` (`runtime_subgraphs[].owner_agent`), retirement schema (`retirement.retired_at`), audited `schema_version` instances: **SUBTRACTION**

**For:** the ceremonial-field claim — **re-scoped after verification.**

**4-reader evidence, per field:**

| Field | validator | instruction | template | closeout/human | Verdict |
|---|---|---|---|---|---|
| `owner_agent` | **0** (`scripts=0`) | 1 mention, `subgraph_subloop_policy.md:400,673` lists it as an *optional enhancement field* — descriptive, not behavioral | **0** | **0** | **DELETE** |
| `retirement.retired_at` | **0** | 1 mention, `recursive_loops.md:681` "so the retirement is auditable" — audit-only, no consumer | **0** | **0** | **DELETE** |
| `schema_version` | 4 script hits — **must audit per artifact** | — | 5 | 2 tests | **DELETE ONLY the instances with no validator reader**; keep where a required-tuple reads it |

**DEFERRED — these were on the incoming list but FAIL the 4-reader test (corrections E1):**

| Field | Why it must NOT be deleted |
|---|---|
| `recorded` | **Validator reader**: in the evidence-entry required-tuple, `validate_loop_plan.py:196`. Deleting breaks R5 for every ledger entry. Also 18 refs, 9 templates. |
| `cache_key` | **Validator reader**: `CONTRACT_REQUIRED`, `checks/__init__.py:89`. Plus 7 refs. |
| `jitter` | **Instruction reader**: the retry-wait formula `wait_n = backoff_base_seconds * 2^n ± jitter`, `exception_handling.md §5.2`. An agent computing a delay reads it. |
| `created_at`, `created_by` | **Validator readers**: `LOOP_META_REQUIRED`, `checks/__init__.py:99`. |
| `heartbeat_at` | **Validator reader** `CLAIM_REQUIRED` (`checks/claim.py:12`) **and** the lease-expiry mechanism (`state_model.md:141-145`). |

**Rollback if gate fails:** each field is deleted in its **own commit** (never batched). `git revert <sha>` restores schema + template + example + fixture together. Because Wave 7 runs last, revert cannot cascade into earlier waves.

**Verify by:** `grep -rn "<field>" skills/create-loop/` → 0 hits after deletion; 11/11 templates; 4/4 examples; `check_pointers.py` 0 dangling; every R1–R48 fixture still behaves; green gate.

**Delegation:** Category `deep` — per-field 4-reader re-verification before each deletion. Skills: `programming`, `git-master`.
**Skills Evaluation:** INCLUDED `programming` — schema edits. INCLUDED `git-master` — one atomic commit per field is the rollback contract. OMITTED `tdd` — removal guarded by existing fixtures + the pointer gate. OMITTED `refactor` — deletion, not restructuring.

**Depends On:** T0.1, T5.2
**Acceptance:** Only the 3 verified fields removed; deferred set untouched; ONE commit per field; green gate after each.

---

#### T7.2 — Research-file removal + 54-link repair
`references/research_dags_multiagent.md` (869), `references/research_durable_loops.md` (640) — **1,509 lines**; **`research-sources.md` PRESERVED**: **SUBTRACTION**

**For:** defect 8 — raw agent transcripts shipped as reference material. **Scope corrected (E2/E3).**

**4-reader evidence:**
- **validator reader:** 0 — no script reads them.
- **instruction reader:** these are transcripts containing thinking-out-loud ("Let me check the project structure and persist the report", "The system is asking me to continue") — no normative instruction.
- **template reader:** 0.
- **closeout/human reader:** they ARE cited — **54 inbound links across 8 files** (`loop_plan_spec.md`×8, `exception_handling.md`×11, `concepts.md`×14, `recovery_protocol.md`×7, `human_approval.md`×5, `evidence_gates.md`×5, `branching_parallelism.md`×2, `state_model.md`×2).

⇒ **Content is deletable; the citations are NOT.** Convert each of the 54 to plain-text attribution (e.g. "Zheng et al. 2023"; "AWS Step Functions retry + jitter") — preserving the claim, killing the dead link. **7 of these sit inside the gate-kind vocabulary table** (`loop_plan_spec.md:160-166`) — that table is locked vocabulary; touch only the citation cell, never the enum.

**`research-sources.md` is PRESERVED** — verified to be a clean cited report (source URLs + filesystem-mapping notes), not a transcript, and it is the one file `SKILL.md:716` points to.

**Rollback if gate fails:** deletion and citation repair land in ONE commit; `git revert <sha>` restores both files and all 54 links atomically. Files are prose-only with zero schema/validator coupling.

**Verify by:** `check_pointers.py` → **0 dangling** (this is the whole point of T0.1); every one of the 54 citations still conveys its claim as text; the gate-kind enum byte-identical; `SKILL.md:716` still resolves; green gate.

**Delegation:** Category `deep` — 54 individual citation repairs where each must preserve its claim. Skills: `writing-great-skills`, `git-master`.
**Skills Evaluation:** INCLUDED `writing-great-skills` — converting pointers to attributions while preserving meaning is exactly its single-source-of-truth/pruning discipline. INCLUDED `git-master` — atomic co-commit of deletion + repair is the rollback contract. OMITTED `programming` — Markdown only. OMITTED `research` — not gathering sources; re-expressing existing ones.

**Depends On:** T0.1
**Acceptance:** 2 files removed; 54 citations converted to text; 0 dangling pointers; gate-kind enum untouched; `research-sources.md` intact; ONE commit; green gate.

---

### GATE G7 — FINAL
```bash
cd skills/create-loop
bash tests/baseline_green.sh                                      # exit 0
python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt   # 0 dangling
python3 scripts/prove_reconstruction.py <all 3 examples>          # 0 regressions
python3 -m py_compile scripts/*.py scripts/checks/*.py
# every fixture R1-R48: previously-rejecting still rejects; R42-R48 GREEN
cd ../.. && node bin/create-loop.js render && git status --porcelain   # empty
node test/installer.test.js                                       # 15 passed
```

---

## TEST-FIRST STRATEGY (RED → GREEN evidence per change)

This repo's "tests" are three distinct harnesses. Use the right one:
1. **`tests/failure_mode_tests.md`** — negative fixtures (must REJECT). **Only R1–R18 are in a runnable script; R19–R41 are prose-only.** Every new rule R42+ **must ship runnable** (heredoc + command + expected), not prose.
2. **`tests/acceptance_tests.md`** — the green gate (must ACCEPT).
3. **`test/installer.test.js`** — render determinism, 15 assertions.

**Rule numbering:** R1–R41 are contiguous; **next free is R42**. R-numbers are TOMBSTONES — never renumber.

| Wave | New guard, written BEFORE the change | RED observation (exact) | GREEN after |
|---|---|---|---|
| 0 | `check_pointers.py` | Delete a reference file in a temp copy → checker exits nonzero naming the severed link | T7.1/T7.2 keep it at 0 dangling |
| 0 | **R42** INCOMPLETE-STATE | **Proved during planning:** plan-only dir → `INTEGRITY OK`, exit 0 | T1.1 → nonzero `[R42 INCOMPLETE-STATE]` |
| 0 | **R43** SELF-ATTESTED-COMPLETION | `assurance` absent from all scripts ⇒ entry validates, exit 0 | T2.2 → rejects |
| 0 | **R44** MISSING-ASSURANCE | No `assurance` field required ⇒ exit 0 | T2.2 → rejects |
| 0 | **R45** GOAL-CONTRACT-UNREAD | No evidence→criterion link exists ⇒ exit 0 | T2.1 → rejects |
| 2 | **R46** SCORE-BELOW-THRESHOLD | `score: 0.0` + `verdict: pass` + `threshold: 0.7` validates clean today | T2.3 → rejects |
| 3 | **R47** BLIND-ORDER-VIOLATION | No mtime/ordering rule exists ⇒ exit 0 | T3.3 → rejects |
| 3 | **R48** MISSING-DISSENT | No dissent event required ⇒ exit 0 | T3.4 → rejects |
| 4 | write-count assertion | Current sequence mandates ~78 writes across 7 files | T4.1 → count reduced, stated, no fact twice |
| 5 | reconstruction table | Non-reconstructible field set unknown | T5.1 → 100% classified |
| 6 | reconstruction regression | — | T6.1 → 0 regressions vs T5.1 |
| 7 | pointer gate + fixture sweep | — | T7.x → 0 dangling, all fixtures behave |

**Regression invariant at every gate:** every fixture that rejected before must still reject. A fixture that *stops* rejecting is a silent capability loss — the single most dangerous outcome of a vocabulary change.

---

## COMMIT STRATEGY (atomic)

**Rules:**
1. **One logical change per commit.** Never batch two convergences.
2. **Vocabulary changes are ONE commit across ALL FOUR layers** — `references/` + `schemas/` + `scripts/checks/__init__.py` + `SKILL.md` + its fixture. A partial sweep leaves the repo self-contradictory: the reference says one thing and the validator enforces another.
3. **`command/` edits commit WITH both rendered dirs.** `command/` + `.opencode/command/` + `.claude/commands/` in the same commit, after `render` + `installer.test.js`.
4. **Test-first = two commits.** `test: add R4x fixture (RED)` then `feat: ... (R4x GREEN)`. The RED commit is the evidence the guard preceded the change.
5. **One commit per deleted field** (T7.1). Never batch deletions — batching destroys per-field rollback.
6. **Deletion + link repair are ONE commit** (T7.2). A commit that deletes a file without repairing its 54 inbound links leaves the tree broken at that SHA.
7. **Every commit is green.** Never commit through a red gate.
8. Do not `--amend` pushed work; do not force-push; do not commit until the user asks.

**Sequence:**
```
W0: test: pointer checker + baseline oracle
    test: R42 RED (integrity accepts unresumable loop)
    test: R43,R44 RED (assurance absent)
    test: R45 RED (goal contract unread)
    feat: reconstruction-proof harness
W1: fix: integrity loads event log, state files mandatory (R42 GREEN)
    fix: R28 depth contradiction
    fix: single normative R36 statement
    fix: example README matches R34
W2: feat: goal-contract readers at 4 points (R45 GREEN)   [4-layer sweep]
    feat: assurance axis (R43,R44 GREEN)                  [4-layer sweep]
    test: R46 RED  →  fix: score-vs-threshold (R46 GREEN)
W3: feat: external-knowledge procedure
    feat: executable-design procedure
    test: R47 RED  →  feat: blind verification (R47 GREEN)
    test: R48 RED  →  feat: dissent protocol (R48 GREEN)
W4: refactor: ORIENT/WORK/COMMIT + render      [command/ + BOTH rendered dirs]
    refactor: de-persona, preserve question sets
    feat: attention invoice
W5: docs: reconstruction proof results
    docs: ADR — D1 decision                    [USER-APPROVED]
W6: refactor: collapse projections             [Branch A only]
    feat: design tournament
W7: chore: delete owner_agent                  [one commit]
    chore: delete retirement.retired_at        [one commit]
    chore: delete audited schema_version       [one commit]
    chore: remove 2 transcripts + repair 54 citations   [ONE commit]
```

---

## RISK REGISTER

| # | Risk | Why likely | Early-detection check, in the wave it happens |
|---|---|---|---|
| **R-1** | **Vocabulary change breaks a pinned fixture silently** — `assurance` (T2.2) or the goal-citation (T2.1) alters the evidence entry shape; a fixture that used to reject now passes. Capability lost with a green-looking gate. | 41 fixtures pin field tuples across 2,617 lines; only R1–R18 run as a script, so R19–R41 regressions are invisible without deliberate checking | **G2**: assert every previously-rejecting fixture STILL rejects — explicitly including prose-only R19–R41, run by hand. Specifically confirm **R7 still rejects** (proves `assurance` is orthogonal, not an enum extension). |
| **R-2** | **Deletion severs inbound Markdown links** — T7.2 touches 54 links across 8 files; 7 sit inside the locked gate-kind table | No existing gate checks pointer integrity; the previous plan under-counted this by ~5× (assumed ~10, actual 54) | **G0** builds `check_pointers.py`; **G7** requires 0 dangling. Additionally diff the gate-kind enum byte-for-byte — citation cells may be edited, enum values may not. |
| **R-3** | **A "ceremonial" field turns out load-bearing** — already happened: `recorded`, `cache_key`, `jitter`, `created_at`, `created_by`, `heartbeat_at` all have live readers despite being on the ceremonial list | The failure mode ("no validator reads it" ⇒ deletable) has recurred 3× this session and I found 3 more instances | **G7**: per-field 4-reader re-verification *at deletion time*, not at plan time; one commit per field so `git revert` is surgical. The deferred set is named explicitly so it is not quietly re-added. |
| **R-4** | **`command/` drift** — T4.1 edits `SKILL.md` §10 and `command/loop-run.md:27-33` describes the same sequence; editing one without the other, or forgetting `render`, ships contradictory instructions | Two files describe one sequence; the rendered dirs are a third and fourth copy | **G4**: `node bin/create-loop.js render && git status --porcelain` must be **empty** (proves determinism and that rendered dirs were committed), plus `installer.test.js` 15 passed. Diff `SKILL.md` §10 against `command/loop-run.md` by hand. |
| **R-5** | **Collapsing a projection loses unreconstructible data** — T6.1 removes a field the event log cannot rebuild; discovered only at a future crash-resume, long after the commit | The event log was never actually loaded by the integrity checker (proved), so confidence in its completeness is untested | **G5** gates T6.1 behind T5.1's measured table; **G6** re-runs the harness demanding 0 regressions. If T5.1 shows a large non-reconstructible set, **D1 goes to Branch B and T6.1 is cancelled** rather than forced. |

---

## WHAT THIS PLAN DELIBERATELY DOES NOT DO

- **Does not reduce line count as a goal.** The 500-line ceiling is retired; `SKILL.md` stays under its real 1000-line limit but shrinking is not an objective. Several tasks *add* lines (T3.1, T3.2) because the measured gaps are missing procedure, not excess prose.
- **Does not delete `execution_intelligence_policy.md`.** A prior metric (validators-per-line) flagged it low-yield; that was a category error. It holds the skill's two strongest behavioral instructions (§3.2 root-cause classification, §3.5 counterexample review). It is a PRESERVE asset and gets *extended* in Wave 3.
- **Does not delete `research-sources.md`.** Verified to be a clean cited report, not a transcript. Only the 2 actual transcripts (1,509 lines) go.
- **Does not delete the 6 deferred fields** (`recorded`, `cache_key`, `jitter`, `created_at`, `created_by`, `heartbeat_at`). Each has a verified validator or instruction reader. Named explicitly so their survival is a decision, not an oversight.
- **Does not delete self-graded gates.** It reclassifies them via `assurance`. All 8 gate kinds survive; 4 simply lose the authority to close a node.
- **Does not renumber any R-rule.** R30 gets a tombstone if removed.
- **Does not stop persisting topology.** LangGraph does not persist topology because *code* holds it; here `loop.plan` IS the executable program. Cargo-culting that would delete the program.
- **Does not build an eval set.** Mechanism *effectiveness* remains unmeasured — no amount of file-reading closes that gap. It needs live loop runs compared against outcomes. Named so it is not mistaken for delivered.
- **Does not execute the new state shape (Branch B).** If D1 goes Branch B, this plan delivers Waves 0–5 + T6.2 and hands off; the 6-file shape needs its own reconstruction proof, migration path for in-flight loops, and fixture set.
- **Does not touch `.agents/knowledge/`** from the skill — the transient/durable boundary is strict. Plan-level ADRs and the T5.1 result are written by *this* work, not by the skill at runtime.
- **Does not convert R19–R41 to runnable fixtures.** A real weakness (23 rules guarded only by prose), but orthogonal to this redesign. New rules R42–R48 ship runnable; retrofitting the older 23 is separate work.

---

## TODO List (ADD THESE)

> CALLER: Add these TODOs using TodoWrite and execute by wave. Every wave must end GREEN before the next begins. **Plan mode is active — nothing below executes until the user approves.**

### Wave 1 (Start Immediately — No Dependencies)

- [ ] **0.1 `scripts/check_pointers.py`: build Markdown pointer-integrity checker to unblock all deletions — expect exit 0 on clean tree, nonzero naming a severed link when a reference file is removed**
  - What: Walk all `.md` under skill root, extract relative links + `#anchors`, resolve on disk, exit nonzero on dangling. Support `--baseline` for the 2 known orphans.
  - Depends: None · Blocks: 4.2, 7.1, 7.2
  - Category: `deep` · Skills: [`programming`]
  - QA: `python3 scripts/check_pointers.py --baseline tests/pointer_baseline.txt` → exit 0 `0 dangling`; on a temp copy with one reference removed → nonzero naming the link

- [ ] **0.2 `tests/baseline_green.sh`: capture the verified green gate as a revert oracle — expect one command reproducing 11 schemas + 11 templates + 4 examples + 2 INTEGRITY OK + render 3 + installer 15/15**
  - What: Script the already-verified baseline; record `git rev-parse HEAD` as the revert anchor.
  - Depends: None · Blocks: all repair/structural tasks
  - Category: `quick` · Skills: []
  - QA: `bash tests/baseline_green.sh` → exit 0; idempotent on re-run

- [ ] **0.3 `tests/failure_mode_tests.md`: add runnable fixture R42 INCOMPLETE-STATE to guard resume safety — expect RED now (plan-only dir returns INTEGRITY OK exit 0)**
  - What: Loop dir with only `loop.plan.yaml`. Runnable heredoc + command + expected nonzero `[R42 INCOMPLETE-STATE]`. Capture actual RED output.
  - Depends: None · Blocks: 1.1
  - Category: `deep` · Skills: [`tdd`]
  - QA: run the command → exit 0 + `INTEGRITY OK` = documented RED

- [ ] **0.4 `tests/failure_mode_tests.md`: add runnable fixtures R43/R44 for the assurance axis — expect RED now (`assurance` appears in no script)**
  - What: R43 = `self_attested` verdict backing `completed` must reject. R44 = missing `assurance` must reject.
  - Depends: None · Blocks: 2.2
  - Category: `deep` · Skills: [`tdd`]
  - QA: both commands exit 0 today = documented RED

- [ ] **0.5 `tests/failure_mode_tests.md`: add runnable fixture R45 GOAL-CONTRACT-UNREAD — expect RED now (no evidence→criterion link exists)**
  - What: A node reaching `completed` whose evidence cites no `success_criteria` id must reject. Design the citation mechanism to be checkable without over-constraining.
  - Depends: None · Blocks: 2.1
  - Category: `ultrabrain` · Skills: [`tdd`]
  - QA: command exits 0 today = documented RED

- [ ] **0.6 `scripts/prove_reconstruction.py`: build the reconstruction harness that resolves fork D1 — expect a per-field RECONSTRUCTIBLE/NOT/NO-SOURCE table for all 4 state artifacts**
  - What: Replay `state/event_log.jsonl`; attempt to rebuild every field of checkpoint / loop.state / node.contract / artifacts INDEX. Exit 0 always (instrument, not gate). Stable field order for diffing.
  - Depends: None · Blocks: 5.1, 5.2, 6.1
  - Category: `ultrabrain` · Skills: [`programming`]
  - QA: runs on all 3 examples; 100% field coverage; machine-diffable output

**GATE G0:** `bash tests/baseline_green.sh` · `check_pointers.py` exit 0 · `prove_reconstruction.py` exit 0 · `py_compile` clean · `installer.test.js` 15 passed · **R42–R45 documented RED**

### Wave 2 (After Wave 1 — REPAIR, all parallel)

- [ ] **1.1 `scripts/check_loop_integrity.py`: load the event log and require checkpoint+ledger+event_log to fix false INTEGRITY OK — expect R42 RED→GREEN with both examples still OK**
  - What: Replace optional `.exists()` guards (~50-74, 104, 125, 132); parse the event log (never opened today); emit `[R42 INCOMPLETE-STATE]`. Keep INDEX optional for childless loops.
  - Depends: 0.2, 0.3 · Blocks: 2.1, 2.2
  - Category: `deep` · Skills: [`programming`, `tdd`]
  - QA: probe dir → nonzero `[R42 INCOMPLETE-STATE]`; both examples → `INTEGRITY OK`; corrupt JSONL → nonzero

- [ ] **1.2 `references/recursive_loops.md:52`: replace "arbitrary depth" with a max_depth-bounded statement to fix the R28 contradiction — expect zero grep hits and R28 still rejecting**
  - Depends: 0.2 · Blocks: none
  - Category: `quick` · Skills: []
  - QA: `grep -rn "arbitrary depth" references/` → none; R28 fixture still rejects

- [ ] **1.3 `references/evidence_gates.md`: make :33-47 the single normative R36 statement and point :262-265 at it — expect one statement preserving the union of both constraints**
  - What: The second copy adds `step_verifier` + threshold; do not drop that clause.
  - Depends: 0.2 · Blocks: none
  - Category: `quick` · Skills: []
  - QA: exactly one normative statement; R36 fixture still rejects

- [ ] **1.4 `examples/example_research_project/README.md:78-83`: reconcile the "gate-exempt" claim with R34 — expect README and plan to agree, or a report that the plan is the real defect**
  - What: Read the plan first. If the plan also has `gate: null`, R34 is passing something it should reject — report rather than paper over.
  - Depends: 0.2 · Blocks: none
  - Category: `deep` · Skills: []
  - QA: `validate_loop_plan.py` on that example → exit 0; README matches plan; R34 still rejects

**GATE G1:** baseline green · **R42 GREEN** · 0 dangling · no "arbitrary depth" · R28/R34/R36 still reject · installer 15 passed

### Wave 3 (After Wave 2 — ADDITIVE core)

- [ ] **2.1 4-layer sweep: add goal-contract readers at dispatch/mutation/verification/termination to fix the missing-reader defect — expect R45 RED→GREEN with 11/11 templates and 4/4 examples still valid**
  - What: `references/state_model.md` + `evidence_gates.md` → `schemas/evidence.ledger.schema.json` → `checks/__init__.py` + `validate_loop_plan.py` → `SKILL.md` §10 → `templates/evidence.ledger.yaml`. Evidence cites the `success_criteria` id it bears on. ONE commit.
  - Depends: 0.5, 1.1 · Blocks: 3.1, 3.2, 4.1
  - Category: `ultrabrain` · Skills: [`programming`, `tdd`, `domain-modeling`]
  - QA: R45 GREEN; 11/11 templates; 4/4 examples; all 4 read points present in §10

- [ ] **2.2 4-layer sweep: add the `assurance` axis orthogonal to the 8 gate kinds so self-graded verdicts cannot close nodes — expect R43+R44 GREEN and R7 STILL REJECTING**
  - What: `assurance: external|blind|self_attested` on every evidence entry. Only `external`+`human_approval` authorize `completed`; `self_attested` → `provisional`. Do NOT extend the gate enum. State how `provisional` maps onto the 15 locked statuses. ONE commit.
  - Depends: 0.4, 1.1 · Blocks: 2.3, 3.3, 4.1
  - Category: `ultrabrain` · Skills: [`programming`, `tdd`, `domain-modeling`]
  - QA: R43+R44 GREEN; **R7 still rejects**; 8 gate kinds unchanged; 11/11 templates; 4/4 examples

- [ ] **2.3 `validate_loop_plan.py` + `checks/gates.py`: enforce score>=threshold and ledger↔node gate_kind match to make `score` load-bearing — expect R46 RED→GREEN**
  - What: Write R46 first (`score: 0.0` + `verdict: pass` + `threshold: 0.7` validates clean today). Then bind scored gates; cross-check ledger `gate_kind` against the node's configured gate (never done today).
  - Depends: 2.2 · Blocks: none
  - Category: `deep` · Skills: [`programming`, `tdd`]
  - QA: R46 RED then GREEN; 4/4 examples validate

**GATE G2:** baseline green · R42–R46 GREEN · **R7 still rejects** · every R1–R41 fixture still rejects · 0 dangling · installer 15 passed

### Wave 4 (After Wave 3 — ADDITIVE procedures)

- [ ] **3.1 `references/execution_intelligence_policy.md` + `templates/interview_brief.md`: write the external-knowledge acquisition procedure to close the RANK-1 NAMED-ONLY gap — expect ≥1 concrete verification action producing an `external`-assurance artifact**
  - What: When external knowledge is required; primary vs recalled source; verify an API/library claim by executing against it; how the finding enters evidence as `external`. Do not disturb existing §3.2/§3.5.
  - Depends: 2.1 · Blocks: none
  - Category: `writing` · Skills: [`research`, `context7`]
  - QA: procedure names concrete executable actions; reference map registers any new doc; 0 dangling; green gate

- [ ] **3.2 `references/execution_intelligence_policy.md` + new `templates/design_brief.md`: write the executable-design procedure to close the RANK-2 NAMED-ONLY gap — expect a design artifact requiring interfaces, data flow, and falsifiable assumptions**
  - What: Deep-module interfaces at clean seams, data flow, assumptions + how each is verified; cite `success_criteria`. Register in `SKILL.md` §16.
  - Depends: 2.1 · Blocks: none
  - Category: `writing` · Skills: [`codebase-design`, `domain-modeling`]
  - QA: artifact demands interfaces+data flow+assumptions; registered; 0 dangling; green gate

- [ ] **3.3 `references/evidence_gates.md` + `checks/provenance.py`: implement blind verification with verdict-first mtime ordering to make agreement evidence not echo — expect R47 RED→GREEN with R36 still rejecting**
  - What: `assurance: blind` — verifier gets artifact+criteria only, never the producer's verdict/rationale. Reviewer writes verdict BEFORE reading the claim; mtime makes it checkable. R47 rejects violations. PRESERVE `branching_parallelism.md:142-149` verbatim.
  - Depends: 2.2 · Blocks: 3.4, 6.2
  - Category: `ultrabrain` · Skills: [`programming`, `tdd`]
  - QA: R47 GREEN; R36 still rejects; isolation rule intact; no false positives on 4 examples

- [ ] **3.4 `references/evidence_gates.md` + `schemas/event_log.schema.json`: add the dissent protocol so overriding a blind reviewer is recorded — expect R48 RED→GREEN with R23/R24/R31/R39 still rejecting**
  - Depends: 3.3 · Blocks: none
  - Category: `deep` · Skills: [`programming`, `tdd`]
  - QA: R48 GREEN; event-log fixtures still reject; follows the typed-event convention

**GATE G3:** baseline green · R47/R48 GREEN · R42–R46 GREEN · R1–R41 still reject · 0 dangling · isolation rule intact · installer 15 passed

### Wave 5 (After Wave 4 — STRUCTURAL attention budget)

- [ ] **4.1 `SKILL.md` §10 (503-515) + `command/loop-run.md:27-33`: restructure per-node flow into ORIENT/WORK/COMMIT to cut the 9:1 write-to-read ratio — expect mandated writes well under 78 with no fact written twice**
  - What: ORIENT = read-only (goal contract + frontier). WORK = engineering. COMMIT = ≤3 appends, snapshot REGENERATED. Preserve the `pre_effect`/`post_effect` + idempotency bracket. Do NOT collapse projections here (that is 6.1, gated on D1).
  - Depends: 2.1, 2.2 · Blocks: 4.3, 4.4, 5.1
  - Category: `ultrabrain` · Skills: [`programming`, `codebase-design`]
  - QA: state the new write count; no duplicate writes; 4/4 examples; 2× INTEGRITY OK; `SKILL.md` ≤1000 lines

- [ ] **4.2 `recursive_planning_immersive_execution.md:93-94` + `interview_brief.md:60-76`: drop the role-label column and re-express its question column as phase checklists — expect zero persona labels with 1:1 question preservation**
  - What: The table's `role it plays` column is the label; `it focuses on` is the substance. Keep every question. KEEP `assignee: user`, `assignee: subagent`, the isolation rule, and R36.
  - Depends: 0.1 · Blocks: none
  - Category: `writing` · Skills: [`writing-great-skills`]
  - QA: `grep -rn "three things at once\|architect · project lead"` → none; enumerate old→new questions 1:1; all 8 perspective mechanisms intact; 0 dangling

- [ ] **4.3 `SKILL.md` §10 COMMIT + `templates/run.log.md`: add the attention invoice (LEARNED / SURPRISED / VERIFIED-vs-BELIEVED) to replace field ceremony with signal — expect ≤3 COMMIT appends preserved**
  - Depends: 4.1 · Blocks: none
  - Category: `deep` · Skills: [`writing-great-skills`]
  - QA: three fields present; still ≤3 appends; state what behavior changes vs default (not a no-op); green gate

- [ ] **4.4 repo root: run render + installer test because `command/loop-run.md` changed — expect 15/15 and a byte-identical re-render**
  - What: `node bin/create-loop.js render` then `node test/installer.test.js`; commit `command/` + `.opencode/command/` + `.claude/commands/` together.
  - Depends: 4.1 · Blocks: none
  - Category: `quick` · Skills: [`git-master`]
  - QA: `render && git status --porcelain` → empty; installer 15 passed

**GATE G4:** baseline green · render deterministic (`git status` empty) · installer 15 passed · 0 dangling · no persona labels · `SKILL.md` ≤1000 · R42–R48 GREEN · R1–R41 still reject

### Wave 6 (After Wave 5 — MEASURE + DECIDE)

- [ ] **5.1 `scripts/prove_reconstruction.py` on all 3 examples: produce the reconstruction table that resolves D1 — expect 100% field coverage with every non-reconstructible field named and reasoned**
  - What: Enumerate every `NOT-RECONSTRUCTIBLE` / `NO-EVENT-SOURCE` field across checkpoint / loop.state / node.contract / artifacts INDEX. Persist to `.agents/knowledge/reference/`.
  - Depends: 0.6, 4.1 · Blocks: 5.2
  - Category: `ultrabrain` · Skills: [`programming`]
  - QA: 100% coverage; non-reconstructible set explicitly listed; output diffable

- [ ] **5.2 ★ DECISION POINT D1 ★ — present the reconstruction table to the USER and record the chosen branch as an ADR — expect a user-approved decision, NOT an agent-selected one**
  - What: 0 non-reconstructible → **Branch A**, collapse safely. Small enumerable set → **Branch A with named exceptions** kept durable. Large/structural → **Branch B**, cancel 6.1 and scope a separate new-shape plan. `loop.state.yaml`'s fate is decided here.
  - Depends: 5.1 · Blocks: 6.1, 7.1
  - Category: **NONE — escalate to user.** Crosses a goal/scope boundary and is irreversible.
  - QA: written decision citing the T5.1 table; ADR under `docs/adr/`; user approval recorded

**GATE G5:** baseline still green (Wave 6 adds no production change) · T5.1 table complete · D1 ADR recorded and user-approved

### Wave 7 (After Wave 6 — branch-dependent)

- [ ] **6.1 [BRANCH A ONLY] `schemas/checkpoint.schema.json` + `state_model.md` + `checks/loop_state.py`: make the checkpoint a regenerated derived cache to remove ~38 projection writes — expect 0 reconstruction regressions vs 5.1**
  - What: Collapse ONLY fields 5.1 proved reconstructible. **Topology still persists** — `loop.plan` IS the program. If R30 is removed, leave a TOMBSTONE; never renumber.
  - Depends: 5.2 · Blocks: none
  - Category: `ultrabrain` · Skills: [`programming`, `tdd`, `codebase-design`]
  - QA: re-run harness → 0 regressions; 4/4 examples; 2× INTEGRITY OK; no renumbering; green gate

- [ ] **6.2 [BOTH BRANCHES] `references/branching_parallelism.md` + `loop_plan_spec.md`: turn `mapper`/`fanout` into the design-tournament primitive so N designs compete with blind selection — expect the fanout enum check and the 3–5 cap intact**
  - What: N competing designs in isolated contexts with planned casualties; winner chosen by blind review (3.3), not the author. Do not touch `checks/__init__.py:73`.
  - Depends: 3.3 · Blocks: none
  - Category: `artistry` · Skills: [`design-an-interface`, `codebase-design`]
  - QA: `fanout` still passes its enum check; cap + isolation preserved; green gate

**GATE G6:** baseline green · 0 reconstruction regressions · 0 dangling · installer 15 passed · all fixtures behave

### Wave 8 (After Wave 7 — SUBTRACTION last)

- [ ] **7.1 `schemas/`: delete only `owner_agent`, `retirement.retired_at`, and audited `schema_version` instances — expect 0 grep hits per field with ONE commit each**
  - What: These 3 pass all four reader tests (0 validator, 0 template, 0 closeout; only descriptive mentions). **DO NOT delete the deferred 6** — `recorded` (`validate_loop_plan.py:196`), `cache_key` (`checks/__init__.py:89`), `jitter` (`exception_handling.md §5.2` retry formula), `created_at`/`created_by` (`checks/__init__.py:99`), `heartbeat_at` (`checks/claim.py:12` + lease mechanism). Re-verify each field's 4 readers AT deletion time. For `schema_version`, audit per artifact — keep where a required-tuple reads it.
  - Depends: 0.1, 5.2 · Blocks: none
  - Category: `deep` · Skills: [`programming`, `git-master`]
  - QA: per field: `grep -rn "<field>"` → 0; 11/11 templates; 4/4 examples; 0 dangling; all fixtures behave; green gate after EACH commit

- [ ] **7.2 `references/`: remove the 2 transcripts (1,509 lines) and convert all 54 inbound citations to plain-text attribution — expect 0 dangling links and a byte-identical gate-kind enum**
  - What: Delete `research_dags_multiagent.md` + `research_durable_loops.md`. **PRESERVE `research-sources.md`** (clean cited report, and `SKILL.md:716` points to it). Repair 54 links across 8 files (`loop_plan_spec.md`×8 — 7 inside the locked gate-kind table, `exception_handling.md`×11, `concepts.md`×14, `recovery_protocol.md`×7, `human_approval.md`×5, `evidence_gates.md`×5, `branching_parallelism.md`×2, `state_model.md`×2). Edit citation cells ONLY; never enum values. ONE commit.
  - Depends: 0.1 · Blocks: none
  - Category: `deep` · Skills: [`writing-great-skills`, `git-master`]
  - QA: `check_pointers.py` → **0 dangling**; each of 54 claims still conveyed as text; gate-kind enum byte-identical; `SKILL.md:716` resolves; green gate

**GATE G7 (FINAL):** `bash tests/baseline_green.sh` · `check_pointers.py` 0 dangling · reconstruction 0 regressions · `py_compile` clean · all R1–R48 fixtures behave · `render && git status` empty · `installer.test.js` 15 passed

## Execution Instructions

1. **Wave 1** — fire all six IN PARALLEL (no dependencies):
   ```
   task(category="deep",       load_skills=["programming"],       run_in_background=false, prompt="Task 0.1: ...")
   task(category="quick",      load_skills=[],                    run_in_background=false, prompt="Task 0.2: ...")
   task(category="deep",       load_skills=["tdd"],               run_in_background=false, prompt="Task 0.3: ...")
   task(category="deep",       load_skills=["tdd"],               run_in_background=false, prompt="Task 0.4: ...")
   task(category="ultrabrain", load_skills=["tdd"],               run_in_background=false, prompt="Task 0.5: ...")
   task(category="ultrabrain", load_skills=["programming"],       run_in_background=false, prompt="Task 0.6: ...")
   ```
   Then verify **GATE G0**. Do not proceed until R42–R45 are documented RED.

2. **Wave 2** — all four REPAIR tasks in parallel; verify **G1** (R42 must be GREEN).

3. **Wave 3** — 2.1 and 2.2 in parallel (different primary files, but both sweep `checks/__init__.py` — if the executor cannot guarantee non-conflicting edits, run them serially). Then 2.3. Verify **G2**, especially that R7 still rejects.

4. **Wave 4** — 3.1, 3.2, 3.3 in parallel; then 3.4. Verify **G3**.

5. **Wave 5** — 4.1 and 4.2 in parallel (different files); then 4.3; then 4.4 (mandatory render). Verify **G4** including render determinism.

6. **Wave 6** — 5.1, then **STOP and escalate 5.2 to the user.** Do not self-select a branch.

7. **Wave 7** — 6.1 only if Branch A; 6.2 either way. Verify **G6**.

8. **Wave 8** — 7.1 (one commit per field) and 7.2. Verify **G7**.

9. **Final QA:** run GATE G7 in full. Every wave boundary must have been GREEN; every R42–R48 must have a captured RED→GREEN transition.

<task_metadata>
session_id: ses_05040d151ffepLgNKNeYhyf37N
task_id: ses_05040d151ffepLgNKNeYhyf37N
subagent: plan
</task_metadata>
---

# AMENDMENT A1 (2026-07-30) — deterministic/semantic division of labor

A constraint was added AFTER this plan was generated. It invalidates one task, re-scopes two,
and adds three. **Where this amendment conflicts with the plan above, this amendment wins.**

## The constraint

Programs verify **determinable low-level facts**. The model judges **what those facts mean and
what to do next**. A validator may prove ONLY the condition it actually inspected, and may never
extrapolate from that to a high-level goal.

Never dress an open/semantic question as a boolean, score, fixed label, or checklist item:

| Program can prove | It does NOT prove |
|---|---|
| tests pass | the design is correct |
| fields complete | the information is sufficient |
| status updated | real progress was made |
| checklist ticked | the risk is resolved |
| output matches format | the result is professional quality |

**State changes must not be auto-driven by surface fields.** Any status change that affects
resource allocation, direction, or completion must rest on a semantic review of actual results.

**Six-part test — a validator may decide state/completion only if ALL hold:**
1. the condition has a clear, stable, computable definition
2. the validator directly inspects the fact it claims to verify
3. passing yields a bounded conclusion, not an extrapolated one
4. the result triggers a clear, justified next action
5. false-pass / false-reject risk is acceptable
6. the program is genuinely more reliable, cheaper, or more consistent than model judgment

Fail any one ⇒ that validator may not determine state, certify completion, or dictate next steps.

## Violations verified in the current skill

- **V1 — R5 is presence-only.** `checks/nodes.py:28-29` is `if field not in node`. A node with
  all 21 required fields present but `title: ""` and `preconditions: []` **passes R5**
  (constructed and confirmed empirically). R5 proves *filled-in*; the surrounding docs read it as
  design completeness. This is precisely "fields complete ≠ information sufficient".
- **V2 — `score` is a semantic judgment wearing a number's clothes.** `llm_judge` is defined as
  "A separate LLM scores the node's output against a rubric" (`evidence_gates.md:126`). The
  number is model opinion; comparing it to a threshold does not convert it into a measurement.
- **V3 — `INTEGRITY OK` over-claims.** It verifies cross-file reference consistency. The name
  asserts whole-loop integrity. The naming is itself an over-extrapolation.

## Plan changes

### RETRACTED

- **T2.3 (enforce `score >= threshold`) — CANCELLED.** It would grant a fabricated model number
  deterministic authority over node completion: the exact anti-pattern. Judged gates are fixed by
  **provenance** (the C2 assurance axis), never by arithmetic on an opinion.
  Fixture **R46 is withdrawn**; do not author it.
  *What replaces it:* nothing. The absence of a threshold check is now CORRECT, and
  `evidence_gates.md` must state why, so a later reader does not "fix" it again.

### RE-SCOPED

- **T0.5 / T2.1 (goal-contract citation) — SPLIT the check.**
  - LEGITIMATE (program): a cited `success_criteria` id **resolves to an id that exists**.
    That is reference validity — determinable, directly inspected, bounded.
  - ILLEGITIMATE (program): treating a resolvable citation as evidence the criterion is
    *satisfied*. Satisfaction is semantic and belongs to the model.
  - R45 asserts reference validity ONLY. Its failure message must say
    `cited criterion id does not exist`, never `criterion not satisfied`.

- **T3.3 (verdict-first mtime) — KEEP, RE-LABEL.** mtime proves **ordering only**. It does not
  prove blindness or independence. Rule text and R47's message must claim ordering and nothing
  more.

### ADDED

- **T1.5 — Rename `INTEGRITY OK` to state what was actually checked** (e.g.
  `CROSS-FILE REFERENCES OK`), and have the summary enumerate which checks ran. **REPAIR**,
  Wave 1, parallel with T1.1–T1.4. Fixes V3. Verify: output no longer claims whole-loop
  integrity; examples still exit 0.

- **T2.4 — Reclassify R5 honestly.** R5 keeps checking presence (legitimate, and the 21-field
  contract depends on it) but its message and the docs must stop implying completeness. Add
  the boundary statement to `evidence_gates.md` / `loop_plan_spec.md`: *presence is not
  sufficiency; whether a field's content is adequate is a semantic judgment the runner must make
  and record.* **REPAIR**, Wave 2. Fixes V1.
  Explicitly does NOT add a non-empty check — a non-empty `preconditions` is not a *correct*
  `preconditions`, so that would repeat the same error one level up.

- **T2.5 — Write the division-of-labor boundary into the skill.** A short normative section:
  what validators may conclude, what only the runner may conclude, and the prohibition on
  surface-field-driven state changes. **ADDITIVE**, Wave 2, after T2.4.
  This is the amendment's most durable deliverable: without it, the next maintainer re-adds a
  threshold check and calls it rigor.

### SURVIVES UNCHANGED

- **C2 assurance axis** — it verifies **who produced a verdict** (determinable, directly
  inspected) and deliberately leaves **whether the verdict is right** to the model. That is the
  correct split, and it is why the fix for self-graded gates is labeling rather than scoring.
- All Wave-0 instrumentation, T1.1–T1.4, Wave 3 procedures, Wave 4 attention budget, Wave 5
  measurement + D1 decision point, Wave 6, Wave 7.

## Standing rule for every future validator in this repo

State, in the rule text, the exact fact inspected and the conclusion NOT licensed. A rule whose
name or message implies more than it inspected is a defect even when its logic is correct.
