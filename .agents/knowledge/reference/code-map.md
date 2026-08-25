---
type: reference
confidence: verified
scope: ["bin/", "command/", ".opencode/command/", ".claude/commands/", "install-commands.sh", "test/", "skills/create-loop/"]
sources: ["package.json", "bin/create-loop.js", "test/installer.test.js", "command/manifest.json", "command/", "skills/create-loop/SKILL.md", "skills/create-loop/README.md", "skills/create-loop/scripts/AGENTS.md", "skills/create-loop/references/protocol_v2.md", "skills/create-loop/references/migration_v1_to_v2.md", "skills/create-loop/tests/experiments/codex_exec_adapter.py", "skills/create-loop/tests/experiments/pilot_runners.py", "skills/create-loop/tests/experiments/pilot_freeze.py", "skills/create-loop/tests/experiments/network_execution_boundary.py", "skills/create-loop/tests/experiments/execution_guard.py", "skills/create-loop/tests/experiments/experiment_harness.py", "skills/create-loop/tests/experiments/evaluation.py"]
last_verified: 2026-08-06
created: 2026-07-03
---

# Code Map

## System Shape

The repository ships two coupled artifact classes: delivery machinery (`bin/`, canonical/rendered commands, installer tests and package metadata) and the installable meta-skill (`skills/create-loop/`). v1 remains readable/writable during transition; v2 is opt-in and adds a smaller JSON/JSONL runtime [source: skills/create-loop/SKILL.md:34-49].

```text
create-loop/
|- bin/create-loop.js                 zero-dependency install/render/uninstall CLI; state v2 + transactions
|- install-commands.sh                compatibility wrapper -> Node --commands-only
|- package.json                       Node >=18, per-file exact package allowlist, render/test scripts
|- test/installer.test.js             dynamically counted delivery/security/package suite
|- command/                            canonical frontmatter-free slash commands + manifest
|- .opencode/command/                  generated OpenCode command exact set
|- .claude/commands/                   generated Claude command exact set
|- skills/create-loop/
|  |- SKILL.md                         protocol entrypoint under executable 1000-line ceiling; v1 default, v2 opt-in
|  |- LICENSE                          installed payload license copy
|  |- references/protocol_v2.md        v2 admission/authority/state/journal/lifecycle/modules
|  |- references/migration_v1_to_v2.md README migration workflow and source-binding runbook
|  |- schemas/                         v1 schemas + seven v2 core/optional/migration schemas
|  |- templates/                       v1 templates + four v2 core templates
|  |- scripts/                         v1 checks plus v2 schema/project/validate/render/migrate tools
|  |- tests_py/                        executable v1/v2 safety plus Phase 5/Pilot focused suites
|  |- tests/baselines/                 frozen v1 audit baseline at 8263f09
|  |- tests/experiments/               Phase 5 freeze, Pilot adapter/runners, isolation, evaluation, and guard
|  `- examples/                        three v1 examples + v2 lightweight/persistent examples
`- .agents/knowledge/                  evolving project knowledge and this map
```

The skill entrypoint maps runtime v2 work to `protocol_v2.md`,
`validate_loop_dir.py`, `project_loop.py`, and `render_resume.py`. README maps
the explicit v1-to-v2 migration workflow and its installed `migrate_v1.py`
backend [source: skills/create-loop/SKILL.md:807-889] [source: skills/create-loop/README.md:160-188] [source: skills/create-loop/references/migration_v1_to_v2.md:1-12].

## Delivery Routing

