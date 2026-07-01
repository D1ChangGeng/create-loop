# Acceptance Tests — the green-path gate

*Diataxis type: **how-to / reference test doc**. This document is the
authoritative green-path acceptance gate for the `create-loop` Agent Skill. It is
written **test-first**: the validator scripts (`scripts/validate_loop_plan.py`,
`scripts/validate_checkpoint.py`, `scripts/render_dag.py`), the JSON schemas, the
YAML templates, and the two worked examples are all authored **afterwards** to
satisfy exactly the commands below. If every command in the
[full green sequence](#full-green-sequence) exits `0`, the package passes the
acceptance gate.*

Every canonical field name and enum value used here is copied verbatim from
[`references/loop_plan_spec.md`](../references/loop_plan_spec.md) and
[`references/state_model.md`](../references/state_model.md).

## How to read this document

- **All paths are relative to `/root/create-loop/create-loop/`.** Run every
  command from that directory.
- Each numbered capability below maps to an **exact runnable command** and its
  **expected result** (exit code + a characteristic of stdout).
- The green path asserts only *acceptance*: valid inputs are accepted, artifacts
  render, budgets hold. Rejection of bad inputs is covered separately in
  [`failure_mode_tests.md`](./failure_mode_tests.md).
- Exit-code convention (contract the scripts must honour):
  `validate_loop_plan.py` and `validate_checkpoint.py` exit `0` **iff** the input
  is valid; on any schema or graph error they exit **nonzero** and print a
  message naming the rule. `render_dag.py` exits `0` and prints the rendered
  graph to stdout.

---

## 1. All 4 schemas are valid JSON and valid Draft-07 metaschema

The package ships four JSON schemas under `schemas/`:
`loop.plan.schema.json`, `node.contract.schema.json`,
`checkpoint.schema.json`, `evidence.ledger.schema.json`.

Each must (a) parse as JSON and (b) declare and conform to JSON Schema Draft-07.

```bash
# 1a. Each schema parses as JSON (exit 0, prints "OK <file>").
for f in schemas/loop.plan.schema.json schemas/node.contract.schema.json \
         schemas/checkpoint.schema.json schemas/evidence.ledger.schema.json; do
  python3 -c "import json,sys; json.load(open(sys.argv[1])); print('OK', sys.argv[1])" "$f"
done
```

Expected: exit `0`; four `OK schemas/...json` lines on stdout.

```bash
# 1b. Each schema declares the Draft-07 metaschema and is itself Draft-07 valid.
python3 -c '
import json, sys
from jsonschema import Draft7Validator
files = ["schemas/loop.plan.schema.json","schemas/node.contract.schema.json",
         "schemas/checkpoint.schema.json","schemas/evidence.ledger.schema.json"]
for f in files:
    s = json.load(open(f))
    assert s.get("$schema","").rstrip("#").endswith("draft-07/schema"), f"{f}: not draft-07"
    Draft7Validator.check_schema(s)   # raises on an invalid schema
    print("draft-07 OK", f)
'
```

Expected: exit `0`; four `draft-07 OK schemas/...json` lines on stdout. A
nonzero exit means a schema is malformed or not declared as Draft-07.

---

## 2. Each of the 4 YAML templates validates against its schema

The package ships four templates under `templates/`. Each is a minimal but
complete, valid instance of its artifact and must validate through the
appropriate script. The `--kind` selector on `validate_loop_plan.py` chooses
which of the three plan-family schemas to apply (`loop_plan` is the default).

```bash
# 2a. loop.plan template (default --kind loop_plan).
python3 scripts/validate_loop_plan.py templates/loop.plan.yaml

# 2b. node.contract template.
python3 scripts/validate_loop_plan.py --kind node_contract templates/node.contract.yaml

# 2c. evidence.ledger template.
python3 scripts/validate_loop_plan.py --kind evidence_ledger templates/evidence.ledger.yaml

# 2d. checkpoint template (its own script).
python3 scripts/validate_checkpoint.py templates/checkpoint.yaml
```

Expected: each command exits `0`. No error message is printed for a valid
template. Exit `0` here proves the template carries every required field
(`schema_version`, `plan_id`, `goal`, `true_intent`, `termination`, `nodes`,
etc.) with in-enum values.

---

## 3. Both worked examples validate (plan + checkpoint)

Two end-to-end examples ship under `examples/`:
`example_product_delivery/` and `example_research_project/`. Each contains a
`loop.plan.yaml` and a `checkpoint.yaml`. The checkpoint is validated **against
its plan** so plan/checkpoint consistency (matching `plan_version`, and
`node_states` keys ⊆ plan node ids) is exercised on the green path too.

```bash
# 3a. product_delivery example: plan then checkpoint (checkpoint checked against plan).
python3 scripts/validate_loop_plan.py examples/example_product_delivery/loop.plan.yaml
python3 scripts/validate_checkpoint.py examples/example_product_delivery/checkpoint.yaml \
        --plan examples/example_product_delivery/loop.plan.yaml

# 3b. research_project example: plan then checkpoint (checkpoint checked against plan).
python3 scripts/validate_loop_plan.py examples/example_research_project/loop.plan.yaml
python3 scripts/validate_checkpoint.py examples/example_research_project/checkpoint.yaml \
        --plan examples/example_research_project/loop.plan.yaml
```

Expected: all four commands exit `0`. Because `--plan` is supplied, exit `0`
also asserts the checkpoint's `plan_version` matches the plan's and every key of
`node_states` is a node `id` defined in the plan.

---

## 4. `render_dag.py` emits both a Mermaid block and a DOT block

`render_dag.py` reads a `loop.plan` and prints two renderings to stdout: a
Mermaid graph (fenced with ```` ```mermaid ```` and a `graph` header) and a
Graphviz DOT block (a `digraph` block).

```bash
# 4a. Render the product_delivery example and confirm both blocks are present.
python3 scripts/render_dag.py examples/example_product_delivery/loop.plan.yaml > /tmp/dag_out.txt
grep -q '```mermaid' /tmp/dag_out.txt && echo "HAS-mermaid-fence"
grep -Eq '^graph (TD|LR)' /tmp/dag_out.txt && echo "HAS-mermaid-graph"
grep -q 'digraph' /tmp/dag_out.txt && echo "HAS-dot-digraph"
```

Expected: `render_dag.py` exits `0`; stdout of the three `grep` checks prints
`HAS-mermaid-fence`, `HAS-mermaid-graph`, and `HAS-dot-digraph`. The rendered
output contains at least one ```` ```mermaid ```` fence with a `graph TD`/`graph
LR` block **and** a `digraph` DOT block naming the plan's nodes as vertices and
each `requires` edge as an edge.

---

## 5. `SKILL.md` respects the line budget (< 600 lines)

The skill entrypoint must stay lean; depth lives in `references/`.

```bash
# 5. SKILL.md must be strictly fewer than 600 lines.
test "$(wc -l < SKILL.md)" -lt 600 && echo "SKILL-line-budget-OK"
```

Expected: exit `0` and `SKILL-line-budget-OK` on stdout. A `SKILL.md` of 600 or
more lines fails the gate.

---

## 6. All scripts compile

Every Python script must byte-compile without a `SyntaxError`.

```bash
# 6. Byte-compile all scripts.
python3 -m py_compile scripts/*.py && echo "PY-COMPILE-OK"
```

Expected: exit `0` and `PY-COMPILE-OK` on stdout.

---

## Full green sequence

Copy-paste this entire block. Run it from `/root/create-loop/create-loop/`. It
runs every acceptance check in order under `set -e`, so the **first** failure
aborts with a nonzero exit; reaching `ALL GREEN` means the package passes the
acceptance gate.

```bash
set -euo pipefail
cd /root/create-loop/create-loop

echo "== 6. scripts compile =="
python3 -m py_compile scripts/*.py
echo "   PY-COMPILE-OK"

echo "== 5. SKILL.md line budget < 600 =="
test "$(wc -l < SKILL.md)" -lt 600
echo "   SKILL-line-budget-OK"

echo "== 1a. schemas parse as JSON =="
for f in schemas/loop.plan.schema.json schemas/node.contract.schema.json \
         schemas/checkpoint.schema.json schemas/evidence.ledger.schema.json; do
  python3 -c "import json,sys; json.load(open(sys.argv[1])); print('   OK', sys.argv[1])" "$f"
done

echo "== 1b. schemas are valid Draft-07 =="
python3 -c '
import json
from jsonschema import Draft7Validator
files = ["schemas/loop.plan.schema.json","schemas/node.contract.schema.json",
         "schemas/checkpoint.schema.json","schemas/evidence.ledger.schema.json"]
for f in files:
    s = json.load(open(f))
    assert s.get("$schema","").rstrip("#").endswith("draft-07/schema"), f+": not draft-07"
    Draft7Validator.check_schema(s)
    print("   draft-07 OK", f)
'

echo "== 2. templates validate =="
python3 scripts/validate_loop_plan.py templates/loop.plan.yaml
python3 scripts/validate_loop_plan.py --kind node_contract templates/node.contract.yaml
python3 scripts/validate_loop_plan.py --kind evidence_ledger templates/evidence.ledger.yaml
python3 scripts/validate_checkpoint.py templates/checkpoint.yaml
echo "   templates OK"

echo "== 3. examples validate (plan + checkpoint) =="
for ex in example_product_delivery example_research_project; do
  python3 scripts/validate_loop_plan.py "examples/$ex/loop.plan.yaml"
  python3 scripts/validate_checkpoint.py "examples/$ex/checkpoint.yaml" \
          --plan "examples/$ex/loop.plan.yaml"
done
echo "   examples OK"

echo "== 4. render_dag emits mermaid + dot =="
python3 scripts/render_dag.py examples/example_product_delivery/loop.plan.yaml > /tmp/dag_out.txt
grep -q '```mermaid' /tmp/dag_out.txt
grep -Eq '^graph (TD|LR)' /tmp/dag_out.txt
grep -q 'digraph' /tmp/dag_out.txt
echo "   render OK"

echo "ALL GREEN"
```

Expected final line on stdout: `ALL GREEN`, with overall exit `0`.
