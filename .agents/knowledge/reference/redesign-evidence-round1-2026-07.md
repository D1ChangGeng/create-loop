# Round-1 Evidence Digest — `skills/create-loop/` redesign

Compiled 2026-07-30. Every claim below was produced by a scoped audit agent and
spot-verified against source. This is the ONLY input Round 2 needs; it supersedes
loose recollection.

---

## 0. The governing test (from the user, this round)

A mechanism is justified ONLY if this chain can be written:

> **records/processes WHAT information → how that changes a later judgment or action → how that change improves the final result**

If the chain cannot be built, or its benefit does not cover cognitive cost +
execution cost + context consumption + maintenance complexity, the mechanism does
not survive by default.

**RETIRED PREMISE:** the user states this is deliberately NOT a traditional skill,
so Anthropic's 500-line SKILL.md ceiling is NOT a constraint. Round-1's §2.1
finding (SKILL.md 803 lines = 60% over) is void. Size alone is no longer evidence
of defect. Only the causal test above decides.

## 0.1 The reported symptom (primary evidence, outranks any audit inference)

The agent spends large amounts of time updating fields whose value the user cannot
see, and under-spends on: understanding goal+constraints, acquiring external
knowledge, identifying technical risk and architectural contradiction, deriving
executable design, verifying assumptions, real implementation/test/iteration, and
correcting the design from long-run feedback.

Mechanisms that simulate professionalism (many fields, states, checklists, role
definitions, process records) are explicitly NOT the goal. Actual professional
capability is.

---

## 1. MEASURED: the attention tax (agent `bg_31220b76`)

Advancing ONE node `todo → in_progress → done` mandates:

| # | File | Writes | Mandating citation |
|---|---|---|---|
| 1 | `contracts/<node>.claim` | 7 fields, `O_CREAT\|O_EXCL` | SKILL.md:503, state_model.md:135 |
| 2 | `state/event_log.jsonl` `pre_effect` | 11 fields | SKILL.md:507, recovery_protocol.md:186-189 |
| 3 | `state/event_log.jsonl` `post_effect` | 6 fields | SKILL.md:509, recovery_protocol.md:191-192 |
| 4 | `contracts/<node>.contract.yaml` | 4 changed + 9 copied verbatim | state_model.md:77-78, 126-127, 241 |
| 5 | `state/evidence.ledger.yaml` | 11 fields | SKILL.md:511, evidence_gates.md:7 |
| 6 | `state/checkpoint.yaml` | **17+ fields, FULL REWRITE — every node's state re-emitted** | SKILL.md:513, state_model.md:174-190 |
| 7 | `loop.state.yaml` + `decision.log.md` + `run.log.md` | remainder | state_model.md, templates |

**~78 field-writes per node advance across 7 files.**
**A blank-session resume reads ~7–9 of them.**
**Ratio ≈ 9:1 write-to-read.**

Aggravating facts:
- `checkpoint.yaml` is a **full rewrite**, not a patch — unchanged nodes are re-emitted every advance.
- The protocol's own State Authority Order (`recovery_protocol.md` §6.0) declares the event log the source of truth ⇒ **~38 of the 78 writes are projections of data already durably written**.
- 20-node loop ⇒ ~1,560 mandated field-writes.

## 2. MEASURED: field read-side graph (agent `bg_609f4541`)

Audited 189 fields across all 11 schemas. Classification by ACTUAL reader
(schema `required` lists, template presence, and prose descriptions do NOT count
as readers):

- **~79 WRITE-ONLY** (42%) — *** RETRACTED, see §CORRECTIONS at end of file. The audit
  excluded PROSE readers, so this count is inflated. At least 10 fields called write-only
  are read by behavioral instruction, 3 of them by the RESUME ALGORITHM itself. Treat 79
  as an UPPER BOUND, not a finding. The verified-ceremonial set is 3 fields. ***
