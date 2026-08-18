---
type: domain
confidence: verified
scope: ["package.json", "bin/", "test/", "skills/create-loop/scripts/", "skills/create-loop/tests/", "skills/create-loop/tests_py/"]
sources: ["package.json", "bin/create-loop.js", "test/installer.test.js", "skills/create-loop/scripts/AGENTS.md", "skills/create-loop/scripts/schema_runtime.py", "skills/create-loop/tests/baseline_green.sh", "skills/create-loop/tests/experiments/codex_exec_adapter.py", "skills/create-loop/tests/experiments/pilot_runners.py", "skills/create-loop/tests/experiments/pilot_freeze.py", "skills/create-loop/tests/experiments/network_execution_boundary.py", "skills/create-loop/tests/experiments/execution_guard.py", "skills/create-loop/tests/experiments/experiment_harness.py", "skills/create-loop/tests/experiments/evaluation.py", "skills/create-loop/tests/experiments/pilot_harness.py", "skills/create-loop/tests_py/"]
last_verified: 2026-08-06
created: 2026-07-03
---

# Tech stack

`create-loop` is a polyglot, file-oriented package: CommonJS Node delivers and renders the skill; standalone Python validates and projects v1/v2 Loop artifacts. There is no runtime daemon or database [source: package.json:25-35] [source: skills/create-loop/scripts/AGENTS.md:1-5].

## Core Invariants

- The installer targets Node `>=18`, uses CommonJS, and imports only `fs`, `path`, `os`, and `crypto` [source: package.json:25-30] [source: bin/create-loop.js:3-8].
- The Node package has no dependency fields; its CLI, tests, renderer, SHA-256 ownership tracking, atomic files, and recovery transactions use the standard library [source: package.json:1-57] [source: bin/create-loop.js:400-547] [source: bin/create-loop.js:690-958].
- Python 3.10+ is the validator runtime. v1 consumes YAML via PyYAML; v2 consumes JSON/JSONL and has a bundled fail-closed Draft 2020-12 subset [source: skills/create-loop/scripts/AGENTS.md:3-5] [source: skills/create-loop/scripts/AGENTS.md:23-27].
- `schema_runtime.py` explicitly enumerates supported schema keywords and reports unsupported keywords instead of silently ignoring them [source: skills/create-loop/scripts/schema_runtime.py:15-20] [source: skills/create-loop/scripts/schema_runtime.py:64-68].

## Tooling and Commands

- npm exposes `render`, read-only `render:check`, and the zero-dependency installer regression suite as `test` [source: package.json:32-35].
- v1 tools are `validate_loop_plan.py`, `validate_checkpoint.py`, and `check_loop_integrity.py`; v2 tools are `validate_loop_dir.py`, `project_loop.py`, `render_resume.py`, and `migrate_v1.py` [source: skills/create-loop/scripts/AGENTS.md:9-27] [source: skills/create-loop/scripts/AGENTS.md:30-41].
- Executable Python regression tests live in `skills/create-loop/tests_py/`: v1 safety tests cover event/evidence/checkpoint defects, while v2 tests cover schema runtime, projection/invariants, and migration [source: skills/create-loop/tests_py/test_v1_safety.py:19-124] [source: skills/create-loop/tests_py/test_v2_protocol.py:102-278].
- The installer test remains a hand-rolled Node harness rather than Jest/Vitest and performs its cleanup in a `finally` block [source: test/installer.test.js:13-18] [source: test/installer.test.js:1755-1759].
- The WSL/Linux rollback oracle compiles Python sources in memory and disables bytecode writes for the entire script, so running the gate does not leave `__pycache__` artifacts in the Skill tree [source: skills/create-loop/tests/baseline_green.sh:1-50].
- Phase 5 has two deliberately separate experiment surfaces. The legacy
  `experiment_harness.py` still describes a prospective 42-pair/84-run formal
  campaign. The opt-in Pilot uses six fixed pairs, 12 arms, 18 producer
  episodes, one non-scoring calibration call, and four blind reviews; it stops
  after a descriptive report and keeps `formal_execution_enabled:false`
  [source: skills/create-loop/tests/experiments/pilot_harness.py:127-151]
  [source: skills/create-loop/tests/experiments/pilot_harness.py:350-380]
  [source: skills/create-loop/tests/experiments/evaluation.py:2437-2477].
