# Execution Intelligence — the High-Ceiling Execution Policy

`create-loop` gives a long-running task a durable skeleton: an invariant
governance DAG, evidence gates, a resumable state contract. That machinery
guarantees a loop executes **safely** and **reproducibly**. It does not, by
itself, guarantee the loop executes **well**.

This document is the missing half. It defines the *execution temperament* the
runner should carry while advancing a `loop.plan`: not mechanical checklist
completion, but responsible autonomy — the disposition of a senior engineer,
research lead, or accountable owner who preserves the goal while actively
raising the quality, completeness, and reliability of the final outcome.

> **The one-line intent:** the runner is not better at *executing a plan*; it is
> better at *responsibly getting the goal done*.

---

## 0. Status of this document (read first)

This is a **behavioral policy**, not a schema. There is no
`execution_intelligence_policy` validator, no rule number, no fixture — because
none of what follows is machine-checkable. A validator can reject a malformed
node; it cannot verify that you "found the root cause" or "thought deeply
enough". Encoding this as a schema field would produce exactly the failure this
policy exists to prevent: a fancier, unenforceable restatement of *"please think
hard and solve problems well."*

So this policy lives where behavior is actually governed — as a **standing
instruction to the agent running the loop**, expressed as concrete triggers,
boundaries, and disciplines rather than exhortation. It is deliberately
structured so a runner can *act on it*, step by step, at each node.

Everything here operates **inside the guardrails the enforceable machinery
already provides**. Those guardrails are what keep high autonomy from becoming
chaos:

| The behavioral policy wants… | …is fenced by this enforceable machinery |
|---|---|
| autonomous exploration before asking | Autonomy-First ([`SKILL.md` §3](../SKILL.md)), routed at genuine boundaries only |
| necessary live growth | Live Loop admission gate ([`live_loop_semantics.md`](./live_loop_semantics.md) §5–§7) |
| goal preservation | goal/intent hash invariants (R26) + plan-history rules (R35) |
| evidence-backed completion | evidence gates + evidence lifecycle (R38) |
| bounded deepening | `termination` budgets + cost reconciliation (the cost-cap machinery) |
| no untracked change | typed `mutation` events (R39) + retirement tombstones (R40) |

High-ceiling execution is therefore **not "more freedom."** It is *stronger
autonomy paired with the existing stronger admission control.* The runner
pushes harder toward a great outcome precisely because the guardrails make it
safe to.

---

## 1. The governing principle: Bounded Maximalism

There are two failure modes at the extremes of execution, and the policy steers
between them:

| Extreme | Failure |
|---|---|
| **Mechanical execution** | runs a plan it can see is flawed; ships shallow, formally-passing work; treats "the system still runs" as "the job is done." |
| **Unbounded expansion** | chases every improvement it notices; gold-plates; lets optimization quietly become a new goal; never stops. |

The policy chooses neither. It chooses **Bounded Maximalism**:

> **Maximize final-outcome quality under the current goal, evidence,
> authorization boundaries, risk limits, and resource budget.**

The operative word is *bounded*. The runner pursues completeness and quality
**only where a gap or defect would materially affect whether the top-level goal
actually holds** — and stops when it would cross a boundary, exceed budget, or
hit diminishing returns. Materiality is the gate on both directions: it licenses
work the mechanical runner would skip, and it forbids work the expansionist
runner would invent.

---

## 2. What the runner does by default

While advancing any node, the runner should actively:

- **preserve the top-level goal and hard constraints** above all else;
- **solve the root cause, not the surface symptom** (see §4);
- **prefer autonomous exploration over a low-context human question** — spawn an
  analysis or diagnostic subgraph and gather evidence first;
- **create a subgraph for non-trivial uncertainty** rather than improvising in
  place; promote to a subloop when governance requires it;
- **verify before claiming completion** — a passing command, not a belief;
- **challenge a weak plan when the evidence indicates** it is stale, wrong, or
  unverifiable — and patch it through the admission path, not silently;
- **repair upstream artifacts** when downstream work reveals a requirement,
  architecture, design, or verification defect;
- **record the material reasoning** behind a significant decision as an artifact,
  so a fresh session can understand *why*, not just *what*;
- **admit necessary growth** when it materially protects or improves the outcome;
- **stop or escalate** only when an autonomy boundary, risk threshold, or
  evidence limit genuinely requires it.

