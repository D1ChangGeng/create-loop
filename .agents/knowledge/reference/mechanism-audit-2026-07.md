---
type: reference
confidence: observed
scope: ["skills/create-loop/"]
sources: ["skills/create-loop/SKILL.md", "skills/create-loop/scripts/", "skills/create-loop/tests/"]
last_verified: 2026-07-31
created: 2026-07-30
---

# Mechanism Audit — `skills/create-loop/` — 2026-07-30

**Status:** historical baseline audit. Its 2026-07-30 inventory and defect claims are retained as
evidence but are not current-state authority after the 2026-07-31 implementation.
**Confidence:** `observed` — every claim carries a `file:line` or captured-output citation; no claim is corroborated by a second independent audit pass except where noted as CORROBORATED.
**Method:** 16 sub-agents. 13 read-only auditors partitioned the tree so every file was claimed by exactly one auditor; 2 hostile critics argued *against* the proposed cuts; 1 Oracle ruled on resume-contract boundaries.
**Purpose:** evidence base for a systemic subtraction refactor. Governing principle: *complexity is not capability; a mechanism must prove its value to earn existence.*

---

## 0. Coverage ledger (completeness gate — CLOSED)

| Slice | Files claimed | Lines |
|---|---|---|
| behavioral policy overlap | `execution_intelligence_policy`, `recursive_planning_immersive_execution`, `layered_execution_chain`, `live_loop_semantics` | 1,521 |
| validator rules R1–R41 | `scripts/*.py`, `scripts/checks/*` | 16 modules |
| state artifacts | `templates/*` (19), `schemas/*` (11) | — |
| vocabulary / enums / tiers | `loop_plan_spec` + all enum surfaces | 407 |
| human / failure axis | `human_approval`, `exception_handling`, `recovery_protocol` | 1,666 |
| tests + examples | `tests/*` (2,954), all 4 worked example dirs | — |
| entrypoint + commands | `SKILL.md`, `command_system`, `command/*` | 904 |
| gates + parallelism | `evidence_gates`, `branching_parallelism`, `parallel_development_protocol` | 1,106 |
| recursion | `recursive_loops` (980), `subgraph_subloop_policy` (714) | 1,694 |
| shipped research notes | `research_dags_multiagent` (869), `research_durable_loops` (640), `research-sources` (317) | 1,826 |
| self-evolution coupling | `self_evolution_integration` | 690 |
| core contract + pointer graph | `concepts`, `state_model`, SKILL→refs pointer map | 693 |
| external grounding | (no repo files) | — |

**Closure:** all 20 `references/` (9,704 lines), 19 templates, 11 schemas, 16 validator modules, 2 test docs, 4 worked examples, 4 slash commands claimed. Zero orphans.

**Wave-1 gap that nearly invalidated the audit:** the first 9 agents left ~4,500 lines unclaimed, including the three largest reference files. Wave 2 corrected two verdicts that wave-1 evidence alone would have gotten wrong (see §4 C3, C4). **Partial coverage produces confident wrong verdicts — the gate is not ceremony.**

---

## 1. The single structural finding

The skill contains **two populations requiring opposite verdicts**. Conflating them is the root design error.

**(A) Mechanically load-bearing.** DAG + `requires` edges, `event_log`, evidence-ledger verdicts, `loop.meta.yaml` identity, resume algorithm, and the structural validators. A fresh zero-memory agent's resume depends on these *mechanically*: delete one and resume provably breaks. This is what the skill is **for**.

**(B) Genuinely inert.** *** CORRECTED: 1,509 lines, not 1,826 — `research-sources.md` (317) is a clean cited report and is PRESERVED. And they are NOT inert-by-reachability: 54 inbound reference links exist. See redesign-evidence-round1 §CORRECTIONS E2/E3. ***

The audit's original framing — "machine-enforced = keep, prose = delete" — was **rejected by Oracle**: this repo ships no runtime, so a compact portion of its prose *is* executable procedure for the next agent. The correct axis is *does removal cause an observable loss*, not *is it enforced by Python*.

---

## 2. Quantified findings

