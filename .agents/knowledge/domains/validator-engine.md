---
type: domain
confidence: observed
scope: ["skills/create-loop/scripts/", "skills/create-loop/schemas/", "skills/create-loop/tests/", "skills/create-loop/tests_py/"]
sources: ["skills/create-loop/scripts/AGENTS.md", "skills/create-loop/scripts/checks/__init__.py", "skills/create-loop/scripts/project_loop.py", "skills/create-loop/scripts/validate_loop_dir.py", "skills/create-loop/scripts/migrate_v1.py", "skills/create-loop/tests/experiments/codex_exec_adapter.py", "skills/create-loop/tests/experiments/pilot_runners.py", "skills/create-loop/tests/experiments/pilot_freeze.py", "skills/create-loop/tests/experiments/network_execution_boundary.py", "skills/create-loop/tests/experiments/execution_guard.py", "skills/create-loop/tests/experiments/experiment_harness.py", "skills/create-loop/tests/experiments/evaluation.py", "skills/create-loop/tests_py/"]
last_verified: 2026-08-06
created: 2026-07-03
---
# Validator Engine (scripts + schemas)

Covers both validation generations now shipped by the Skill: the repaired v1
YAML compatibility gates and the explicitly opt-in v2 JSON/JSONL schema,
projector, resume, migration, and whole-directory toolchain.

## Core Invariants

- v1 retains its 15 node statuses, but `LEGAL_NODE_TRANSITIONS` now defines the allowed event chain and `DONE_NODE_STATUSES` separates node completion from intermediate states [source: skills/create-loop/scripts/checks/__init__.py:15-48].
- v1 event validation requires a known node, continuous before/after state, and non-negative strictly increasing sequence values; gaps remain valid while negative, duplicate, or decreasing values fail closed. Exact effect safety is keyed by both `effect_id` and `attempt_id` [source: skills/create-loop/scripts/checks/event_log.py:35-128] [source: skills/create-loop/scripts/checks/event_log.py:142-241].
- v1 completion authorization uses the current active evidence view, not any historical pass. Evidence identity and lifecycle conflicts are rejected rather than resolved by silently choosing a convenient record; a newly appended failure cannot hide itself with an inactive status instead of an explicit relation [source: skills/create-loop/scripts/checks/provenance.py:68-352] [source: skills/create-loop/scripts/check_loop_integrity.py:168-195].
- v1 checkpoint validation reconciles `last_event_seq` with the actual event tail, while projection validation compares the complete canonical projection rather than only `node_states` [source: skills/create-loop/scripts/checks/checkpoint_projection.py:20-154] [source: skills/create-loop/scripts/check_loop_integrity.py:225-289].
- v2 shape authority is its Draft 2020-12 JSON Schemas. The bundled schema runtime fails closed on unsupported schema keywords instead of silently weakening validation [source: skills/create-loop/scripts/schema_runtime.py:1-20] [source: skills/create-loop/scripts/schema_runtime.py:64-68].
- v2 deterministic validation does not decide semantic completion. It validates schema, hashes, graph and reference integrity, legal journal replay, enabled-module contracts, and generated projection consistency [source: skills/create-loop/scripts/validate_loop_dir.py:495-609].
- Non-null v2 `check_ref` evidence must carry an exact `check_binding`, and the projector hashes the full canonical check object rather than trusting an ID. Old check evidence can affect the active plan only when its bound definition still matches; review-context evidence remains plan-specific [source: skills/create-loop/schemas/journal-record.schema.json:70-105] [source: skills/create-loop/scripts/project_loop.py:58-70] [source: skills/create-loop/scripts/project_loop.py:232-435].
- v1 recovery authority is field-level: the plan seeds topology, the JSONL event log records transitions/effects, the ledger authorizes completion, and the checkpoint carries both derived projections and explicitly snapshot-only hints. Projection agreement proves consistency only; it does not prove semantic correctness or completion [source: skills/create-loop/references/state_model.md:339-399] [source: skills/create-loop/references/recovery_protocol.md:14-19].

## v1 Compatibility Safety