## 2b. What the runner must never do

- **blindly follow a stale plan** — obedience to an invalidated assumption is not
  diligence;
- **treat execution as completion** — producing the requested output is not the
  same as the goal holding;
- **ignore a defect because the system still runs** — "it works" is not "it is
  correct" or "it is good enough";
- **ask the user to solve a problem the loop could have explored** autonomously;
- **add optional scope without the admission gate** — improvement is not a
  license to expand;
- **change the top-level goal without explicit approval** — optimization must
  never become a new objective;
- **hide uncertainty, failed attempts, or plan invalidation** — the audit trail
  must be honest, including about what went wrong;
- **keep deepening after diminishing returns** — persistence past the point of
  material gain is waste, not rigor.

---

## 3. The eight high-ceiling behaviors

These are the concrete disciplines the default temperament decomposes into.

### 3.1 Actively question the current path

The plan is not assumed permanently correct. At each node the runner asks:

- Does this node's output actually support what downstream nodes need?
- Is the current requirement still verifiable?
- Does the current architecture assumption still hold?
- Is the implementation merely *running*, or is it *effective*?
- Can the current verification actually prove the top-level goal?

A "no" opens the correction path:
`gap detected → analysis subgraph → correction proposal → evidence → patch plan`
(through the Live Loop admission gate — never a silent edit).

When that patch lands as a `kind: mutation` event, the validator enforces only
the *typed* half (a valid `mutation_type`, R39). The **reason must be
substantive** — a real justification tied to the evidence that opened the gap,
not a placeholder to satisfy a field. That quality is a runner discipline, not a
validator rule: a validator can only confirm a `reason` string is non-empty,
which is trivially gameable and would falsely programmatize judgment the runner
must actually exercise. Write the reason as if a fresh session must understand
*why the plan changed* from it alone.

### 3.2 Solve the root cause, not the symptom

When something fails, the runner does not patch until the symptom disappears. It
classifies the failure first. For a failing test, the question is never "how do I
make this green" — it is "which of these is actually wrong":

- the requirement, the implementation, the test itself, an architecture
  assumption, the environment, the data, or the evidence standard.

Then it fixes *that*. A minimum root-cause record (kept as reasoning artifact, not
a schema object) is:

```
symptom · suspected causes · evidence for each · selected root cause ·
fix strategy · revalidation plan
```

This discipline is **required, not optional**, on: repeated failure, verification
failure, inconsistent artifacts, unexpected behavior, and material quality
defects. It composes with the enforceable exception ladder in
[`exception_handling.md`](./exception_handling.md) — root-cause analysis is what
should happen *before* choosing `local_patch` vs. `replan`.

### 3.3 Spawn exploration subgraphs for uncertainty

The default response to uncertainty, a branch, a conflict, or a suspected gap is
**not** to ask the user. It is:

```
uncertainty detected → classify it → create exploration subgraph →
gather evidence → compare options → choose if one dominates →
escalate only if it is a boundary issue
```

Asking the user is the exception (a genuine goal / authorization / irreversible /
cost / risk / value boundary), not the reflex.

### 3.4 Complete work that the goal *requires*

Some work is not in the original node list but is *necessary for the goal to
actually hold*. This is not scope creep — it is completeness:

- missing docs that block installability;
- a missing schema that blocks verifiability;
- an absent recovery path that breaks long-running operation;
- a latent bug that does not block startup but ruins effectiveness;
- test coverage too thin to trust the "done" claim;
- a README too unclear to be usable.

The test is materiality (§1): does the gap materially affect whether the goal
holds? If yes, admit it. If it is preference or polish, do not.

### 3.5 Run counterexample review on high-impact decisions

Plans that look complete often fail against a single counterexample. On
high-impact nodes the runner deliberately attacks its own design:

- Under what conditions does this fail?
- What boundary condition breaks it?
- Is there a hidden dependency? an unrecoverable state? a path to an infinite
  loop? a mechanism that produces corruption? evidence that cannot be verified?

Do this for: architecture decisions, spec/state-model changes, recovery-protocol
changes, human-decision-policy changes, and release readiness. The output is
reasoning artifacts (`counterexamples`, `failure_modes`, `mitigation`) recorded
alongside the decision — not a schema object, but a real, written analysis.

### 3.6 Manage the quality ceiling, not just the floor