| Task | Start here | Supporting evidence |
|---|---|---|
| Change host destinations/frontmatter | `bin/create-loop.js` `HOSTS` | [source: bin/create-loop.js:40-69] |
| Change install-state schema/root binding | `newState`, `normalizeState`, `readState` | [source: bin/create-loop.js:256-404] |
| Change ownership/upgrade semantics | `planManaged`, `planObsolete` | [source: bin/create-loop.js:611-685] |
| Change transaction intent authority | `transactionIntent`, `transactionIntentSha256`, `assertTransactionAnchor` | [source: bin/create-loop.js:690-724] |
| Change committed recovery projection | `committedStateMatchesTransaction` | [source: bin/create-loop.js:726-749] |
| Change crash recovery | `validateTransactionOperations`, `recoverTransaction`, `applyHostTransaction` | [source: bin/create-loop.js:827-895] [source: bin/create-loop.js:897-1157] [source: bin/create-loop.js:1159-1235] |
| Change command Skill-root validation | `inspectCommandSkillRoot`, `validateCommandSkillProjection` | [source: bin/create-loop.js:1312-1452] |
| Change pending-root resolution/pre-mutation planning | `inspectPendingTransactions`, `resolveInstallCommandSkillRoot`, `buildInstallPlans` | [source: bin/create-loop.js:1556-1635] |
| Change install/uninstall orchestration | `cmdInstall`, `cmdUninstall` | [source: bin/create-loop.js:1638-1759] |
| Change manifest validation | `loadCommandManifest` + `command/manifest.schema.json` | [source: bin/create-loop.js:1241-1274] [source: command/manifest.schema.json:6-42] |
| Change renderer exact-set behavior | `assertSafeRenderDirectory`, `cmdRender` | [source: bin/create-loop.js:1776-1858] |
| Change package contents | `package.json` per-file `files` set + exact pack-path assertions | [source: package.json:37-214] [source: test/installer.test.js:1720-1753] |
| Change shell compatibility path | `install-commands.sh` | [source: install-commands.sh:1-40] |

State v2 records `stateRoot`, optional project root, per-host roots/anchors, and per-host transaction anchors. Pending operations are staged under `.create-loop/transactions/` (or the global equivalent), carry pre/post ownership state, and are bound to install state by transaction ID, phase, and an ordered intent digest. Both pending execution and committed cleanup validate selected kind, confined unique destination, delete-null stage, and exact canonical write stage `<stageDir>/<index>.stage`; cleanup uses only those validated stage paths [source: bin/create-loop.js:690-749] [source: bin/create-loop.js:827-895] [source: bin/create-loop.js:897-1157].

## Command Routing

| Task | Start here | Rule |
|---|---|---|
| Edit a command | `command/<id>.md` | Body is frontmatter-free [source: command/AGENTS.md:8-10] |
| Edit command metadata | `command/manifest.json` | Four protocol-neutral v1/v2 entries [source: command/manifest.json:5-29] |
| Validate/render changes | `node bin/create-loop.js render`, then `render --check`, then installer test | [source: command/AGENTS.md:12-16] |
| Understand v1/v2 selection | `command/loop-new.md`, `loop-run.md`, `loop-resume.md`, `loop-status.md` | Existing artifacts must agree with selector [source: command/loop-run.md:10-13] |
| Change lightweight durability upgrade | `command/loop-run.md`, `protocol_v2.md`, projector/validator `JOURNAL-MODE` rules | Exact four-record control prefix, explicit `plan_change:null`, node-identical bridge [source: command/loop-run.md:22-40] [source: skills/create-loop/references/protocol_v2.md:19-33] |
| Regenerate host files | `.opencode/command/`, `.claude/commands/` | Generated exact sets; never edit directly [source: command/AGENTS.md:22-25] |
| Preserve spaced install/workspace paths | all `python`/`python3` invocations in `command/*.md` | Quote both resolved script paths and Loop/plan/checkpoint arguments [source: command/loop-new.md:38-73] [source: test/installer.test.js:1492-1500] [source: test/installer.test.js:1700-1709] |

## v1 Protocol and Validator Routing

| Task | Start here | Deep area |
|---|---|---|
| v1 vocabulary and plan fields | `references/loop_plan_spec.md`, `references/state_model.md` | `schemas/loop.plan.schema.json`, `scripts/checks/__init__.py` |
| v1 plan/artifact validation | `scripts/validate_loop_plan.py` | concern modules under `scripts/checks/` [source: skills/create-loop/scripts/AGENTS.md:9-22] |
| v1 checkpoint projection | `scripts/validate_checkpoint.py` | event/evidence/projection checks [source: skills/create-loop/scripts/AGENTS.md:10-12] |
| v1 whole-loop gate | `scripts/check_loop_integrity.py` | composes validators and cross-file rules [source: skills/create-loop/scripts/AGENTS.md:12-13] |
| v1 executable safety regressions | `tests_py/test_v1_safety.py` | event, evidence, checkpoint classes [source: skills/create-loop/tests_py/test_v1_safety.py:19-124] |

