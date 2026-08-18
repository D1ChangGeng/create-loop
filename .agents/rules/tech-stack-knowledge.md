---
description: "Read tech-stack knowledge before modifying files in this scope"
globs:
  - "package.json"
  - "bin/**"
  - "test/**"
  - "skills/create-loop/scripts/**"
  - "skills/create-loop/tests/**"
  - "skills/create-loop/tests_py/**"
---
Before making changes in this area, read `.agents/knowledge/domains/tech-stack.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- Installer stays zero-runtime-dependency (Node stdlib only), Node >=18.
- Two toolchains: Node.js for installer/render/delivery tests and Python 3.10+ for v1/v2 validators, projection, resume, and migration.
- npm exposes `render`, read-only `render:check`, and `test`; the installer suite remains a hand-rolled zero-dependency harness.
- v1 YAML tooling needs PyYAML; v2 runtime uses bundled JSON/JSONL schema support and must not require `jsonschema` in installed operation.
- The npm payload is an explicit per-file allowlist verified by exact `npm pack --dry-run --json` path equality.
- The custom source-available `LICENSE` is authoritative; npm uses `SEE LICENSE IN LICENSE`, and the root/Skill-local copies stay byte-identical.
- Python syntax gates compile in memory with bytecode writes disabled; they must not leave `__pycache__` in the source tree.
- Phase 5 has two surfaces: the legacy prospective 42-pair/84-run formal shell and an opt-in six-pair Pilot. Do not report planned runs as executed evidence.
- The Pilot guard is wired through adapter/runner launch, evidence-first settlement, review sealing, and evaluation replay. Authority and the provider-only OS boundary must validate before credential reads, ledger initialization/reservation, or Codex launch.
- Pilot/hard ceilings are authorized and fixed at 23 calls / 1.33M tokens / 20,100 seconds and 126 calls / 7.56M tokens / 113,400 seconds; USD remains `not-measured`. Authorization does not bypass technical readiness or enable the formal campaign.
- Real execution remains fail-closed until the frozen Linux reviewer Codex `0.144.1` identity and authenticated default-deny provider-endpoint-only network boundary exist. Until then the authoritative usage is zero and there is no v1/v2 result.
- The legacy host-outer network prefix is not a reviewer contract; runtime rejects reviewer composition before WSL/Codex and keeps the trusted backend registry empty until a guest-local role/platform boundary is implemented.
- Readiness scope is explicit: no role means complete Pilot topology; freeze construction and every grant validation always use that full gate, while calibration/producer/reviewer launch paths may validate only the role they are about to execute.
- Knowledge health uses `inbox_unprocessed_count` for active pressure; `inbox_count` is the historical total. Hook scripts must remain LF, and the OpenCode bridge must preserve stop stderr versus compact stdout.
- Receipt timestamps and monotonic wall time must describe the same provider-call interval; do not widen guard tolerance to hide setup/postflight timing drift.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
