# create-loop

A meta-skill for long-running AI work. After admission, v1 produces a
`loop.plan` DAG and v2 produces an immutable goal plus versioned plans; durable
modes add the evidence and recovery state a fresh agent needs to resume with
zero prior chat memory. The paradigm is "write the loop, not the prompt."

Protocol v1 remains the compatibility default. Protocol v2 is an explicit
opt-in while paired evaluation is pending. v2 first admits only tasks that
benefit from durable control, then uses immutable `goal.json`, immutable
versioned plans, one append-only `journal.jsonl`, and generated `resume.json`.
See [`references/protocol_v2.md`](references/protocol_v2.md).

The model is layered:

- **Layer 0** is a Charter interview baked into the loop as its first
  governance node. It produces a control profile, not a requirements dump:
  task type, success/failure criteria, the approval boundary, the
  persistence contract. Anything knowable only by later research or
  implementation is recorded as `unknown` / `assumption` /
  `research_question` and routed to the owning node.
- **Layer 1** is `loop.plan v0`, the top-level governance DAG. It holds
  only design-time-invariant nodes (the ones that are mandatory and
  unchanging for the task class). Vendors, files, tests, and discovered
  defects do not live here.
- **Layer 2** is the runtime subgraphs generated inside each node when
  concrete work becomes knowable.

Four principles govern how the plan behaves at runtime. **Autonomy-first**:
the loop resolves branches, unknowns, and blockers by spawning exploration
and diagnostic subgraphs and gathering evidence — it asks the user only at
genuine boundaries (goal, authorization, irreversibility, cost, risk, value).
**Live Loop Semantics**: the top-level goal and governance skeleton stay
stable while the execution path grows from evidence — evidence-driven
completeness growth, not scope creep. **Recursive Planning ⇄ Immersive
Execution**: the loop recursively switches between a global whole-graph
planning view and a local immersive per-node execution view; when a node
proves complex it descends into a subgraph or child subloop, then writes
products, evidence, and decisions back to the parent, which re-plans and
advances. **Layered Execution Chain**: the runner descends a ladder of
execution layers (Top-level Loop → Node → Subgraph → Subloop → Action Plan →
Immersive Action → Return) and uses a leaf-action test to decide when to stop
planning and execute — avoiding both premature execution (acting while work is
still vague) and over-planning (splitting work that is already executable).

The plan is also **recursive**: each node dispatches its work across a
**three-tier model** (`action` atomic, `subgraph` lightweight inline
runtime, `subloop` directory-materialized child loop). When a child
graph is non-trivial it gets its own isolated per-loop directory under
the parent's `_loops/` (e.g. `L<seq>-<slug>/_loops/L<seq>.<seq>-<slug>/`)
with its own `loop.meta.yaml`, `loop.plan.yaml`, checkpoint, evidence
ledger, logs, and `artifacts/`. Inline `subgraph` and `allow_subgraph`
fields on a node are still the lightweight path; promotion to a
directory-materialized subloop is governed by the Admission Gate. Full
spec in [`references/recursive_loops.md`](references/recursive_loops.md)
and the tier / Promotion Gate vocabulary in
[`references/subgraph_subloop_policy.md`](references/subgraph_subloop_policy.md).

When more than one such unit develops code **at once** — parallel actions,
sibling subgraphs, concurrent sub-loops, or a multi-role team — the
[`references/parallel_development_protocol.md`](references/parallel_development_protocol.md)
governs how to split, isolate each unit in its own git worktree, merge through a
non-mutating pre-flight, and converge (with an owner-gate on publish and a
rollback ladder).

Full reasoning lives in `references/concepts.md`. The vocabulary
(vocabulary, enums, transitions) lives in `references/loop_plan_spec.md`
and `references/state_model.md`. The recursive planning-and-execution rhythm
is in `references/recursive_planning_immersive_execution.md`, and the layer
ladder it descends is in `references/layered_execution_chain.md`.

---

## 1. Install