## v2 Core Routing

| Concern | Canonical files | Entry points |
|---|---|---|
| Protocol semantics | `references/protocol_v2.md` | admission L8, authority L23, states L42, journal L66, execution L94, lifecycle L112, modules L129 [source: skills/create-loop/references/protocol_v2.md:8-144] |
| Goal | `schemas/goal.schema.json`, `templates/goal.json` | immutable Loop identity/criteria/authorization |
| Plan | `schemas/plan.schema.json`, `templates/plan-v1.json` | immutable versions, DAG, control mode/modules |
| Journal | `schemas/journal-record.schema.json`, `templates/journal.jsonl` | ordered transitions/evidence/decisions/effects/completion/reopen |
| Resume | `schemas/resume.schema.json`, `templates/resume.json` | generated cache only |
| Optional concurrency | `schemas/claim-v2.schema.json` | validated only when module enabled |
| Optional artifacts | `schemas/artifact-index-v2.schema.json` | current-selection registry; evidence keeps an independent path/hash binding |
| Migration runbook | `references/migration_v1_to_v2.md` | README entry for explicit conversion and migration maintenance |
| Migration report | `schemas/migration-report.schema.json` | conservative source hashes/warnings for imported Loop validation |
| Runtime schema subset | `scripts/schema_runtime.py` | `validate()` and `validate_file()` [source: skills/create-loop/scripts/schema_runtime.py:64-149] |
| Canonical projection | `scripts/project_loop.py` | six states, exact old/new `plan_change` causality, node-identical lightweight bridge, retired node IDs, journal replay, check/artifact reality binding, effects and confined deliverables [source: skills/create-loop/scripts/project_loop.py:714-795] [source: skills/create-loop/scripts/project_loop.py:810-970] [source: skills/create-loop/scripts/project_loop.py:1065-1175] [source: skills/create-loop/scripts/project_loop.py:1446-1658] [source: skills/create-loop/scripts/project_loop.py:1661-1790] |
| Whole-loop deterministic gate | `scripts/validate_loop_dir.py` | graph, journal payloads, claims, live artifact registry plus durable evidence bindings, child/module contracts [source: skills/create-loop/scripts/validate_loop_dir.py:151-311] [source: skills/create-loop/scripts/validate_loop_dir.py:313-396] [source: skills/create-loop/scripts/validate_loop_dir.py:398-541] [source: skills/create-loop/scripts/validate_loop_dir.py:543-657] [source: skills/create-loop/scripts/validate_loop_dir.py:660-774] |
| Resume generation | `scripts/render_resume.py` | atomic write and read-only `--check` [source: skills/create-loop/scripts/render_resume.py:14-32] |
| v1 migration | `references/migration_v1_to_v2.md` + `scripts/migrate_v1.py` | README-routed maintenance runbook plus pre-resolution symlink/reparse rejection, one byte snapshot, authority-field validation, source-hash journal/report binding, ancestry-safe dry-run staging, pre-publication mutation recheck, canonical single-owner outputs, atomic sibling publication [source: skills/create-loop/references/migration_v1_to_v2.md:1-12] [source: skills/create-loop/scripts/migrate_v1.py:62-105] [source: skills/create-loop/scripts/migrate_v1.py:451-501] [source: skills/create-loop/scripts/migrate_v1.py:716-764] |
| Executable tests | `tests_py/test_v2_*.py` | schema, projector/invariants, optional modules, migration, path/evidence hardening [source: skills/create-loop/tests_py/test_v2_protocol.py:102-278] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:478-626] |

## Baselines and Experiment Infrastructure