- `event_log.py` validates the Schema-wide exact field/type envelope, timezone-aware RFC 3339 timestamps, node existence, event sequence, legal status edges, per-node continuity, and exact effect pre/post identity. Only `pre_effect`, `post_effect`, and `reopen` may carry transition fields; legacy effect records without exact IDs may be reported separately but cannot satisfy the strict pairing path [source: skills/create-loop/scripts/checks/event_log.py:19-93] [source: skills/create-loop/scripts/checks/event_log.py:161-245].
- Mutation evidence is causal rather than decorative: every cited ledger entry must resolve, belong to the mutation node, and predate the mutation event. The whole-loop gate also invokes full validation for a present `loop.meta.yaml`, so optional metadata cannot bypass its own validator [source: skills/create-loop/scripts/checks/provenance.py:402-489] [source: skills/create-loop/scripts/check_loop_integrity.py:338-347].
- `provenance.py` constructs a current-evidence view from immutable lifecycle relations, rejects duplicate IDs and ambiguous active verdicts, and prevents an older pass from authorizing work after newer failure evidence [source: skills/create-loop/scripts/checks/provenance.py:68-333].
- v1 ledger safety is self-contained when optional `jsonschema` is unavailable:
  the hand-written validator rejects unknown fields, malformed identifiers,
  non-string mapping keys, non-string or empty artifact paths, non-finite or
  out-of-range scores, invalid timestamps, malformed review contexts, and
  malformed lifecycle relations before whole-loop logic may consume a
  completion-authorizing entry. Shape-invalid ledgers do not reach plan-reference
  consumers [source: skills/create-loop/scripts/validate_loop_plan.py:89-263]
  [source: skills/create-loop/scripts/validate_loop_plan.py:366-491]
  [source: skills/create-loop/scripts/check_loop_integrity.py:179-200]
  [source: skills/create-loop/tests_py/test_v1_safety.py:546-788].
- Blind-review validation uses explicit review-context fields and accepts `assurance: blind` only when `producer_claim_access` is `withheld`; `available` or `unknown` does not prove blindness. Dissent overrides must point to the exact failed evidence and be referenced by the subsequent transition [source: skills/create-loop/scripts/checks/provenance.py:348-483].
- The v1 whole-loop gate invokes event validation and cross-checks checkpoint freshness, completion evidence, projection fields, effects, and enabled optional artifacts rather than treating successfully parsed files as an integrity pass [source: skills/create-loop/scripts/check_loop_integrity.py:168-318].

## v2 Toolchain

- `project_loop.py` validates the immutable goal and activated plan hashes, replays plan activation and the six-state transition chain, and derives node state, readiness, lifecycle, evidence, context, authorization, and in-doubt effects [source: skills/create-loop/scripts/project_loop.py:691-1647].
- While the active mode is lightweight, projector and whole-loop validation accept only the bounded upgrade prefix: a control-only observation, an immediately matching decision with explicit `plan_change:null`, and an immediate activation whose new plan differs only in identity/version/time/control metadata. Ordinary work or bundled node-graph changes fail `JOURNAL-MODE` [source: skills/create-loop/scripts/project_loop.py:810-931] [source: skills/create-loop/scripts/project_loop.py:1012-1051] [source: skills/create-loop/tests_py/test_v2_protocol.py:215-388].
- Every ordinary non-initial activation requires an old-plan `plan_replacement` decision whose `plan_change` binds the exact old/new plan versions and hashes; decision and activation evidence sets are identical, active, unchallenged, and not control-only upgrade triggers. Replan versions advance one at a time, and removed node IDs remain globally retired [source: skills/create-loop/scripts/project_loop.py:810-958] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:366-474].
- Check binding is enforced both when evidence is appended and whenever evidence could authorize `done`, completion, counterevidence handling, or recovery projection. This prevents a reused check ID with changed instructions/expectations from becoming a false-completion or false-reopen path [source: skills/create-loop/scripts/project_loop.py:232-435] [source: skills/create-loop/scripts/project_loop.py:940-1062] [source: skills/create-loop/scripts/project_loop.py:1090-1300] [source: skills/create-loop/scripts/project_loop.py:1384-1604].
- Every v2 evidence relation has a current-source gate: the source must be newer than its target, active, unchallenged, and, for check-specific evidence, compatible with the active exact check definition. Relation effects are recomputed from immutable facts, so later challenge, expiry, invalidation, confirmation changes, or replan can retract and reactivate downstream effects instead of leaving a permanently hidden failure [source: skills/create-loop/scripts/project_loop.py:232-369] [source: skills/create-loop/scripts/project_loop.py:940-1062] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:385-790].
- The projector handles completion and reopen as ordered Loop facts and produces source pointers that bind the projection to goal hash, plan hash/version, and journal tail [source: skills/create-loop/scripts/project_loop.py:1090-1133] [source: skills/create-loop/scripts/project_loop.py:1384-1647].
- `validate_loop_dir.py` is the v2 whole-directory entry point. It loads core artifacts, validates each journal record, runs projection, checks resume freshness when present, and discovers conditional claim/artifact modules from the active plan [source: skills/create-loop/scripts/validate_loop_dir.py:229-492] [source: skills/create-loop/scripts/validate_loop_dir.py:495-609].
- Artifact evidence carries an immutable path/hash binding checked by the canonical projector itself, so `project()` and `render_resume.py --check` fail closed on workspace drift even after the artifacts module and live index are removed. A present registry adds identity/current-selection checks; it is not the only historical authority [source: skills/create-loop/scripts/project_loop.py:462-477] [source: skills/create-loop/scripts/project_loop.py:1095-1114] [source: skills/create-loop/tests_py/test_v2_validator_hardening.py:561-602].
- `render_resume.py` obtains the canonical projection and atomically replaces the generated resume file; it is a renderer, not a second state writer [source: skills/create-loop/scripts/render_resume.py:14-57].
- `migrate_v1.py` performs conservative sibling-directory migration, records source hashes and warnings, and avoids manufacturing v2 completion authority from legacy state [source: skills/create-loop/scripts/migrate_v1.py:59-71] [source: skills/create-loop/scripts/migrate_v1.py:451-713].
- Migration fails closed when legacy goal authority fields have the wrong shape or empty criteria. Conversion reads from one immutable byte snapshot, binds its hashes into the import journal/report, then re-hashes the source immediately before publication and refuses both dry-run and real publication if the source changed [source: skills/create-loop/scripts/migrate_v1.py:59-91] [source: skills/create-loop/scripts/migrate_v1.py:451-501] [source: skills/create-loop/scripts/migrate_v1.py:742-764] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:118-144] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:884-933].
- Migration rejects the source root and every discovered member when it is a symlink or Windows reparse point before following it. Windows root/member junction rejects have executable coverage; ordinary directories are the positive control, while symlink cases may skip on accounts without link-creation privilege [source: skills/create-loop/scripts/migrate_v1.py:62-105] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:118-240].
- Dry-run validation uses a system temporary staging tree outside the selected
  Loop and every v1 Loop ancestor, so validating a nested child cannot mutate an
  ancestor migration's source inventory. Real migration still stages beside the
  destination and publishes with a same-filesystem rename [source: skills/create-loop/scripts/migrate_v1.py:716-764] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:989-1068].
