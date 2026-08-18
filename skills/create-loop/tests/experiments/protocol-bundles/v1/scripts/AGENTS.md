# skills/create-loop/scripts/ — VALIDATOR ENGINE

Python 3.8+ check engine for the YAML artifacts the skill emits. Authoritative enforcement of rules **R1–R41**. Read-only: loads YAML, prints violations to stderr, exits `0` (valid) / `1` (structural error) / `2` (load/usage error). Deps: stdlib + **PyYAML** (mandatory) + `jsonschema` (optional bonus layer; degrades gracefully if absent).

## STRUCTURE
```
scripts/
├── validate_loop_plan.py    dispatcher over 10 artifact kinds (--kind ...); aggregates R1–R41
├── validate_checkpoint.py   checkpoint vs plan (R6/R19/R20/R22/R33)
├── check_loop_integrity.py  WHOLE-LOOP-DIR gate: composes both validators + cross-file reconciliation
├── render_dag.py            plan → Mermaid + Graphviz DOT to stdout (read-only, human inspection)
└── checks/                  rule modules — one concern each
    ├── __init__.py          SINGLE SOURCE OF TRUTH: every enum, regex, *_REQUIRED tuple
    ├── graph.py    R1 cycle / R2 dangling dep      ├── gates.py    R3/R7/R34
    ├── nodes.py    R4/R5/R8/R13/R35                 ├── meta.py     R9/R10/R11/R12/R17
    ├── index.py    R16/R37 (path↔disk)             ├── caps.py     R28/R29
    ├── claim.py    R21                             ├── event_log.py R23/R24/R31/R39
    ├── provenance.py R26 goal-hash / R36 verifier  ├── retirement.py R40 tombstone
    ├── runtime.py  R5/R14/R15/R25 (subgraph)       ├── loop_state.py R30
    └── artifact_index.py R41 (one authority/path)
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
```

## CONVENTIONS
- **`checks/__init__.py` is the ONLY place enums/regexes/required-field tuples live.** Adding a gate/node/status token = edit those frozensets/tuples FIRST, then the consuming rule module, then keep `schemas/*.json` in lockstep.
- Rule numbers (Rn) are the cross-citation language across SKILL.md, references, schemas, and tests — never renumber; append.
- `check_loop_integrity.py` runs the per-file validators as subprocesses AND reconciles cross-file invariants (checkpoint↔plan↔ledger↔index, completed-needs-active-evidence, evidence-artifact-exists). A nonzero exit means enter a recovery subgraph, do NOT advance.
- After changing any validator or schema, run `tests/failure_mode_tests.md` (rejection fixtures) plus the acceptance gate.

## ANTI-PATTERNS
- NEVER hard-code an enum inline in a rule module — import from `checks/__init__.py`.
- NEVER make a script mutate an artifact — these are read-only checks.
- Do NOT let `validate_loop_plan.py` and the JSON Schemas disagree on any enum/required field — the Python validator is authoritative, the schema mirrors it.
