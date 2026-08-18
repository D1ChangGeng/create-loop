# Parallel Development Protocol — Split, Isolate, Merge, Converge

*Diataxis type: **reference + how-to**. This document defines the reusable,
host-conditional discipline for running more than one unit of concurrent code
development at once: the six-phase split → isolate → execute → verify → merge →
converge arc, git-worktree-per-unit isolation, the capability-detection fallback
table, the owner-gate on publish, and the rollback ladder. It is a behavioral
protocol — it adds no schema field, rule, or status, reusing the existing
machinery by reference.*

When a loop opens more than one unit of *code development* at once — parallel
actions, sibling subgraphs, concurrent sub-loops, or a multi-role team — it must
not improvise. Ad-hoc parallelism is how a run ends up with two agents fighting
over one working tree, half-merged branches, and a state that no fresh session
can trust. This protocol is the reusable, host-conditional discipline for doing
it safely: **split** into independent units, **isolate** each in its own git
worktree, **execute** with a bounded fan-out, **verify** each against its gate,
**merge** through a non-mutating pre-flight, and **converge** — including a
defined rollback ladder when a unit fails.

> This is a **behavioral protocol**, not a schema. There is no
> `parallel` validator, no rule number, no fixture — because nothing here is
> machine-decidable from a plan document. "Are these two units truly
> independent?" and "is this merge safe to apply?" are runner and owner
> judgments; encoding them as validator rules would only fake the judgment the
> runner must actually exercise (the same reason the mutation-`reason` check was
> removed — see [`execution_intelligence_policy.md` §0](./execution_intelligence_policy.md)).
> The one genuinely structural contract — two sibling units must not both claim
> the same produced artifact — is already enforced by the artifact-authority rule
> (R41) and the isolation rule in
> [`branching_parallelism.md` §7.2](./branching_parallelism.md#72-avoiding-two-writers-on-the-same-artifact).

## 0. Scope — and what this is NOT

This protocol governs **concurrent code development**: units that edit files and
produce commits in parallel. That is distinct from the *scratch-directory
isolation* for read-mostly exploration subagents already specified in
[`branching_parallelism.md` §7](./branching_parallelism.md#7-context-isolation-between-parallel-subagents).
Exploration subagents write to per-branch scratch dirs and never touch the git
working tree; code-development units each need a real git **worktree** so their
edits, index, and commits cannot collide.

This protocol does **not**:

- build an orchestration engine or scheduler — the `.agents/loops/…` tree, the
  event log, and the checkpoint *are* the runtime; a host that offers real
  concurrency is used when present, else execution is sequential;
- automate `push` / `merge` / PR — those are owner-gated (§9);
- add a schema field or validator rule — it reuses the existing machinery;
- introduce a new status — it reuses the 15 node and 8 subgraph statuses from
  [`state_model.md`](./state_model.md#node-status-enum);
- duplicate the fan-out cap, join/reducer semantics, or cost bounds — those live
  in [`branching_parallelism.md`](./branching_parallelism.md) and are referenced,
  not restated.

## 1. The six-phase arc

```
SPLIT     → partition the work into independent units (one unit = one branch = one worktree)
ISOLATE   → give each unit its own git worktree over the shared object store
EXECUTE   → dispatch with a bounded fan-out; each unit is a subloop or a claimed node
VERIFY    → each unit passes its own evidence gate before it may converge
MERGE     → non-mutating conflict pre-flight, then integrate in a chosen order
CONVERGE  → aggregate, tag an anchor, and on failure walk the rollback ladder
```

Each phase has a clear entry condition and hands a defined artifact to the next.
The arc is the same whether the units are sibling subgraphs in one session or
directory-materialized child loops driven by a team.

## 2. SPLIT — independent unit boundaries

A unit is admitted to parallel development only when it passes the independence
test already defined in
[`branching_parallelism.md` §3.1](./branching_parallelism.md#31-the-three-checks)
and [§4.1](./branching_parallelism.md#41-the-three-part-rule): no shared mutable
state, no shared produced artifact, and no dependency edge between the units.
Whether that test passes is a **runner judgment**, informed by the
[High-Ceiling Execution](./execution_intelligence_policy.md) temperament — not a
validator check.

Each admitted unit gets:

- a **unit id** — its node id, or a child-loop id
  (`L<seq>.<local>-<slug>`, see
  [`recursive_loops.md` §3.3](./recursive_loops.md#33-loop-id-rule-locked));
- a **branch**, named `loop/<unit-id>` (or the host's convention, e.g. OpenCode's
  `opencode/<name>`) — one branch per unit, never shared;
- an **owner lease** — a [`claim.yaml`](../templates/claim.yaml) claim so a
  `running` unit is single-flight (see
  [`state_model.md` → Per-node claim/lease](./state_model.md#per-node-claimlease));
- an **artifact authority** — every file the unit produces is registered in the
  [`artifacts/INDEX.yaml`](../templates/artifact.index.yaml) registry so exactly
  one authoritative version per path survives convergence (rule R41).

A non-trivial unit is best modelled as a **directory-materialized child loop**
([`recursive_loops.md`](./recursive_loops.md)): it already has its own directory,
plan, checkpoint, evidence ledger, and `closeout.md` — which is exactly a
parallel sub-loop with an isolated workspace and a return contract. Lightweight
units stay inline `subgraph`s per
[`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md).

## 3. ISOLATE — one git worktree per unit

The isolation primitive is **`git worktree`**, not multiple clones and not a
shared checkout. A repository supports one main worktree plus N linked worktrees
that share a single `.git` object/ref store but each hold their own `HEAD`,
`index`, and `MERGE_HEAD`.

```bash
# one worktree per unit, branched from the integration base
git worktree add -b loop/<unit-id> <loops-dir>/<unit-id>/worktree <base>
```

Why this and nothing else:

- **Two writers on one index corrupt it.** Git guards the index with
  `index.lock` (`O_CREAT|O_EXCL`); a second writer is *rejected*, not queued — a
  fail-fast, not a mutex. A shared checkout across two units therefore races and
  breaks. A worktree gives each unit its own `index`, `HEAD`, and merge state, so
  their edits cannot collide.
- **The object store is shared and safe.** Objects are content-addressed
  (append-only); ref updates go through per-ref lockfiles atomically. So N
  worktrees over one `.git` never lose each other's commits.
- **One branch per worktree.** Git refuses to check the same branch out in two
  worktrees — which is the invariant we want: one unit, one branch, one tree.

Cleanup is explicit: `git worktree remove --force <dir>` then
`git branch -D loop/<unit-id>` (or keep the branch for audit). A wrecked unit is
dropped by removing its worktree, never by mutating a sibling's.

This is the code-development counterpart to the scratch-dir rule in
[`branching_parallelism.md` §7.1](./branching_parallelism.md#71-where-each-subagent-writes):
scratch dirs isolate *notes*; worktrees isolate *the working tree and index*.

## 4. Capability detection and the graceful fallback

There is **no cross-agent standard** for parallel spawn / isolation / merge (MCP
is for tools, A2A for messaging). So the protocol is **host-conditional**: detect
what the host provides, and fall back to a filesystem lowest-common-denominator
when it does not. Never claim a capability the host lacks — this is the parallel
extension of the degradation table in `SKILL.md` §13.

| Capability | If the host provides it | Fallback |
|---|---|---|
| worktree management | host worktree API (e.g. OpenCode `Worktree.create()` → branch `opencode/<name>`) | the agent runs `git worktree add` itself via the shell |
| concurrent subagents | host spawn with a parallel fan-out (e.g. a `task`-style tool; a 3–5 or 5-slot cap) | **sequential execution** — units run one at a time |
| background / async | host background tasks that auto-return results | run synchronously and accept the latency |
| shared task list | host tasklist with atomic claims | a JSONL manifest under a file lock (`flock`) |
| mailbox | host message bus | `inbox/`/`outbox/` `*.md` files per unit |
| auto result aggregation | host injects a unit's result into the parent | read each unit's `closeout.md` / status file after it exits |

The LCD — **sequential execution + worktree (or sibling-dir) isolation + a JSONL
manifest under a file lock + a manual merge** — is the pattern Anthropic's
multi-agent system recommends ("subagent output to a filesystem to minimise the
game of telephone") and it works against a bare shell. Real throughput is a
*bonus the host may grant*, never a correctness assumption.

## 5. EXECUTE — bounded fan-out, isolated context

Dispatch follows the orchestrator-worker shape already specified in
[`branching_parallelism.md` §4`](./branching_parallelism.md#4-parallelise-only-if-truly-independent):
a bounded fan-out (the §4.2 cap — 3–5 is the well-attested sweet spot), each unit
with **isolated context** (only its own worktree + inputs), and cost charged
against `termination.max_cost_units`
([§8](./branching_parallelism.md#8-concurrency-limits-and-cost-bounds)). The
orchestrator holds the integration branch; workers never see each other's trees.
Each unit outputs to the filesystem (its worktree + `closeout.md`) and returns a
lightweight reference, not a narrative — minimising context bleed. Deepen or
widen the fan-out only under the [deepening triggers](./execution_intelligence_policy.md#4-deepening-triggers--deepen-selectively-not-everywhere);
collapse to serial when the collapse signal fires
([§4.3](./branching_parallelism.md#43-the-collapse-signal)).

## 6. VERIFY — each unit passes its own gate before it may converge

A unit is eligible for merge **only** when it has reached `completed` through its
own evidence gate — a passing, `active` ledger entry per
[`evidence_gates.md`](./evidence_gates.md) and the evidence-lifecycle rule (R38).
An unverified unit never enters the merge queue; a unit whose gate fails goes to
`verification_failed` and runs the exception ladder in its own worktree, in
isolation, without blocking its siblings.

## 7. MERGE — non-mutating pre-flight, then ordered integration

Convergence is gated by a **non-mutating conflict pre-flight** so the integration
tree is never left half-merged:

```bash
# exit 0 = clean, exit 1 = conflict; does NOT touch the working tree or index
git merge-tree --write-tree <integration-branch> loop/<unit-id>
```

Only a unit that (a) is `completed` (§6) and (b) pre-flights clean against the
current integration tip is integrated. The integration order is chosen to land
independent units first and defer likely-conflicting ones; when several units
pre-flight clean against each other they may be integrated together, otherwise
one at a time on a dedicated integration worktree. Whether an ambiguous merge is
*safe to apply* is an **owner/runner judgment**, never an automated decision — a
conflicting unit is surfaced, not force-merged. The join/reducer semantics for
combining sibling outputs are already specified in
[`branching_parallelism.md` §5](./branching_parallelism.md#5-join-and-merge-semantics)
and are reused here.

Record the whole convergence event in the
[`parallel_convergence_plan.md`](../templates/parallel_convergence_plan.md)
template: the unit inventory, each pre-flight verdict, the integration order, the
tag anchor (§8), and the aggregate-verify result.

## 8. CONVERGE — aggregate, anchor, and the rollback ladder

Before each risky integration, drop an **annotated tag** as a rollback anchor:

```bash
git tag -a integration/<checkpoint> <integration-branch> -m "pre-<unit-id>"
```

After integrating, run the **aggregate verification** — the integration branch as
a whole must still pass the loop's success criteria, not merely each unit in
isolation (a set of individually-green units can still be jointly wrong). If it
does, advance; if not, walk the **rollback ladder**, cheapest first:

1. `git reset --hard integration/<checkpoint>` — undo on a private integration
   branch (nothing has been published);
2. `git revert -m 1 <bad-merge-sha>` — forward-only undo when the merge was
   already pushed/shared (never rewrite published history);
3. `git reset --hard <branch>@{1}` — recover via reflog when the anchor was lost;
4. `git worktree remove --force <dir>` + `git worktree prune` — discard a wrecked
   unit's tree entirely.

Conflict, failure, blocked, and rollback are **exceptions**, handled by the
taxonomy and bounded ladder in
[`exception_handling.md`](./exception_handling.md#2-the-exception-taxonomy) — a
merge conflict is an `inconsistent_result`, a stuck unit is `no_progress`, and
each maps to the ladder (`local_retry → local_patch → replan → escalate`) and to
a node status (`blocked`, `verification_failed`) with recovery per
[`recovery_protocol.md`](./recovery_protocol.md).

## 9. OWNER-GATE — commit is autonomous, publish is not

The boundary is sharp and reuses the existing authority machinery
([`human_approval.md`](./human_approval.md)):

- **Autonomous:** create a worktree, commit to the unit's *local* branch, run the
  unit's gate, and pre-flight a merge. These are reversible and local.
- **Owner-only:** `git push`, `git merge` into the shared/integration branch that
  will be published, and PR creation. These cross the §3 Autonomy boundary
  (external side effect / irreversible / shared visibility) and require an
  approved decision — surfaced as a
  [Human Decision Package](../templates/human_decision_request.md), not a bare
  question.

On a host with permission control (e.g. OpenCode), enforce this with
`permission.bash`:

```jsonc
{ "permission": { "bash": {
  "git worktree *": "allow",
  "git commit *":   "allow",
  "git push *":     "deny",
  "git merge *":    "deny"
} } }
```

so a unit can develop and commit on its branch but cannot publish or merge; the
owner performs `push`/`merge` as a separate, gated step.

## 10. Multi-role / team development

When several roles develop in parallel, each role is a unit under this protocol:
its own worktree, branch, lease, and gate. Cross-role coordination uses the
handoff schema in
[`human_approval.md` §5](./human_approval.md#5-the-handoff-schema-cross-session--cross-agent)
— `{summary, findings, confidence, verify_before_using}` — written to a
[`handoff.md`](../templates/handoff.md) per role. Where the host provides a team
mailbox/tasklist (e.g. an OpenCode team mode with per-member worktrees and a
JSONL mailbox under file locks), use it; where it does not, fall back to the
handoff-doc + JSONL-manifest pattern from §4. No nested teams and no shared
working tree — the isolation invariant (§3) holds for roles exactly as for nodes.

## 11. Auditability

Every parallel run reconstructs from the filesystem: the `event_log` records each
unit's dispatch/merge as `mutation` and effect events; the `decision.log`
captures the split decision and each owner-gated publish; the
`parallel_convergence_plan.md` records the pre-flight verdicts and integration
order; the annotated tags are the rollback anchors. A fresh session reading these
knows which units ran, which merged, which rolled back, and why — without any
in-memory state (the State Authority Order in
[`recovery_protocol.md` §6.0](./recovery_protocol.md#60-state-authority-order-who-to-trust-when-files-disagree)
governs conflicts among these files).

## 12. What this protocol deliberately avoids

- **No orchestration engine.** The loop tree + event log + checkpoint is the
  runtime; the host supplies concurrency or the protocol runs sequentially.
- **No faked merge-safety validator.** `git merge-tree` is a runtime pre-flight
  described here, not a plan-shape contract.
- **No new schema field or rule.** Worktree/branch are runtime conventions with
  no plan consumer; the produced-artifact collision they would guard is already
  R41 + [§7.2](./branching_parallelism.md#72-avoiding-two-writers-on-the-same-artifact).
- **No per-unit version lock.** The `claim.yaml` lease + `artifact.index.yaml`
  authority already cover ownership.
- **No auto-publish.** Push/merge/PR are owner-gated, always.

## 13. Acceptance checklist for this document

This protocol is verified — test-first — by the checks below; they are the
pass/fail contract a QA pass runs against this doc and the artifacts it touches.
Because there is no schema change (DECISION: zero rules, zero fixtures), "tests"
here are the dead-link, consistency, and no-invented-field assertions, not a new
validator.

- [ ] **Structure.** All 13 numbered sections (§0–§12) plus this checklist and a
  See-also block are present; §0 states the scratch-vs-worktree distinction and
  the NOT-build list.
- [ ] **Links resolve.** Every `](./…)` / `](../…)` target file exists and every
  `#anchor` matches a slugified heading in the target — including
  [`../templates/parallel_convergence_plan.md`](../templates/parallel_convergence_plan.md).
- [ ] **Enums verbatim.** Every status name used here (`running`, `completed`,
  `blocked`, `verification_failed`) matches
  [`state_model.md`](./state_model.md#node-status-enum) exactly — no invented
  status.
- [ ] **No invented schema field or rule.** This doc introduces no `loop.plan`
  field, no `parallel:` block, and no rule number ≥ R42; the only structural
  contract (two units, one produced path) is delegated to R41 +
  [`branching_parallelism.md` §7.2](./branching_parallelism.md#72-avoiding-two-writers-on-the-same-artifact).
- [ ] **Capability table consistent.** The §4 host-capability rows extend, and do
  not contradict, the degradation table in `SKILL.md` §13.
- [ ] **No duplication.** Fan-out cap, join/reducer, and cost bounds are
  referenced into [`branching_parallelism.md`](./branching_parallelism.md), not
  restated.
- [ ] **Zero-schema held.** `git diff --stat` shows no change under `schemas/`,
  `scripts/`, or `tests/failure_mode_tests.md`; the full-green sequence still
  prints `ALL GREEN (incl. child-loops)` and `SKILL.md` stays < 1000 lines.

---

## See also

- [`branching_parallelism.md`](./branching_parallelism.md) — the control-flow vocabularies, the serial-vs-parallel decision rule (§3), the fan-out cap and collapse signal (§4), join/reducer semantics (§5), scratch-dir context isolation (§7), and cost bounds (§8). This protocol adds the git-worktree layer for *code* development on top.
- [`recursive_loops.md`](./recursive_loops.md) — the directory-materialized child loop, i.e. a parallel sub-loop with its own isolated workspace and return contract.
- [`subgraph_subloop_policy.md`](./subgraph_subloop_policy.md) — the action / subgraph / subloop tiers that decide whether a unit is inline or materialized.
- [`human_approval.md`](./human_approval.md) — the owner-gate (§2 authority tiers, §5 handoff schema) and the Human Decision Package that publish steps route through.
- [`exception_handling.md`](./exception_handling.md) — the taxonomy and bounded ladder that conflict / failure / blocked / rollback map onto.
- [`recovery_protocol.md`](./recovery_protocol.md) — the State Authority Order and recovery procedure that make parallel state safe across sessions.
- [`evidence_gates.md`](./evidence_gates.md) — the per-unit gate a unit must pass before it may converge.
- [`execution_intelligence_policy.md`](./execution_intelligence_policy.md) — the High-Ceiling temperament behind the independence and merge-safety judgments this protocol leaves to the runner.
- [`state_model.md`](./state_model.md) — the node statuses, the claim/lease mechanism, and the event log this protocol reuses without extension.