- Pilot and hard ceilings are frozen at 23 calls / 1,330,000 total tokens /
  20,100 seconds and 126 calls / 7,560,000 total tokens / 113,400 seconds.
  USD and pricing-derived fields remain `not-measured`. The user authorized
  these call/token/time ceilings for the Pilot, but that authorization neither
  enables the separate formal campaign nor bypasses execution-readiness gates
  [source: skills/create-loop/tests/experiments/pilot_harness.py:127-151]
  [source: skills/create-loop/tests/experiments/evaluation.py:1618-1632]
  [source: AGENTS.md:72-73].
- The experiment freeze input set is derived from the live non-generated
  experiment tree and classified exactly; unclassified or missing adapter,
  enforcement, schema, fixture, evaluator, or harness files fail before a
  manifest can authorize them. Pilot authority then uses a two-stage freeze:
  pre-calibration static authority, raw-derived calibration evidence, and a
  final freeze for producer/reviewer grants
  [source: skills/create-loop/tests/experiments/snapshot_tools.py:51-157]
  [source: skills/create-loop/tests_py/test_experiment_snapshots.py:219-238]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-368]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:626-733].
- The Pilot guard is connected to real launch and evidence paths. Adapter and
  runner entry points validate canonical freeze/grant authority and the
  separate execution boundary before loading credential-bearing environments,
  initializing or reserving ledger state, or spawning Codex. They reserve the
  exact per-call maximum, preserve provider JSONL, require one unambiguous
  request ID and usage record, freeze workspace/evidence manifests, write the
  receipt, and settle through the hash-chained guard. Pilot evaluation and
  review sealing replay the same grant/anchor/spend, receipt, evidence,
  workspace, oracle, and review bindings rather than trusting trace labels
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1261-1367]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1439-1467]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1645-1768]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:242-290]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:401-623]
  [source: skills/create-loop/tests/experiments/evaluation.py:1276-1354]
  [source: skills/create-loop/tests/experiments/evaluation.py:1560-1632]
  [source: skills/create-loop/tests/experiments/evaluation.py:1873-2076].
- Receipt timestamps and monotonic wall time now cover the same provider-call
  interval. Adapter postflight validation is excluded; reviewer isolation is
  prepared first, then the outer runner measures the complete reviewer launch
  rather than trusting an inner elapsed value. The one-second guard tolerance
  remains unchanged
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1451-1467]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:486-523]
  [source: skills/create-loop/tests/experiments/execution_guard.py:308-348]
  [source: skills/create-loop/tests_py/test_experiment_codex_adapter.py:360-415]
  [source: skills/create-loop/tests_py/test_experiment_pilot_runners.py:492-578].
- Real Pilot execution is still fail-closed. The repository reports exactly two
  unresolved readiness blockers: a frozen Linux reviewer Codex `0.144.1`
  identity and an authenticated OS-enforced default-deny boundary limited to
  the frozen provider endpoint. A tool-profile string is not a substitute for
  either proof; no real provider call, grant, receipt, or Pilot result exists
  yet [source: skills/create-loop/tests/experiments/network_execution_boundary.py:114-163]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:166-295]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:152-183]
  [source: AGENTS.md:73].
- Availability of `bwrap`, `nft`, and `iptables` is not execution readiness.
  The production backend registry remains empty, the reviewer bubblewrap layer
  deliberately delegates networking to an outer launcher, and the current
  proof path checks only one allowed and one denied TCP probe. A trusted backend
  still needs protected implementation identity plus runtime evidence for its
  namespace, default-deny policy, DNS/IPv4/IPv6 behavior, and process-tree
  inheritance [source: skills/create-loop/tests/experiments/network_execution_boundary.py:34-39]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:239-283]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:348-380]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:376-413].
- The current boundary contract is not only missing a trusted backend; its one
  outer `launch_prefix` shape cannot model both supported launch topologies.
  Producer/calibration can prepend a Windows wrapper directly to Codex, but a
  Linux reviewer enforcer must sit after WSL entry and before bubblewrap/Codex.
  Runtime therefore rejects reviewer use of the v1 prefix before launch instead
  of wrapping `wsl.exe`. The generic live probe still invokes host
  `sys.executable`, so it cannot prove a reviewer-local runtime boundary. Any
  future backend contract must bind role/platform, insertion point, probe
  runtime, and the exact protected process tree rather than merely adding a
  registry entry
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-379]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:417-462]
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1285-1292]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:518-538]
  [source: skills/create-loop/tests/experiments/reviewer_isolation.py:604-686]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-254]
  [source: skills/create-loop/tests_py/test_experiment_reviewer_isolation.py:387-415].