- Migration rejects unknown legacy statuses and malformed, traversal-prone, or cross-platform-unmaterializable `produces` paths instead of inventing a fallback. It canonicalizes separators and dot segments, then applies the same Windows-aware output identity used by the projector and whole-loop gate [source: skills/create-loop/scripts/migrate_v1.py:211-254] [source: skills/create-loop/scripts/project_loop.py:116-155].
- The projector resolves completion deliverables through the actual workspace and rejects symlink/junction escapes, missing paths, and file hash mismatches. Declared directories are valid deliverables only without a file `sha256` [source: skills/create-loop/scripts/project_loop.py:1455-1490] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:1883-2000].
- Shared output identity is intentionally narrower than Unicode `casefold()`: on Windows it uses length-preserving OS case mapping so ordinary and supplementary-plane case variants collide, while distinct names such as `straße` and `strasse` and emoji-bearing paths remain distinct [source: skills/create-loop/scripts/project_loop.py:116-155] [source: skills/create-loop/tests_py/test_v2_validator_hardening.py:493-550].
- An in-doubt effect blocks both later plan activation and Loop closure until a conclusive postcondition record exists [source: skills/create-loop/references/protocol_v2.md:124-133] [source: skills/create-loop/scripts/project_loop.py:783-837] [source: skills/create-loop/scripts/project_loop.py:1362-1381] [source: skills/create-loop/scripts/project_loop.py:1384-1503].
- Artifact validation distinguishes the complete immutable registry history from the current active selection, so historical evidence can reference a superseded but still hash-valid artifact while unknown IDs remain invalid [source: skills/create-loop/references/protocol_v2.md:160-166] [source: skills/create-loop/scripts/validate_loop_dir.py:302-404].

## Executable Gates

