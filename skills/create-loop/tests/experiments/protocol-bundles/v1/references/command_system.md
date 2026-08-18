# Command System

`create-loop` ships four slash commands that map to its four recurring entry
points, so you do not have to hand-write a prompt each time you start, advance,
resume, or inspect a loop. The commands are thin: each one loads the skill and
runs the matching Mode. They are an ergonomic convenience — the skill also
activates from natural language (see [Natural-language fallback](#natural-language-fallback)).

## The four commands

| Command | Maps to | What it does |
|---|---|---|
| `/loop-new "<goal>"` | Mode A — Create a loop | Runs the Loop Startup (Charter) interview, emits `loop.plan v0`, and materialises the loop directory under `.agents/loops/L<seq>-<slug>/`. |
| `/loop-run [node-id]` | Mode B — Run / advance a loop | Reads the checkpoint, claims and executes the next ready node, evaluates its evidence gate, records evidence + event log, writes the checkpoint. |
| `/loop-resume [loop-dir]` | Mode C — Resume from a blank session | Reconstructs state from the checkpoint + event log with no prior chat memory, honours claim/lease, and continues. |
| `/loop-status [loop-id]` | Observability snapshot | Read-only report: goal, current active node, ready set, blockers, pending approvals, next action. |

Each command's body delegates to the skill's Mode of the same name; it never
improvises plan changes.

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
```

Re-running upgrades in place; hand-edited files are preserved unless `--force`.

### With the bundled shell installer

```bash
# From the repo root. Installs both runtimes into the current project.
./install-commands.sh

# Global (user-level), OpenCode only:
./install-commands.sh --runtime opencode --global

# A specific project, Claude Code only, overwriting existing files:
./install-commands.sh --runtime claude --project /path/to/project --force
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
