# create-loop

A meta-skill for long-running AI work. You give it a short goal for a task
that cannot finish in one sitting, and it produces a `loop.plan`: a recursive
execution-control DAG plus evidence gates plus a persistent state contract
that a fresh agent can resume from a blank session, with zero prior chat
memory. The paradigm is "write the loop, not the prompt."

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

Two principles govern how the plan behaves at runtime. **Autonomy-first**:
the loop resolves branches, unknowns, and blockers by spawning exploration
and diagnostic subgraphs and gathering evidence — it asks the user only at
genuine boundaries (goal, authorization, irreversibility, cost, risk, value).
**Live Loop Semantics**: the top-level goal and governance skeleton stay
stable while the execution path grows from evidence — evidence-driven
completeness growth, not scope creep.

Full reasoning lives in `references/concepts.md`. The vocabulary
(vocabulary, enums, transitions) lives in `references/loop_plan_spec.md`
and `references/state_model.md`.

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

The validator and renderer scripts use Python 3.8+ and PyYAML.

```bash
# PyYAML is required by the scripts.
python3 -c "import yaml; print('yaml', yaml.__version__)"
# -> yaml 5.x or newer. If this fails:
pip install pyyaml
```

Optional, for the extra metaschema validation in acceptance tests:

```bash
python3 -c "import jsonschema; print('jsonschema', jsonschema.__version__)"
# -> jsonschema 4.x. If absent, the scripts degrade gracefully:
#    schema validation still runs through PyYAML + the validator scripts,
#    only the Draft-07 metaschema self-check is skipped.
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

### Validate a plan

```bash
# Default kind: loop_plan (the top-level governance DAG).
python3 scripts/validate_loop_plan.py <plan.yaml>

# Per-node contract.
python3 scripts/validate_loop_plan.py --kind node_contract <node.contract.yaml>

# Append-only evidence ledger.
python3 scripts/validate_loop_plan.py --kind evidence_ledger <evidence.ledger.yaml>
```

Exit `0` means valid. Nonzero exit prints the rule the input violated.

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

Two end-to-end examples ship under `examples/`:

- `examples/example_product_delivery/`: software delivery loop (REST
  API service with auth, persistence, deployment). Read its
  `README.md` for the full walkthrough.
- `examples/example_research_project/`: research investigation loop
  (cited survey plus defensible recommendation on
  retrieval-augmentation vs hallucination). Heavier on branching and
  replan. Read its `README.md`.

Each example contains a `loop.plan.yaml` and a `checkpoint.yaml` that
both pass the validators:

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

The append-only event log referenced by `checkpoint.event_log_ref` is
the lowest-level replay primitive (per `references/concepts.md` §7). All
of these are plain files. A fresh agent resumes by reading the
checkpoint, verifying evidence, computing the ready set from the
dependency graph, and dispatching the next node.

---

## 3. Maintain

The acceptance gate is the authoritative green-path check. The full
runnable block lives in `tests/acceptance_tests.md` under
[Full green sequence](tests/acceptance_tests.md#full-green-sequence):

```bash
set -euo pipefail
cd <package-root>            # the directory containing SKILL.md

echo "== scripts compile =="
python3 -m py_compile scripts/*.py

echo "== SKILL.md line budget < 600 =="
test "$(wc -l < SKILL.md)" -lt 600

echo "== schemas parse as JSON and are valid Draft-07 =="
# (4 files under schemas/)

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

If you want the byte-for-byte version, paste the block from
`tests/acceptance_tests.md`. Reaching the `ALL GREEN` line means the
package passes the gate.

Rejection of bad inputs (schema errors, broken dependency edges,
out-of-enum statuses) is covered separately in
[`tests/failure_mode_tests.md`](tests/failure_mode_tests.md). Run those
when you change the validators or the schemas.

### House rules

- **Schemas are the machine contract.** If you change a field name,
  enum, or required-attribute, update the matching
  `schemas/*.json` first, then the templates in `templates/` and the
  examples in `examples/`, then re-run the acceptance gate.
- **`SKILL.md` stays lean.** Depth lives in `references/`. The skill
  entrypoint must stay strictly under 600 lines (enforced by
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

`create-loop` is licensed under the **Business Source License 1.1** (BSL-1.1),
the same license as the companion [`self-evolution`](https://github.com/D1ChangGeng/self-evolution)
skill.

- Free for personal use, open-source projects (derivatives must also be open
  source), companies with fewer than 10 employees, and educational/research
  use.
- Companies with 10+ employees using the original skill in production, or
  anyone offering it as a hosted/managed service, need a commercial license.
- Derivative works must be public and open source; they may not be sold.
- **Change Date 2030-07-02:** on that date the work converts to the
  Apache License 2.0 and all restrictions are removed.

See [`LICENSE`](../../LICENSE) for the full text and FAQ.