- `tests/baselines/v1-8263f09.json` freezes the 2026-07-31 audit at commit `8263f09...`, including the prior 14/15 installer result and known v1 safety defects; it is historical baseline evidence, not current truth [source: skills/create-loop/tests/baselines/v1-8263f09.json:3-9].
- `tests/experiments/scenarios.json` defines 14 paired v1/v2 situations with three runs per version, including no-loop admission, recovery, false completion, effects, concurrency, authorization, and reopen [source: skills/create-loop/tests/experiments/scenarios.json:1-20].
- `preregistration.json` remains the legacy prospective 42-pair/84-run formal
  shell. `pilot-preregistration.json` is the active six-pair Pilot contract: 23
  calls, 1.33M total tokens, 20,100 seconds, no USD measurement, one frozen
  Windows producer CLI slot, and explicit unresolved reviewer/network slots.
  User authorization covers the Pilot/hard call-token-time ceilings; it does
  not turn the legacy formal shell on
  [source: skills/create-loop/tests/experiments/pilot_harness.py:127-151]
  [source: skills/create-loop/tests/experiments/pilot_harness.py:182-239]
  [source: AGENTS.md:73].
- Offline Pilot command entrypoints are `pilot_harness.py validate|plan` and,
  when a corresponding immutable artifact exists,
  `pilot_freeze.py check-pre-calibration --freeze PATH` or
  `pilot_freeze.py check-final --freeze PATH`. These commands validate or
  plan only; they do not create a freeze or launch an adapter
  [source: skills/create-loop/tests/experiments/pilot_harness.py:496-513]
  [source: skills/create-loop/tests/experiments/pilot_harness.py:541-559]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:757-789].
- `baseline-source.{json,tar}` freezes the v1 commit blob set and deterministic
  archive; `candidate-source.json` captures the current v2 worktree; and
  `instrument-manifest.json` binds one exact static evaluator input set.
  `freeze_experiment.py` refreshes those candidate/instrument/preregistration
  bindings in one pass, while `--check` compares without writing [source: skills/create-loop/tests/experiments/snapshot_tools.py:240-345]
  [source: skills/create-loop/tests/experiments/snapshot_tools.py:540-650]
  [source: skills/create-loop/tests/experiments/freeze_experiment.py:19-85].
- `trace.schema.json`, `blind-review-manifest.schema.json`, and
  `report.schema.json` define the run/review/report envelopes. Cross-file
  validators reject timing/provenance drift, A/A blind assignments, path/hash
  drift, report exact-set/arithmetic errors, and fabricated eligibility. Legacy
  reports cannot claim eligibility without a bound authoritative evaluation
  manifest/result [source: skills/create-loop/tests/experiments/experiment_harness.py:430-718]
  [source: skills/create-loop/tests/experiments/experiment_harness.py:843-849].
- `workspace_builder.py` creates deterministic, reality-bound local fixtures and
  presented-artifact manifests; `evaluation.py` verifies canonical blind A/B
  assignment and invokes the frozen `deterministic_runner.py` against both
  source snapshots before accepting submitted suite results. Only the frozen
  deterministic smoke metric is authoritative in the legacy formal shell; the
  other formulas remain `authority-missing` and their gates stay
  `insufficient-data`. `execution_guard.py` supplies the immutable
  grant/ledger/receipt/spend-summary state machine shared by Pilot launch,
  settlement, review sealing, and evaluation replay
  [source: skills/create-loop/tests/experiments/workspace_builder.py:247-396]
  [source: skills/create-loop/tests/experiments/evaluation.py:426-440]
  [source: skills/create-loop/tests/experiments/evaluation.py:515-627]
  [source: skills/create-loop/tests/experiments/execution_guard.py:370-790].
  The runner materializes the complete captured source byte map in a private
  subprocess tree, checks it before and after execution, and never exposes the
  parent source tree to validator/import/schema/fixture swaps
  [source: skills/create-loop/tests/experiments/deterministic_runner.py:35-179]
  [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:299-445].
- Pilot execution routing is authority-first:
  `network_execution_boundary.py` validates both frozen CLI identities and an
  expiring provider-endpoint-only OS proof; `pilot_freeze.py` creates a
  pre-calibration freeze and a raw-derived final freeze;
  `codex_exec_adapter.py` executes one producer episode;
  `pilot_runners.py` owns calibration, isolated review, oracle, and review seal;
  `pilot_campaign.py` assembles frozen evidence without launching a provider;
  and `evaluation.py --pilot` cross-validates three independent grants,
  workspace/evidence/receipt bindings, oracles, and four sealed reviews before
  producing a descriptive report
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-733]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1261-1367]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:242-290]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:855-927]
  [source: skills/create-loop/tests/experiments/evaluation.py:1503-1632]
  [source: skills/create-loop/tests/experiments/evaluation.py:1873-2076].
