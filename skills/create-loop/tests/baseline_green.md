# Baseline Green Rollback Oracle

> **Historical v1 baseline.** This document describes the pre-v2 rollback
> oracle and its old absolute counts. It is not the current full acceptance
> gate; use `python -m unittest discover -s tests_py`, the current v1/v2 example
> gates, and the repository installer tests for current behavior.

This script is a compatibility rollback oracle derived from the pre-v2 gate. The
frozen audit numbers for the requested reference commit live in
`tests/baselines/v1-8263f09.json`; they are evidence, not assertions about the
current tree. The script now discovers the current schema set, enforces the
entrypoint ceiling, validates every v1 template kind, checks representative v1
examples and integrity directories, renders a DAG, and requires the current
installer suite to report zero failures.

## Run

From the skill root (the directory containing `SKILL.md`):

```bash
bash tests/baseline_green.sh
```

The script resolves the repository root relative to its own location, so the
installer test does not depend on a machine-specific absolute path.

## Assertions

The script exits nonzero at the first failed assertion and prints an
`ASSERTION FAILED: ...` message naming the broken condition. It asserts:

1. Every Python file matched by `scripts/*.py` and `scripts/checks/*.py`
   compiles in memory with `compile(...)`; the gate sets
   `PYTHONDONTWRITEBYTECODE=1` so it does not leave cache files in the source tree.
2. `SKILL.md` is at most 1000 lines; it never pins an exact line count.
3. `schemas/` contains at least the 11 v1 schemas and every current `.json` file parses.
4. The baseline loop-plan, node-contract, evidence-ledger, and checkpoint
   templates pass their validators.
5. `example_product_delivery` and `example_research_project` each have a valid
   plan and a checkpoint that validates against that plan.
6. The root and child directories in `example_child_loop_tree` each pass the
   whole-loop integrity gate and print `CROSS-FILE REFERENCES OK`.
7. Rendering the product-delivery plan emits a fenced `mermaid` block.
8. Running `node test/installer.test.js` from the repository root exits zero
   and reports a zero-failure summary; the assertion count is intentionally dynamic.

This intentionally excludes later Wave-0 scripts such as `check_pointers.py`
and `prove_reconstruction.py`; it records only the pre-refactor baseline.

## Expected Output

Successful output includes section headers and per-check confirmations. Schema,
integrity, and installer commands may print additional detail. The final line is
always exactly:

```text
ALL GREEN
```

The complete expected success shape is:

```text
== Python compilation ==
PYTHON COMPILE OK
== SKILL.md line budget ==
SKILL.md <current> LINES OK (ceiling 1000)
== JSON schemas ==
JSON OK schemas/<schema>.json
... one JSON OK line per current schema ...
== Baseline templates ==
BASELINE TEMPLATES OK
== Worked examples ==
EXAMPLE OK example_product_delivery
EXAMPLE OK example_research_project
== Loop integrity ==
... CROSS-FILE REFERENCES OK for the root loop ...
... CROSS-FILE REFERENCES OK for the child loop ...
== DAG rendering ==
MERMAID FENCE OK
== Installer tests ==
... <current count> passed, 0 failed ...
ALL GREEN
```
