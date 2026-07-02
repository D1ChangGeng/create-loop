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

- **All paths are relative to the skill root (the directory containing `SKILL.md`).** Run every
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

## 1. All 7 schemas are valid JSON and valid Draft-07 metaschema

The package ships seven JSON schemas under `schemas/`:
`loop.plan.schema.json`, `node.contract.schema.json`,
`checkpoint.schema.json`, `evidence.ledger.schema.json`,
`loop.meta.schema.json`, `loops.index.schema.json`, `node.runtime.schema.json`
(the three trailing schemas back the recursive-child-loop / three-tier feature:
`loop.meta.yaml`, the `INDEX.yaml` files, and per-node `node.runtime.yaml`).

Each must (a) parse as JSON and (b) declare and conform to JSON Schema Draft-07.

```bash
# 1a. Each schema parses as JSON (exit 0, prints "OK <file>").
for f in schemas/loop.plan.schema.json schemas/node.contract.schema.json \
         schemas/checkpoint.schema.json schemas/evidence.ledger.schema.json \
         schemas/loop.meta.schema.json schemas/loops.index.schema.json \
         schemas/node.runtime.schema.json; do
  python3 -c "import json,sys; json.load(open(sys.argv[1])); print('OK', sys.argv[1])" "$f"
done
```

Expected: exit `0`; seven `OK schemas/...json` lines on stdout.

```bash
# 1b. Each schema declares the Draft-07 metaschema and is itself Draft-07 valid.
python3 -c '
import json, sys
from jsonschema import Draft7Validator
files = ["schemas/loop.plan.schema.json","schemas/node.contract.schema.json",
         "schemas/checkpoint.schema.json","schemas/evidence.ledger.schema.json",
         "schemas/loop.meta.schema.json","schemas/loops.index.schema.json",
         "schemas/node.runtime.schema.json"]
for f in files:
    s = json.load(open(f))
    assert s.get("$schema","").rstrip("#").endswith("draft-07/schema"), f"{f}: not draft-07"
    Draft7Validator.check_schema(s)   # raises on an invalid schema
    print("draft-07 OK", f)
'
```

Expected: exit `0`; seven `draft-07 OK schemas/...json` lines on stdout. A
nonzero exit means a schema is malformed or not declared as Draft-07.

---

## 2. Each of the 7 YAML templates validates against its schema

The package ships seven templates under `templates/`. Each is a minimal but
complete, valid instance of its artifact and must validate through the
appropriate script. The `--kind` selector on `validate_loop_plan.py` chooses
which schema to apply (`loop_plan` is the default; the others are
`node_contract`, `evidence_ledger`, `loop_meta`, `loops_index`, and
`node_runtime`).

```bash
# 2a. loop.plan template (default --kind loop_plan).
python3 scripts/validate_loop_plan.py templates/loop.plan.yaml

# 2b. node.contract template.
python3 scripts/validate_loop_plan.py --kind node_contract templates/node.contract.yaml

# 2c. evidence.ledger template.
python3 scripts/validate_loop_plan.py --kind evidence_ledger templates/evidence.ledger.yaml

# 2d. checkpoint template (its own script).
python3 scripts/validate_checkpoint.py templates/checkpoint.yaml

# 2e. loop.meta template (--kind loop_meta).
python3 scripts/validate_loop_plan.py --kind loop_meta templates/loop.meta.yaml

# 2f. loops.index template (--kind loops_index).
python3 scripts/validate_loop_plan.py --kind loops_index templates/loops.index.yaml

# 2g. node.runtime template (--kind node_runtime).
python3 scripts/validate_loop_plan.py --kind node_runtime templates/node.runtime.yaml
```

Expected: each command exits `0`. No error message is printed for a valid
template. Exit `0` here proves the template carries every required field
(`schema_version`, `plan_id`, `goal`, `true_intent`, `termination`, `nodes`,
etc.; and for the new artifacts `loop_id`, `type`, `parent`, `root`,
`return_contract`; `loops[]`/`children[]`; `node_id`, `runtime_subgraphs[]`)
with in-enum values.

> **Note (illustrative human_intervention_policy).** `templates/loop.plan.yaml`
> now also carries an illustrative, valid **optional** top-level
> `human_intervention_policy` block (the Human Decision Package policy). It is
> optional — plans and examples that omit it stay valid — so command **2a**
> already covers it: exit `0` there confirms the populated policy validates
> (in-enum `default_mode`, `preferred_answer_format`, and
> `decision_package_required_when` tokens). No new command is required.

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

> **Note (child_loops now required).** After Wave 6, `child_loops` is a
> **required** field on every plan node (empty sentinel `[]` when a node has no
> directory-materialized children). Both examples above now carry `child_loops`
> on every node, so exit `0` here also confirms the plans satisfy the new
> required-field rule.

---

## 3b. The recursive child-loop tree example validates end-to-end

A third example ships under `examples/example_child_loop_tree/` — a materialized
recursive loop tree (root loop with `_loops/` children/grandchildren) exercising
the directory-materialized child-loop feature. Every `loop.meta.yaml`,
`loop.plan.yaml`, and `INDEX.yaml` in that tree must validate through the
extended CLI. The commands below discover each artifact type and validate it with
the matching `--kind`.