- Remainder split validator-read / instruction-read.

**CRITICAL DISTINCTION — two kinds of write-only, opposite remedies:**

**(a) Ceremonial — genuinely deletable / auto-derivable:**
`schema_version` (×5 files), `created`/`created_at`/`recorded`/`heartbeat_at`/`acquired_at`
timestamps, `retry_policy.jitter`, `node.contract.cache_key`,
`runtime_subgraphs[].owner_agent`, `runtime_subgraphs[].created_at`/`updated_at`,
`subgraph.parent_ref`/`schema_version`/`plan_version`, `retirement.retired_at`,
`event_log.entries[].phase`/`intent`/`from_status`/`to_status`,
`artifacts[].type`/`owner_node`/`produced_by`, `loop.meta.created_by`/`depth`.

**(b) Goal-anchor fields that are write-only because NOTHING RE-READS THEM — the
defect is a MISSING READER, not a useless field:**
`success_criteria`, `failure_criteria`, `non_goals`, `constraints`,
`termination.max_iterations`/`max_wall_clock_hours`/`max_cost_units`/`max_active_subgraphs`,
`nodes[].inputs`/`preconditions`/`postconditions`, `loop.meta.scope.in`/`scope.out`,
`checkpoint.open_blockers[]`, `evidence.entries[].rationale`.
⇒ These encode goal + constraint + acceptance. That the protocol never re-reads
them is the mechanical cause of goal drift. **Deleting them would be the wrong fix.**

**Instruction-read (no validator, but a real behavioral consumer) — protected:**
`requires`, `node_states`, `ready_set`, `parallelizable`, `priority`,
`allow_subgraph`, `subgraph`, `child_loops[].path`/`closeout`, `gate`,
`gate.rubric`, `gate.evidence_ref`, evidence `verdict`/`status`,
`retry_policy`, `on_failure`, persistent `attempt`, `assignee`,
`termination.done_when`, `human_intervention_policy.*` (4 sub-fields),
`checkpoint_id`, artifact-index `path`/`status`/`supersedes`, event-log
`seq`/`kind`/`idempotency_key`/`result_hash`.

## 3. MEASURED: gate assurance — the decisive finding (agent `bg_b066b6ba`)

The 8 locked gate kinds, classified by whether the verdict comes from something
OTHER than the thing being judged:

| Gate kind | Verdict producer | Classification |
|---|---|---|
| `artifact_exists` | script / filesystem stat | **EXTERNALLY-GROUNDED** (by design) |
| `automated_check` | script exit code + `{passed}` | **EXTERNALLY-GROUNDED** (by design) |
| `test` | sandbox test execution | **EXTERNALLY-GROUNDED** (by design) |
| `human_approval` | the literal user answer | **EXTERNALLY-GROUNDED** (by design) |
| `llm_judge` | a model judging output vs rubric | **SELF-ATTESTED** |
| `self_consistency` | K samples of the model's own reasoning | **SELF-ATTESTED** |
| `evaluator_optimizer` | model critique/accept loop | **SELF-ATTESTED** |
| `step_verifier` | model per-step scoring | **SELF-ATTESTED** |

**4 externally grounded, 4 self-attested. Half the gate vocabulary cannot detect
the error class it exists to catch.**

**Worse — enforcement is shape-only.** `validate_loop_plan.py:174-227` checks enum
membership + required-field presence + lifecycle consistency.
`check_loop_integrity.py:119-129` checks only that `artifact_path` **exists on
disk** (HTTP URLs exempt). NOTHING runs a test, parses `{passed}`, compares
`score` to `threshold`, or checks the ledger `gate_kind` matches the node's
configured gate. Consequence, quoted from the audit:

> "With only the checked-in validators, an agent can manufacture a passing ledger
> entry plus an existing artifact path for **any** gate kind."