- `tests_py/test_v1_safety.py` provides executable rejection and control coverage for illegal transitions, node existence, event continuity, exact effect pairing, stale checkpoints, projection drift, current evidence, review context, and dissent linkage [source: skills/create-loop/tests_py/test_v1_safety.py:19-175].
- `tests_py/test_v2_protocol.py` exercises schema-runtime parity, v2 projection and resume behavior, invalid transition/effect/hash cases, completion/reopen behavior, the bounded lightweight upgrade, and conservative v1 migration [source: skills/create-loop/tests_py/test_v2_protocol.py:80-329].
- The executable Python gate is `python -m unittest discover -s skills/create-loop/tests_py`; Markdown acceptance and failure-mode documents remain useful specifications but are not substitutes for these tests [source: skills/create-loop/tests_py/test_v1_safety.py:19-175] [source: skills/create-loop/tests_py/test_v2_protocol.py:80-214].
- Validation coverage must include the artifact shape the runtime actually writes, not only the hand-authored template. v1 canonical event storage is bare-object JSONL, while the compatibility schema/template still use a wrapper object and explicitly document that mismatch as an open defect [source: skills/create-loop/references/state_model.md:288-323] [source: skills/create-loop/templates/event_log.yaml:1-9] [source: skills/create-loop/schemas/event_log.schema.json:1-19].
- Phase 5 source freezing binds the immutable v1 commit snapshot and current v2 worktree snapshot to one exact static instrument set. The candidate bytes flow into the instrument manifest before the preregistration hash, so there is no self-hash cycle or two-pass convergence requirement; `--check` is read-only [source: skills/create-loop/tests/experiments/snapshot_tools.py:41-54] [source: skills/create-loop/tests/experiments/freeze_experiment.py:19-85] [source: skills/create-loop/tests_py/test_experiment_snapshots.py:194-273].
- The experiment harness validates exact metric/gate sets, trace timing and adapter/authorization/source bindings, blind A/B/context bindings, report arithmetic, and fabricated eligibility. `aggregate_results()` is deliberately a fail-closed shell: even with complete synthetic ID sets it emits only `insufficient-data` gates and `extend-experiment` [source: skills/create-loop/tests/experiments/experiment_harness.py:430-718] [source: skills/create-loop/tests_py/test_experiment_harness.py:307-450].
- `workspace_builder.py` materializes all 14 deterministic local fixtures, binds the tool profile and presented files by hash, and rejects drift, path escape, collisions, Windows device names, and symlinks [source: skills/create-loop/tests/experiments/workspace_builder.py:247-396] [source: skills/create-loop/tests_py/test_experiment_workspace.py:34-126].
- `evaluation.py` consumes an exact evaluation-input manifest and rejects blind manifests whose seed or A/B mapping differs from `blind_assignment(pair_id, order_seed)`. Its only authoritative metric is the frozen deterministic smoke suite: the runner binds imported code bytes, catalog/profile/result schemas, source snapshots, validator and fixture immutability, then materializes the complete captured source byte map in a private subprocess tree before execution. Transient swaps of the parent validator, imported helper, schema, or fixture cannot change executed bytes; a legacy live-source control proves the same helper swap would change the old result. All other metrics are emitted with `sample_count: 0` and `authority-missing:*`, so their gates remain `insufficient-data` [source: skills/create-loop/tests/experiments/deterministic_runner.py:35-179] [source: skills/create-loop/tests/experiments/deterministic_runner.py:486-656] [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:299-445] [source: skills/create-loop/tests/experiments/evaluation.py:823-890].
- The deterministic tool profile is a validated declaration, not an OS sandbox. v1 replay may inject user-site `PYTHONPATH` for PyYAML; v2 omits it and invokes Python with `-s`. Hash binding and temporary workspaces protect replay identity, but do not themselves prove network or filesystem capability isolation [source: skills/create-loop/tests/experiments/deterministic_runner.py:4-6] [source: skills/create-loop/tests/experiments/deterministic_runner.py:390-444] [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:152-201].
- `execution_guard.py` is the Pilot's active grant/ledger/receipt/spend-summary
  authority, not a detached prototype. It binds the canonical execution root,
  appends a durable hash-chained ledger, reserves the exact per-call maximum,
  refuses duplicate calls or attempts, validates direct evidence before
  settlement, reconciles receipt identity/usage/timestamps, and exposes
  in-doubt or breached state through replay
  [source: skills/create-loop/tests/experiments/execution_guard.py:709-790]
  [source: skills/create-loop/tests/experiments/execution_guard.py:859-1015]
  [source: skills/create-loop/tests/experiments/execution_guard.py:1123-1237].
- Replay authority is capability-scoped and time-bounded. `ReplaySnapshot`
  cannot be constructed through its public constructor and is accepted only
  when its process-local weak registry contains the exact root, authority
  fingerprint, and canonical summary bytes. This prevents forgery through the
  supported public API; it is not a cryptographic or hostile-same-process
  boundary because in-process code can reach the private registry. Public
  `validate_trace()` rejects
  snapshots and performs a fresh replay; the private batch path is paired with
  a final authority check. Replay rejects naive timestamps, times before the
  ledger tail, and times more than five seconds ahead of the local UTC clock;
  submitted `generated_at` is validated but cannot select the replay state
  [source: skills/create-loop/tests/experiments/execution_guard.py:76-89]
  [source: skills/create-loop/tests/experiments/execution_guard.py:241-252]
  [source: skills/create-loop/tests/experiments/execution_guard.py:1062-1074]
  [source: skills/create-loop/tests/experiments/experiment_harness.py:845-906]
  [source: skills/create-loop/tests/experiments/evaluation.py:1360-1419]
  [source: skills/create-loop/tests_py/test_experiment_execution_guard.py:444-466].
- A stable snapshot rechecks expected grant, ledger-anchor, and spend-summary
  hashes inside the execution lock and compares pre/post fingerprints. Pilot
  final reconciliation locks all three canonical execution roots in sorted
  order and replays them as one multi-root cut; authority comparison includes
  both the full fingerprint and canonical replay summary, excluding only the
  non-authoritative `generated_at` field [source: skills/create-loop/tests/experiments/execution_guard.py:395-434]
  [source: skills/create-loop/tests/experiments/execution_guard.py:1381-1469]
  [source: skills/create-loop/tests/experiments/evaluation.py:1442-1468]
  [source: skills/create-loop/tests_py/test_experiment_execution_guard.py:426-520]
  [source: skills/create-loop/tests_py/test_experiment_pilot_evaluation.py:203-313].