- Network launch composition currently has one host-outer API. Native
  producer/calibration calls consume it directly; reviewer use is now rejected
  before WSL because this route cannot represent a Linux-only enforcement
  prefix between WSL entry and bubblewrap/Codex, and its generic probe uses the
  host runtime. Treat role/platform-specific composition as a required
  interface refactor, not as evidence that a backend exists
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-379]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:417-462]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1474]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:518-538]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:604-686]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-254]
  [source: skills/create-loop/tests_py/test_experiment_reviewer_isolation.py:387-415].
- Adapter and runner receipts bind raw provider request identity, complete token
  usage, direct evidence, and the final workspace. Their timestamps and
  monotonic wall time now cover the same provider-call interval; reviewer
  isolation preparation occurs before that interval, while guard validation
  keeps its existing one-second consistency bound
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1451-1467]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1645-1768]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:486-623]
  [source: skills/create-loop/tests/experiments/execution_guard.py:308-348].
- Guard replay snapshots are process-local capability tokens for supported
  callers, not a cryptographic or hostile-same-process boundary. Public trace
  validation always replays live authority; the private evaluation batch route
  may reuse a snapshot only before a final recheck. `_pilot_recheck_authorities`
  calls `replay_snapshots()` once for calibration, producer, and reviewer roots,
  so their final authority is observed under one ordered multi-root lock rather
  than three independently drifting reads [source: skills/create-loop/tests/experiments/execution_guard.py:76-89]
  [source: skills/create-loop/tests/experiments/execution_guard.py:1381-1469]
  [source: skills/create-loop/tests/experiments/experiment_harness.py:845-906]
  [source: skills/create-loop/tests/experiments/evaluation.py:1442-1468].
- `tests_py/test_experiment_snapshots.py`, `test_experiment_harness.py`,
  `test_experiment_workspace.py`, `test_experiment_deterministic_runner.py`,
  `test_experiment_evaluation.py`, `test_experiment_execution_guard.py`, and
  the Pilot adapter/freeze/harness/runner/network/evaluation suites validate the
  offline and fake-Codex chain. Fake boundaries prove rejection/control logic,
  not current OS readiness
  [source: skills/create-loop/tests_py/test_experiment_snapshots.py:69-273]
  [source: skills/create-loop/tests_py/test_experiment_harness.py:125-762]
  [source: skills/create-loop/tests_py/test_experiment_workspace.py:34-126]
  [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:28-245]
  [source: skills/create-loop/tests_py/test_experiment_evaluation.py:376-593]
  [source: skills/create-loop/tests_py/test_experiment_execution_guard.py:105-473]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:141-229]
  [source: skills/create-loop/tests_py/test_experiment_codex_adapter.py:324-571]
  [source: skills/create-loop/tests_py/test_experiment_pilot_freeze.py:285-509]
  [source: skills/create-loop/tests_py/test_experiment_pilot_runners.py:273-578].
- Real Pilot execution remains blocked before calibration, freeze, grant, or
  launch because the repository lacks the frozen Linux reviewer Codex `0.144.1`
  identity and authenticated provider-only OS network boundary. Consequently
  there are still zero real calls/tokens/seconds and no v1/v2 result. Even a
  completed Pilot would keep `formal_execution_enabled:false`; the prospective
  formal campaign needs a separate freeze and decision
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests/experiments/evaluation.py:2420-2477]
  [source: AGENTS.md:73].

## Key Entry Points

