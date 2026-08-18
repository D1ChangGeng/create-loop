# Closeout — L001 example-delivery (root loop)

> **Status:** the root loop is still `running`; this closeout is a stub that the
> loop will finalize once `verify` and `closeout` complete. It is the return
> interface a parent would read — but L001 is a `root_loop`, so `parent_updates`
> is empty and there is no parent to integrate the result.

## What this loop delivers

The example feature deliverable (`artifacts/deliverable.md`) plus the fix for the
effectiveness bug discovered mid-run. The bug fix was too heavyweight to host as
an inline subgraph, so it was materialized as the child loop **L001.01** under
`_loops/` (see the `build` node's `child_loops[]` reference).

## Artifacts (required_outputs)

- `artifacts/deliverable.md` — the built deliverable.

## Evidence

- Passing entries in `state/evidence.ledger.yaml` for `charter` (human_approval)
  and, once complete, `build` (test), `verify` (llm_judge), `closeout`
  (artifact_exists).

## Child loops

- **L001.01 — fix-effectiveness-bug** (`running`). Owns the effectiveness bug
  fix with its own plan, checkpoint, evidence, and closeout. The parent reads
  `_loops/L001.01-fix-effectiveness-bug/closeout.md` and applies its
  `parent_updates` to the `build` node before re-evaluating build's test gate.

## Parent updates

None — L001 is a `root_loop` (`parent: null`).

## Open blockers

None at the root level; `build` waits on the child loop's return.