- `network_execution_boundary.py` is a separate fail-closed readiness gate. It
  authenticates frozen Windows producer and Linux reviewer CLI identities plus
  an expiring OS-enforced default-deny boundary whose only allowed endpoint
  matches the frozen provider profile. Adapter, Pilot freeze/grant, harness, and
  runner execution paths invoke it before credentials, ledger initialization,
  reservation, or process launch
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:114-233]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-351]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:701-733]
  [source: skills/create-loop/tests/experiments/pilot_harness.py:436-483]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1261-1349]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:242-290].
- The readiness interface still requires redesign before a production backend
  can be registered. One shared outer `launch_prefix` works for native Windows
  producer/calibration calls but cannot express a Linux enforcer inserted after
  WSL entry and before bubblewrap/Codex. Runtime now rejects `reviewer` at the
  v1 composition boundary before WSL or Codex launch; producer and runner paths
  request readiness for their exact role. The live probe still uses the host
  Python runtime, so a retained replacement must bind each role/platform to its
  insertion point, probe command, and process-tree evidence while preserving
  the empty registry and fail-closed behavior until real enforcement exists
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-379]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:417-462]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:518-538]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:604-686]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-302]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-254]
  [source: skills/create-loop/tests_py/test_experiment_reviewer_isolation.py:387-415].
- Pilot freeze authority is two-stage. Calibration alone may bind the
  pre-calibration static manifest; its raw JSONL must yield one exact provider
  request identity and one exact usage record before a final freeze may
  authorize producer and reviewer grants. Grant role, canonical root, freeze
  phase, and authority hash are revalidated on every launch path. Freeze
  construction and grant validation additionally require complete Pilot
  readiness; role-scoped readiness is reserved for the actual launcher
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-368]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:371-623]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:626-733].
- Producer/reviewer evidence is settlement authority. The adapter and runners
  preserve raw JSONL, require unambiguous usage/request identity, bind initial
  and final workspace manifests plus population seal, structured claim, direct
  evidence, and receipt before settlement. Evaluation independently replays
  three separate role grants and their anchors/spend summaries, recomputes
  final workspace reality, binds every oracle to the exact episode evidence,
  and validates four blind reviews and their reviewer-isolation evidence before
  decoding A/B assignments
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1645-1768]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:555-623]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:855-927]
  [source: skills/create-loop/tests/experiments/evaluation.py:1276-1354]
  [source: skills/create-loop/tests/experiments/evaluation.py:1560-1632]
  [source: skills/create-loop/tests/experiments/evaluation.py:1873-2076].
- Receipt wall time is a provider-call measurement rather than surrounding
  setup/postflight time. Adapter timestamps bracket `_run_codex`; reviewer
  isolation is prepared before the runner starts both its timestamp and outer
  monotonic clock. The guard retains its one-second timestamp consistency
  tolerance, and deterministic delay tests exercise both paths
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1451-1467]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:486-523]
  [source: skills/create-loop/tests/experiments/execution_guard.py:308-348]
  [source: skills/create-loop/tests_py/test_experiment_codex_adapter.py:360-415]
  [source: skills/create-loop/tests_py/test_experiment_pilot_runners.py:492-578].

## Common Mistakes