- Guard replay snapshots are process-local opaque capabilities rather than
  serializable evidence. Public trace validation always replays the current
  execution root; only the private evaluation batch path may reuse a snapshot,
  and Pilot final authority reconciliation takes one locked cut across the
  calibration, producer, and reviewer roots. Replay time must be timezone-aware,
  no earlier than the ledger tail, and no more than five seconds ahead of the
  local UTC clock [source: skills/create-loop/tests/experiments/execution_guard.py:76-89]
  [source: skills/create-loop/tests/experiments/execution_guard.py:241-252]
  [source: skills/create-loop/tests/experiments/execution_guard.py:1381-1469]
  [source: skills/create-loop/tests/experiments/experiment_harness.py:845-906]
  [source: skills/create-loop/tests/experiments/evaluation.py:1442-1468].

## Package and Text Policy

- The npm `files` array enumerates every shipped path individually; it contains no directories, globs, or negative rules, and includes the root and Skill-local custom license payloads [source: package.json:37-214].
- Package verification is executable: two `npm pack --dry-run --json` manifests must match and the complete packed path set must equal the declared payload plus `package.json`; required payloads must exist, while caches, dependencies, `.pyc`, and undeclared files remain absent [source: test/installer.test.js:1720-1753].
- Generated protocol bundles are authenticated frozen evaluator snapshots, not live package source. Pointer checking excludes their Markdown with an explicit count while bundle manifests bind their bytes; npm likewise excludes bundles and raw experiment outputs [source: skills/create-loop/scripts/check_pointers.py:139-149] [source: skills/create-loop/scripts/check_pointers.py:162-208] [source: test/installer.test.js:1910-1931].
- The supported Node floor/new-runtime matrix is executable through `test/node-matrix.js`, using pinned official Node 18.20.8 and 24.13.0 archive hashes and an external cache [source: test/node-matrix.js:2] [source: test/node-matrix.js:12-20] [source: test/node-matrix.js:84-119].
- Repository-generated Markdown, JSON, JavaScript, and shell files are normalized to LF to avoid Windows renderer drift [source: .gitattributes:1-5].
- Knowledge health separates the immutable historical inbox total from the
  active backlog: `inbox_count` counts every `##` record, while
  `inbox_unprocessed_count` excludes entries explicitly absorbed or
  superseded. The project stop hook uses the active backlog, with a legacy
  fallback to `inbox_count`, and the OpenCode bridge preserves stop-hook stderr
  separately from compact-hook stdout [source: .agents/knowledge/manifest.json:193-200]
  [source: .agents/hooks/stop.sh:18-45]
  [source: .agents/hooks/opencode-plugin.mjs:11-57].
- License authority is the custom source-available `LICENSE`, not the standard SPDX `BUSL-1.1` text. npm metadata uses `SEE LICENSE IN LICENSE`, and the root and Skill-local payloads must remain byte-identical so installed references resolve [source: package.json:23] [source: package.json:46] [source: package.json:59] [source: test/installer.test.js:1720-1724].

## Architecture Consequences

- There is no npm install/build phase needed to execute the CLI from a GitHub package; adding a runtime npm dependency would break a primary distribution invariant [source: package.json:26-35] [source: bin/create-loop.js:1-8].
- JSON Schema has two roles: v1 retains Draft-07 schemas, while v2 core schemas are Draft 2020-12 and runtime-validated through the bundled subset with optional CI parity against full `jsonschema` [source: command/manifest.schema.json:1-3] [source: skills/create-loop/scripts/AGENTS.md:49-52].
- v2 writes JSON/JSONL control artifacts; v1 compatibility remains YAML plus JSONL event logs. Tool selection must follow detected protocol rather than file extension assumptions alone [source: command/loop-run.md:10-20] [source: skills/create-loop/references/protocol_v2.md:23-40].

## Common Mistakes

- Do not use Node APIs newer than the declared Node 18 floor in installer or test code [source: package.json:29-30].
- Do not make `jsonschema` mandatory for normal installed operation; the bundled runtime exists to keep v2 zero-dependency and fail closed [source: skills/create-loop/scripts/schema_runtime.py:1-5] [source: skills/create-loop/scripts/AGENTS.md:23-25].
- Do not treat `.opencode/node_modules/` or Python caches as project sources or package payload [source: package.json:37-214] [source: test/installer.test.js:1725-1753].
- Do not rely on the old `.project-scan.txt` file counts as current inventory; it predates v2 schemas/scripts/tests and the delivery rewrite [source: .agents/knowledge/reference/.project-scan.txt:1-4].