### 2.1 Scale vs. published ceiling
- `SKILL.md` = 803 lines. Whole skill = 23,142 lines. `references/` = 9,704 lines across 20 files.
- Anthropic's open Agent Skills spec (agentskills.io/specification, Dec 2025) states: keep `SKILL.md` **under 500 lines**, move detail to references. Entrypoint is 60% over.
- 4 slash commands = 130 lines total, adding **no operational semantics** beyond SKILL.md modes.

### 2.2 Policy-prose yield
2,944 lines across the human/failure axis produce **4 enforceable rules**, 3 of which are enum guards:

| File | LOC | New schema fields | Validator rules |
|---|---|---|---|
| `human_approval.md` | 630 | 0 | 1 (R34) |
| `exception_handling.md` | 578 | 0 | 2 (both enum) |
| `recovery_protocol.md` | 458 | 0 | 1 (R6) |
| `self_evolution_integration.md` | 690 | 0 | **0** |
| `parallel_development_protocol.md` | 348 | 0 | **0** |
| `templates/task_profile.yaml` | 240 | **no schema exists** | **not a dispatchable kind** |

`task_profile` — the Layer-0 charter — is not among the 10 kinds `validate_loop_plan.py:258-294` dispatches. Only ~5 of its fields feed `loop.plan`.

### 2.3 Validator classification (R1–R41)
- **STRUCTURAL-REAL** (prevent unrecoverable corruption): R1 cycle detect (`checks/graph.py:31`), R2 dangling requires (`graph.py:23`), R3 non-trivial node must carry gate (`gates.py:37`), R6 checkpoint↔plan match (`validate_checkpoint.py:144`), R19 deprecated-only-requires deadlock (`validate_checkpoint.py:178`).
- **SELF-IMPOSED**: R5 (21 required node fields, `checks/__init__.py:81-86`), R11 (12 `loop.meta` fields), R13, R16, R17. Auditor verdict: *"only ~3–5 fields per tuple are actually consumed."* No operational reader found for `assignee`, `notes`, `cache_key`, `priority`, `parallelizable`, `compensation_of`, `promotion_policy`.
- **Enum guards**: R4, R7, R8, R9, R10, R12, R14, R15, R18, R20 — *originally classed cosmetic; see §4 C1, overturned.*

### 2.4 State artifacts are self-declared projections
The skill **documents its own redundancy**. `recovery_protocol.md:332-346` §6.0 "State Authority Order" ranks: `event_log` = primary truth, *"every other state file is a projection of it"*; `checkpoint` = snapshot trusted only when it agrees; `loop.state` = *"a convenience cache, always rederivable."* Corroborated at `state_model.md:289-291`.
- `loop.state.yaml`: **0 unique fields** of 10 — all copied or derivable; `lease_index` mirrors `contracts/*.claim`.
- `checkpoint.yaml`: 18 fields, only 2 unique (`checkpoint_id`, `checkpoint_seq`), both bookkeeping.
- `SKILL.md:549` itself: stored `ready_set` is *"advisory"*, recomputed from `requires` + `node_states`.

### 2.5 Gate assurance
- Real & cheap: `artifact_exists`, `automated_check`, `test`. Real & expensive: `human_approval`.
- **`llm_judge`**: nothing prevents `verdict: pass` for nothing. The rule at `evidence_gates.md:46` ("verifier MUST NOT be the producing agent" for `risk: high`) is enforced **only** for the narrow risky-node case at `checks/provenance.py:71` (R36).
- **`step_verifier`**: cites PRM literature; no PRM exists — no verifier model, no loading code. The agent scores its own steps.
- Partial: `self_consistency` (K samples, same model, no cross-model independence), `evaluator_optimizer` (trajectory on disk ⇒ least-bad).
- **Gate selection is not deterministic**: multiple kinds defensibly fit any node; the ranking at `evidence_gates.md:240-260` is prose, not a function.

### 2.6 Vocabulary vs. demonstrated need
Node kinds: 8 defined. Instantiation across the 4 **worked examples** (`templates/loop.plan.yaml` excluded — it is a template, not an example, per `tests/acceptance_tests.md:127`):

`milestone` 29 · `gate` 10 · `approval` 2 · `compensation` 1 · `branch` 1 · `join` 1 · **`mapper` 0 · `fanout` 0** (44 nodes)

