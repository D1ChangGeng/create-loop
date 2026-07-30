# Evidence Gates: Why They Exist and How to Choose One

*Diataxis type: **reference + explanation**. This document is the
authoritative guide to the eight gate kinds. It explains why gates are
the only way a node reaches `completed`, and gives the tradeoffs that
determine which kind to assign to which node. For the field dictionary,
see [`loop_plan_spec.md` §4](./loop_plan_spec.md#4-evidence-gates). For
the ledger where verdicts are recorded, see
[`state_model.md` §evidence-ledger](./state_model.md#evidence-ledger).*

---

## 1. Why gates exist

A node is not `completed` because an agent says so. It is `completed`
because **evidence says so**. Every non-trivial node carries a `gate`,
an explicit verification with a defined `kind`, an optional numeric
`threshold`, an optional `rubric`, and a pointer to the evidence
artifact it writes. The transition
`verifying → completed` is committed to the checkpoint **only** when
the latest active ledger entry has `verdict == pass` and declares
`assurance: external`, or its `gate_kind` is `human_approval`. Any other
verdict (`fail`, `inconclusive`) drives the transition to
`verification_failed`, which feeds the
[escalation ladder](./loop_plan_spec.md#62-on_failure--the-escalation-ladder)
([`state_model.md` §state-transition-table](./state_model.md#state-transition-table)).

The principle behind the rule: evidence is **external and re-readable**.
A fresh session can trust the plan without trusting a prior agent's
word, because the proof sits on disk in the form of files and ledger
entries that the next agent can inspect
([`concepts.md` §5](./concepts.md#5-why-evidence-gates)).

### 1.1 Generator/verifier separation

For high-risk nodes the producer must not grade itself. The
[Anthropic generator/verifier pattern](https://www.anthropic.com/research/building-effective-agents)
and the
[harness design post](https://www.anthropic.com/engineering/harness-design-long-running-apps)
both report that self-evaluation is a trap; adversarial or
context-isolated evaluators work better. The `verifier` field on the
ledger entry records who did the grading, drawn from
`{agent, subagent, user, script}`
([`state_model.md` §evidence-ledger](./state_model.md#evidence-ledger)).
A node whose `risk` is `high` MUST use a scored gate (`llm_judge`,
`self_consistency`, `evaluator_optimizer`, or `step_verifier`) with a
`threshold >= 0.7`, and MUST record a `verifier` other than the
producing `agent`.

---

## 2. The gate object

The shape of a `gate` is fixed
([`loop_plan_spec.md` §4.1](./loop_plan_spec.md#41-gate-object)):

| field | type | meaning |
|-------|------|---------|
| `kind` | enum | one of the eight gate kinds below |
| `threshold` | number (0..1) or `null` | pass threshold for scored gates; `null` for pass/fail gates |
| `rubric` | path or `null` | path to the rubric document for judged gates |
| `evidence_ref` | path | path to the evidence artifact this gate writes |

A verdict is recorded in the
[evidence ledger](./state_model.md#evidence-ledger) as one entry per
evaluation, with fields including `verdict` (`pass`, `fail`,
`inconclusive`), `score` (0..1 or `null`), `verifier`
(`agent`, `subagent`, `user`, `script`), `artifact_path`, `rationale`,
`assurance` (`external`, `blind`, `self_attested`), optional
`success_criteria_id`, and `recorded` (ISO-8601). Multiple entries per node are allowed; the
**latest** entry governs the next transition.

---

## 3. The eight gate kinds

Each kind has a fixed cost / strength profile. Pick the cheapest kind
that gives the signal you need; reserve the expensive kinds for the
nodes where the cheap ones would lie.

### 3.1 `artifact_exists`

The cheapest gate. Passes iff a file exists at the path the node
declared in its `produces` list. Use it for nodes whose contract is
"this file lands here" and where the file's contents are validated by
a downstream node's own gate. Cost is essentially zero (a `stat` call).
Strength is low: a present file is not a correct file. Pair it with a
downstream `automated_check` or `test` for any non-trivial content.

| | |
|---|---|
| when to use | mechanical "did the artifact land" checks; final-mile delivery of cached or human-produced files |
| evidence artifact | the artifact itself, recorded by path |
| pass condition | file present and non-empty |
| cost / strength | negligible cost, lowest strength |

### 3.2 `automated_check`

A deterministic scripted check. Lint, schema validation, format
conformance, structural assertions over the produced artifact. The
runner executes the script, captures exit code and structured output,
and writes the result.

| | |
|---|---|
| when to use | anything with a deterministic validator: JSON Schema, regex, AST shape, lint rule |
| evidence artifact | script stdout/stderr plus a structured `{passed, details}` record |
| pass condition | script exit code 0 and structured `passed == true` |
| cost / strength | low cost (single script invocation), medium-to-high strength if the script is exhaustive |

### 3.3 `test`

Code tests run in a sandbox as evidence. The CodeAct pattern and
eval-driven TDD
([`./research_dags_multiagent.md` §3.7 to 3.8](./research_dags_multiagent.md))
both treat test execution as the gold standard: deterministic, fast,
self-describing, and high signal-to-noise. The runner executes the
node's tests in a sandbox; `verifier: script` is recorded.

| | |
|---|---|
| when to use | any node that produces or modifies code; any node whose contract is "behave like this under these inputs" |
| evidence artifact | test report (per-case pass/fail, assertion output, coverage if available) |
| pass condition | every required test case passes |
| cost / strength | medium cost (sandbox execution), high strength |

### 3.4 `llm_judge`

A separate LLM scores the node's output against a rubric. Drawn from
[Zheng et al. 2023 (arXiv 2306.05685)](https://arxiv.org/abs/2306.05685),
which showed strong LLM judges reach >80% agreement with both
controlled and crowdsourced human preferences. The four documented
biases, all of which the rubric can mitigate:

- **position bias**: prefer the first option. Mitigate by swapping
  positions across two calls and reporting the mean.
- **verbosity bias**: prefer the longer answer. Mitigate by
  normalising to length and explicitly weighting against verbosity.
- **self-enhancement bias**: prefer the judge's own prior outputs.
  Mitigate by using a different model family for judging than for
  generation, and by referencing a known-good baseline.
- **limited reasoning ability**: judges struggle on multi-step
  reasoning. Mitigate by decomposing into per-step `step_verifier`
  calls when the output is multi-step.

| | |
|---|---|
| when to use | quality judgements that resist deterministic check (writing quality, design taste, plan feasibility) |
| evidence artifact | judge output: `score`, `rationale`, `rubric_breakdown` |
| pass condition | `score >= threshold` |
| cost / strength | high cost (LLM call), medium strength (biases are real) |

### 3.5 `self_consistency`

Sample the node's reasoning K times at high temperature, then take the
majority vote (or aggregate rationales). Drawn from
[Wang et al. 2022 (arXiv 2203.11171)](https://arxiv.org/abs/2203.11171).
The agreement rate is itself an honest uncertainty estimate; a node
whose K samples disagree is genuinely uncertain and should escalate
rather than be marked `completed`.

| | |
|---|---|
| when to use | nodes whose answer admits multiple valid reasoning paths (math, classification, constrained extraction) |
| evidence artifact | the K samples plus the aggregate verdict |
| pass condition | majority agrees AND `score >= threshold` (where score = agreement rate) |
| cost / strength | K times the cost of a single LLM call; strength scales with K |

### 3.6 `evaluator_optimizer`

A generate → critique → revise loop until the evaluator accepts the
output. The
[Anthropic evaluator-optimizer pattern](https://www.anthropic.com/research/building-effective-agents)
recommends this when LLM responses can be demonstrably improved by
explicit feedback and the LLM can produce such feedback. Each pass
records its own ledger entry; the loop terminates on a `pass` verdict
or on hitting a budget cap.

| | |
|---|---|
| when to use | open-ended generation where iteration improves quality (drafts, designs, plans) |
| evidence artifact | the final accepted output plus the trajectory of `{draft, feedback}` pairs |
| pass condition | evaluator returns `verdict == pass` |
| cost / strength | N passes; strength rises with each iteration, bounded by the iteration cap |

### 3.7 `step_verifier`

Step-level / process-reward verification. Drawn from the PRM
literature ([`./research_dags_multiagent.md` §3.6](./research_dags_multiagent.md));
a judge scores **each step** of a multi-step output rather than only
the final answer. This is what makes "the agent got the right answer
for the wrong reason" detectable.

| | |
|---|---|
| when to use | multi-step reasoning chains, tool-use sequences, code generation with intermediate states |
| evidence artifact | per-step scores plus an aggregate score |
| pass condition | every required step scores above the per-step threshold AND the aggregate `score >= threshold` |
| cost / strength | high cost (one verifier call per step), high strength (catches reasoning failures invisible to `llm_judge`) |

### 3.8 `human_approval`

A human signs off. Drawn from the human-in-the-loop literature
([`./research_durable_loops.md` §3.1](./research_durable_loops.md)).
Passes iff a user verdict (`pass` or `fail`) is recorded for the
node's `pending_approvals` entry. While the gate is open, the node's
status is `waiting_user`; the runner surfaces the `approval` node
with its `token` and waits.

| | |
|---|---|
| when to use | any node whose side effects are irreversible or whose quality is fundamentally judgemental (legal, financial, user-facing copy) |
| evidence artifact | the human verdict plus their rationale |
| pass condition | user returns `verdict == pass` |
| cost / strength | highest latency cost (waits on a human), highest legitimacy |

---

## 4. The orthogonal assurance axis

Gate kind and assurance answer different questions. Treat every ledger entry as
a point in a two-axis model:

- **WHAT was checked — `gate_kind`:** one of the eight kinds in §3.
- **WHERE THE VERDICT CAME FROM — `assurance`:** one of the three provenance
  classes below.

| assurance | provenance recorded |
|-----------|---------------------|
| `external` | grounded in something outside the model: a process exit code, test result, real tool/API observation, or file-existence observation |
| `blind` | an independent context produced the verdict without seeing the producer's claim or rationale |
| `self_attested` | model opinion about its own or a peer's output |

The axes are orthogonal. An `llm_judge` may be `blind` or `self_attested`; a
`test`, `automated_check`, or `artifact_exists` observation is normally
`external`. `assurance` is not a ninth gate kind.

### 4.1 Blind verification procedure: verdict first

An entry may declare `assurance: blind` only when the runner uses this
procedure:

1. Give the verifier the artifact under review and the evaluation criteria
   only. Do not provide the producer's verdict, claim, or rationale.
2. The verifier writes its verdict to the entry's `artifact_path` before it is
   allowed to read the producer's claim.
3. After the verdict exists, expose the producer claim at
   `producer_claim_path`. Keep both files so R47 can compare their mtimes.

The verdict file must therefore have an mtime no later than the producer claim
file. R47 rejects the opposite ordering. **This mtime comparison proves
ordering only.** It does not prove blindness or independence: a reviewer could
peek through an unrecorded channel and still satisfy the file ordering. The
runner remains responsible for context isolation and for deciding whether the
declared `blind` provenance is credible.

A negative blind verdict cannot be silently discarded. The runner must either
address it before completion or override it on record: the overriding ledger
entry names the negative entry in `overrides_entry_id`, and a `dissent` event
for the node records in `reason` why the runner proceeded. R48 detects only the
absence of that event when the node is completed; it does not judge whether the
override was justified or whether either verdict is correct.

Only an active passing entry declaring `assurance: external`, or a passing
`gate_kind: human_approval` entry, may authorize `completed`. A passing
`self_attested` entry has **provisional evidence standing** only. `provisional`
is a property of evidence rather than a 16th node status, because it describes
the authority of a verdict rather than execution lifecycle. Passing `blind`
evidence is also non-authorizing under this rule. Provisional evidence can never
satisfy `done_when`.

**Deterministic/semantic boundary.** The validator inspects only the declared
`assurance`, `gate_kind`, lifecycle `status`, and `verdict` fields. It may report
whether those literal fields authorize the declared node status. It does **not**
license the conclusion that evidence labelled `external` is adequate, correct,
or sufficient to prove the node genuinely done. Those are semantic judgments
for the runner.

The same boundary applies to R5's 21-field contract: presence is not
sufficiency. R5 inspects required-key presence only; whether a field's content is
adequate is a semantic judgment the runner must make and record.

**`artifact_exists` is the weakest external observation.** It is genuinely
external — a filesystem observation, not model opinion — so it satisfies the
authorization rule above. But it proves only that a path exists, never that its
contents are adequate, relevant, or even non-empty. That makes it the cheapest
way to close a node dishonestly: write a file, observe the file, mark
`completed`. Nothing in this vocabulary prevents that, and no validator can,
because "is this artifact any good" is exactly the semantic question programs
may not answer.

The runner therefore owes a judgment the validator cannot make: for a node whose
work is substantive, `artifact_exists` alone is not sufficient authorization —
pair it with a gate that inspects content (`test`, `automated_check`) or with
`human_approval`. Reserve `artifact_exists` as sole authorization for nodes whose
`done_when` genuinely IS "the artifact exists". If you find yourself reaching for
it to unblock a node you could not otherwise close, that is the signal the node
is not actually done.

### 4.2 Why judged scores have no threshold validator (R46 tombstone)

No validator enforces `score >= threshold` for a judged gate. An `llm_judge`
score is model opinion against a rubric; arithmetic does not convert that opinion
into a measurement or give it deterministic authority over completion. The
score and threshold remain context for the runner's semantic review, not a
machine completion rule.

Judged gates gain assurance through the provenance axis in §4: record where the
verdict came from and apply the authorization rule for that declared provenance.
This checks who produced a verdict, not whether the verdict is right. `R46` was
allocated to the rejected threshold check and withdrawn; it is a permanent
tombstone, has no fixture, and must never be reused.

---

## 5. Reinforcing patterns

Two patterns are not gates themselves but reinforce specific gate
choices:

- **Reflexion** ([Shinn et al. 2023, arXiv 2303.11366](https://arxiv.org/abs/2303.11366))
  is a "verbal self-reflection after failure" loop. It is typically
  implemented as an `evaluator_optimizer` subgraph where the
  reflection text feeds the next generation pass. A node that
  combines Reflexion-style reflection with an `evaluator_optimizer`
  gate can lift its pass rate substantially on HumanEval-class tasks.

- **CodeAct** ([`./research_dags_multiagent.md` §3.7](./research_dags_multiagent.md))
  collapses multi-tool sequences into a single sandboxed Python
  program. When the node's output is code or test execution, the
  strongest gate is `test` against a CodeAct-written program, not
  `llm_judge` on the program's prose explanation.

Both patterns are referenced from
[`concepts.md` §5](./concepts.md#5-why-evidence-gates) and appear in
the cost / strength discussion above.

---

## 6. Choosing a gate kind

The default heuristic, in order of preference:

1. **Prefer deterministic gates.** `test`, `automated_check`, and
   `artifact_exists` are cheaper and stronger than any LLM-based gate.
   If a deterministic validator exists, use it.
2. **Use `step_verifier` for multi-step reasoning.** When the node
   produces a chain of intermediate steps whose correctness matters,
   per-step verification catches failures that an end-of-output
   `llm_judge` would miss.
3. **Use `llm_judge` only when no deterministic check fits.** Writing
   quality, design taste, plan feasibility. Always pair with a rubric
   and the bias mitigations in §3.4.
4. **Use `self_consistency` when calibration matters as much as the
   answer.** Math, classification, structured extraction where
   uncertainty is itself the signal.
5. **Use `evaluator_optimizer` for open-ended generation that benefits
   from iteration.** Drafts, designs, plans.
6. **Use `human_approval` for irreversible or judgemental nodes.**
   Anything that should not auto-proceed without a human eye.

For the high-risk scored-gate, threshold, and verifier-independence
requirements, see [§1.1](#11-generatorverifier-separation).

---

## 7. The non-trivial-node rule

Every node in the plan carries a `gate` field
([`loop_plan_spec.md` §2](./loop_plan_spec.md#2-node-object)). A `gate`
of `null` is permitted only for nodes whose entire purpose is a trivial
mechanical edit. The exemption whitelist mirrors the TDD exemption
whitelist:

- **Pure formatting**: whitespace, line endings, import ordering, sort
  order, case-only renames. No semantic content changes.
- **Comment-only edits**: doc comments, header comments, inline
  explanations. No executable code change.
- **Rename-only**: identifier renames where the rename tool verified
  that no other reference resolves the old name. Static-analysis
  verified.
- **Lockfile regeneration**: dependency lockfiles produced by a pinned
  tool whose diff is mechanical.
- **Trivial scaffolding**: empty stubs whose content is filled in by a
  downstream node.

Anything outside the whitelist carries a `gate`, even if that gate is
just `artifact_exists`. The reason: a node without a `gate` cannot
fail cleanly, and a node that cannot fail cleanly cannot be retried,
replanned, or escalated. The exemption whitelist is small on purpose.

A node in a `subgraph` is held to the same rule — subgraphs do not get
to relax evidence requirements — but a lightweight subgraph records its
evidence through its own compact shape rather than a full `gate` object:

- A subgraph-local node cannot reach `status: completed` with a null
  `output`; the `output` artifact path IS its evidence (enforced by
  rule **R25**).
- A subgraph whose own `status` is `completed` MUST carry a
  `completion_gate.pass_condition` recording how completion was verified
  (also R25).

So the guarantee "evidence, not the agent, says done" holds at both the
node and the subgraph tier; only the recording mechanism is lighter. See
[`subgraph_subloop_policy.md` §8](./subgraph_subloop_policy.md#8-subgraph-control-fields).

---

## 8. Verdict recording

When a gate evaluates, the runner appends one entry to the
[`evidence.ledger`](./state_model.md#evidence-ledger):

| field | value |
|-------|-------|
| `node_id` | the node under evaluation |
| `gate_kind` | one of the eight kinds |
| `verdict` | `pass`, `fail`, or `inconclusive` |
| `score` | numeric 0..1 for scored gates, `null` for pass/fail gates |
| `artifact_path` | the path the evidence was written to |
| `rationale` | a string explaining why the verdict was reached |
| `verifier` | who graded: `agent`, `subagent`, `user`, or `script` |
| `assurance` | verdict provenance: `external`, `blind`, or `self_attested` |
| `success_criteria_id` | optional citation to a `loop.plan.success_criteria[].id` |
| `overrides_entry_id` | optional `entry_id` of a prior verdict this entry overrides |
| `recorded` | ISO-8601 timestamp |
| `entry_id` | a unique id for the ledger entry |

The next state transition reads the **latest** entry for the node.
Multiple entries per node are allowed and expected: each retry writes
a new entry; each evaluator-optimizer iteration writes a new entry;
cache hits cite the prior entry's `entry_id`. Entries are append-only;
corrections are new entries that record the supersession.

When `success_criteria_id` is present, R45 deterministically checks whether the
cited criterion id exists in the plan. This is reference validity only: a
resolving citation does not license the conclusion that the criterion is
satisfied, met, or demonstrated by the evidence. The field remains optional;
the validator neither requires every entry to cite a criterion nor infers
coverage from citation presence.

---

## 9. Filesystem realisation

| gate kind | artifact path (relative to `runs/<run-id>/`) |
|-----------|---------------------------------------------|
| `artifact_exists` | the produced artifact itself |
| `automated_check` | `evidence/<node-id>/check.json` |
| `test` | `evidence/<node-id>/test_report.json` |
| `llm_judge` | `evidence/<node-id>/verdict.json` (includes `score`, `rationale`, `rubric_breakdown`) |
| `self_consistency` | `evidence/<node-id>/samples/<i>.json` plus `evidence/<node-id>/aggregate.json` |
| `evaluator_optimizer` | `evidence/<node-id>/iter_<N>/draft.json` and `feedback.json` |
| `step_verifier` | `evidence/<node-id>/steps/<i>.json` plus `evidence/<node-id>/aggregate.json` |
| `human_approval` | `evidence/<node-id>/human_verdict.json`, `pending_approvals` entry |

The `verifier` recorded in the ledger maps to who actually graded:
`script` for `automated_check`/`test`/`artifact_exists`,
`agent`/`subagent`/`user` for the LLM-and-human gates.

---

## See also

- [`concepts.md` §5](./concepts.md#5-why-evidence-gates) gives the
  rationale for the gate protocol.
- [`loop_plan_spec.md` §4](./loop_plan_spec.md#4-evidence-gates) defines the
  the gate object and the canonical list of eight kinds.
- [`loop_plan_spec.md` §4.2`](./loop_plan_spec.md#42-gate-kinds) lists
  the gate-kind table with scored-or-not flags and source citations.
- [`state_model.md` §evidence-ledger](./state_model.md#evidence-ledger)
  defines the verdict-recording schema.
- [`state_model.md` §state-transition-table](./state_model.md#state-transition-table)
  shows how a verdict drives the `verifying → completed` /
  `verification_failed` transition.
- [`recovery_protocol.md`](./recovery_protocol.md) explains what happens
  when gates fail: the escalation ladder, retry budget, and replan.
- [`./research_dags_multiagent.md`](./research_dags_multiagent.md) covers
  LLM-as-judge, self-consistency, Reflexion, evaluator-optimizer, PRMs,
  CodeAct sources.
