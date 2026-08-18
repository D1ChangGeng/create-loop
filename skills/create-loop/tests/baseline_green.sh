#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

fail() {
  echo "ASSERTION FAILED: $*" >&2
  exit 1
}

assert_command() {
  local assertion=$1
  shift
  "$@" || fail "$assertion"
}

compile_python_sources() {
  python3 -B - "$@" <<'PY'
import pathlib
import sys
import tokenize

for pattern in sys.argv[1:]:
    paths = sorted(pathlib.Path().glob(pattern))
    if not paths:
        raise SystemExit(f"no Python sources matched: {pattern}")
    for path in paths:
        with tokenize.open(path) as source:
            compile(source.read(), str(path), "exec")
PY
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
skill_root=$(cd -- "$script_dir/.." && pwd)
repo_root=$(cd -- "$skill_root/../.." && pwd)

node_cmd=${NODE_CMD:-node}
if ! command -v "$node_cmd" >/dev/null 2>&1; then
  if command -v node.exe >/dev/null 2>&1; then
    node_cmd=node.exe
  else
    fail "Node.js is required to run the repository installer tests"
  fi
fi

cd "$skill_root"

echo "== Python compilation =="
assert_command "Python files under scripts/ or scripts/checks/ did not compile" \
  compile_python_sources 'scripts/*.py' 'scripts/checks/*.py'
echo "PYTHON COMPILE OK"

echo "== SKILL.md line budget =="
# Ceiling, never an exact pin: waves 1-4 edit SKILL.md by design.
skill_lines=$(wc -l < SKILL.md)
[[ $skill_lines -le 1000 ]] || \
  fail "SKILL.md line count is $skill_lines; exceeds the enforced 1000-line ceiling"
echo "SKILL.md ${skill_lines} LINES OK (ceiling 1000)"

echo "== JSON schemas =="
mapfile -t schema_files < <(printf '%s\n' schemas/*.json)
[[ ${#schema_files[@]} -ge 11 ]] || \
  fail "schemas/ contains ${#schema_files[@]} JSON files; expected at least the 11 v1 schemas"
for schema in "${schema_files[@]}"; do
  assert_command "$schema does not parse as JSON" \
    python3 -c "import json,sys; json.load(open(sys.argv[1])); print('JSON OK', sys.argv[1])" "$schema"
done

echo "== Baseline templates =="
assert_command "templates/loop.plan.yaml failed loop-plan validation" \
  python3 scripts/validate_loop_plan.py templates/loop.plan.yaml
assert_command "templates/node.contract.yaml failed node-contract validation" \
  python3 scripts/validate_loop_plan.py --kind node_contract templates/node.contract.yaml
assert_command "templates/evidence.ledger.yaml failed evidence-ledger validation" \
  python3 scripts/validate_loop_plan.py --kind evidence_ledger templates/evidence.ledger.yaml
assert_command "templates/checkpoint.yaml failed checkpoint validation" \
  python3 scripts/validate_checkpoint.py templates/checkpoint.yaml
# Must list EVERY template that has a --kind: an omitted template can violate an
# enforced rule and still leave this gate green.
for pair in "artifact_index:artifact.index.yaml" "claim:claim.yaml" \
            "event_log:event_log.yaml" "loop_meta:loop.meta.yaml" \
            "loop_state:loop.state.yaml" "loops_index:loops.index.yaml" \
            "node_runtime:node.runtime.yaml"; do
  kind="${pair%%:*}"; file="${pair#*:}"
  assert_command "templates/$file failed $kind validation" \
    python3 scripts/validate_loop_plan.py --kind "$kind" "templates/$file"
done
echo "BASELINE TEMPLATES OK"

echo "== Worked examples =="
for example in example_product_delivery example_research_project; do
  assert_command "examples/$example/loop.plan.yaml failed plan validation" \
    python3 scripts/validate_loop_plan.py "examples/$example/loop.plan.yaml"
  assert_command "examples/$example/checkpoint.yaml failed validation against its plan" \
    python3 scripts/validate_checkpoint.py "examples/$example/checkpoint.yaml" \
      --plan "examples/$example/loop.plan.yaml"
  echo "EXAMPLE OK $example"
done

echo "== Loop integrity =="
for loop_dir in \
  examples/example_child_loop_tree/L001-example-delivery \
  examples/example_child_loop_tree/L001-example-delivery/_loops/L001.01-fix-effectiveness-bug; do
  integrity_output=$(python3 scripts/check_loop_integrity.py "$loop_dir") || \
    fail "$loop_dir failed the integrity check"
  printf '%s\n' "$integrity_output"
  [[ $integrity_output == *"CROSS-FILE REFERENCES OK"* ]] || \
    fail "$loop_dir integrity output did not contain CROSS-FILE REFERENCES OK"
done

echo "== DAG rendering =="
dag_output=$(python3 scripts/render_dag.py examples/example_product_delivery/loop.plan.yaml) || \
  fail "render_dag.py failed for example_product_delivery"
[[ $dag_output == *'```mermaid'* ]] || \
  fail "render_dag.py output did not contain a mermaid fence"
echo "MERMAID FENCE OK"

echo "== Installer tests =="
installer_output=$(cd "$repo_root" && "$node_cmd" test/installer.test.js) || \
  fail "repo-root installer tests exited nonzero"
printf '%s\n' "$installer_output"
[[ $installer_output == *"passed, 0 failed"* ]] || \
  fail "installer test output did not report a zero-failure summary"

echo "ALL GREEN"