Including `templates/loop.plan.yaml` (4 nodes: 3 `milestone` + 1 `approval`): `milestone` 32, `approval` 3, 48 nodes total. Counts re-verified against source 2026-07-30; an earlier draft of this file said 27/3 for the worked examples, which double-counted the template. By the two-adapter test, `branch`/`join`/`compensation` are single-instance (hypothetical) seams; `mapper`/`fanout` are uninstantiated.

### 2.7 Shipped research notes actively contradict the design
- `research_dags_multiagent.md` lines 1–282 are task-runner metadata (`Task ID:`, `Duration:`) and the producing agent's *"let me search for…"* monologue — ~32% of the file. `research_durable_loops.md` lines 1–140 likewise.
- Proposes **16 node kinds** (`:560`) against the locked 8; proposes `runs/<run_id>/<orchestrator>/<i>/` (`:426`) against the actual `.agents/loops/`.
- **No vocabulary is defined only here** — the research files *use* locked terms, never define them.
- 2 of the 3 are unreachable from `SKILL.md`'s pointer table *** but carry 54 inbound links from 8 reference files — deletion requires citation repair in the same commit (E2). ***

This is worse than dead weight: an agent that reads them and then checks the templates receives conflicting instructions.

### 2.8 Pointer graph explains why prose is inert
Per `writing-great-skills`, a context pointer's *wording* — not its target — decides whether material is ever loaded. Large references sit behind vague pointers ("Full spec: X", "see X"), e.g. `live_loop_semantics` (406 lines, only `SKILL.md:203` "Full spec:"), `execution_intelligence_policy` (416 lines, `:219`/`:272` vague). Meanwhile `recursive_loops` (980 lines) is reached by an **unconditional** "Read X" at `:58`. Large files pay full maintenance cost at near-zero read probability.

### 2.9 What the green gate actually proves
All 10 baseline validator commands exit 0 (captured). But `tests/acceptance_tests.md` §green-sequence **never exercises against a real on-disk example**: the `claim` mechanism, `event_log` replay, `loop.state.yaml`, `artifacts/INDEX.yaml`, `node.runtime.yaml`, `human_intervention_policy` semantics, `plan_history` hash verification, all 4 behavioral policies, the recovery protocol, the parallel-development protocol, self-evolution integration, subgraph→subloop admission logic, the child-loop isolation rule, escalation-ladder *behavior*, and all 15 node-status *transitions*. These are template-parsed only.

`failure_mode_tests.md` (2,617 lines): 41 named failure modes, **40 fully paste-runnable, 0 prose-only**. R19 ships its checkpoint fixture but describes its companion plan in prose only (`:1943-1983`) — as written the command fails. R1–R18 have an aggregate runner (`:1184-1936`); R19–R41 have none.

Examples are **mostly load-bearing**, not ceremony: empty-field tax is 10.1% / 8.7% / 10.1% / 11.0% across the four plans. `child_loops: []` = 18 lines/plan, `subgraph: null` = 17 lines/plan. Relaxing the 21-field rule would shrink each big plan ~4%, not materially.

### 2.10 External grounding (decisive frame)
- **[OFFICIAL]** agentskills.io spec (Dec 2025): `SKILL.md` < 500 lines.
- **[OFFICIAL]** docs.claude.com best-practices: *"The context window is a public good… Does this paragraph justify its token cost?"*
- **[OFFICIAL]** Anthropic: *"Create evaluations BEFORE writing extensive documentation. This ensures your Skill solves real problems rather than documenting imagined ones."* → a 23k-line skill with 41 rules and no eval set is **structurally inverted**.
- **[OFFICIAL]** *Building Effective Agents* (Dec 2024): simple composable patterns over frameworks.
- **[PEER]** *Lost in the Middle* (TACL 2023): mid-context rules land in the attention valley.
- **[PEER]** *Multi-IF* (Meta, Nov 2024): adherence degrades per turn — o1-preview 0.877@turn1 → 0.707@turn3; defines an **Instruction Forgetting Ratio** for rules agents previously followed.
- **[GRAY]** Inferal (Jan 2026): ~3-constraint ceiling before adherence collapses.

**Implication:** a skill whose entire purpose is multi-session execution operates precisely where per-turn instruction forgetting is worst. **Mechanism count is inversely related to mechanism adherence.** The subtraction thesis has an empirical basis, not merely an aesthetic one.

---

## 3. Incidental defects (repair regardless of subtraction)

