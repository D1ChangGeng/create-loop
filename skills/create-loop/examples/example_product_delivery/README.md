# Worked example — software product delivery loop

A complete, schema-valid `create-loop` run for a realistic multi-session
software delivery:

> **Goal:** *Ship a REST API service with auth, persistence, and a deployment.*
> **Deliverable class:** `code_impl` / `production_launch`.

This directory contains three artifacts you can validate and render as-is:

| file | what it is |
|------|------------|
| [`loop.plan.yaml`](./loop.plan.yaml) | the `loop.plan v0` — the design-invariant governance DAG plus one materialised runtime subgraph |
| [`checkpoint.yaml`](./checkpoint.yaml) | a mid-run durable snapshot a blank session resumes from |
| `README.md` | this walkthrough |

---

## 1. The three-layer model, as seen in this plan

`create-loop` splits the work into three layers (see
[`references/concepts.md` §8](../../references/concepts.md)). All three are visible here:

**Layer 0 — the Charter interview, expressed as the first node.**
The interview is not an external step; it is the loop's first governance node,
**`N0_charter`** (`kind: gate`, `requires: []`, `gate.kind: human_approval`). Its
job is to produce the control profile (`artifacts/task_profile.yaml`) — task
type, end-state, success/failure criteria, the risk & approval boundary, the
persistence requirements. It does **not** try to pin down which auth scheme or
which database to use; those are routed forward as unknowns.

**Layer 1 — `loop.plan v0`: the design-invariant governance nodes only.**
Every top-level node carries `design_invariant: true`. These are the nodes that
are *known at design time AND invariant for the task class* — they would appear
for any auth+persistence+deploy service, regardless of the eventual tech choices:

```
N0_charter → N1_discovery ┐
             N2_risk_screen ┘→ N3_feasibility → N4_requirements_baseline →
N5_architecture → N6_verification_plan → N7_implementation → N8_review →
N9_release_approval → N10_deploy → N11_handoff → N12_closeout
                         (N10c_rollback_compensation pairs with N10_deploy)
```

No top-level node names a vendor, a DB engine, an endpoint, or a file. "That an
architecture exists" is invariant (`N5_architecture`); *which modules it names*
lives in the artifact, not the graph.

**Layer 2 — the runtime subgraph inside `N7_implementation`.**
`N7_implementation` sets `allow_subgraph: true` and carries a **populated
`subgraph`** (`parent_ref: N7_implementation`, `plan_version: 2`). Its children
are `design_invariant: false` — they were only knowable once `N5_architecture`
named the modules:

| child node | kind | gate |
|------------|------|------|
| `impl_auth` | milestone | `test` |
| `impl_persistence` | milestone | `test` |
| `impl_api` | milestone | `test` |
| `impl_integration_gate` | gate | `test` |

This is recursion made concrete: `N7_implementation` cannot reach `completed`
until every subgraph child is terminal **and** its own `test` gate passes. The
runtime-discovered specifics (JWT bearer auth, the persistence layer + migrations,
the REST endpoints) are confined to this subgraph and never pollute the top level.

---

## 2. Which nodes run in parallel

Parallelism is derived from real artifact dependencies, not authored order
(see [`concepts.md` §2](../../references/concepts.md)).

- **Top level:** `N1_discovery` ∥ `N2_risk_screen`. Both `require` only
  `N0_charter`, share no other dependency, and are marked
  `parallelizable: true`. They fan back in at `N3_feasibility`, which lists
  *both* in its `requires` and is therefore `ready` only when both are
  `completed`.
- **Inside the subgraph:** `impl_auth` ∥ `impl_persistence`. Both have
  `requires: []` within the fragment and `parallelizable: true`; they fan in at
  `impl_api` (which requires both), which then feeds `impl_integration_gate`.

---

## 3. Where the gates and the approval are

Evidence gates (a node cannot reach `completed` until its gate passes):

