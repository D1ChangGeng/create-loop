# Worked Example — Research Investigation Loop

A complete, schema-valid `create-loop` for a **long-running research
investigation**. Nothing is built or shipped here: the loop gathers sources,
appraises evidence, frames hypotheses, runs a comparative analysis, verifies
findings, synthesises a survey, and clears a peer-review gate before a human
approves the recommendation.

Contrast with [`../example_product_delivery/`](../example_product_delivery/),
which builds and ships software. This example is deliberately a different
domain and leans harder on **branching and replan**.

## The scenario

> **Goal.** Produce a rigorous, cited survey and a defensible recommendation on
> which retrieval-augmentation strategy best reduces hallucination in
> long-context question answering.

- **Deliverable class:** `research_report` (a survey + recommendation + evidence
  bundle) — not a code artifact.
- **What "done" means (`true_intent`):** the recommendation must survive expert
  peer review. The value is the strength and transparency of the evidence, not
  merely naming a winner.
- **Bounds:** 30 iterations, 600 cost units, no wall-clock cap (research is
  bounded by cost/iteration, not a clock).

## The three-layer model, mapped to real node ids

| Layer | What it is | Where it lives in this example |
|-------|------------|--------------------------------|
| **Layer 0 — Charter** | The Loop Startup interview, expressed as the *first governance node* (not an external step). | `N0_charter` (`kind: gate`, `human_approval`, `requires: []`). |
| **Layer 1 — governance DAG** | Design-time-invariant research phases. Every top-level node has `design_invariant: true`. | `N1_scoping` → `N2_source_gathering` / `N2b_protocol_preregistration` → `N3_evidence_appraisal` → `N4_hypothesis_framing` → `N5_experiment_or_analysis` → `N6_findings_verification` → `N6b_route_on_findings` → `N7_synthesis` → `N8_peer_review` → `N9_recommendation_approval` → `N10_handoff` → `N11_closeout`. |
| **Layer 2 — runtime subgraph** | Work only knowable once a node runs: *which* datasets, *which* comparisons. Confined to a subgraph with `design_invariant: false`. | The `subgraph` inside `N5_experiment_or_analysis`: `S5a_setup_analysis_env` → (`S5b_analyze_dataset_A` ∥ `S5c_run_comparison_B`) → `S5d_validate_result_C`. |

Which papers to read, which datasets to score, and which comparisons to run are
**not** knowable at authoring time, so they never appear at the top level. They
materialise as the isomorphic subgraph inside `N5_experiment_or_analysis`
(`parent_ref: N5_experiment_or_analysis`).

## Where the branch and the replan are

- **Branch:** `N6b_route_on_findings` (`kind: branch`) is a conditional router.
  It samples a `self_consistency` gate for agreement on whether the evidence is
  conclusive, then routes: **conclusive → `N7_synthesis`**, **inconclusive →
  replan `N5_experiment_or_analysis` for more analysis**.
- **Replan path (currently active):** `N6_findings_verification` (`kind: gate`,
  `step_verifier`, threshold `0.85`) **failed at 0.71** because dataset A was
  not length-matched (an uncontrolled confound). Its `on_failure: replan` put
  `N5_experiment_or_analysis` into `blocked` — the loop is re-materialising N5's
  subgraph with a length-matched control arm before re-verifying. A second
  replan edge also exists at `N8_peer_review` (`on_failure: replan`), which
  sends a failed peer review back to regenerate `N7_synthesis`.

## What runs in parallel

- **Top level:** `N2_source_gathering` and `N2b_protocol_preregistration` both
  depend only on `N1_scoping` and not on each other, so both carry
  `parallelizable: true` and dispatch concurrently. They fan back in at the
  `N3_evidence_appraisal` gate (which `requires` both).
- **Inside the subgraph:** `S5b_analyze_dataset_A` and `S5c_run_comparison_B`
  both depend only on `S5a_setup_analysis_env`, are marked
  `parallelizable: true`, and are merged by the `join` node
  `S5d_validate_result_C`.

## Where the gates are