## Verified Facts

- `SKILL.md` is governed by an executable 1000-line ceiling; v2 detail is routed through `references/protocol_v2.md` and scripts rather than duplicating the full protocol in the entrypoint [source: skills/create-loop/tests/acceptance_tests.md:215-225] [source: skills/create-loop/SKILL.md:808-880].
- The installer harness derives its pass/fail count from every `ok(...)` assertion and emits a zero-failure summary; baseline integration checks match that summary rather than pinning an assertion count that changes as safety coverage grows [source: test/installer.test.js:13-18] [source: test/installer.test.js:1755-1759] [source: skills/create-loop/tests/baseline_green.sh:117-122].

## Open Questions

- No committed CI workflow currently expresses the combined Node and Python gate. Should a future CI matrix pin Node 18 plus one newer Node and multiple Python versions? [source: .agents/knowledge/reference/.project-scan.txt:85-89] [ASK USER]
- Python 3.10 is now the explicit floor because the validator code uses modern generics/unions and `dataclass(slots=True)` [source: skills/create-loop/scripts/checks/checkpoint_projection.py:11] [source: skills/create-loop/scripts/schema_runtime.py:27-58].
- Full `jsonschema` parity is described as a CI responsibility, but no dependency manifest or CI job currently pins its version [source: skills/create-loop/scripts/AGENTS.md:49-52]. [TODO]
- Which approved installation and enforcement route will supply the exact Linux
  reviewer Codex `0.144.1` bytes and an expiring, authenticated provider-only
  OS network boundary? Until both bindings are frozen, calibration and grant
  creation must remain blocked before credentials or ledger mutation
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:152-183]. [ASK USER/EXTERNAL]
- A full formal default-version experiment still needs a separately frozen
  multi-instance campaign. The six-pair Pilot can report only a task-scoped
  tendency and must not be relabeled as significance or release evidence
  [source: skills/create-loop/tests/experiments/evaluation.py:2420-2477].

## Correction History

- 2026-08-06: Made the legacy network launcher topology explicit in code. The
  host-outer prefix is accepted only for native producer/calibration; reviewer
  readiness fails before WSL or Codex until a guest-local role/platform contract
  exists. This preserves the empty trusted-backend registry and does not claim
  real OS isolation
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:286-333]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-302]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-254]
  [source: skills/create-loop/tests_py/test_experiment_reviewer_isolation.py:387-415].

- 2026-08-06: Readiness now distinguishes one-role execution from complete
  Pilot authority. Calibration reuses the producer CLI; producer/calibration
  launch gates validate only that effective identity and launch topology, while an
  omitted role means all Pilot roles and therefore fails on the unsupported v1
  reviewer topology. Both freeze phases and every grant revalidate complete
  Pilot readiness before any real call; only the adapter/runner launch path may
  narrow readiness to the role it is about to execute
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:33-38]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:407-474]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:341-353]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:626-641]
  [source: skills/create-loop/tests/experiments/pilot_freeze.py:701-736]
  [source: skills/create-loop/tests_py/test_experiment_network_execution_boundary.py:200-247]
  [source: skills/create-loop/tests_py/test_experiment_pilot_freeze.py:285-314]
  [source: skills/create-loop/tests_py/test_experiment_pilot_freeze.py:490-552].

- 2026-08-06: Recorded the final replay-authority boundary and its executable
  regression result. Ordinary callers cannot construct an accepted
  `ReplaySnapshot` through the public path; this is a process-local API
  capability, not a cryptographic or hostile-same-process security boundary.
  Manifest grant/anchor/summary bindings are rechecked while the
  execution lock is held; canonical anchor/summary bytes and replay-time bounds
  are mandatory; and the three Pilot execution roots receive one atomic final
  authority cut. The complete Python suite passed 474 tests with 4 environment
  skips, while freeze/harness validation still reported zero real traces and an
  execution-blocked Pilot [source: skills/create-loop/tests/experiments/execution_guard.py:76-89]
  [source: skills/create-loop/tests/experiments/execution_guard.py:1381-1469]
  [source: skills/create-loop/tests/experiments/evaluation.py:1360-1468]
  [source: skills/create-loop/tests_py/test_experiment_execution_guard.py:426-466]
  [source: skills/create-loop/tests_py/test_experiment_pilot_evaluation.py:203-313].