```bash
# 3b-i. Every loop.meta.yaml validates (--kind loop_meta).
find examples/example_child_loop_tree -name loop.meta.yaml \
  -exec python3 scripts/validate_loop_plan.py --kind loop_meta {} \;

# 3b-ii. Every loop.plan.yaml validates (default --kind loop_plan).
find examples/example_child_loop_tree -name loop.plan.yaml \
  -exec python3 scripts/validate_loop_plan.py {} \;

# 3b-iii. Every INDEX.yaml validates (--kind loops_index).
find examples/example_child_loop_tree -name INDEX.yaml \
  -exec python3 scripts/validate_loop_plan.py --kind loops_index {} \;
```

Expected: every spawned validation exits `0`. Because `find … -exec … \;` runs
the validator once per matched file, a nonzero exit from any single file
propagates and fails the check. Exit `0` across all three finds proves each
`loop.meta.yaml` carries a valid identity/relation block (`loop_id`, `type`,
`parent`/`root`, `return_contract`), each nested `loop.plan.yaml` is a valid plan
(with `child_loops` present on every node), and each `INDEX.yaml` — global
(`loops[]`) or local (`children[]`) — validates against `loops.index.schema.json`.

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

## 5. `SKILL.md` respects the line budget (< 1000 lines)

The skill entrypoint must stay lean; depth lives in `references/`.

```bash
# 5. SKILL.md must be strictly fewer than 1000 lines.
test "$(wc -l < SKILL.md)" -lt 1000 && echo "SKILL-line-budget-OK"
```

Expected: exit `0` and `SKILL-line-budget-OK` on stdout. A `SKILL.md` of 1000 or
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

Copy-paste this entire block. Run it from the skill root (the directory containing `SKILL.md`). It
runs every acceptance check in order under `set -e`, so the **first** failure
aborts with a nonzero exit; reaching `ALL GREEN (incl. child-loops)` means the
package passes the acceptance gate.

```bash
set -euo pipefail
# Run from the skill root (the directory containing SKILL.md).
cd "$(dirname "$0")" 2>/dev/null || true   # or: cd /path/to/skills/create-loop

echo "== 6. scripts compile =="
python3 -m py_compile scripts/*.py
echo "   PY-COMPILE-OK"

echo "== 5. SKILL.md line budget < 1000 =="
test "$(wc -l < SKILL.md)" -lt 1000
echo "   SKILL-line-budget-OK"

echo "== 1a. schemas parse as JSON =="
for f in schemas/loop.plan.schema.json schemas/node.contract.schema.json \
         schemas/checkpoint.schema.json schemas/evidence.ledger.schema.json \
         schemas/loop.meta.schema.json schemas/loops.index.schema.json \
         schemas/node.runtime.schema.json schemas/claim.schema.json \
         schemas/event_log.schema.json schemas/loop.state.schema.json; do
  python3 -c "import json,sys; json.load(open(sys.argv[1])); print('   OK', sys.argv[1])" "$f"
done

echo "== 1b. schemas are valid Draft-07 =="
python3 -c '
import json
from jsonschema import Draft7Validator
files = ["schemas/loop.plan.schema.json","schemas/node.contract.schema.json",
         "schemas/checkpoint.schema.json","schemas/evidence.ledger.schema.json",
         "schemas/loop.meta.schema.json","schemas/loops.index.schema.json",
         "schemas/node.runtime.schema.json","schemas/claim.schema.json",
         "schemas/event_log.schema.json","schemas/loop.state.schema.json"]
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
python3 scripts/validate_loop_plan.py --kind loop_meta templates/loop.meta.yaml
python3 scripts/validate_loop_plan.py --kind loops_index templates/loops.index.yaml
python3 scripts/validate_loop_plan.py --kind node_runtime templates/node.runtime.yaml
python3 scripts/validate_loop_plan.py --kind claim templates/claim.yaml
python3 scripts/validate_loop_plan.py --kind event_log templates/event_log.yaml
python3 scripts/validate_loop_plan.py --kind loop_state templates/loop.state.yaml
python3 scripts/validate_loop_plan.py --kind node_runtime templates/node.runtime.yaml
echo "   templates OK"

echo "== 3. examples validate (plan + checkpoint) =="
for ex in example_product_delivery example_research_project; do
  python3 scripts/validate_loop_plan.py "examples/$ex/loop.plan.yaml"
  python3 scripts/validate_checkpoint.py "examples/$ex/checkpoint.yaml" \
          --plan "examples/$ex/loop.plan.yaml"
done
echo "   examples OK"

echo "== 3b. child-loop tree example validates (meta + plan + index) =="
find examples/example_child_loop_tree -name loop.meta.yaml \
  -exec python3 scripts/validate_loop_plan.py --kind loop_meta {} \;
find examples/example_child_loop_tree -name loop.plan.yaml \
  -exec python3 scripts/validate_loop_plan.py {} \;
find examples/example_child_loop_tree -name INDEX.yaml \
  -exec python3 scripts/validate_loop_plan.py --kind loops_index {} \;
echo "   child-loop tree OK"

echo "== 4. render_dag emits mermaid + dot =="
python3 scripts/render_dag.py examples/example_product_delivery/loop.plan.yaml > /tmp/dag_out.txt
grep -q '```mermaid' /tmp/dag_out.txt
grep -Eq '^graph (TD|LR)' /tmp/dag_out.txt
grep -q 'digraph' /tmp/dag_out.txt
echo "   render OK"

echo "ALL GREEN (incl. child-loops)"
```

Expected final line on stdout: `ALL GREEN (incl. child-loops)`, with overall
exit `0`.