Cheapest cheat per gate (abridged): `artifact_exists` → `touch` any file (integrity
checker tests `.exists()` only, though the norm says non-empty); `test` → write a
fake report listing all cases passed; `automated_check` → fabricate
`{passed:true}`; `self_consistency` → copy ONE answer into all K sample files and
claim unanimity; `step_verifier` → omit the hard steps from the claimed step set;
`human_approval` → write `human_verdict.json` and label `verifier: user` (no token
link to `pending_approvals`).

**`score` is inert.** Required on EVERY ledger entry (schema + 4 scored-gate prose
rules branch on it), but **no validator ever compares `score` to `threshold`**.
The machine transition gates on `verdict: pass` alone (`state_model.md:267-269`).
So `score: 0.0` + `verdict: pass` validates clean. `score` is a required field
that changes nothing.

**Verifier independence (R36) is real but shallow.** Rule
(`evidence_gates.md:33-47`, :262-265): a `risk: high` node MUST record `verifier`
≠ producing `agent`. `checks/provenance.py:71-110` DOES enforce a narrower version:
`risk in ("med","high") AND produces non-empty AND verifier == "agent"` → reject.
But it does not enforce the scored-gate requirement, the `threshold >= 0.7`
requirement, or restrict to the documented gate kinds. And the ledger carries no
producer ID / verifier ID / session ID / model ID / signature — only one of four
role strings. ⇒ **a producing agent can simply label its own verdict
`verifier: subagent` or `verifier: script`.** The rule is syntactically enforceable
but semantically unfalsifiable without a runner that owns ledger writes.

**Two additional defects found:** (i) `evidence_gates.md:33-47` and :262-265 state
two NON-IDENTICAL versions of the independence rule (the second adds
`step_verifier` + threshold). (ii) `example_research_project/README.md:78-83`
claims `N9_recommendation_approval` is "gate-exempt" with `gate: null`, which
**contradicts R34** (`checks/gates.py:24-35`) requiring approval nodes to carry a
`human_approval` gate.

## 4. MEASURED: high-value behavior coverage (agent `bg_1fac5b2a`)

Verdicts (agent REVISED 3 of 7 upward on its second pass — the revised set is
authoritative):

| # | Behavior | Verdict | ~lines | Strongest instruction |
|---|---|---|---|---|
| 1 | Goal + constraints | PROCEDURE-SPECIFIED | ~70 | `templates/interview_brief.md:93-100` |
| 2 | **External knowledge acquisition** | **NAMED-ONLY** | ~15 | `interview_brief.md:146-156` |
| 3 | Risk / contradiction discovery | PROCEDURE-SPECIFIED | ~85 | `execution_intelligence_policy.md:198-211` |
| 4 | **Executable technical design** | **NAMED-ONLY** | ~30 | `interview_brief.md:199-211` |
| 5 | Assumption verification | PROCEDURE-SPECIFIED | ~45 | `SKILL.md:118-123` |
| 6 | Implementation / test / iteration quality | PROCEDURE-SPECIFIED | ~95 | `execution_intelligence_policy.md:146-167` |
| 7 | Long-run design correction | PROCEDURE-SPECIFIED | ~135 | `live_loop_semantics.md:132-154` |

Ranked gaps: **RANK 1 external knowledge** (HIGH) — research is named but no
external-source / real-API verification procedure exists. **RANK 2 executable
design** (HIGH) — architecture and ADRs named without required interfaces, data
flow, or design artifact. **RANK 3 implementation quality** (HIGH) — testing
exists but professional test strategy under-specified. Nothing is fully ABSENT.

**⚠ THIS INVERTS A ROUND-1 CONCLUSION.** Round 1 scored reference prose by
validators-per-line and flagged `execution_intelligence_policy.md` (416 lines,
0 validators, 0 schema fields) as low-yield. It is in fact the home of the two
STRONGEST high-value instructions in the entire skill — verified by direct read:
- §3.2 root-cause classification: *"the question is never 'how do I make this
  green' — it is 'which of these is actually wrong': the requirement, the
  implementation, the test itself, an architecture assumption, the environment,
  the data, or the evidence standard."* Marked **"required, not optional"**.
