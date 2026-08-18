---
description: "Read validator-engine knowledge before modifying files in this scope"
globs:
  - "skills/create-loop/scripts/**"
  - "skills/create-loop/schemas/**"
  - "skills/create-loop/tests/**"
  - "skills/create-loop/tests_py/**"
---
Before making changes in this area, read `.agents/knowledge/domains/validator-engine.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- Select v1 or v2 before editing: v1 compatibility vocabulary lives in references plus `checks/__init__.py`; v2 shape authority lives in its Draft 2020-12 schemas.
- v1 keeps historical R-family identifiers; v2 uses named invariant families and must not extend the R-number sequence.
- Validators and projectors are read-only over authority artifacts; only `render_resume.py` may replace generated `resume.json`. Migration dry-runs stage outside Loop ancestry, while real migration publishes a new sibling directory atomically.
- Every retained invariant needs executable reject and control coverage under `tests_py/`; Markdown scenarios are specifications, not the regression gate.
- Test the artifact shape the runtime actually writes, not only its template; calibrate any fixture/measurement harness against a known reject and control before trusting a surprising result.
- V1 recovery authority is field-level: plan, JSONL event log, ledger, and checkpoint each own different facts; projection agreement proves consistency, never semantic completion.
- Check-specific v2 evidence binds the complete canonical check definition, and relation effects are derived dynamically from current immutable evidence.
- Ordinary v2 replans require an old-plan `plan_replacement` decision whose `plan_change` binds exact old/new versions and hashes; its active unchallenged evidence refs exactly equal activation refs.
- The lightweight durability bridge is control-only, uses explicit `plan_change:null`, and cannot change the goal binding or node graph.
- Artifact evidence retains an immutable path/hash binding independent of the live registry; the canonical projector and resume renderer verify it against workspace reality.
- Output paths share one canonicalizer and Windows-aware identity across projector, validator, and migration; directories are deliverables but only files may carry `sha256`.
- v1 sequence gaps are valid but negative/non-monotonic values are not; inactive fresh failures cannot hide behind older passes, and blind review requires withheld producer-claim access.
- v1 event records use the Schema-wide exact field/type envelope; only pre/post/reopen carry transitions, mutation evidence must resolve to the same node and predate the mutation, and present loop metadata receives its full validator in the whole-loop gate.
- Optional `jsonschema` may add v1 diagnostics but cannot supply installed safety; hand-written validators must reject every malformed field/type that completion or recovery consumes, including YAML non-finite numbers and non-string mapping keys, before cross-file consumers run.
- Deterministic replay executes the complete captured source byte map from a private subprocess tree; parent-worktree validator/helper/schema/fixture swaps must not affect executed bytes. Migration rejects source symlinks and Windows reparse points before traversal.
- Experiment validation distinguishes the legacy deterministic 84-run plan from the six-pair Pilot and from validated evidence. Blind A/B labels follow preregistered assignment, and deterministic-suite claims are replayed from frozen source/catalog/runner bytes.
- Pilot authority is two-stage: pre-calibration static freeze, raw-derived calibration evidence, then a final freeze for producer/reviewer grants. Role, canonical execution root, freeze phase, and authority hashes must be revalidated before launch.
- The guard is wired into adapter/runner reservation and settlement, review sealing, and Pilot evaluation. Raw request identity, token usage, workspace/population/evidence manifests, receipts, oracles, and review-isolation evidence must reconcile end to end.
- Replay snapshots are process-local capabilities: public trace validation replays current authority, and Pilot final reconciliation must take one ordered, locked multi-root cut before reporting.
- The authorized Pilot/hard call-token-time ceilings do not satisfy execution readiness. Missing Linux reviewer Codex `0.144.1` identity or authenticated provider-only OS boundary must stop before credentials, ledger mutation, or process launch.
- The legacy v1 network prefix is host-outer only: producer/calibration may use it, but reviewer readiness must fail before WSL until a guest-local role/platform contract binds the insertion point and probe runtime.
- Role-bound readiness validates only the effective CLI/topology (calibration maps to producer); role-less readiness validates the complete Pilot. Freeze/grant authority must always use the complete gate, and only the actual launcher may narrow by role.
- Provider-call timestamps and monotonic `wall_seconds` share one boundary; reviewer isolation preparation and adapter postflight stay outside it. Keep the deterministic one-second receipt consistency guard.
- `formal_execution_enabled` remains false, and neither an offline green suite nor a six-pair Pilot may be presented as a formal default-version or superiority conclusion.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