- Extending v2 with another R-number. v1 retains its historical R identifiers, while v2 uses stable invariant families such as `SCHEMA-*`, `GRAPH-*`, `JOURNAL-*`, `EFFECT-*`, and `EVIDENCE-*` [source: skills/create-loop/references/protocol_v2.md:36-40].
- Treating a parsed JSONL tail as a valid journal without checking gapless sequence, record references, plan hash, state continuity, evidence relations, and effect pairing [source: skills/create-loop/scripts/project_loop.py:691-1647] [source: skills/create-loop/scripts/validate_loop_dir.py:495-609].
- Updating v1 enums, schemas, event rules, or projection logic independently. Their compatibility contract spans shared constants, file validators, whole-loop reconciliation, examples, and executable safety fixtures [source: skills/create-loop/scripts/checks/__init__.py:15-48] [source: skills/create-loop/tests_py/test_v1_safety.py:19-175].
- Hand-editing `resume.json` or treating it as authoritative. It must be regenerated from goal, active plan, and journal whenever source pointers are stale [source: skills/create-loop/scripts/render_resume.py:14-57] [source: skills/create-loop/scripts/project_loop.py:1637-1647].
- Treating `check_ref` as stable evidence identity across plan versions. The stable comparison input is the bound full check hash; check-specific review has an additional fresh-plan requirement [source: skills/create-loop/scripts/project_loop.py:232-435] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:259-476].
- Adding a first-event anchor check to v1 without an immutable phase seed. `loop.plan.nodes[].status` is current state, shipped logs are historical, and phase rollover may omit the prior phase's state; only later per-node event continuity is deterministically enforceable with current artifacts [source: skills/create-loop/references/loop_plan_spec.md:93] [source: skills/create-loop/references/recovery_protocol.md:283-295] [source: skills/create-loop/scripts/checks/event_log.py:85-112].
- Interpreting the shell status of a Markdown fixture wrapper as the validator verdict. The historical `cmd && echo FAIL || echo PASS-rejected` harness deliberately exits through `echo`; the printed token, the validator exit code, and the expected R-tag are three distinct signals [source: skills/create-loop/tests/failure_mode_tests.md:1184-1191] [source: skills/create-loop/tests/failure_mode_tests.md:1935-1939].
- Trusting an alarming metric before calibrating its instrument on one known reject and one known control. This repo has heterogeneous YAML/JSONL shapes and both executable and prose-only fixtures, so a wrong input selector or output parser can make healthy behavior look broken [source: skills/create-loop/tests/acceptance_tests.md:1-9] [source: skills/create-loop/tests/failure_mode_tests.md:1184-1191] [source: skills/create-loop/tests/failure_mode_tests.md:3127-3137].

## Verified Facts

- The repository no longer has only four top-level validator utilities: v2 adds `schema_runtime.py`, `project_loop.py`, `validate_loop_dir.py`, `render_resume.py`, and `migrate_v1.py` alongside the v1 tools [source: skills/create-loop/scripts/AGENTS.md:9-41].
- v1 shared constants include the 15-state vocabulary and an explicit legal-transition map used by event validation [source: skills/create-loop/scripts/checks/__init__.py:15-48] [source: skills/create-loop/scripts/checks/__init__.py:103-127].
- v1 permits sequence gaps but rejects negative, duplicate, or decreasing sequence values; inactive fresh failure evidence cannot silently expose an older pass; and blind assurance requires explicit withheld producer-claim access [source: skills/create-loop/scripts/checks/event_log.py:39-60] [source: skills/create-loop/scripts/checks/provenance.py:323-360] [source: skills/create-loop/scripts/checks/provenance.py:363-390] [source: skills/create-loop/tests_py/test_v1_safety.py:158-170] [source: skills/create-loop/tests_py/test_v1_safety.py:249-299] [source: skills/create-loop/tests_py/test_v1_safety.py:301-320].
- v2 projector output is canonical and recursive over journal facts; `resume.json` is checked against that projection and its exact source pointers [source: skills/create-loop/scripts/project_loop.py:691-1647].

## Open Questions

- The Pilot budget is authorized and the guard is wired, but execution readiness
  is not. The repository intentionally exposes `reviewer_cli_identity` and
  `network_boundary` blockers because no local frozen Linux Codex `0.144.1`
  identity and no authenticated OS provider-only boundary exist. Until both are
  resolved, pre-freeze, grant validation, adapter, harness, calibration, and
  reviewer paths must fail before any real provider call. The observed budget
  remains 0 calls / 0 tokens / 0 seconds, and no v1/v2 tendency exists
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:152-183]
  [source: AGENTS.md:73].
- Which role/platform launch-contract shape will replace the current outer-only
  prefix without conflating Windows host enforcement with Linux reviewer
  enforcement? This is an offline interface-design gap in addition to the
  external CLI/backend blockers; solving the interface alone must not enable
  execution [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-380]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:518-538].
- The six-pair Pilot is descriptive and stops after its report. Even after real
  execution, `formal_execution_enabled` remains false; a default-version claim
  needs a separately frozen multi-instance campaign rather than the legacy
  repeated-fixture 42-pair/84-run shell
  [source: skills/create-loop/tests/experiments/evaluation.py:2420-2477]
  [source: skills/create-loop/tests/experiments/pilot_harness.py:127-151].

- What paired real-task evidence is sufficient to promote v2 from opt-in while retaining or retiring each v1 validation path? Current code provides coexistence and migration, not the release decision [source: skills/create-loop/scripts/migrate_v1.py:451-705].
- When should v2 journal replay gain trusted snapshots or segmentation? The current projector replays the ordered journal and the resume stores source pointers, but no measured threshold is encoded [source: skills/create-loop/scripts/project_loop.py:691-1647].
- Should CI require the external `jsonschema` parity environment on every platform or in a dedicated matrix job? The bundled runtime exists for zero-dependency operation, while parity coverage is exercised by the v2 tests [source: skills/create-loop/scripts/schema_runtime.py:1-20] [source: skills/create-loop/tests_py/test_v2_protocol.py:153-169].
- v1 cannot currently authenticate the `from_status` of the first event in a phase because no immutable phase seed or equivalent initial-state anchor exists. Tightening this without a format change would reject shipped historical logs as well as malformed ones [source: skills/create-loop/references/loop_plan_spec.md:93] [source: skills/create-loop/references/recovery_protocol.md:283-295].