| Symbol | Location | Role |
|---|---|---|
| `HOSTS` | `bin/create-loop.js:44` | OpenCode/Claude adapters |
| `normalizeState` | `bin/create-loop.js:332` | state v1/v2 validation, root binding, and transaction-anchor shape |
| `planManaged` | `bin/create-loop.js:658` | ownership-aware write planning |
| `planObsolete` | `bin/create-loop.js:703` | conservative obsolete-file reconciliation |
| `transactionIntent` | `bin/create-loop.js:744` | canonical ordered mutation intent |
| `assertTransactionAnchor` | `bin/create-loop.js:773` | bind transaction file to install-state authority and phase |
| `committedStateMatchesTransaction` | `bin/create-loop.js:780` | allow only the exact committed state projection plus conservative create downgrade |
| `recoverTransaction` | `bin/create-loop.js:1020` | validate or resume an anchored interrupted host transaction |
| `applyHostTransaction` | `bin/create-loop.js:1284` | stage, anchor, apply, commit, and clear host mutation |
| `loadCommandManifest` | `bin/create-loop.js:1387` | strict canonical command loading |
| `inspectCommandSkillRoot` | `bin/create-loop.js:1457` | exact Skill identity/script validation |
| `validateCommandSkillProjection` | `bin/create-loop.js:1504` | planned/recovery Skill projection validation |
| `inspectPendingTransactions` | `bin/create-loop.js:1698` | validate every pending transaction without mutation |
| `buildInstallPlans` | `bin/create-loop.js:1723` | construct and validate the current request before recovery |
| `cmdInstall` | `bin/create-loop.js:1837` | locked full-preflight install/upgrade |
| `cmdUninstall` | `bin/create-loop.js:1905` | locked confined tracked removal |
| `cmdRender` | `bin/create-loop.js:1976` | temporary exact-set renderer/check |
| `project` | `skills/create-loop/scripts/project_loop.py:714` | v2 canonical projection |
| `validate_loop_dir` | `skills/create-loop/scripts/validate_loop_dir.py:660` | v2 deterministic directory gate |
| `require_execution_ready` | `skills/create-loop/tests/experiments/network_execution_boundary.py:404` | frozen CLI plus provider-only OS readiness gate |
| `validate_grant_authority` | `skills/create-loop/tests/experiments/pilot_freeze.py:701` | role/freeze/root authority check before Pilot execution |
| `execute` | `skills/create-loop/tests/experiments/codex_exec_adapter.py:1265` | one authority-bound producer episode |
| `_run_codex_call` | `skills/create-loop/tests/experiments/pilot_runners.py:399` | calibration/reviewer provider call with durable recovery |
| `replay` | `skills/create-loop/tests/experiments/execution_guard.py:1374` | hash-chain, budget, receipt, evidence, and in-doubt projection |
| `replay_snapshots` | `skills/create-loop/tests/experiments/execution_guard.py:1381` | one locked replay cut across one or more execution roots |
| `validate_trace` | `skills/create-loop/tests/experiments/experiment_harness.py:845` | public trace validation with fresh execution-authority replay |
| `load_pilot_evaluation_inputs` | `skills/create-loop/tests/experiments/evaluation.py:1644` | cross-validate complete Pilot evidence before reporting |

## Open Questions

- The reference tree still contains broad v1 research/policy documents that are not individually mapped here. Which should remain active versus be marked compatibility-only as v2 matures? [source: skills/create-loop/SKILL.md:808-880] [TODO]
- No CI file currently invokes the combined Node/Python/package gates; the historical project scan records the absence of a committed workflow [source: .agents/knowledge/reference/.project-scan.txt:85-89]. [ASK USER]
- v1 read-only compatibility retirement remains gated on later paired experiments and user release decisions; no removal location should be treated as active yet [source: skills/create-loop/SKILL.md:34-49].

## Correction History

- 2026-08-06: Split readiness scope explicitly. Full-campaign callers validate
  every role and launch topology; role-bound execution validates only its
  effective CLI and topology, with calibration reusing producer. Freeze/grant
  call sites now match those semantics, preventing producer-only authority from
  being mistaken for a complete Pilot boundary
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:407-474]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-353]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:626-641]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:701-736].

- 2026-08-06: Added the fail-closed role boundary for the legacy network
  launcher. Producer/calibration keep the native host-outer path; reviewer is
  rejected before WSL until a guest-local contract is implemented. The Pilot
  remains blocked and the trusted backend registry remains empty
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-333]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1285-1292]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:267-274].

- 2026-08-05: Replaced the stale "unwired guard / unauthorized budget" route
  with the implemented Pilot chain. Guard state is consumed by producer and
  reviewer launch, evidence-first settlement, review sealing, and evaluation;
  the fixed call-token-time ceilings are authorized. Execution remains blocked
  only at the unresolved reviewer CLI and provider-only OS boundary, so no real
  result or default-version conclusion exists
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1261-1367]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:242-290]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests/experiments/evaluation.py:1503-1632]
  [source: AGENTS.md:73].