| # | Defect | Evidence |
|---|---|---|
| D-a | `recursive_loops.md:52` says recursion is "to arbitrary depth"; `loop_plan_spec.md:70` enforces `termination.max_depth` (R28, `checks/caps.py`); all examples set 3 | live contradiction in locked vocabulary |
| D-b | `check_loop_integrity.py` never loads the event log; treats checkpoint and ledger as **optional** (`:62`) | **exit 0 does not prove safe blank-session resume** |
| D-c | `acceptance_tests.md:33` says "7 schemas"; runnable block at `:262` lists 11 | doc/code drift; code is the contract |
| D-d | `acceptance_tests.md:295` and `:300` run identical `--kind node_runtime` check | no-op duplicate |
| D-e | No gate checks Markdown pointer integrity anywhere in the repo | deleting any reference silently severs inbound links |

---

## 4. Adversarial corrections — 4 of 8 proposed cuts overturned

The hostile round is the most load-bearing part of this audit. An audit that confirms all its own hypotheses is a rubber stamp.

**C1 — Enum guards are NOT cosmetic. (OVERTURNED)**
`status`, `gate.kind`, `on_failure` are strings that **select state-machine and escalation behavior**. `status: done` is not a typo — it is a node that neither executes nor terminates. Must stay: R4 (`nodes.py:36`), R7 (`gates.py:9`), R8 (`nodes.py:57`), R9/R12 (`meta.py:30`/`:45`), R14/R15 (`runtime.py:50`/`:64`), R18 (`validate_loop_plan.py:87`) — each pinned by a negative fixture. Validators are the **only executable enforcement layer this package ships**.
*Safe residue:* R20 folds into the generic enum check (losing only error-message quality); R10 may move to JSON Schema **only after** that schema gains `pattern`/`maxLength` (`loop.meta.schema.json:26` currently lacks both).
*Qualification:* R15's two enums are **scope-disjoint, not string-disjoint** — they share `running`/`blocked`/`completed`/`cancelled`.

**C2 — Deleting `loop.state.yaml` is INDEFENSIBLE as specified. (OVERTURNED)**
"0 unique fields" is true of its 10 schema fields but it is the declared **home** for `human_decisions[]` and `active_constraints` (`templates/human_decision_request.md:18,:273,:291,:320`) and for Option-A `runtime_subgraphs` (`subgraph_subloop_policy.md:203-224`). **None exist in `checkpoint.schema.json`.** Deletion without naming new homes strands three live contracts. Deletable only *with* migration, and only together with its schema, template, R30, and command readers.

**C3 — `fanout` is load-bearing. (OVERTURNED — wave-2 only)**
(a) `checks/__init__.py:73` `GATE_REQUIRED_KINDS` deliberately **omits** `fanout`/`compensation` with an explanatory comment — that is a behavioral branch keyed on `kind`, so "no dispatch branch anywhere" is false. (b) `control_flow: fanout` (`loop_plan_spec.md:378`) is a **separate enum**; deleting the node kind yields a half-vocabulary. (c) `fanout/join` appears in `SKILL.md:13` — the **model-invocation description**, i.e. trigger surface. Cost/benefit is the worst in the plan: ~2 enum lines saved against rewriting an untouched 387-line file plus perturbing invocation. `mapper` is one of two named carriers of Layer 2 (`SKILL.md:72`).

**C4 — Policy prose is only *partially* duplicative. (PARTIALLY OVERTURNED — wave-2 only)**
The deletion case *"collapses three different things into Autonomy-First: execution temperament, operational safety protocols, and cross-system integrity boundaries. Those are not synonyms."* Six kernels have no other home and cannot be validator-checked (whether a diagnosis is causal, or an improvement substantial, is semantic judgment):
`execution_intelligence_policy.md` — root-cause record `:158`; adversarial-review triggers `:198`; quality-uplift cost gate `:222`; Goal Alignment Check `:232`; safety veto on deepening `:289`; transactional completion `:312`; execution-profile definitions `:347` (the only substantive definitions of the 4 profile names).
`layered_execution_chain.md` — layer-switch cascade `:200`; boundary-as-leaf-disqualifier `:253`; leaf-action test `:291`; **negative** examples `:304` ("fix the issue as appropriate" is not a leaf); positive examples `:318`; return relations `:349`.
Verdict: **extract kernels, do not delete files wholesale.** EIP collapses defensibly to ~120–170 lines. Only `recursive_planning_immersive_execution.md` fails to justify standalone existence.

