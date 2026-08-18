# skills/create-loop/scripts/ — VALIDATOR ENGINE

Python 3.10+ validation tooling. The v1 compatibility engine validates YAML
R-family invariants. The v2 engine validates JSON/JSONL deterministic facts and
projects generated resume state; neither engine decides semantic completion.

## STRUCTURE
```
scripts/
├── validate_loop_plan.py    dispatcher over 11 artifact kinds (--kind ...); aggregates v1 R-family checks
├── validate_checkpoint.py   checkpoint vs plan (R6/R19/R20/R22/R33)
├── check_loop_integrity.py  WHOLE-LOOP-DIR gate: composes both validators + cross-file reconciliation
├── render_dag.py            plan → Mermaid + Graphviz DOT to stdout (read-only, human inspection)
├── checks/                  rule modules — one concern each
    ├── __init__.py          SINGLE SOURCE OF TRUTH: every enum, regex, *_REQUIRED tuple
    ├── graph.py    R1 cycle / R2 dangling dep      ├── gates.py    R3/R7/R34
    ├── nodes.py    R4/R5/R8/R13/R35                 ├── meta.py     R9/R10/R11/R12/R17
    ├── index.py    R16/R37 (path↔disk)             ├── caps.py     R28/R29
    ├── claim.py    R21                             ├── event_log.py R23/R24/R31/R39
    ├── provenance.py R26 goal-hash / R36 verifier  ├── retirement.py R40 tombstone
    ├── runtime.py  R5/R14/R15/R25 (subgraph)       ├── loop_state.py R30
│   └── artifact_index.py R41 (one authority/path)
├── schema_runtime.py        zero-dep fail-closed subset for v2 Draft 2020-12
├── project_loop.py          canonical v2 journal projector
├── validate_loop_dir.py     v2 whole-loop deterministic gate
├── render_resume.py         atomic v2 resume writer / read-only --check
└── migrate_v1.py            conservative sibling-only v1 import
```

## INVOCATION
```bash
python3 validate_loop_plan.py [--kind KIND] <file> [--plan P] [--root R]
#   KIND ∈ loop_plan node_contract evidence_ledger loop_meta loops_index
#          node_runtime claim event_log loop_state artifact_index  (default: loop_plan)
#   --plan → ledger R36 · --root → index R37 disk reconciliation
python3 validate_checkpoint.py <checkpoint.yaml> [--plan P] [--claims D] [--enforce-claims] [--meta M]
python3 check_loop_integrity.py <loop-dir>   # run at session start, after every node completion, after every mutation
python3 render_dag.py <plan.yaml>
python validate_loop_dir.py <v2-loop-dir>
python render_resume.py <v2-loop-dir> [--check]
python migrate_v1.py <v1-loop-dir> [v2-sibling-dir] [--dry-run]
python ../tests/experiments/freeze_experiment.py        # refreshes candidate/instrument/preregistration bindings
python ../tests/experiments/freeze_experiment.py --check # read-only exact freeze check
python ../tests/experiments/experiment_harness.py validate
python ../tests/experiments/experiment_harness.py plan [--output run-plan.json]
python ../tests/experiments/deterministic_runner.py --protocol v1
python ../tests/experiments/deterministic_runner.py --protocol v2
python ../tests_py/test_experiment_workspace.py
python ../tests_py/test_experiment_evaluation.py
python ../tests_py/test_experiment_execution_guard.py
```

## CONVENTIONS
- For v1, **`checks/__init__.py` is the only Python mirror for enums, regexes,
  and required-field tuples.** Change canonical v1 references first, keep Draft-07
  schemas in lockstep, then update this mirror and its consumers. v2 enums remain
  authoritative in the Draft 2020-12 schemas.
- The optional v1 `jsonschema` layer may add diagnostics, but installed safety
  cannot depend on it. Hand-written validators must enforce every shape/type
  constraint consumed by whole-loop completion or recovery logic.
- For v1, rule numbers (Rn) are the compatibility cross-citation language — never renumber. v2 uses named invariant families.
- `check_loop_integrity.py` runs the per-file validators as subprocesses AND reconciles cross-file invariants (checkpoint↔plan↔ledger↔index, completed-needs-active-evidence, evidence-artifact-exists). A nonzero exit means enter a recovery subgraph, do NOT advance.
- After changing any validator or schema, add and run executable reject/control
  coverage under `tests_py/`; keep `tests/failure_mode_tests.md` as a readable
  specification, not the only regression gate.
- v2 schemas are canonical for shape. `schema_runtime.py` must fail closed on
  unsupported keywords; `project_loop.py` enforces ordered prior references,
  exact state/effect chains, shared cross-platform output identity, and resume
  projection. Add reject and control fixtures under `tests_py/` for every
  retained invariant family.
- Experiment schema documents use the same bundled runtime subset. The freeze
  tool binds an immutable v1 snapshot, the candidate worktree, and one exact
  instrument set. `workspace_builder.py` supplies concrete reality bindings;
  `evaluation.py` enforces canonical blind assignment and uses the frozen
  `deterministic_runner.py` to recompute catalog results instead of trusting
  submitted suites. Only that deterministic smoke metric has authoritative
  replay; formulas for the remaining metrics fail closed to `insufficient-data`.
  The runner injects user-site dependencies only for v1 PyYAML, disables
  user-site imports for v2, and treats the tool profile as a declaration rather
  than an OS sandbox. `execution_guard.py` supplies immutable grant/ledger/
  receipt/spend-summary replay, and the Pilot adapter/runners connect that
  authority to raw provider evidence, trace validation, oracle evaluation, and
  blind-review sealing. Every launch path separately requires a frozen Linux
  reviewer Codex `0.144.1` identity and authenticated OS-enforced provider-only
  network boundary; both remain unresolved, so no real provider call has
  occurred. Pilot/hard limits are frozen at 23 calls / 1.33M tokens / 20,100
  seconds and 126 calls / 7.56M tokens / 113,400 seconds; USD is `not-measured`.
  The legacy 42-pair / 84-run plan is prospective, `formal_execution_enabled`
  remains false, and none of these checks proves v2 wins.

## ANTI-PATTERNS
- NEVER hard-code an enum inline in a rule module — import from `checks/__init__.py`.
- NEVER make a validator or projector mutate its inputs. `render_resume.py`
  writes only generated `resume.json`, and `migrate_v1.py` writes only a new
  sibling v2 directory unless `--dry-run` is used. Dry-run staging stays in the
  system temporary area outside the source Loop ancestry; real migration stages
  beside the destination to preserve atomic publication.
- For v1, do not let `validate_loop_plan.py` and its JSON Schemas disagree on
  any enum or required field: the compatibility Python validator remains
  authoritative. For v2, Draft 2020-12 schemas are shape-authoritative and
  Python adds only ordered, graph, filesystem, and cross-record invariants.
