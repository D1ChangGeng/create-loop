# Parallel Convergence Plan: One Merge/Converge Event

*Diataxis type: **how-to**. This is the artifact an orchestrator writes when it
converges the results of parallel code-development units back onto an
integration branch. It records one convergence event: which units are being
merged, the non-mutating pre-flight verdict for each, the chosen integration
order, the rollback anchor, the aggregate-verify result, and the rollback ladder
to invoke on failure. It is the merge/converge counterpart to
[`handoff.md`](./handoff.md) (which bridges sessions) — this document bridges
**branches**. The full protocol it implements is
[`references/parallel_development_protocol.md`](../references/parallel_development_protocol.md)
§7 (MERGE) and §8 (CONVERGE).*

---

## When to write a convergence plan

Write one whenever two or more units developed in parallel are about to be
integrated. It is authored **before** the first merge (so the pre-flight
verdicts and integration order are decided up front) and updated in place as each
unit lands. Do not write one for a single serial unit — a lone branch merges
under the ordinary owner-gate with no convergence to plan.

A convergence plan is distinct from a handoff: a handoff carries *run state*
across a session boundary; a convergence plan carries *merge decisions* across a
set of sibling branches within (or into) one integration branch.

---

## Field set

A complete plan covers C1 through C7. C1–C3 are filled before any merge; C4–C6
are filled as integration proceeds; C7 is filled only if the rollback ladder
fires.

### C1. Convergence header

The integration branch the units merge into, the integration base sha they all
branched from, the `plan_id` / `plan_version` the units belong to, and the owner
who must approve the publish (§9 owner-gate). One `event_log` `mutation` entry id
per merge is recorded here for audit.

### C2. Unit inventory

One row per unit being converged, each with: its **unit id** (node id or
child-loop id), its **branch** (`loop/<unit-id>`), its **worktree** path, its
**owner/lease** (the `claim.yaml` holder), and its **gate status** — a unit is
eligible only when `completed` through its own evidence gate
([`evidence_gates.md`](../references/evidence_gates.md)). A unit in any other
status is listed but marked *not eligible* and excluded from this event.

### C3. Pre-flight verdicts

For each eligible unit, the result of the **non-mutating** conflict pre-flight
against the current integration tip:

```bash
git merge-tree --write-tree <integration-branch> loop/<unit-id>   # exit 0 = clean, 1 = conflict
```

Record `clean` or `conflict` and, for a conflict, the conflicting paths. A
conflicting unit is **surfaced, never force-merged** — whether an ambiguous merge
is safe to apply is an owner/runner judgment (§7), so a conflict routes to C7 or
back to the unit's owner, not into the merge queue.

### C4. Integration order

The order in which clean units are integrated — independent units first,
likely-conflicting ones deferred. Units that pre-flight clean against each other
may be integrated together; otherwise one at a time on a dedicated integration
worktree. State the reason for the chosen order in one line.

### C5. Rollback anchor

The annotated tag dropped before the first risky integration, so any step can be
undone:

```bash
git tag -a integration/<checkpoint> <integration-branch> -m "pre-<unit-id>"
```

Record the tag name and the sha it points at.

### C6. Aggregate-verify result

The result of re-running the loop's success criteria against the **whole**
integration branch after all units land — not merely each unit in isolation (a
set of individually-green units can still be jointly wrong). Record `pass`
(advance, then route the publish through the owner-gate) or `fail` (go to C7).

### C7. Rollback ladder invoked (only if C6 failed)

Which rung of the §8 rollback ladder was walked, cheapest first, and the result:

1. `git reset --hard integration/<checkpoint>` — undo on the private integration
   branch (nothing published);
2. `git revert -m 1 <bad-merge-sha>` — forward-only undo when already
   pushed/shared (never rewrite published history);
3. `git reset --hard <branch>@{1}` — recover via reflog when the anchor was lost;
4. `git worktree remove --force <dir>` + `git worktree prune` — discard a wrecked
   unit's tree.

Record which exception class this maps to in
[`exception_handling.md`](../references/exception_handling.md#2-the-exception-taxonomy)
(a merge conflict is an `inconsistent_result`; a stuck unit is `no_progress`) and
the node status the affected unit lands in (`blocked` or `verification_failed`).

---

## Worked skeleton (fill in the values)

```markdown
# Convergence Plan: {integration_branch}

Written by: {orchestrator session_id or agent name}
Written at: {ISO datetime}

## C1. Convergence header

- integration_branch: {branch}
- integration_base:   {sha}
- plan:               {plan_id} v{plan_version}
- owner:              {who approves publish}
- event_log entries:  {mutation entry ids}

## C2. Unit inventory

| unit_id | branch | worktree | owner/lease | gate status | eligible |
|---|---|---|---|---|---|
| {id} | loop/{id} | {path} | {claim holder} | completed | yes |
| {id} | loop/{id} | {path} | {claim holder} | verification_failed | no |

## C3. Pre-flight verdicts

- {unit_id}: clean
- {unit_id}: conflict — {conflicting paths}  → routed to {owner | C7}

## C4. Integration order

1. {unit_id} — {reason}
2. {unit_id} — {reason}

## C5. Rollback anchor

- tag: integration/{checkpoint}
- sha: {sha}

## C6. Aggregate-verify result

{pass | fail}. {one-sentence: which success criteria, evidence path}

## C7. Rollback ladder invoked (only if C6 failed)

- rung: {1 reset --hard | 2 revert -m1 | 3 reflog | 4 worktree remove}
- result: {what happened}
- exception_class: {inconsistent_result | no_progress | ...}
- unit status: {blocked | verification_failed}
```

---

## Pointers

The plan is committed on the integration branch next to the loop's checkpoint.
The related durable artifacts a reader opens alongside it:

```
- checkpoint:     {path to checkpoint.yaml}
- event_log:      {path to event_log.jsonl}
- decision_log:   {path to decision.log.md}
- artifact_index: {path to artifacts/INDEX.yaml}
- claim(s):       {path(s) to per-unit claim.yaml}
```