**Upheld:** research-note deletion (§2.7), `assignee`/`notes` demotion, the vocabulary-instantiation counts, and the two-population split (§1).

---

## 5. Oracle rulings (resume-contract boundary)

**Minimal durable control set:** `loop.meta.yaml` (identity/ancestry — not inferable from directory names) · `loop.plan.yaml` · `checkpoint.yaml` (the current event-log contract is **not** complete enough to reconstruct its fields, despite being declared secondary) · the event log named by `checkpoint.event_log_ref` (R23 guards replay of unresolved non-idempotent effects) · `evidence.ledger.yaml` + every active entry's artifact (a checkpoint cannot authoritatively assert completion — `state_model.md:267`) · `node.contract` for nodes with consumed attempts or in-flight work · claim files **only** under concurrency.
Not fundamental: `task_profile`, logs, handoff, `_loops/INDEX.yaml` (index, not identity source), `loop.state.yaml`.

**Two missing load-bearing checks:** (1) event-completeness/replay — prove the log reconstructs authoritative checkpoint fields; (2) cross-file identity — prove `loop.meta.loop_id`, plan, checkpoint, parent reference, and directory all agree.

**The 21-field tuple:** *"all fields required for forward compatibility" is a trap* — it freezes accidental structure and invites placeholder data. A field is structurally required only if omission makes one of these impossible: cross-artifact identity/join · topology/readiness/transition · execution-or-completion permission · post-interruption reconstruction · safety/retry/cost/approval/recursion bound · parser discriminant (`schema_version`, `kind`). Forward compatibility belongs in `schema_version` + explicit migration rules, not in mandatory empty sentinels. Empty sentinels are justified only when empty and absent differ in meaning.

**Self-graded gates are net-NEGATIVE, not merely weak:** they mint the same authoritative `pass` as an independent check, producing *false assurance*. A durable rationale improves auditability, not epistemic strength. Fix = reclassify as an **attestation gate** with an explicit assurance label (`self_attested` ≠ script/user-verified), barred from solely authorizing irreversible effects, security/compliance claims, or high-risk completion. If assurance levels are unacceptable, remove the kinds from authoritative completion. **A rationale alone does not repair self-grading.**

**Dead vocabulary vs. extension point** — a declared extension point needs all four: distinct semantics · a consumer or validator branch implementing them · a canonical end-to-end example · a **committed** near-term adopter (not a possible future design).

---

## 6. Open decisions (block execution)

| # | Decision | Recommendation |
|---|---|---|
| DG1 | `mapper`/`fanout`: delete vs. keep-and-make-load-bearing | **Keep**, add a worked fixture. Poor cost/benefit to delete (C3). Depends on the user's planned new engineering skills — a committed adopter converts these from dead vocabulary to a real seam. |
| DG2 | `next_suggested_action` | **Keep.** Schema-`required`, and it is the actionable half of the recovery frontier; a checkpoint stating where you are but not what to do next weakens the resume promise. Drop only the 3 optional back-compat fields. |
| DG3 | `loop.state.yaml` migration targets | `human_decisions[]` / `active_constraints` → `decision.log.md` canonical (+ optional checkpoint mirror); `runtime_subgraphs` → `node.runtime.yaml` as sole home (withdraw Option A). |
| DG4 | Self-graded gates | Introduce assurance levels per §5. Not deletion. |

---

## 7. Method note for the next analysis round

Two properties of this audit are worth preserving in any follow-up:
1. **Disjoint partition, then corroboration.** 13 auditors read non-overlapping files, so convergence on the A/B split is independent corroboration rather than echo.
2. **The hostile round changed the answer.** 4 of 8 cuts fell. Any future round that produces no overturned hypotheses should be treated as under-powered, not as confirmation.

Known blind spots: (a) no dynamic evidence — the repo ships no runtime, so every "would break at runtime" claim is inferential, not observed; (b) no eval set exists, so mechanism *effectiveness* (as opposed to mechanism *presence*) was never measured for any surviving mechanism — Anthropic's "build evaluations first" gap is unaddressed by this audit and cannot be closed by reading files.