The quickest path is the [`skills`](https://github.com/vercel-labs/skills)
CLI. It works with OpenCode, Claude Code, Codex, Cursor, and many more:

```bash
# Install globally (user-level), for all projects.
npx skills add D1ChangGeng/create-loop --skill create-loop -g -y

# Or install into the current project only.
npx skills add D1ChangGeng/create-loop --skill create-loop -y
```

The install command is also the update command — re-running it overwrites the
skill files with the latest version. Any runtime loop state a project has
created (its `run-id` directories, checkpoints, ledgers) lives separately and
is never touched.

Use it without installing (generate the prompt, or launch an agent directly):

```bash
npx skills use D1ChangGeng/create-loop --skill create-loop --agent claude-code
```

### Manual install

`create-loop` is also a standard Agent Skill directory, so you can copy it
wherever your host discovers skills:

```bash
# Generic global skills location.
cp -R skills/create-loop/ ~/.agents/skills/create-loop/

# OpenCode user-level skills.
cp -R skills/create-loop/ ~/.config/opencode/skills/create-loop/

# Per-project Claude skills.
cp -R skills/create-loop/ .claude/skills/create-loop/
```

Symlinks work the same way. If your host uses a different skills path,
consult its skill-loading docs. The agent loads the skill through its
normal discovery, no daemon, no API key.

### Prerequisites

The scripts use Python 3.10+. v1 YAML validators require PyYAML. Native v2
JSON/JSONL projection, validation, and resume rendering use the standard
library.

```bash
# PyYAML is required by the scripts.
python3 -c "import yaml; print('yaml', yaml.__version__)"
# -> yaml 5.x or newer. If this fails:
pip install pyyaml
```

Optional, for the v1 bonus schema layer and v2 parity tests:

```bash
python3 -c "import jsonschema; print('jsonschema', jsonschema.__version__)"
# -> jsonschema 4.x. If absent, v1 hand-written validation and the bundled v2
#    schema runtime still run, including completion-relevant ledger shape checks;
#    only external parity and the Draft-07 metaschema self-check are skipped.
```

Nothing else is needed. No database, no server, no background runtime.
The skill is filesystem-based: a run is a directory of YAML/Markdown
files that any agent can read and write.

---

## 2. Use

There are two entry points: create a loop from a short goal, or resume
an existing loop. The agent skill is invoked through your host's normal
skill interface (follow the host's `SKILL.md` loading conventions). The
scripts below are the local checks you run against the artifacts the
skill emits.

Before creating artifacts, apply admission: a short, low-risk, single-session
task with no durable recovery or dependency-control need remains an ordinary
task. Use `--protocol v2` on slash commands to opt into v2; otherwise new Loops
use v1. Existing Loops are detected from their artifacts and each write path
follows that protocol.

### Validate and resume a v2 Loop

```bash
python scripts/validate_loop_dir.py <loop-dir>
python scripts/render_resume.py <loop-dir> --check
```

The v2 gate checks deterministic structure, graph, hash, ordered journal,
state/effect/evidence, conditional-module, and projection-freshness invariants.
It does not decide that the real goal is complete. Ordinary replans use a
`plan_replacement` decision with an exact old/new version-and-hash
`plan_change` binding and the same causal evidence set as activation. The
lightweight durability bridge changes only control metadata; semantic plan
changes happen in a later, freshly evidenced replan. Projection and resume
rendering also fail closed if a bound artifact path or hash drifts.

### Explicit v1 → v2 migration

For an explicit v1 → v2 conversion, read the complete
[`references/migration_v1_to_v2.md`](references/migration_v1_to_v2.md) runbook
before invoking `scripts/migrate_v1.py`. The runbook defines prerequisites,
dry-run and sibling-destination rules, source hashing, conservative status,
evidence, and effect mapping, publication, verification, and rollback boundaries.

### Validate a plan

```bash
# Default kind: loop_plan (the top-level governance DAG).
python3 scripts/validate_loop_plan.py <plan.yaml>

# Per-node contract.
python3 scripts/validate_loop_plan.py --kind node_contract <node.contract.yaml>

# Append-only evidence ledger.
python3 scripts/validate_loop_plan.py --kind evidence_ledger <evidence.ledger.yaml>

# Per-loop control profile (`loop.meta.yaml`).
python3 scripts/validate_loop_plan.py --kind loop_meta <loop.meta.yaml>

# Tree index file (one `INDEX.yaml` per run root and per `_loops/` directory).
python3 scripts/validate_loop_plan.py --kind loops_index <INDEX.yaml>

# Per-node runtime hosting record (`node.runtime.yaml`, subgraph tier).
python3 scripts/validate_loop_plan.py --kind node_runtime <node.runtime.yaml>

# Artifact registry (`artifacts/INDEX.yaml`): one authoritative version per path.
python3 scripts/validate_loop_plan.py --kind artifact_index <artifacts/INDEX.yaml>
```

Exit `0` means valid. Nonzero exit prints the rule the input violated.

### Whole-loop-directory integrity gate

The per-file validators each see one artifact; corruption in a long-running
loop is usually cross-file. Run the integrity gate over an entire loop directory
at every session start, after every node completion, and after every plan
mutation:

```bash
python3 scripts/check_loop_integrity.py <loop-dir>
```

It composes the per-file validators AND cross-file reconciliation (checkpoint↔
plan↔ledger↔index, a `completed` node needs active passing evidence, every
evidence `artifact_path` exists). Exit `0` = safe to advance; nonzero = enter a
recovery subgraph instead of advancing (see
[`references/recovery_protocol.md`](references/recovery_protocol.md) §6.0).

### Validate a checkpoint against its plan

```bash
python3 scripts/validate_checkpoint.py <checkpoint.yaml> --plan <plan.yaml>
```

Exits `0` only when the checkpoint's `plan_version` matches the plan
and every key of `node_states` is a node `id` defined in the plan.

### Render the DAG

```bash
python3 scripts/render_dag.py <plan.yaml>
```

Prints a Mermaid block (fenced ```` ```mermaid ```` with a `graph TD` or
`graph LR` header) and a Graphviz DOT `digraph` block to stdout. Pipe to
a file if you want both.

### Worked examples

Five executable examples/fixtures ship under `examples/`:

- `examples/example_product_delivery/`: software delivery loop (REST
  API service with auth, persistence, deployment). Read its
  `README.md` for the full walkthrough.
- `examples/example_research_project/`: research investigation loop
  (cited survey plus defensible recommendation on
  retrieval-augmentation vs hallucination). Heavier on branching and
  replan. Read its `README.md`.
- `examples/example_child_loop_tree/`: a materialized recursive
  child-loop tree (one parent loop with a `L001.01-...` subloop under
  its `_loops/`), exercising `loop.meta.yaml`, `child_loops`, the
  `INDEX.yaml` files, and the isomorphic per-loop layout. Read its
  `README.md`.
- `examples/example_v2_lightweight/`: the two-artifact opt-in v2 minimum.
- `examples/example_v2_persistent/`: v2 goal, activated plan, journal, and
  canonical resume fixture.

The three v1 examples contain YAML plan/checkpoint artifacts; the two v2
examples contain JSON core artifacts. Representative checks are:

```bash
python3 scripts/validate_loop_plan.py          examples/example_product_delivery/loop.plan.yaml
python3 scripts/validate_checkpoint.py         examples/example_product_delivery/checkpoint.yaml \
        --plan examples/example_product_delivery/loop.plan.yaml
python3 scripts/validate_loop_plan.py          examples/example_research_project/loop.plan.yaml
python3 scripts/validate_checkpoint.py         examples/example_research_project/checkpoint.yaml \
        --plan examples/example_research_project/loop.plan.yaml
python3 scripts/render_dag.py                  examples/example_product_delivery/loop.plan.yaml
```

### The run-id directory at runtime

`create-loop` is a control artifact generator, not a long-running
process. When the skill is invoked on a real task, it creates a run-id
directory and populates it from `templates/`:

| file | template | purpose |
|------|----------|---------|
| `loop.plan.yaml` | `templates/loop.plan.yaml` | the governance DAG the loop executes against |
| `task_profile.yaml` | `templates/task_profile.yaml` | Layer 0 control profile output |
| `node.contract.yaml` | `templates/node.contract.yaml` | per-node execution contract (gate, retry budget, attempts) |
| `checkpoint.yaml` | `templates/checkpoint.yaml` | durable snapshot a fresh session resumes from |
| `evidence.ledger.yaml` | `templates/evidence.ledger.yaml` | append-only gate verdicts (`pass` / `fail` / `inconclusive`) |
| `decision.log.md` | `templates/decision.log.md` | mid-run decisions (architecture, operational) |
| `run.log.md` | `templates/run.log.md` | append-only run narrative |
| `handoff.md` | `templates/handoff.md` | handoff doc written at each stop so a fresh agent can pick up |
| `closeout.md` | `templates/closeout.md` | end-of-run summary |
| `human_decision_request.md` | `templates/human_decision_request.md` | when the loop must ask the user to decide: a context-complete, YAML-answerable Human Decision Package (options, trade-offs, recommendation) rather than a bare question |
| `loops.index.yaml` | `templates/loops.index.yaml` | tree index over the run root (one per `_loops/`) |

The append-only event log referenced by `checkpoint.event_log_ref` is
the lowest-level replay primitive (per `references/concepts.md` §7). All
of these are plain files. A fresh agent resumes by reading the
checkpoint, verifying evidence, computing the ready set from the
dependency graph, and dispatching the next node.

### Per-loop layout (recursive)

A run is a **tree of isomorphic per-loop directories**, not a single
flat directory. The top-level run root lives at
`.agents/loops/L<seq>-<slug>/` and contains the artifacts above plus:

- `loop.meta.yaml`: the per-loop control profile (see
  `references/recursive_loops.md` §6 for the exact field set).
- `artifacts/`: node-produced outputs the loop references from `produces`.
- `_loops/INDEX.yaml`: the tree index over materialized child loops
  (one row per child).
- `_loops/L<seq>.<seq>-<slug>/`: a **directory-materialized child
  loop** for any non-trivial child work promoted past the Admission Gate.
  Every child follows the same per-loop shape, recursively: its own
  `loop.meta.yaml`, `loop.plan.yaml`, `checkpoint.yaml`,
  `evidence.ledger.yaml`, logs, `closeout.md`, `artifacts/`, its own
  `_loops/` for further nesting, and its own `_loops/INDEX.yaml`.
- `nodes/<id>/node.runtime.yaml`: per-node runtime hosting record
  for nodes running their work on the lightweight `subgraph` tier
  (`action` / `subgraph` / `subloop`, see
  `references/subgraph_subloop_policy.md`).

The per-loop layout is **isomorphic**: the root loop and every child
loop under `_loops/` follow the same shape. Inline `subgraph` /
`allow_subgraph` fields on a node stay the lightweight path; promotion
to a directory-materialized subloop is governed by the Admission Gate in
[`references/recursive_loops.md`](references/recursive_loops.md) §8.
The three-tier decision tree lives in
[`references/subgraph_subloop_policy.md`](references/subgraph_subloop_policy.md) §11.

### Slash commands (optional, ergonomic)

Four commands map to the recurring entry points, so you do not hand-write a
prompt each time. They ship at the repo root (`.opencode/command/` and
`.claude/commands/`) because `npx skills add` installs only the skill directory;
copy them in with `./install-commands.sh` (or by hand):

| Command | Mode | Does |
|---------|------|------|
| `/loop-new "<goal>"` | A | Charter interview → `loop.plan v0` |
| `/loop-run [node]` | B | advance the next ready node |
| `/loop-resume [dir]` | C | reconstruct from checkpoint + event log |
| `/loop-status [id]` | — | read-only snapshot (goal, active node, blockers) |

All four accept `--protocol v2`; v1 remains the default. Existing Loop
artifacts override guessing, and an explicit selector must agree with them.

```bash
./install-commands.sh                       # both runtimes, current project
./install-commands.sh --runtime opencode --global
./install-commands.sh --skill-root /path/to/create-loop
```

The commands-only installer must bind the rendered commands to one real
installed Skill. It checks the project or global `.agents` and `.claude` Skill
locations, deduplicates equivalent real paths, and rejects zero or multiple
distinct matches. Use `--skill-root <dir>` for any other location or to resolve
an ambiguity; the selected root must contain `SKILL.md` and every script used by
the canonical commands.

Uninstalled, the skill still activates from natural language ("create a loop",
"resume the loop", "loop status"). Full spec:
[`references/command_system.md`](references/command_system.md).

---

## 3. Maintain

`tests/acceptance_tests.md` is the historical v1 compatibility green-path
specification. The executable cross-protocol gate is `tests_py/`; the current
repository delivery gate additionally runs the Node installer suite.

```bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd <package-root>            # the directory containing SKILL.md

echo "== scripts compile =="
python3 -B - <<'PY'
import pathlib
import tokenize

for pattern in ("scripts/*.py", "scripts/checks/*.py"):
    paths = sorted(pathlib.Path().glob(pattern))
    if not paths:
        raise SystemExit(f"no Python sources matched: {pattern}")
    for path in paths:
        with tokenize.open(path) as source:
            compile(source.read(), str(path), "exec")
PY

echo "== SKILL.md line budget <= 1000 =="
test "$(wc -l < SKILL.md)" -le 1000

echo "== schemas parse as JSON =="
# v1 uses Draft-07; v2 uses Draft 2020-12.

echo "== templates validate =="
python3 scripts/validate_loop_plan.py            templates/loop.plan.yaml
python3 scripts/validate_loop_plan.py --kind node_contract templates/node.contract.yaml
python3 scripts/validate_loop_plan.py --kind evidence_ledger templates/evidence.ledger.yaml
python3 scripts/validate_checkpoint.py           templates/checkpoint.yaml

echo "== examples validate (plan + checkpoint) =="
for ex in example_product_delivery example_research_project; do
  python3 scripts/validate_loop_plan.py  "examples/$ex/loop.plan.yaml"
  python3 scripts/validate_checkpoint.py "examples/$ex/checkpoint.yaml" \
          --plan "examples/$ex/loop.plan.yaml"
done

echo "== render_dag emits mermaid + dot =="
python3 scripts/render_dag.py examples/example_product_delivery/loop.plan.yaml | \
  grep -q '```mermaid'
```

Use `tests/acceptance_tests.md` when changing v1 compatibility behavior, and
run `python -m unittest discover -s tests_py` for executable v1/v2 regression.

Rejection of bad inputs (schema errors, broken dependency edges,
out-of-enum statuses) is covered separately in
[`tests/failure_mode_tests.md`](tests/failure_mode_tests.md). Run those
when you change the validators or the schemas.

Executable cross-protocol regression lives under `tests_py/`:

```bash
python -m unittest discover -s tests_py
python tests_py/test_experiment_workspace.py
python tests_py/test_experiment_evaluation.py
python tests_py/test_experiment_execution_guard.py
python tests/experiments/freeze_experiment.py --check
python tests/experiments/experiment_harness.py validate
python tests/experiments/experiment_harness.py plan
python tests/experiments/deterministic_runner.py --protocol v1
python tests/experiments/deterministic_runner.py --protocol v2
```

The Phase 5 tools freeze/check source and instrument bindings, build concrete
reality-bound workspaces and presented artifacts, enforce the preregistered
blind A/B assignment, rerun the frozen deterministic validator catalog against
the frozen v1 and candidate v2 sources, evaluate the frozen deterministic smoke
metric authoritatively, keep other gate formulas explicitly
`insufficient-data`, and provide an immutable grant/ledger/receipt/spend-summary
guard. Grants and usage receipts bind model, reasoning effort, tool profile,
adapter/provider identity, raw token usage, and wall time. Pricing, billable-token,
and USD fields are intentionally absent or `not-measured`. The runner uses user-site PyYAML only
for v1; v2 disables user-site imports. Its tool profile is a validated
declaration, not an OS capability or network sandbox.
Validation still reports planned runs separately from validated traces.

Phase 5 now includes an opt-in six-pair Pilot execution chain. Authority-first
adapter and runner paths validate the canonical grant and a separate OS-enforced
provider-only network boundary before reading credentials, initializing or
reserving ledger budget, or launching Codex. Raw provider request identity and
token usage, workspace/evidence manifests, receipts, settlement, traces, oracle
results, and blind-review seals are cross-validated. The repository remains
fail-closed because the Linux reviewer Codex `0.144.1` identity and authenticated
OS-level network boundary are unresolved, so no real provider call has occurred.
Pilot/hard limits are frozen at 23 calls / 1.33M tokens / 20,100 seconds and 126
calls / 7.56M tokens / 113,400 seconds; USD remains `not-measured`. The legacy
42-pair / 84-run plan is prospective only. `formal_execution_enabled` remains
false, and these instruments establish neither a default-version decision nor
v2 superiority.

### House rules

- **Select the protocol before editing.** v1 vocabulary is canonical in
  `references/loop_plan_spec.md` and `references/state_model.md`, with the
  compatibility Python validator authoritative. v2 shape is canonical in its
  Draft 2020-12 schemas after `references/protocol_v2.md` defines semantics.
- **`SKILL.md` stays lean.** Depth lives in `references/`. The skill
  entrypoint must not exceed 1000 lines (enforced by
  `tests/acceptance_tests.md` §5).
- **Vocabulary is locked in the references.** `references/loop_plan_spec.md`
  and `references/state_model.md` are the single source of truth for
  field names, enums, and transitions. Anything that disagrees with
  them is wrong.

### Optional self-evolution integration

`create-loop` does not require any other skill to work. If your project
already runs the `self-evolution` agent skill (a `.agents/knowledge/`
directory exists), verified reusable findings from a run can be
promoted to that knowledge base through the `[LOOP]` channel marker.
The full adapter spec, including what must NOT cross the boundary
(checkpoint snapshots, event logs, retry counters, status churn), is in
[`references/self_evolution_integration.md`](references/self_evolution_integration.md).

If `.agents/knowledge/` is absent, the skill is fully self-contained.
Findings stay in the run's `closeout.md`. Nothing breaks.

---

## 4. Extend

The vocabulary docs are the single source of truth. Anything you add
must key off them.

### Add a new gate kind, node kind, or status

1. Edit `references/loop_plan_spec.md` and `references/state_model.md`
   to add the new token to the canonical enum and Glossary.
2. Update the matching `schemas/*.json` so the new value is in the
   `enum` (or new sub-schema) the validator checks against.
3. Update the validator scripts in `scripts/` so they accept the new
   value where appropriate (and reject the old closed set everywhere
   else).
4. Add a fixture under `tests/failure_mode_tests.md` that exercises
   the new value's green-path use, plus an invalid-input fixture to
   prove the validator catches misuse.
5. Re-run the full acceptance gate
   (`tests/acceptance_tests.md#full-green-sequence`).

### Add a recursive-loop field, INDEX entry, or tier token

Recursive-loop vocabulary lives in two extra reference docs that key off
`loop_plan_spec.md` and `state_model.md`. Touch them when you change
anything in the child-loop or subgraph layer:

1. [`references/recursive_loops.md`](references/recursive_loops.md) is the
   authoritative source for the `loop.meta.yaml` field set, the
   `child_loops` node-field shape, the per-loop checkpoint additions,
   the `_loops/` directory convention, the Admission Gate, the
   `L<seq>-<slug>/` naming, and the `INDEX.yaml` schema.
2. [`references/subgraph_subloop_policy.md`](references/subgraph_subloop_policy.md)
   is the authoritative source for the three-tier model (`action`,
   `subgraph`, `subloop`), the subgraph's own lighter status enum, the
   `node.runtime.yaml` field set, and the Promotion Gate.
3. Update the matching `schemas/loop.meta.schema.json`,
   `schemas/loops.index.schema.json`, or
   `schemas/node.runtime.schema.json` so the validator enforces the new
   shape, and add a `templates/` entry plus a green-path fixture in
   `tests/failure_mode_tests.md`.
4. Re-run the full acceptance gate
   (`tests/acceptance_tests.md#full-green-sequence`).

### Add a new template or reference doc

1. Drop the file under `templates/` (for run artifacts) or
   `references/` (for vocabulary, models, or external research).
2. Register it in `SKILL.md`'s reference map so the agent knows to read
   it. Update any example that should reference the new doc.

### Add another worked example

1. Create `examples/<your_example>/` with three files: a
   `loop.plan.yaml`, a `checkpoint.yaml`, and a `README.md` walking a
   reader through the design choices.
2. The plan and checkpoint must validate against the schemas and pass
   the acceptance gate unchanged.
3. Add the example to the loop in `tests/acceptance_tests.md` §3 so the
   green sequence picks it up alongside `example_product_delivery` and
   `example_research_project`.

### Notes

- Licensing and attribution for cited research (durable execution,
  DAG/multi-agent orchestration, evidence gates) are documented in the
  reference docs themselves.
- The skill has no real background runtime. It is filesystem-based and
  relies on manual re-invocation (your host loads the skill, the agent
  reads the checkpoint, picks the next node). This is the deliberate
  degraded-mode design explained in `references/concepts.md` §10.

---

## License

`create-loop` uses custom source-available Business Source License terms in
[`LICENSE`](LICENSE). They are not the standard SPDX `BUSL-1.1` text.

- Free for personal use, open-source projects (derivatives must also be open
  source), companies with fewer than 10 employees, and educational/research
  use.
- Companies with 10+ employees using the original skill in production, or
  anyone offering it as a hosted/managed service, need a commercial license.
- Derivative works must be public and open source; they may not be sold.
- **Change Date 2030-07-02:** on that date the work converts to the
  Apache License 2.0 and all restrictions are removed.

See [`LICENSE`](LICENSE) for the controlling text and FAQ in an installed payload.
