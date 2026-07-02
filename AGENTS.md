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
| Deep per-area knowledge | [.agents/knowledge/domains/](.agents/knowledge/domains/) (installer, commands, skill-protocol, validator-engine, tech-stack) |
| Full code map + routing | [.agents/knowledge/reference/code-map.md](.agents/knowledge/reference/code-map.md) |

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

## SESSION START

1. Read this file for project overview and routing.
2. Check `.agents/knowledge/manifest.json` — if `inbox_count > 10` or `days_since_evolution > 14`, suggest an evolution pass to the user.
3. Read the relevant `.agents/knowledge/domains/*.md` for your current task (use the WHERE TO LOOK table above).

## CODING DISCIPLINE

These behavioral rules reduce common AI coding mistakes. They bias toward caution over speed — for trivial, local tasks, use judgment. Escalate caution on subsystem transitions, external-system operations, or knowledge-affecting work.

**Think before coding.** State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. If something is unclear, stop and ask.

**Simplicity first.** Minimum code that solves the problem. No speculative features, no premature abstractions, no error handling for impossible scenarios. If you wrote 200 lines and it could be 50, rewrite it.

**Surgical changes.** Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Match existing style. If your changes create orphans (unused imports/variables), clean those up — but don't remove pre-existing dead code unless asked.

**Goal-driven execution.** Transform tasks into verifiable goals before starting. For multi-step tasks, state a plan with verification checkpoints. Loop until verified — don't declare done without evidence.

**Context familiarity is not domain competence.** When a task shifts to a subsystem you haven't read the source for in this session, read the relevant domain file before acting. If you cannot cite the specific file/line that governs the behavior you're about to change, you don't know enough yet.

**No partial delivery.** When a task requires multiple steps, complete all of them. If blocked, state the blocker and propose alternatives instead of delivering an incomplete result.

**Project-specific gates.** Editing `command/` bodies or `manifest.json` → run `node bin/create-loop.js render` then `node test/installer.test.js`, and commit `command/` + both rendered dirs together. Editing the skill's vocabulary → follow the source-of-truth order (references → schemas → `scripts/checks/__init__.py` → SKILL.md) and re-run the acceptance gate.

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