- 2026-08-05: Superseded the 2026-08-01 statement that the spend guard was
  unwired and the budget was unauthorized. The Pilot adapter, runner,
  evaluation, and review seal now consume canonical guard authority and direct
  evidence; the user authorized the fixed Pilot/hard call-token-time ceilings.
  Execution nevertheless remains at zero because the reviewer CLI identity and
  provider-only OS boundary fail before credentials, ledger initialization, or
  launch [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1261-1367]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:242-290]
  [source: skills/create-loop/tests/experiments/network_execution_boundary.py:236-295]
  [source: skills/create-loop/tests/experiments/evaluation.py:1560-1632]
  [source: AGENTS.md:73].
- 2026-08-05: Corrected receipt timing after a load-sensitive regression showed
  timestamps included postflight work while `wall_seconds` measured only the
  subprocess. Both adapter and runner now align timestamp and monotonic bounds;
  reviewer isolation preparation stays outside the charged call window, and
  the deterministic delay controls pass without weakening the guard tolerance
  [source: skills/create-loop/tests/experiments/codex_exec_adapter.py:1451-1467]
  [source: skills/create-loop/tests/experiments/pilot_runners.py:486-523]
  [source: skills/create-loop/tests_py/test_experiment_codex_adapter.py:360-415]
  [source: skills/create-loop/tests_py/test_experiment_pilot_runners.py:492-578].

- 2026-08-01: The 35-file instrument exact set now includes separate case and authoritative-run schemas. Replay binds imported runner bytes, all deterministic schemas, captured fixtures, and validator immutability; v1 alone receives user-site PyYAML while v2 runs with `-s` [source: skills/create-loop/tests/experiments/snapshot_tools.py:50-84] [source: skills/create-loop/tests/experiments/deterministic_runner.py:31-37] [source: skills/create-loop/tests/experiments/deterministic_runner.py:390-444] [source: skills/create-loop/tests/experiments/deterministic_runner.py:486-581] [source: skills/create-loop/tests_py/test_experiment_deterministic_runner.py:28-245].

- 2026-08-01: Corrected the evaluator authority boundary: only the frozen deterministic smoke metric can drive an authoritative gate today. Oracle, review, recovery, cost, and productivity formulas remain present but emit `authority-missing:*` and `insufficient-data` until typed telemetry, independent review receipts, and authoritative workspace bindings exist [source: skills/create-loop/tests/experiments/evaluation.py:73-92] [source: skills/create-loop/tests/experiments/evaluation.py:823-890] [source: skills/create-loop/tests_py/test_experiment_evaluation.py:401-439].

- 2026-08-01: Added the source/instrument snapshot and freeze toolchain, expanded experiment regression coverage beyond planning/authorization, and recorded that the packaged payload must carry the complete offline validation chain [source: skills/create-loop/tests/experiments/freeze_experiment.py:19-85] [source: skills/create-loop/tests_py/test_experiment_snapshots.py:69-273] [source: package.json:202-225].

- 2026-07-31: Replaced the stale Node-only scan summary and fixed installer-test count. Current stack includes v2 JSON/JSONL Python tooling, executable `unittest` suites, package-manifest assertions, LF policy, and a dynamically counted zero-failure installer gate [source: skills/create-loop/scripts/AGENTS.md:23-52] [source: test/installer.test.js:13-18] [source: test/installer.test.js:1755-1759].
- 2026-07-31: Corrected package knowledge from an extension-oriented allowlist to a per-file exact payload with full dry-run manifest equality [source: package.json:37-214] [source: test/installer.test.js:1720-1753].
- 2026-07-31: Corrected the license description: the package does not claim the standard BUSL-1.1 text; the custom root `LICENSE` controls and is duplicated byte-for-byte in the installed Skill payload [source: package.json:23] [source: test/installer.test.js:1720-1724].
- 2026-07-31: Corrected the rollback oracle's compilation step after WSL verification showed that `py_compile` writes source-tree caches even when the caller exports `PYTHONDONTWRITEBYTECODE`; the script now owns a no-bytecode invariant and compiles sources in memory [source: skills/create-loop/tests/baseline_green.sh:1-50].

## Related

- [installer.md](installer.md) - Node delivery implementation
- [validator-engine.md](validator-engine.md) - v1/v2 deterministic checks
- [../reference/code-map.md](../reference/code-map.md) - concrete file routing