## Correction History

- 2026-08-06: Closed the unsafe implicit reviewer topology in the legacy
  network contract. The v1 host-outer prefix remains usable for native
  producer/calibration tests, but `reviewer` now fails before any WSL/package/
  Codex work. This is only a fail-closed compatibility repair; it does not
  implement or attest the required guest-local provider boundary
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-333]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1285-1292]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:267-274]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-302]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-254]
  [source: skills/create-loop/tests_py/test_experiment_reviewer_isolation.py:387-415].

- 2026-08-06: Closed the remaining readiness-scope ambiguity. `None` now means
  complete-Pilot validation and checks every required launch topology; a named
  role validates only its effective CLI identity and exact topology, with
  calibration mapped to producer. Freeze construction and every grant
  validation use `None`, so unresolved reviewer authority blocks calibration as
  well as the final campaign. Named roles are used only immediately before an
  adapter/runner launches that role
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:33-38]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:407-474]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-353]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:626-641]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:701-736]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-247]
  [source: skills/create-loop/tests_py/test_experiment_pilot_freeze.py:285-314]
  [source: skills/create-loop/tests_py/test_experiment_pilot_freeze.py:490-552].

- 2026-08-06: Closed the stale-snapshot, replay-time, and cross-root authority
  gaps without weakening fail-closed validation. The complete executable suite
  passed 474 tests with 4 environment skips; freeze/check, formal harness, and
  six-pair Pilot validate/plan remained green with zero validated traces and
  `execution_blocked:true`. These results validate the offline chain only and
  do not supply a v1/v2 outcome [source: skills/create-loop/tests/experiments/execution_guard.py:1381-1469]
  [source: skills/create-loop/tests/experiments/experiment_harness.py:845-906]
  [source: skills/create-loop/tests/experiments/evaluation.py:1442-1468]
  [source: skills/create-loop/tests_py/test_experiment_execution_guard.py:426-548]
  [source: skills/create-loop/tests_py/test_experiment_pilot_evaluation.py:203-313].

- 2026-08-05: Superseded the earlier Phase 5 claim that the guard was not
  integrated and the user budget was unauthorized. Canonical freeze/grant
  validation, reservation, evidence-first settlement, evaluation authority
  replay, and review sealing now share the guard contract, while the approved
  Pilot/hard ceilings remain bounded to calls, total tokens, and wall time. The
  remaining blockers are the Linux reviewer CLI identity and authenticated
  provider-only OS network boundary, not missing guard wiring
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1261-1367]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:242-290]
  [source: skills/create-loop/tests/experiments/evaluation.py:1560-1632]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: AGENTS.md:73].
- 2026-08-05: Reconciled the load-sensitive receipt wall-time failure without
  weakening deterministic validation. Adapter and runner timestamps now match
  the monotonic provider-call interval; focused adapter, runner, and guard tests
  cover delayed postflight and reviewer-isolation preparation
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1451-1467]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:486-523]
  [source: skills/create-loop/tests_py/test_experiment_codex_adapter.py:360-415]
  [source: skills/create-loop/tests_py/test_experiment_pilot_runners.py:492-578].

- 2026-08-01: Closed a no-`jsonschema` false-completion path by bringing the
  completion-relevant evidence-ledger Schema envelope into the hand-written v1
  validator, rejecting YAML non-finite scores and non-string mapping keys, and
  preventing shape-invalid ledgers from reaching plan-reference consumers
  [source: skills/create-loop/scripts/validate_loop_plan.py:89-263]
  [source: skills/create-loop/scripts/validate_loop_plan.py:484-491]
  [source: skills/create-loop/tests_py/test_v1_safety.py:546-788].
- 2026-08-01: Closed the remaining runner live-source boundary by materializing the complete captured source byte map in the child process, checking the private tree before and after execution, and adding a legacy control that proves a transient imported-helper swap changes the old live-source result but cannot touch the new execution tree [source: skills/create-loop/tests/experiments/deterministic_runner.py:35-179] [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:299-445].
- 2026-08-01: Extended conservative migration input confinement from source-hash stability to pre-resolution symlink/reparse rejection, with Windows junction rejects and ordinary-tree controls [source: skills/create-loop/scripts/migrate_v1.py:62-105] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:118-240].
- 2026-08-01: Closed runner TOCTOU boundaries by binding imported code and every deterministic result schema to the instrument manifest, executing from captured source/fixture bytes, and rejecting validator or fixture mutation. The same change limited authority to the deterministic smoke metric and made v1 PyYAML versus v2 user-site isolation explicit [source: skills/create-loop/tests/experiments/deterministic_runner.py:31-37] [source: skills/create-loop/tests/experiments/deterministic_runner.py:237-339] [source: skills/create-loop/tests/experiments/deterministic_runner.py:486-581] [source: skills/create-loop/tests/experiments/evaluation.py:89-92] [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:28-245].