| Node | `kind` | gate | why |
|------|--------|------|-----|
| `N0_charter` | gate | `human_approval` | charter sign-off |
| `N2_source_gathering` | milestone | `llm_judge` 0.8 | source relevance |
| `N3_evidence_appraisal` | gate | `llm_judge` 0.8 | methodological grading (`on_failure: replan`) |
| `N4_hypothesis_framing` | milestone | `self_consistency` 0.75 | hypotheses well-formed |
| `N5_experiment_or_analysis` | milestone | `llm_judge` 0.8 | analysis plausibility |
| `N6_findings_verification` | gate | `step_verifier` 0.85 | independent reproduction (**failed → replan**) |
| `N6b_route_on_findings` | branch | `self_consistency` 0.8 | route agreement |
| `N7_synthesis` | milestone | `evaluator_optimizer` 0.85 | generate→critique→revise |
| `N8_peer_review` | gate | `llm_judge` 0.9 | peer-review rubric (`on_failure: replan`) |
| `N9_recommendation_approval` | approval | `null` | approval self-gates via its human_approval handoff |
| `S5d_validate_result_C` | join | `step_verifier` 0.85 | merged-result validation |

The **approval gate** is `N9_recommendation_approval` — its `gate` is `null`
because `approval` nodes are gate-exempt (they self-gate through the human
handoff surfaced in `checkpoint.pending_approvals`).

## How to resume from the checkpoint

`checkpoint.yaml` is a mid-run snapshot: `N0`–`N4` completed, N5's subgraph ran,
but `N6_findings_verification` failed and `N5_experiment_or_analysis` is
`blocked` on a replan. A fresh session with no chat memory resumes by reading
persistent state only (see `references/state_model.md` §"Resume from a blank
session"):

1. Read `checkpoint.yaml`: `node_states`, `ready_set` (empty), `blocked`,
   `iteration: 17`, `cost_units_spent: 428.0`.
2. Verify evidence: for each `completed` node, confirm a passing
   `evidence.ledger` entry at its `evidence_ref`; any `completed` node lacking
   passing evidence is demoted to `verifying`.
3. Honour the `blocked` entry: `N5_experiment_or_analysis` needs a superseding
   subgraph fragment (a new fragment `plan_version`) with a length-matched
   control arm, then re-run `S5b_analyze_dataset_A` and `S5c_run_comparison_B`,
   re-join at `S5d_validate_result_C`, and re-run the `N6_findings_verification`
   gate.
4. Do **not** advance to `N6b_route_on_findings` until `N6_findings_verification`
   records a passing verdict — exactly what `next_suggested_action` says.

`next_suggested_action` is an advisory hint; the dependency graph plus recorded
statuses are the source of truth.

## Validate and render

Run from the skill root (`/root/create-loop/create-loop/`):

```bash
# 1. Validate the plan (structure + graph rules R1–R8, recurses into the subgraph)
python3 scripts/validate_loop_plan.py examples/example_research_project/loop.plan.yaml

# 2. Validate the checkpoint against the plan (R6 consistency: keys/ids/versions match)
python3 scripts/validate_checkpoint.py \
  examples/example_research_project/checkpoint.yaml \
  --plan examples/example_research_project/loop.plan.yaml

# 3. Render the DAG (prints a Mermaid block and a Graphviz DOT block)
python3 scripts/render_dag.py examples/example_research_project/loop.plan.yaml
```

All three exit `0`. `render_dag.py` draws the top-level chain, the parallel
`N2`/`N2b` fork, the `N6b_route_on_findings` branch diamond, the
`N9_recommendation_approval` approval stadium, and the `N5_experiment_or_analysis`
subgraph as a nested Mermaid `subgraph` / DOT cluster.

## Files

- `loop.plan.yaml` — the 14-node top-level governance DAG (all
  `design_invariant: true`) plus the runtime subgraph inside
  `N5_experiment_or_analysis`.
- `checkpoint.yaml` — a mid-run snapshot with `N5_experiment_or_analysis`
  `blocked` on an in-flight replan triggered by `N6_findings_verification`.
- `README.md` — this file.
