# Worked example — a directory-materialized child loop tree

A real, on-disk example of the **recursive directory-materialized child loop**
mechanism from [`references/recursive_loops.md`](../../references/recursive_loops.md).
Where the other two examples show an inline `subgraph` inside a node, this one
shows the heavyweight escalation: a non-trivial piece of work materialized as an
**isolated child loop directory** (a *subloop*) under the parent's `_loops/`.

## The tree

```
example_child_loop_tree/
  INDEX.yaml                                 # GLOBAL index (loops[]) — the top-level loop
  L001-example-delivery/                     # root_loop, depth 0
    loop.meta.yaml                           # type: root_loop, parent: null, depth: 0
    loop.plan.yaml                           # charter -> build -> verify -> closeout
    checkpoint.yaml                          # node_states match the 4 plan nodes
    closeout.md                              # the root's own return interface (stub)
    _loops/                                  # control dir: this loop's child loops
      INDEX.yaml                             # LOCAL index (children[]) — direct children
      L001.01-fix-effectiveness-bug/         # child_loop, depth 1
        loop.meta.yaml                       # type: child_loop, parent{L001}, root{L001}
        loop.plan.yaml                       # reproduce -> root_cause -> fix -> regression_verify
        checkpoint.yaml                      # base 17 fields + the 7 child-loop additions
        closeout.md                          # the child's return interface to the parent
```

## The parent → child reference

The `build` node in `L001-example-delivery/loop.plan.yaml` carries a **populated
`child_loops[]` reference** (the shape locked in `recursive_loops.md` §10.1):

```yaml
child_loops:
  - loop_id: L001.01
    path: _loops/L001.01-fix-effectiveness-bug
    spawn_reason: "leftover bug harming the final effect; needs its own plan + evidence audit (Admission Gate #1, #3)"
    status: running
    closeout: _loops/L001.01-fix-effectiveness-bug/closeout.md
```

Both `path` and `closeout` resolve **relative to the parent loop directory**
(`L001-example-delivery/`) and point at the **real child directory on disk**.
Every other node in the plan carries the explicit empty sentinel
`child_loops: []`.

## The return contract

The child never writes the parent's state directly (the isolation rule,
`recursive_loops.md` §9). It influences the parent **only** through its
`return_contract` (declared in the child's `loop.meta.yaml`) realized as
`closeout.md`:

1. The child reaches its required outputs (`artifacts/root-cause.md`,
   `artifacts/fix-evidence.md`) and writes `closeout.md`.
2. The parent reads that `closeout.md` via the `child_loops[].closeout` path.
3. The parent applies each `parent_updates` entry — mark `build`'s
   effectiveness postcondition satisfied, then re-run `verify`'s `llm_judge`
   gate.

## How to resume a child

A fresh session resumes the child loop from
`_loops/L001.01-fix-effectiveness-bug/checkpoint.yaml` alone. Beyond the base 17
checkpoint fields it carries the 7 child-loop additions (§7.4):

- `loop_id: L001.01`, `parent_loop_id: L001`, `parent_node_id: build`
- `current_node: root_cause` — where to pick up in *this* loop's plan
- `last_valid_artifacts: [artifacts/repro.md]` — safe to reuse
- `next_recommended_action` — advisory hint (distinct from the base
  `next_suggested_action`)
- `open_blockers: []`

Read the relevant `INDEX.yaml` first (global at the tree root, local under
`_loops/`) — the tree walk is the fallback of last resort.

## Validate (all exit 0)

Run from the skill root:

```bash
# loop.meta files
find examples/example_child_loop_tree -name loop.meta.yaml \
  -exec python3 scripts/validate_loop_plan.py --kind loop_meta {} \;

# loop.plan files
find examples/example_child_loop_tree -name loop.plan.yaml \
  -exec python3 scripts/validate_loop_plan.py {} \;

# INDEX files
find examples/example_child_loop_tree -name INDEX.yaml \
  -exec python3 scripts/validate_loop_plan.py --kind loops_index {} \;

# checkpoints against their sibling plans
python3 scripts/validate_checkpoint.py \
  examples/example_child_loop_tree/L001-example-delivery/checkpoint.yaml \
  --plan examples/example_child_loop_tree/L001-example-delivery/loop.plan.yaml
python3 scripts/validate_checkpoint.py \
  examples/example_child_loop_tree/L001-example-delivery/_loops/L001.01-fix-effectiveness-bug/checkpoint.yaml \
  --plan examples/example_child_loop_tree/L001-example-delivery/_loops/L001.01-fix-effectiveness-bug/loop.plan.yaml
```