- §3.5 counterexample review: *"the runner deliberately attacks its own design"* —
  with a concrete question set for architecture / spec / recovery / release nodes.
Measuring behavioral instruction by machine-enforcement was a category error.
**Behavioral instruction and machine enforcement are different goods.**

## 5. MEASURED: role mechanisms (agent `bg_5ad6cb8f`)

8 PERSPECTIVE-ALLOCATING / 3 ORG-SIMULATION / 3 BOOKKEEPING.

**Earns its cost (perspective-allocating):**
- `assignee: user` — real capability gap (goal sovereignty, authorization, legal,
  blast radius); real external party; is the canonical independent reviewer.
  `human_approval.md:603-604`: the human_approval gate is the ONLY gate whose
  `verifier: user` produces a verdict.
- `assignee: subagent` — genuine context isolation, explicitly specified:
  per-branch `input.json` / `output.json` / `notes.md` (invisible to siblings),
  `git worktree` per unit for code. The sharpest line in the skill
  (`branching_parallelism.md:142-149`): *"Two subagents that share context are not
  parallel; they are one subagent with split attention."* Fan-out capped 3–5.
- generator/verifier separation (R36) — the ONE role rule with validator teeth.

**Org-simulation (cost without distinct perspective):**
- `recursive_planning_immersive_execution.md:93-94` — "architect · project lead ·
  layout designer" (global view) vs "executor · researcher · engineer · verifier"
  (local view). Same agent, same context, different label. Hat-wearing.
- `interview_brief.md:60-76` — "You are three things at once: a control engineer,
  a systems architect of governance, a project lead who owns schedule and budget."
  Three hats, one context, no independent verdict.

**Bookkeeping (a string field, not a role):** `runtime_subgraphs[].owner_agent`,
`artifacts[].owner_node`/`produced_by`.

**Cost measured on the ONE role handoff that is real:** a single `assignee: user`
approval writes back to FOUR artifacts (`decision.log.md`, `loop.state.yaml`,
`checkpoint.yaml`, sometimes `loop.plan.yaml`), the decision package template is
**15 sections**, and the answer YAML has 8 keys.

## 6. EXTERNAL EVIDENCE — what causally improves agent output (`bg_bc51fdd4`)

| Topic | Finding | Strength | vs user hypothesis |
|---|---|---|---|
| Self-evaluation | Harmful self-preference **persists specifically when the model's own answer is objectively wrong** — ~86% MATH500, ~73% MMLU (Qwen2.5-72B) | rigorous-eval | Chen, arXiv:2504.03846, 2025 — **UNDERMINES self-grading** |
| Execution-based verification | Tests / execution / mutation testing / counterexamples beat unsupported self-assessment; weak tests still create false confidence | rigorous-eval | **SUPPORTS** |
| Planning | Decomposition helps structured tasks; **short-horizon plans + observation-driven replanning beat rigid static plans** | rigorous-eval | Yao ReAct, ICLR/arXiv:2210.03629 — **MIXED** |
| Instruction overload | Compliance degrades with instruction COUNT and turn count; independent per-constraint checks partially recover it | rigorous-eval | Wen, NeurIPS/arXiv:2407.03978, 2024 — **SUPPORTS** |
| Assumption tracking | Helps ONLY when the hypothesis selects a DISCRIMINATING observation; generic assumption lists lack causal evidence | preprint | **MIXED** |
| Long-horizon failure taxonomy | goal misunderstanding · invalid plan · stale state · context loss · error cascade · coordination failure · premature termination | preprint | Cemri, arXiv:2503.13657, 2025 — **SUPPORTS** |

