# create-loop — PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-03 · **Commit:** a724311 · **Branch:** main

## OVERVIEW
`create-loop` is a **meta Agent Skill** ("write the loop, not the prompt"): given a short goal it emits a `loop.plan` — a recursive execution-control DAG + evidence gates + a filesystem state contract a fresh zero-memory agent can resume. This repo is **the packaged skill + its standalone installer + slash commands**, NOT a loop runtime. Two artifact classes: the skill itself (Markdown + JSON Schema + Python validators), and the delivery machinery (Node installer, rendered host commands).

## STRUCTURE
```
create-loop/
├── bin/create-loop.js       standalone installer CLI (Node ≥18, ZERO deps; install/uninstall/render/list)
├── command/                 CANONICAL slash-command source (manifest.json + frontmatter-free bodies)
├── .opencode/command/       RENDERED OpenCode commands — generated, do not hand-edit
├── .claude/commands/        RENDERED Claude Code commands — generated, do not hand-edit
├── install-commands.sh      Path-B installer (copies rendered commands only)
├── test/installer.test.js   asserts `render` is byte-for-byte deterministic
├── skills/create-loop/      THE INSTALLABLE SKILL (see its own AGENTS.md)
├── .agents/loops/           runtime loop state home (created at USE time, not part of source)
└── .opencode/node_modules/  third-party deps — NOISE, ignore entirely
```

## WHERE TO LOOK
| Task | Location |
|------|----------|
| What the skill teaches / its protocol | [skills/create-loop/SKILL.md](skills/create-loop/SKILL.md) (≤1000-line entrypoint) |
| Locked vocabulary / enums / field dicts | `skills/create-loop/references/loop_plan_spec.md` + `state_model.md` |
| Add/edit a slash command | [command/](command/) → then `render` |
| Change install behavior | [bin/create-loop.js](bin/create-loop.js) |
| Validator rules (R1–R41) | [skills/create-loop/scripts/](skills/create-loop/scripts/) |
| Regression gate | `skills/create-loop/tests/acceptance_tests.md` + `test/installer.test.js` |

## COMMANDS
```bash
node bin/create-loop.js render      # regenerate .opencode/command + .claude/commands from command/ (npm run render)
node test/installer.test.js         # installer regression (npm test) — asserts render determinism
# skill-side validators (need python3 + PyYAML):
python3 skills/create-loop/scripts/validate_loop_plan.py <plan.yaml>
python3 skills/create-loop/scripts/check_loop_integrity.py <loop-dir>
```

## CONVENTIONS
- **Slash commands have ONE source of truth: `command/`.** `.opencode/command/*.md` and `.claude/commands/*.md` are RENDERED artifacts. Edit a body in `command/`, edit metadata in `command/manifest.json`, then `node bin/create-loop.js render`, then commit `command/` AND both rendered dirs together.
- **`render` is deterministic** — running it on unchanged `command/` must reproduce host files byte-for-byte (`test/installer.test.js` asserts this).
- Frontmatter is NOT stored in bodies: OpenCode gets `agent: build`, Claude gets `argument-hint` — the renderer injects each per host.
- Installer is **zero-dependency** Node ≥18 (only `fs/path/os/crypto`). Do not add npm runtime deps to `bin/`.
- Skill runtime state lives in `.agents/loops/L<seq>-<slug>/` on the filesystem — there is NO daemon, DB, or background process. "Degraded mode" (no subagents/hooks) is the same contract with fewer conveniences, never a second implementation.
- License is **BUSL-1.1** (converts to Apache-2.0 on 2030-07-02). Keep new files consistent.

## ANTI-PATTERNS (THIS PROJECT)
- **NEVER hand-edit `.opencode/command/` or `.claude/commands/`** — they are overwritten by `render`. Edit `command/` instead.
- NEVER commit a `command/` change without re-rendering (host files drift silently otherwise).
- NEVER add a runtime npm dependency to the installer.
- Do NOT treat `.opencode/node_modules/` as project code — it is vendored third-party noise.
- Do NOT edit `SKILL.md` and its `references/` vocabulary independently — the references are the source of truth; SKILL.md must agree.

## NOTES
- Three user install paths: (A) `npx github:D1ChangGeng/create-loop` = Node installer, skill + commands, hash-tracked upgrade; (B) `./install-commands.sh` = commands only; (C) `npx skills add … --skill create-loop` = skill only (`npx skills add` never writes a host command dir — that is why commands ship separately at repo root).
- Installer tracks every written file by sha256 in `install-state.json` (global `~/.config/create-loop/`, project `<proj>/.create-loop/`) → re-run upgrades in place, preserves user-edited files (`--force` to overwrite).