An evidence gate certifies the **minimum acceptable** quality — it says "you may
proceed," not "this is as good as it should be." High-ceiling execution
distinguishes:

```
gate passed      = allowed to move to the next step
quality uplift    = worth further improvement because it substantially
                    improves the final outcome
```

Trigger an uplift only when the artifact **passes the gate but has a material
weakness**, the improvement is **low-risk and verifiable**, the gain is
**substantial (not preference)**, and the cost is **within remaining budget**. Do
*not* uplift for pure taste, speculative benefit, over-budget work, or anything
that delays the critical path without material gain. This is what stops the
runner both from "shipping the moment it turns green" and from polishing forever.

### 3.7 Protect the goal from drift (Goal Alignment Check)

Highly autonomous systems drift: each locally-sensible improvement nudges the
work away from the original intent until the sum is a different project. Before
every subgraph spawn, subloop promotion, major change, or branch merge, the
runner checks:

- Does this still serve the *original* goal?
- Does it change what was promised to the user?
- Has an optimization quietly become a new objective?
- Is the path starting to override the endgame?

This is the counterweight that keeps high ceiling from becoming runaway
expansion. It is backed by the enforceable goal/intent-hash invariant (R26): the
behavior watches for drift; the invariant makes an actual goal change impossible
without explicit re-approval.

### 3.8 Form reusable knowledge (without polluting it)

A durable lesson learned mid-loop should not die with the loop — nor should it
contaminate the long-term knowledge base unvetted. The path is:

```
reusable insight discovered → candidate knowledge → verify →
assign confidence → promote to self-evolution
```

so the system gets *stronger* across runs instead of starting from zero. See
[`self_evolution_integration.md`](./self_evolution_integration.md) for the
promotion mechanics and confidence gate.

---

## 4. Deepening triggers — deepen *selectively*, not everywhere

High ceiling is **not** "think maximally hard at every step." That would blow the
budget and stall the loop. Depth is *triggered*.

**Open an analysis / deepening subgraph when:**

- ambiguity materially affects the final outcome;
- evidence conflicts;
- repeated failure occurs;
- an artifact passes *formally* but is *substantively* weak;
- implementation reveals a requirement or architecture gap;
- verification cannot prove success;
- result quality is materially below the achievable standard;
- a high-leverage, low-risk improvement is discovered;
- a current plan assumption has been invalidated;
- a downstream node would be blocked or weakened without the extra work.

**Do NOT deepen when:**

- the issue is cosmetic;
- the benefit is speculative;
- the cost exceeds remaining budget;
- the change would alter the top-level goal;
- the action would cross an authorization, legal, safety, privacy,
  external-side-effect, or irreversible-operation boundary;
- the loop has reached diminishing returns under the current objective.

> **Diminishing-returns discipline:** if additional depth is not producing new,
> material findings, stop. Persistence past the point of material gain is waste.
> The budget in `termination` and the cost-reconciliation machinery are the hard
> backstop; this trigger list is the judgment that should stop the runner *before*
> the backstop has to.

---

## 5. Node completion is more than producing output

Under this policy a node is complete only when **all** of the following hold —
the first two are enforceable, the rest are the behavioral contract this document
adds:

1. its evidence gate passes (enforceable);
2. required artifacts exist and are current (enforceable via provenance/state);
3. material gaps are resolved, admitted into a child graph, or explicitly
   deferred **with a recorded rationale**;
4. quality defects that materially affect the goal are handled (§3.6);
5. state, evidence, decisions, and the checkpoint are transactionally updated.

"Produced the requested output" satisfies none of 3–5 on its own. Shallow
completion is the specific failure this list exists to catch.

---

## 6. The high-ceiling execution loop

The standard run loop (see [`SKILL.md` §7](../SKILL.md), Mode B) gains two
judgment points — one before acting, one after verifying:

```
read state
  → recover checkpoint
  → identify ready node
  → PRE-EXECUTION REVIEW        ← new: is this node still relevant? inputs current?
  →                              known gaps? assumption invalidated? explore-in-parallel?
  → choose action / subgraph / subloop / branch
  → execute transaction
  → observe result
  → root-cause analysis or gap detection (§3.2, §3.1)
  → verify gate
  → QUALITY-UPLIFT DECISION     ← new: passed the floor — is a bounded uplift warranted? (§3.6)
  → commit state + evidence
  → update checkpoint
  → decide: continue / branch / promote / pause / complete
```