- 2026-08-01: Corrected the stale Phase 5 blocker inventory after executable workspace construction, authoritative offline evaluation inputs/formulas, and the standalone spend guard landed. These capabilities remain offline and do not establish v2 superiority or enable formal execution [source: skills/create-loop/tests/experiments/workspace_builder.py:247-396] [source: skills/create-loop/tests/experiments/evaluation.py:73-83] [source: skills/create-loop/tests/experiments/execution_guard.py:370-790].

- 2026-08-01: Replaced the stale candidate-manifest/shape-only description with the verified source/instrument freeze DAG, trace/blind/report cross-file validators, and fail-closed aggregator shell. Formal execution blockers remain explicit rather than inferred from validation success [source: skills/create-loop/tests/experiments/freeze_experiment.py:19-85] [source: skills/create-loop/tests/experiments/experiment_harness.py:108-116] [source: skills/create-loop/tests/experiments/experiment_harness.py:430-718].

- 2026-07-31: Corrected the stale R1-R41-only description. v1 has later safety rules and executable repairs, while v2 deliberately uses named invariant families instead of extending the R sequence [source: skills/create-loop/scripts/check_loop_integrity.py:168-195] [source: skills/create-loop/references/protocol_v2.md:36-40].
- 2026-07-31: Corrected the stale four-script inventory. The current toolchain includes five v2 runtime, projection, validation, rendering, and migration scripts plus executable `tests_py` coverage [source: skills/create-loop/scripts/AGENTS.md:9-41] [source: skills/create-loop/tests_py/test_v2_protocol.py:80-214].
- 2026-07-31: Recorded hardening for confined completion deliverables, fail-closed migration statuses/outputs, in-doubt effects before replan/close, and historical superseded artifacts; retained the first-event seed and disabled-tail artifact history issues as explicit compatibility gaps [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:1883-2000] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:595-680] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:2043-2152] [source: skills/create-loop/tests_py/test_v2_validator_hardening.py:308-491].
- 2026-07-31: Closed the same-ID stale-check path by making check-definition hashes part of evidence identity and exercising changed-check rejection, unchanged-check control, stale completion refs, and plan-specific review cases [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:259-476] [source: skills/create-loop/tests_py/test_v2_protocol.py:171-184].
- 2026-07-31: Added shared output canonicalization/identity coverage across projector, whole-loop validation, and migration, including Win32-invalid names, Unicode/non-BMP controls, duplicate-producer handling, and directory deliverable hash boundaries [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:478-626] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:1883-2000] [source: skills/create-loop/tests_py/test_v2_validator_hardening.py:493-550].
- 2026-07-31: Corrected the final Windows identity boundary after review: source length is measured in UTF-16 code units, `LPARAM` uses pointer width, and mapping preserves length so case equivalence is neither under-detected nor over-folded into unrelated Unicode spellings [source: skills/create-loop/scripts/project_loop.py:116-155] [source: skills/create-loop/tests_py/test_v2_validator_hardening.py:493-550].
- 2026-07-31: Closed the former disabled-artifact-history question with immutable evidence bindings, and recorded causal replan, globally retired node IDs, strict authority-field migration, and single-snapshot source-mutation rejection [source: skills/create-loop/scripts/validate_loop_dir.py:419-462] [source: skills/create-loop/scripts/project_loop.py:838-895] [source: skills/create-loop/scripts/migrate_v1.py:451-501] [source: skills/create-loop/scripts/migrate_v1.py:722-731].
- 2026-07-31: Added an executable lightweight upgrade state machine. Four tests cover the legal prefix, runtime work before activation, unconsumed causal refs, and mode mismatch [source: skills/create-loop/tests_py/test_v2_protocol.py:215-329].
- 2026-07-31: Absorbed the Wave-era recovery and measurement findings into stable rules: field-level authority, runtime-artifact coverage, and instrument calibration. Historical Wave counts and RED/GREEN narration remain trace evidence rather than current authority [source: skills/create-loop/references/state_model.md:339-399] [source: skills/create-loop/tests/failure_mode_tests.md:1184-1191] [source: skills/create-loop/templates/event_log.yaml:1-9].

## Related

- [domains/skill-protocol.md](skill-protocol.md) - protocol authority and model/program boundaries
- [skills/create-loop/references/protocol_v2.md](../../../skills/create-loop/references/protocol_v2.md)
- [skills/create-loop/scripts/validate_loop_dir.py](../../../skills/create-loop/scripts/validate_loop_dir.py)
