# Baseline Green Rollback Oracle

This baseline captures the verified-green state before the multi-wave refactor.
If a later wave breaks behavior, compare with or revert to git commit
`9b670ee8f705bff998e4f73c4a509f4b18ca0990`.

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
   byte-compiles with `python3 -m py_compile`.
2. `SKILL.md` is exactly 803 lines.
3. `schemas/` contains exactly 11 `.json` files and every one parses as JSON.
4. The baseline loop-plan, node-contract, evidence-ledger, and checkpoint
   templates pass their validators.
5. `example_product_delivery` and `example_research_project` each have a valid
   plan and a checkpoint that validates against that plan.
6. The root and child directories in `example_child_loop_tree` each pass the
   whole-loop integrity gate and print `INTEGRITY OK`.
7. Rendering the product-delivery plan emits a fenced `mermaid` block.
8. Running `node test/installer.test.js` from the repository root exits zero
   and reports `15 passed, 0 failed`.

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
== SKILL.md line count ==
SKILL.md 803 LINES OK
== JSON schemas ==
JSON OK schemas/<schema>.json
... 11 JSON OK lines total ...
== Baseline templates ==
BASELINE TEMPLATES OK
== Worked examples ==
EXAMPLE OK example_product_delivery
EXAMPLE OK example_research_project
== Loop integrity ==
... INTEGRITY OK for the root loop ...
... INTEGRITY OK for the child loop ...
== DAG rendering ==
MERMAID FENCE OK
== Installer tests ==
... 15 passed, 0 failed ...
ALL GREEN
```