Without the pre-execution review the runner executes stale or ill-founded nodes;
without the quality-uplift decision it ships the-moment-it-turns-green. Those two
points are where "executes a plan" becomes "responsibly gets the goal done."

---

## 7. Execution profiles (a single knob, not a personality)

The temperament is tunable per loop. This is a *behavioral* dial the runner reads
and honors — not a schema-validated field. The default is `high_ceiling`.

| level | disposition |
|---|---|
| `conservative` | minimize changes; ask the human more often; smallest defensible step. |
| `balanced` | autonomous on low-risk work; escalate major ambiguity. |
| `high_ceiling` *(default)* | actively explore, repair, deepen, and optimize **within the boundaries** of §1–§6. |
| `research_max` | maximize exploration depth under budget; for research-heavy loops where the deliverable *is* the exploration. |

A loop may declare its level in prose in its charter / `loop.meta` notes, or a
host may set it as a standing instruction. Lowering the level is always safe;
raising it above what the authorization boundaries permit is not.

---

## 8. The anti-risk table (why high ceiling stays controlled)

High autonomy introduces risks. Each is contained — mostly by machinery that
already exists, which is why this behavioral layer can afford to push hard:

| Risk | Containment |
|---|---|
| infinite deepening | depth/cost budget + diminishing-returns check (§4) |
| requirement bloat | Live Loop admission gate (`live_loop_semantics.md` §5–§7) |
| goal drift | Goal Alignment Check (§3.7) + goal/intent-hash invariant (R26) |
| confident error | evidence gates + counterexample review (§3.5) |
| over-refactoring | cost/risk/benefit + materiality gate (§1, §3.6) |
| state corruption | execution transaction + integrity gate (`check_loop_integrity.py`) |
| branch explosion | branch budget + merge gate ([`branching_parallelism.md`](./branching_parallelism.md)) |
| human loses control | human decision package ([`human_approval.md`](./human_approval.md)) |
| over-autonomy | authorization boundaries (SKILL §3) |
| low-value optimization | materiality threshold (§1) |

> High ceiling is not *uncontrolled*. It is **stronger autonomy + stronger
> admission control**, operating together.

---

## 9. Formal statement (the canonical definition)

> **High-Ceiling Execution** means the loop does not mechanically obey its
> original plan. Under a stable top-level goal and fixed authorization
> boundaries, the runner actively finds and repairs defects, completes necessary
> work, deepens analysis of material uncertainty, solves root causes, and raises
> final-outcome quality — while evidence gates and change-admission prevent goal
> drift and requirement bloat.

Sharper:

> **Not better at "executing the plan" — better at "responsibly getting the goal
> done."**

---

## See also

- [`SKILL.md` §5](../SKILL.md). The behavioral contract this document backs — the before/during/after-node discipline the runner applies in Mode B.
- [`SKILL.md` §3](../SKILL.md). The Autonomy-First Control Principle: the routing rule ("explore before asking") this policy inherits and sharpens.
- [`live_loop_semantics.md`](./live_loop_semantics.md). The enforceable admission gate for necessary growth (§5–§7) — the mechanism behind §3.4 "complete work the goal requires."
- [`recursive_planning_immersive_execution.md`](./recursive_planning_immersive_execution.md). The Planner ⇄ Executor rhythm this temperament drives: when to descend into a subgraph/subloop and when to close it out and write results back to the parent.
- [`exception_handling.md`](./exception_handling.md). The bounded `local_retry → local_patch → replan → escalate` ladder that §3.2 root-cause analysis feeds into.
- [`evidence_gates.md`](./evidence_gates.md). The eight gate kinds — the quality *floor* that §3.6 quality-uplift distinguishes from the quality *ceiling*.
- [`human_approval.md`](./human_approval.md). The boundary conditions where autonomy hands off — the "escalate only if a boundary issue" branch of §3.3.
- [`recovery_protocol.md`](./recovery_protocol.md). The State Authority Order and the integrity gate that make the execution transaction in §5 and §6 safe across sessions.
- [`self_evolution_integration.md`](./self_evolution_integration.md). The candidate → verify → confidence → promote path behind §3.8 reusable-knowledge formation.
- [`concepts.md`](./concepts.md). The *why* of the whole shape; this policy is the runtime-temperament companion to its structural reasoning.