- **Evidence / test gates:** `N3_feasibility`, `N7_implementation`, and all four
  subgraph children use `kind: test`. `N8_review` uses `kind: evaluator_optimizer`
  (`threshold: 0.85`, generate→critique→revise). `N6_verification_plan`,
  `N10_deploy`, and `N12_closeout` use `kind: automated_check`.
  `N1_discovery`, `N2_risk_screen`, `N4_requirements_baseline`, `N5_architecture`
  use `kind: llm_judge` with a scored threshold. `N11_handoff` uses the cheapest
  gate, `artifact_exists`.
- **The approval gate:** **`N9_release_approval`** is `kind: approval`,
  `assignee: user`, and is **gate-exempt** (`gate: null`) — an approval node
  self-gates via its human handoff. It is what stands between review and any
  production side-effect.
- **Saga compensation:** **`N10_deploy`** is the side-effecting deploy;
  **`N10c_rollback_compensation`** (`kind: compensation`, `requires:
  [N10_deploy]`, `gate: null`) is its paired undo. At runtime its
  `node.contract.compensation_of` = `N10_deploy`.

---

## 4. How to resume from the checkpoint

`checkpoint.yaml` is a mid-run snapshot. Its `node_states` keys match the 14
top-level node ids exactly, and `plan_id` / `plan_version` match the plan. Where
the run stands:

- `N0_charter` … `N8_review` — **completed**.
- `N9_release_approval` — **waiting_user** (open human release gate), listed in
  `pending_approvals` with token `appr-N9-7f3c9a12`.
- `N10_deploy` — **blocked**, recorded in `blocked` with a reason (needs the
  `N9_release_approval` approval *and* a production DB credential in the secret store).
- `N10c_rollback_compensation`, `N11_handoff`, `N12_closeout` — **pending**.
- `ready_set: []` — nothing is dispatchable while `N9_release_approval` waits on the user.

A fresh session with no chat memory resumes by running the recovery protocol in
[`references/state_model.md` §"Resume from a blank session"](../../references/state_model.md):

1. **Acquire / confirm the run** via the `run_id` directory (single-flight).
2. **Read state** — load this checkpoint for `plan-product-delivery-0007`,
   `plan_version: 1`.
3. **Verify evidence** — for each `completed` node (`N0_charter`…`N8_review`),
   confirm a passing `evidence.ledger` entry at its `evidence_ref`; any missing
   one is demoted to `verifying`.
4. **Verify consistency** — recompute readiness from the graph; confirm no node
   is `running` (none is here).
5. **Check termination** — `iteration: 37` < `60`, `cost_units_spent: 1142` <
   `2000`; no `failure_criteria` hold. Continue.
6. **Identify ready nodes** — the recomputed `ready_set` is empty.
7. **Handle open handoffs** — `pending_approvals` is non-empty, so surface
   `N9_release_approval` (token `appr-N9-7f3c9a12`) to the user first.
8. On approval, provision the DB credential to clear `N10_deploy`'s
   precondition, then dispatch `N10_deploy` (log the side-effect; keep
   `N10c_rollback_compensation` armed), then `N11_handoff`, then `N12_closeout`.

This is exactly what `checkpoint.yaml`'s `next_suggested_action` advises — but
note it is advisory; the ready set is always recomputed from the graph, never
trusted from the snapshot.

---

## 5. Validate + render (exact commands)

Run from the skill root (`create-loop/create-loop/`):

```bash
# 1. Validate the plan (structure + graph rules R1–R8). Exit 0 = valid.
python3 scripts/validate_loop_plan.py examples/example_product_delivery/loop.plan.yaml

# 2. Validate the checkpoint against the plan (R6 consistency). Exit 0 = valid.
python3 scripts/validate_checkpoint.py \
  examples/example_product_delivery/checkpoint.yaml \
  --plan examples/example_product_delivery/loop.plan.yaml

# 3. Render the DAG to Mermaid + Graphviz DOT (prints both blocks). Exit 0.
python3 scripts/render_dag.py examples/example_product_delivery/loop.plan.yaml
```

All three exit `0`. The render emits a ```` ```mermaid ```` block (with the
`N7_implementation` subgraph shown as a Mermaid `subgraph` and
`N9_release_approval` drawn as a stadium/approval shape) followed by a
`digraph loop_plan { … }` DOT block.