**COUNTER-EVIDENCE the user must absorb (their hypothesis is too broad as stated):**
- Mechanical enumeration IS valuable **when each enumerated item has an objective
  verifier** — rule-augmented evaluation exposes failures holistic scoring misses
  (Wen 2024).
- Self-consistency / majority voting DOES improve accuracy **when a reliable
  discrete verifier exists** — that is aggregation, not subjective self-scoring
  (Wang, arXiv:2203.11171).
- Per-constraint self-refinement (check each constraint separately, repair
  violations) improves compliance — NOT equivalent to holistic self-scoring
  ("Curse of Instructions", OpenReview 2025).
- Deterministic checks are legitimate as **necessary-but-not-sufficient**
  conditions.

⇒ **The correct rule is NOT "mechanical checks are low value". It is: a check
earns its cost only if its verdict is produced by something OTHER than the thing
being checked, and each checked item has an objective verifier.**

**Failure modes and whether scaffolding can prevent them** (all "NOT preventable
by scaffolding: no" ⇒ all ARE preventable):
goal misunderstanding → explicit success-condition extraction + external acceptance
checks · invalid decomposition → dependency discovery + executable subgoals +
short-horizon replanning · stale state → mandatory post-action state reads ·
repeated failed actions → failure memory tied to a CHANGED hypothesis (prohibit
unchanged retry) · error compounding → causal-boundary checkpoints + external
verification after high-impact steps.

## 7. EXTERNAL EVIDENCE — what production systems actually persist (`bg_1f5471b0`)

**PERSIST (verified against primary sources):** append-only event log
(Temporal Workflow History, LangGraph checkpoint+writes, Codex rollout JSONL,
OpenHands event stream) · `thread_id`/resume key · atomic state snapshot ·
per-step input/output memoization keyed by step ID (Inngest) · pending writes so
successful siblings don't re-run (LangGraph `put_writes`) · plan as structured JSON
(Devin) · agent-written memory file (Claude Code MEMORY.md) · project instruction
file (AGENTS.md, 60k+ repos) · git commit history · action-observation pairs ·
human-readable progress summary · **resource POINTERS, lazy-loaded** (Anthropic
multi-agent research system).

**DELIBERATELY DO NOT PERSIST:** raw tool-result content after synthesis (context
rot) · vector embeddings (AutoGPT REMOVED Pinecone/Milvus/Weaviate — plain JSON
won) · full conversation history (context reset + structured handoff instead) ·
**graph topology / node-edge definitions (LangGraph persists STATE, not topology —
"code is the source of truth; persisting it breaks versioning")** · **per-node
retry count in user-visible state (LangGraph keeps it in checkpointer metadata,
NOT state — "transient, internal to runtime")** · free-form reasoning traces ·
semantic "why this decision" annotations (Devin persists only user-CONFIRMED
knowledge entries) · hypothetical what-if branches.

**Event log vs snapshot — industry consensus:** event log is the source of truth,
snapshots are a derivative query-performance cache. Snapshot alone is unsafe
(loses intermediate transitions); log alone is correct but slow. Both Temporal and
LangGraph persist both. LangGraph's 2026 DeltaChannel makes it explicit.
⇒ **The skill's State Authority Order is CORRECT and matches industry. The defect
is that it then mandates ~38 projection writes per node anyway.**

**Human-in-loop in production:** durable state written at the pause point, **zero
compute held**, resume by replay + typed input (LangGraph `interrupt()` +
`Command`, Temporal Signal, Inngest `waitForEvent`).

**BLUNT VERDICT ON OUR DESIGN (quoted):**
1. ACHIEVABLE filesystem-only: event log (append-only JSONL), thread_id (loop dir
   name), state snapshot (one JSON at step boundary), plan JSON, `progress.md`,
   memory notes, AGENTS.md, git history.
2. CARGO-CULT (imported from systems that HAVE a runtime we do not): per-step
   pending-writes queue (no superstep model) · parallel execution tokens (no
   scheduler) · runtime retry counters in user state (no runtime to count) ·
   per-node execution-status fields (no live execution) · cryptographic evidence
   ledgers with provenance chains (no oracle to verify against).
3. *"durability for a markdown-instructed agent IS git + one JSONL file + a
   progress doc. The 21-field-per-node DAG, evidence ledger, claim file, and
   artifact index are theater unless you have a runtime enforcing gates against
   them — Anthropic's own four-piece artifact set for a long-running agent is
   init.sh + claude-progress.txt + feature-list.json + git. Four files. Not four
   systems."*
4. **wait-for-event pause is NOT achievable without a runtime.** LangGraph
   `interrupt()` and Temporal `waitForEvent` both require a process holding pause
   state + a scheduler to deliver resume. Without a daemon the approval gate MUST
   be a next-session protocol: write `waiting-for-approval.md`, exit, human
   restarts a session that reads it. Devin/Codex/Claude Code all
   dehydrate-and-rehydrate despite HAVING runtimes.
5. **Definition of "resumable" for a runtime-less agent:** the next agent is
   stateless; its job is read filesystem → understand state → continue. *"The state
   contract is the README a future agent will read. If a human cannot read it cold
   and know what to do next, the agent cannot either. Optimize for that, not for
   symmetric parallelism with Temporal."*

---

## 8. Carried forward from Round 1 (still valid, premise-independent)

- `check_loop_integrity.py` **never loads the event log** and treats checkpoint +
  ledger as optional (`if ...exists()` at :62, :67, :104) ⇒ **exit 0 does not prove
  safe resume.** Oracle-confirmed inverse defect: under-enforcement, not over.
- `research_dags_multiagent.md` (869) + `research_durable_loops.md` (640) = 1,509
  lines of RAW AGENT TRANSCRIPTS — they literally open with `Task ID: bg_...` /
  `Duration: 10m 52s` / `Session ID: ...`. Both unreachable from SKILL.md's POINTER TABLE
  *** but NOT unreachable from the skill: 54 inbound links from 8 reference files, 7 of them
  citation cells INSIDE the gate-kind vocabulary table. See §CORRECTIONS. ***
  (0 inbound). They propose 16 node kinds vs the locked 8, and `runs/<run_id>/`
  vs the shipped `.agents/loops/` — i.e. they CONTRADICT the shipped design.
- Live contradiction: `recursive_loops.md` §1 "arbitrary depth" vs
  `loop_plan_spec.md` §1.2 `termination.max_depth` (R28); examples set 3.
- `self_evolution_integration.md` = 690 lines → 0 validators, 0 schema fields.
- Node kinds: 8 locked. Instantiation in the 4 worked examples: `milestone` 29,
  `gate` 10, `approval` 2, `join` 1, `compensation` 1, `branch` 1,
  **`mapper` 0, `fanout` 0**. (Incl. `templates/loop.plan.yaml`: `milestone` 32,
  48 nodes total.)
- `fanout` is deliberately omitted from `GATE_REQUIRED_KINDS`
  (`checks/__init__.py:73`) ⇒ it HAS a behavioral branch even at 0 instances.
- `NODE_REQUIRED` = exactly 21 fields (`checks/__init__.py:81`).
- No existing gate checks Markdown pointer integrity ⇒ deleting reference files
  silently severs 10+ inbound links. Pointer checker is a Wave-0 precondition.
- Enum guards are behavior-selecting, not cosmetic: `status: done` (vs `completed`)
  yields a node that neither executes nor terminates.
- R-numbers are pinned by fixture IDs across `failure_mode_tests.md` (2,617 lines)
  ⇒ renumbering after a removal invalidates fixtures; tombstone instead.
- 4 worked examples are ~90% load-bearing (empty-field tax ~10%), NOT ceremony.
- The green gate never exercises 6 of the 11 artifact kinds it nominally validates.

## 9. Open decisions still gating execution

1. `next_suggested_action` — schema-`required`, read only as a tie-break hint. Recommend KEEP.
2. `loop.state.yaml` — declared home for `human_decisions[]` / `active_constraints` / `runtime_subgraphs` that are ABSENT from `checkpoint.schema.json`. Migration target: `decision.log.md` + `node.runtime.yaml`.
3. `mapper` / `fanout` — 0 instances. Recommend KEEP + add a worked fixture IF the user's planned new engineering Skills will use them. **User has not yet named those skills.**
4. Self-graded gates (`llm_judge` / `step_verifier` / `self_consistency` / `evaluator_optimizer`) — net-negative as authoritative. Fix via ASSURANCE LEVELS (`self_attested` ≠ `script`), not deletion.


---

## CORRECTIONS (appended after Round 2 — read before using any number above)

Six claims in this digest were overturned by verification. Every correction below was
confirmed by running code or reading the cited line — none is an opinion.

| # | Retracted claim | Verified reality | Evidence |
|---|---|---|---|
| E1 | "9 genuinely ceremonial fields, safe to delete" | **3 of the 9 have live readers.** `recorded` is in the evidence-entry required tuple (`validate_loop_plan.py:196`); `cache_key` is in `CONTRACT_REQUIRED` (`checks/__init__.py:89`); `jitter` is read by the backoff formula (`exception_handling.md:337-361`). Also `created_at`/`created_by` are in `LOOP_META_REQUIRED` (`checks/__init__.py:99`) and `heartbeat_at` is in `CLAIM_REQUIRED` (`checks/claim.py:12`) and IS the lease mechanism. | verified by grep on the required-tuples |
| E2 | research transcripts are "unreachable" | **54 inbound links** from 8 reference files (`loop_plan_spec` x8, `exception_handling` x11, `concepts` x14, `recovery_protocol` x7, `human_approval` x5, `evidence_gates` x5, `branching_parallelism` x2, `state_model` x2). Deleting them severs citations *inside the gate-kind vocabulary table*. | verified by link grep |
| E3 | all 3 research files are raw transcripts | `research-sources.md` (317 lines) is a **clean cited report** with source URLs and filesystem-mapping notes. Only the other two (1,509 lines) are transcripts. The "16 node kinds / runs/<run_id>/" text describes OTHER systems (prior art), not competing claims about this skill. | verified by reading the head |
| E4 | integrity checker "exit 0 does not prove safe resume" | **Confirmed and worse.** A directory containing ONLY `loop.plan.yaml` — no checkpoint, no ledger, no event log — exits **0** printing `INTEGRITY OK`. It actively certifies an unresumable loop as healthy. | reproduced empirically |
| E5 | R28 governs `max_depth` | Correct (`caps.py:41` emits `[R28 CAP-EXCEEDED]`). Verified only because the docstring reads ambiguously. | no change |
| E6 | (not previously stated) | **Only R1-R18 have a runnable fixture script.** R19-R41 are prose-only. Next free rule number is **R42**. Any new rule must ship a runnable fixture. | verified |

### The recurring error in this investigation

Four separate times, a mechanism was judged by the WRONG detector:

1. Judged reference prose by validators-per-line -> nearly deleted
   `execution_intelligence_policy.md`, which holds the skill's STRONGEST behavioral
   instruction (root-cause classification, counterexample review).
2. Judged fields by validator-reads-only -> called the goal contract ceremonial when the
   resume algorithm itself reads `failure_criteria`, `max_iterations`, `max_cost_units`.
3. Judged reachability by SKILL.md's pointer table -> missed 54 inbound reference links.
4. Judged the 500-line ceiling as binding -> the user retired it as a non-constraint.

**All four erred toward deletion.** Any future round must apply the 4-reader test
(validator / behavioral instruction / template / closeout-or-human) before calling
anything unread, and must state which detector it used.