- 2026-08-05: Added the two-stage Pilot freeze, exact live instrument-input set,
  provider-call wall-time boundary, OS reviewer isolation, and complete
  oracle/review/evidence routing to this map
  [source: skills/create-loop/tests/experiments/snapshot_tools.py:51-157]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-733]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1451-1467]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:486-523]
  [source: skills/create-loop/tests/experiments/evaluation.py:1873-2076].

- 2026-08-01: Added private-tree deterministic replay and migration reparse routing after final review proved the old live-source helper race changed real results and Windows junction inputs required pre-resolution rejection [source: skills/create-loop/tests/experiments/deterministic_runner.py:35-179] [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:299-445] [source: skills/create-loop/scripts/migrate_v1.py:62-105] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:118-240].

- 2026-08-01: Bound blind review labels to the preregistered assignment and made the packaged deterministic catalog/schema/runner authoritative through evaluator replay; submitted suite exact sets, verdicts, and full outputs are now comparison inputs rather than self-certifying results [source: skills/create-loop/tests/experiments/evaluation.py:426-440] [source: skills/create-loop/tests/experiments/evaluation.py:515-627] [source: skills/create-loop/tests_py/test_experiment_evaluation.py:477-624].

- 2026-08-01: Retired the stale candidate-manifest route, made source/instrument snapshots and freeze/check canonical, and documented the trace/blind/report validators plus insufficient-data aggregator shell [source: skills/create-loop/tests/experiments/freeze_experiment.py:19-85] [source: skills/create-loop/tests/experiments/experiment_harness.py:430-718].

- 2026-07-31: Rebuilt the stale 2026-07-03 map. Removed obsolete 556/114-line, R1-R41-only, shell-copier, and three-example claims; added state v2/transactions, v2 schemas/templates/scripts/tests, frozen baseline, 14-scenario experiment infrastructure, and current delivery routing [source: bin/create-loop.js:245-547] [source: bin/create-loop.js:690-958] [source: skills/create-loop/scripts/AGENTS.md:23-52].
- 2026-07-31: Removed exact mutable line/assertion counts and refreshed symbol locations after installer transaction/locking hardening; added confined completion and artifact history/current-selection routing [source: bin/create-loop.js:301-1238] [source: skills/create-loop/scripts/project_loop.py:691-1600] [source: skills/create-loop/scripts/validate_loop_dir.py:229-609].
- 2026-07-31: Added exact package-set, spaced-command, and shared output-path routing after final delivery review exposed those cross-subsystem contracts [source: package.json:37-214] [source: test/installer.test.js:1492-1500] [source: test/installer.test.js:1700-1753] [source: skills/create-loop/scripts/project_loop.py:116-155].
- 2026-07-31: Added command Skill-root projection and pre-recovery planning routes after recovery review established that pending transactions and the new invocation must both pass deterministic preflight before any mutation [source: bin/create-loop.js:1237-1699] [source: test/installer.test.js:345-585].
- 2026-07-31: Added transaction-intent anchor routing and refreshed all installer symbol locations after anchoring hardening; expanded v2 routes for causal plan activation, retired node IDs, durable artifact evidence bindings, and source-stable migration publication [source: bin/create-loop.js:690-749] [source: skills/create-loop/scripts/project_loop.py:810-970] [source: skills/create-loop/scripts/validate_loop_dir.py:398-541] [source: skills/create-loop/scripts/migrate_v1.py:716-764].
- 2026-07-31: Added immutable committed-recovery projection routing and the bounded lightweight durability bridge after crash and protocol review exposed both hidden transition gaps [source: bin/create-loop.js:726-749] [source: test/installer.test.js:817-944] [source: skills/create-loop/tests_py/test_v2_protocol.py:215-329].

## Maintenance

Re-verify line references whenever `bin/create-loop.js`, command bodies/manifest, v2 schemas/scripts, or tests change. Preserve historical baselines as evidence; do not rewrite them to match current behavior.
