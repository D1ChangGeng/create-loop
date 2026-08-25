# create-loop — PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-03 · **Last reconciled:** 2026-08-06 · **Branch:** main

## OVERVIEW
`create-loop` is a **meta Agent Skill** ("write the loop, not the prompt"). v1 remains the compatibility default; explicit opt-in v2 adds a smaller JSON/JSONL execution-control core while paired validation is pending. This repo is **the packaged skill + its standalone installer + slash commands**, NOT a daemon or loop runtime.

## STRUCTURE
```
create-loop/
├── bin/create-loop.js       standalone installer CLI (Node ≥18, ZERO deps; install/uninstall/render/list)
├── command/                 CANONICAL slash-command source (manifest.json + frontmatter-free bodies)
├── .opencode/command/       RENDERED OpenCode commands — generated, do not hand-edit
├── .claude/commands/        RENDERED Claude Code commands — generated, do not hand-edit
├── install-commands.sh      compatibility wrapper over Node --commands-only
├── test/installer.test.js   renderer/installer/package safety regression
├── skills/create-loop/      THE INSTALLABLE SKILL (see its own AGENTS.md)
│   ├── references/protocol_v2.md  opt-in v2 runtime protocol
│   ├── references/migration_v1_to_v2.md  README migration workflow and source-binding runbook
│   ├── scripts/{project_loop,validate_loop_dir,render_resume,migrate_v1}.py
│   ├── tests/experiments/   freeze/check, workspace fixtures, offline evaluation, execution guard
│   └── tests_py/            executable v1/v2 safety + experiment workspace/evaluation/guard tests
├── .agents/loops/           runtime loop state home (created at USE time, not part of source)
└── .opencode/node_modules/  third-party deps — NOISE, ignore entirely
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| What the skill teaches / its protocol | [skills/create-loop/SKILL.md](skills/create-loop/SKILL.md) (≤1000-line entrypoint) |
| v1 locked vocabulary / fields | `skills/create-loop/references/loop_plan_spec.md` + `state_model.md` |
| v2 protocol / authority / state / journal | `skills/create-loop/references/protocol_v2.md` |
| Explicit v1 → v2 migration | root/Skill README → `skills/create-loop/references/migration_v1_to_v2.md` |
| Add/edit a slash command | [command/](command/) → then `render` |
| Change install behavior | [bin/create-loop.js](bin/create-loop.js) |
| v1 validators (R-family compatibility) | [skills/create-loop/scripts/](skills/create-loop/scripts/) |
| v2 projector / deterministic gate | `project_loop.py` + `validate_loop_dir.py` |
| Phase 5 offline experiment infrastructure | `workspace_builder.py` + `evaluation.py` + `execution_guard.py` |
| Regression gate | `skills/create-loop/tests_py/` + experiment freeze/check/validate + `skills/create-loop/tests/acceptance_tests.md` + `test/installer.test.js` |
| Deep per-area knowledge | [.agents/knowledge/domains/](.agents/knowledge/domains/) (installer, commands, skill-protocol, validator-engine, tech-stack) |
| Full code map + routing | [.agents/knowledge/reference/code-map.md](.agents/knowledge/reference/code-map.md) |

## COMMANDS
```bash
node bin/create-loop.js render      # regenerate .opencode/command + .claude/commands from command/ (npm run render)
node test/installer.test.js         # installer regression (npm test) — asserts render determinism
node test/node-matrix.js --download --full # official-hash Node 18.20.8/24.13.0 matrix; cache stays outside repo
# skill-side validators (need python3 + PyYAML):
python3 skills/create-loop/scripts/validate_loop_plan.py <plan.yaml>
python3 skills/create-loop/scripts/check_loop_integrity.py <loop-dir>
# v2 core:
python skills/create-loop/scripts/validate_loop_dir.py <loop-dir>
python skills/create-loop/scripts/render_resume.py <loop-dir> --check
python -m unittest discover -s skills/create-loop/tests_py
python skills/create-loop/tests/experiments/freeze_experiment.py --check
python skills/create-loop/tests/experiments/experiment_harness.py validate
python skills/create-loop/tests/experiments/experiment_harness.py plan
python skills/create-loop/tests/experiments/pilot_harness.py validate
python skills/create-loop/tests/experiments/pilot_harness.py plan
# pilot freeze artifacts are optional; these commands only validate an existing artifact:
python skills/create-loop/tests/experiments/pilot_freeze.py check-pre-calibration --freeze <path>
python skills/create-loop/tests/experiments/pilot_freeze.py check-final --freeze <path>
```

## CONVENTIONS
- **Slash commands have ONE source of truth: `command/`.** `.opencode/command/*.md` and `.claude/commands/*.md` are RENDERED artifacts. Edit a body in `command/`, edit metadata in `command/manifest.json`, then `node bin/create-loop.js render`, then commit `command/` AND both rendered dirs together.
- **`render --check` is read-only and exact-set deterministic**; tests must not rewrite canonical source or tracked generated files.
- Frontmatter is NOT stored in bodies: OpenCode gets `description`; Claude gets
  `description` plus `argument-hint`. The renderer injects host metadata.
- Installer is **zero-dependency** Node ≥18 (only `fs/path/os/crypto`). Do not add npm runtime deps to `bin/`.
- Skill runtime state lives in `.agents/loops/L<seq>-<slug>/` on the filesystem — there is NO daemon, DB, or background process. v1 and v2 write paths must be explicitly detected and never mixed.
- v2 is opt-in. Ordinary tasks create no Loop; lightweight writes goal+plan; persistent/governed add journal+generated resume and only risk-triggered modules.
- v2 output paths share one canonicalizer across plans, migration, projection, and validation; Win32-unmaterializable names fail closed, and directory deliverables never carry file hashes.
- Phase 5 freeze has one exact instrument input set. Run `freeze_experiment.py` after reviewed source changes, then `--check`; offline freeze/check/harness validation reports planned runs separately from validated traces and never launches an adapter.
- Phase 5 includes an opt-in six-pair Pilot execution chain. Authority-first adapter and runner paths validate the canonical grant and a separate OS-enforced provider-only network boundary before reading credentials, initializing or reserving ledger budget, or launching Codex. Guard replay snapshots are process-local capabilities for ordinary callers, not a cryptographic or hostile-same-process boundary; standalone trace validation always replays current authority, while Pilot evaluation takes one locked multi-root final cut and rejects authority drift. Raw provider request identity and token usage, workspace and evidence manifests, receipts, settlement, traces, oracle results, and blind-review seals are cross-validated. The repository remains fail-closed because the Linux reviewer Codex `0.144.1` identity and authenticated OS-level network boundary are unresolved, so no real provider call has occurred. The current single outer-prefix launch contract cannot express the different enforcement insertion points needed by a native Windows producer and a WSL reviewer; runtime now accepts it only for producer/calibration and rejects reviewer launch before WSL. Do not register a backend until a role/platform-specific guest contract and real OS enforcement are implemented. Pilot and hard limits are frozen at 23 calls / 1.33M tokens / 20,100 seconds and 126 calls / 7.56M tokens / 113,400 seconds; USD remains `not-measured`. The legacy 42-pair / 84-run plan is prospective only. `formal_execution_enabled` remains false, and no default-version or v2-superiority conclusion exists.
- License authority is the custom source-available text in `LICENSE` (not the standard SPDX `BUSL-1.1` text); it converts to Apache-2.0 on 2030-07-02. Keep the root and Skill-local copies identical.

## ANTI-PATTERNS (THIS PROJECT)
- **NEVER hand-edit `.opencode/command/` or `.claude/commands/`** — they are overwritten by `render`. Edit `command/` instead.
- NEVER commit a `command/` change without re-rendering (host files drift silently otherwise).
- NEVER add a runtime npm dependency to the installer.
- Do NOT treat `.opencode/node_modules/` as project code — it is vendored third-party noise.
- Do NOT edit `SKILL.md` and its protocol references independently: v1 vocabulary lives in `loop_plan_spec.md`/`state_model.md`; v2 lives in `protocol_v2.md` plus its Draft 2020-12 schemas.

## NOTES
- Three user install paths: (A) `npx github:D1ChangGeng/create-loop` = Node installer, skill + commands, hash-tracked upgrade; (B) `./install-commands.sh` = commands only; (C) `npx skills add … --skill create-loop` = skill only (`npx skills add` never writes a host command dir — that is why commands ship separately at repo root).
- Installer tracks every written file by sha256 in `install-state.json` (global `~/.config/create-loop/`, project `<proj>/.create-loop/`) → re-run upgrades in place, preserves user-edited files (`--force` to overwrite).

## SESSION START

1. Read this file for project overview and routing.
2. Check `.agents/knowledge/manifest.json` — `inbox_count` is the historical total, while `inbox_unprocessed_count` is the active backlog; if the latter is `> 10` or `days_since_evolution > 14`, suggest an evolution pass to the user.
3. Read the relevant `.agents/knowledge/domains/*.md` for your current task (use the WHERE TO LOOK table above).

## CODING DISCIPLINE

These behavioral rules reduce common AI coding mistakes. They bias toward caution over speed — for trivial, local tasks, use judgment. Escalate caution on subsystem transitions, external-system operations, or knowledge-affecting work.

**Think before coding.** State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. If something is unclear, stop and ask.

**Simplicity first.** Minimum code that solves the problem. No speculative features, no premature abstractions, no error handling for impossible scenarios. If you wrote 200 lines and it could be 50, rewrite it.

**Surgical changes.** Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Match existing style. If your changes create orphans (unused imports/variables), clean those up — but don't remove pre-existing dead code unless asked.

**Goal-driven execution.** Transform tasks into verifiable goals before starting. For multi-step tasks, state a plan with verification checkpoints. Loop until verified — don't declare done without evidence.

**Context familiarity is not domain competence.** When a task shifts to a subsystem you haven't read the source for in this session, read the relevant domain file before acting. If you cannot cite the specific file/line that governs the behavior you're about to change, you don't know enough yet.

**No partial delivery.** When a task requires multiple steps, complete all of them. If blocked, state the blocker and propose alternatives instead of delivering an incomplete result.

**Project-specific gates.** Editing `command/` bodies or `manifest.json` → run `node bin/create-loop.js render`, `render --check`, then `node test/installer.test.js`, and keep `command/` + both rendered dirs together. Editing v1 vocabulary follows references → schemas → `scripts/checks/__init__.py` → SKILL. Editing v2 follows `protocol_v2.md` → v2 schemas → projector/validator → SKILL. Run executable tests for both.

## POST-TASK CHECKLIST

After completing any non-trivial task:

1. Run tests if code was changed (`node test/installer.test.js` for installer/command changes; the skill acceptance gate for skill changes).
2. Check if any of these knowledge capture conditions apply:
   - Discovered how something works that was not already documented
   - Fixed a bug that revealed a hidden assumption
   - Made a decision that constrains future implementation choices
   - Noticed a pattern that spans multiple files, modules, or workflows
   - Found that existing knowledge was wrong, incomplete, or outdated
   - Found that the self-evolution skill itself had a flaw (tag as `[SKILL-FIX:self-evolution]`)
3. If any condition is met, **write the inbox entry NOW** — append to `.agents/knowledge/inbox/{YYYY-MM}.md` before reporting completion:
   ```
   ## {date} {time} — {context}
   - {observation}
   - [source: {file:line}]
   ```
   If existing knowledge needs correction, tag with `[DOMAIN-FIX: domains/X.md]`.
4. **State your capture decision in one line** after acting (e.g. `Capture: none`, `Capture: inbox (hidden assumption in X)`).

### Skill Ecosystem

Before building a capability from scratch, check if a skill already exists: ensure `find-skills` is available (`npx skills add https://github.com/vercel-labs/skills --skill find-skills -g -y`), then `npx skills find [query]`. If a workflow has been refined 3+ times, consider crystallizing it via `skill-creator`.

See `.agents/knowledge/README.md` for the full protocol, confidence model, and promotion rules.

## SELF-EVOLUTION RULES

When modifying this codebase, update knowledge **in the same commit**:

- New host adapter / installer behavior → update `domains/installer.md`
- New slash command or render change → update `domains/commands.md` + `reference/code-map.md`
- New skill vocabulary / status / gate / node kind → update `domains/skill-protocol.md` and `domains/validator-engine.md`
- New validator rule → update `domains/validator-engine.md`
- Significant structure change → update `reference/code-map.md` and the STRUCTURE + WHERE TO LOOK sections above

**Single Source of Truth:** Each rule has exactly one canonical home in `.agents/knowledge/domains/`. This file holds summaries with pointers. When updating a rule, update the domain file — not this file.

- **Confidence:** All AI-generated knowledge starts as `observed`. To earn `verified`, cite 2+ corroborating sources. Only human-approved, stable knowledge becomes `canonical`.
- **Evidence:** Every non-trivial claim needs `[source: file:line]`.
- **Unknowns:** "Open Questions" sections are mandatory in domain files.
- **Conflicts:** When two knowledge entries contradict, surface BOTH. Never silently pick one side.
