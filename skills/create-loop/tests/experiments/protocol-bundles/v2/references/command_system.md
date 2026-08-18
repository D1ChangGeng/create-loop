# Command System

`create-loop` ships four slash commands that map to its four recurring entry
points, so you do not have to hand-write a prompt each time you start, advance,
resume, or inspect a loop. The commands are thin: each one loads the skill and
runs the matching Mode. They are an ergonomic convenience — the skill also
activates from natural language (see [Natural-language fallback](#natural-language-fallback)).

## The four commands

| Command | Maps to | What it does |
|---|---|---|
| `/loop-new [--protocol v1|v2] "<goal>"` | Create/admit | Rejects unnecessary Loop creation; otherwise uses v1 by default or explicit opt-in v2. |
| `/loop-run [--protocol v1|v2] [target]` | Run / advance | Detects the existing protocol, validates it, and advances without mixing write paths. |
| `/loop-resume [--protocol v1|v2] [loop-dir]` | Blank-session resume | Uses v1 checkpoint/event recovery or v2 goal/plan/journal projection. |
| `/loop-status [--protocol v1|v2] [loop]` | Observability snapshot | Strictly read-only, protocol-aware status and stale-cache reporting. |

v1 remains the transition default. v2 is selected only by `--protocol v2` for a
new Loop, or detected from an existing `goal.json` with `schema_version: "2.0"`.
An explicit selector must agree with existing artifacts. Commands never
auto-migrate or mix v1 and v2 write paths.

## Install

`npx skills add` installs only the skill directory (`SKILL.md` + its supporting
files). Slash commands are a separate, per-runtime concept, so the command files
live at the **repository root** (`.opencode/command/` and `.claude/commands/`),
rendered from the canonical source in `command/`. There are three ways to place
them.

### With the standalone installer (recommended)

The repo ships a standalone installer that copies the skill **and** the commands
in one command, then tracks them for idempotent upgrade:

```bash
# Auto-detect hosts, install into the current project.
npx github:D1ChangGeng/create-loop

# Global (user-level); or one host; or preview.
npx github:D1ChangGeng/create-loop -g
npx github:D1ChangGeng/create-loop --host claude -g
npx github:D1ChangGeng/create-loop --dry-run

# Commands only (skill already installed via `npx skills add`).
npx github:D1ChangGeng/create-loop --commands-only
npx github:D1ChangGeng/create-loop --commands-only --skill-root /path/to/create-loop
```

Re-running upgrades in place; hand-edited files are preserved unless `--force`.
Commands-only mode searches only the selected scope's native `.agents` and
`.claude` Skill locations. Equivalent real paths are deduplicated, but zero or
multiple distinct valid roots are errors; `--skill-root` is the explicit
authority. Before rendering, the installer requires a regular `SKILL.md` and
every contained `<CREATE_LOOP_SKILL_ROOT>/scripts/...` target referenced by the
canonical command bodies. Full skill+command installation instead embeds each
host's Skill destination, and uninstall uses recorded ownership without
requiring the Skill root to remain on disk.
The root is canonicalized to `/` separators before rendering. Spaces and
ordinary Unicode are supported, while shell-interpolation/control characters
are rejected before any install write so a path cannot become executable
command syntax.

### With the bundled shell installer

```bash
# From the repo root. Installs both runtimes into the current project.
./install-commands.sh

# Global (user-level), OpenCode only:
./install-commands.sh --runtime opencode --global

# A specific project, Claude Code only, overwriting existing files:
./install-commands.sh --runtime claude --project /path/to/project --force
./install-commands.sh --project /path/to/project --skill-root /path/to/create-loop
```

### By hand

| Runtime | Project scope | Global scope |
|---|---|---|
| OpenCode | `cp .opencode/command/*.md <project>/.opencode/command/` | `cp .opencode/command/*.md ~/.config/opencode/command/` |
| Claude Code | `cp .claude/commands/*.md <project>/.claude/commands/` | `cp .claude/commands/*.md ~/.claude/commands/` |

After copying, type `/loop-` in the agent and the four commands appear.

## Arguments

Both runtimes substitute the text after the command name:

- `$ARGUMENTS` — the entire argument string (e.g. the goal for `/loop-new`).
- `$1`, `$2` — positional arguments (quote multi-word values).

Examples:

```
/loop-new "ship a REST API with auth and a deploy"
/loop-new --protocol v2 "investigate and implement a resumable migration"
/loop-run n7_implementation
/loop-resume .agents/loops/L001-ship-rest-api
/loop-status L001
```

## Natural-language fallback

The command files are optional. The skill's `SKILL.md` description carries
trigger phrases — "create a loop", "run/advance the loop", "resume the loop from
checkpoint", "loop status / where are we" — so an agent that has the skill
installed activates it from plain language even where no command file is present.
Use commands for speed and discoverability; rely on the fallback everywhere else.

## See also

- [`../SKILL.md`](../SKILL.md) — the Modes the commands invoke (A create, B run,
  C resume) and the reference map.
- [`recovery_protocol.md`](recovery_protocol.md) — what `/loop-resume` runs.
- [`recursive_loops.md`](recursive_loops.md) — the `.agents/loops/` layout the
  commands read and write.
