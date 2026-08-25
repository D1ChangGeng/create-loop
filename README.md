# create-loop

A meta-skill for long-running AI work. After admission, v1 produces a
`loop.plan` DAG and v2 produces an immutable goal plus versioned plans; durable
modes add the evidence and recovery state a fresh agent needs to resume with
zero prior chat memory. The paradigm is **"write the loop, not the prompt."**

The skill itself lives in [`skills/create-loop/`](skills/create-loop/). Its
full documentation is in [`skills/create-loop/README.md`](skills/create-loop/README.md).

Protocol v1 remains the compatibility default. Protocol v2 is an explicit
opt-in (`/loop-new --protocol v2 ...`) while paired evaluation is pending. v2
uses immutable `goal.json` and versioned plans, one append-only `journal.jsonl`,
and a generated `resume.json`; short single-session tasks create no Loop at all.

Explicit v1 → v2 conversions use the
[migration runbook](skills/create-loop/references/migration_v1_to_v2.md), which
is the maintenance entry point for migration work.

## Install

There are two ways to install, depending on whether you want the slash commands
too. The difference matters because `npx skills add` installs **only the skill
directory** — it has no post-install hook and never writes a host's command
directory. The commands are a separate, per-host concept.

### Path A — one command, skill + slash commands (recommended)

The standalone installer copies the skill **and** renders the
`/loop-new`, `/loop-run`, `/loop-resume`, `/loop-status` commands into each
detected host (or both supported hosts when none is detected), then records a
manifest so a re-run upgrades in place. No npm
publish, no global install — it runs straight from the repo:

```bash
# Auto-detect hosts (OpenCode, Claude Code) and install into the current project.
npx github:D1ChangGeng/create-loop

# Global (user-level), for all projects.
npx github:D1ChangGeng/create-loop -g

# Preview without writing anything, or target one host.
npx github:D1ChangGeng/create-loop --dry-run
npx github:D1ChangGeng/create-loop --host claude -g
```

Re-run any time to **upgrade**: managed files are refreshed, files you hand-edit
are preserved (pass `--force` to overwrite). Files that already existed with
identical content are adopted but never claimed as installer-owned, so
`uninstall` will not remove them. Install state is written atomically and a
corrupt state fails closed instead of guessing what the installer owns.
`npx github:D1ChangGeng/create-loop uninstall` removes only installer-owned
files within the selected host roots. Full flags: `--help`.

> Slash commands work by reusing each host's **native** command support —
> OpenCode reads `.opencode/command/*.md`, Claude Code reads
> `.claude/commands/*.md` (both verified). On a host without a slash-command
> convention, the commands simply aren't installed there; the skill still
> activates from natural language ("create a loop", "resume the loop"). The
> installer never claims a capability a host doesn't have.

### Path B — `skills` CLI (skill only)

If you only want the skill (and will drive it by natural language, or install
commands separately), use the [`skills`](https://github.com/vercel-labs/skills)
CLI (OpenCode, Claude Code, Codex, Cursor, and more):

```bash
# Install globally (user-level), for all projects.
npx skills add D1ChangGeng/create-loop --skill create-loop -g -y

# Or install into the current project only.
npx skills add D1ChangGeng/create-loop --skill create-loop -y
```

Re-running the command updates the skill in place. Use it without installing:

```bash
npx skills use D1ChangGeng/create-loop --skill create-loop --agent claude-code
```

To add the slash commands afterward, either run the bundled installer from a
clone of this repo, or run the standalone installer in commands-only mode
(no clone needed):

```bash
# Option 1 — bundled shell compatibility wrapper (from a clone).
git clone https://github.com/D1ChangGeng/create-loop.git
cd create-loop
./install-commands.sh              # current project, both hosts
./install-commands.sh --global     # user-level, both hosts

# Option 2 — standalone installer, commands only (no clone needed).
npx github:D1ChangGeng/create-loop --commands-only        # current project
npx github:D1ChangGeng/create-loop --commands-only -g     # global
```

Commands-only installation discovers an existing Skill at the finite native
locations for the selected scope: `.agents/skills/create-loop` or
`.claude/skills/create-loop` in a project, and their user-level equivalents for
global installs. Exactly one valid root must exist. If the Skill is elsewhere,
or both roots contain distinct copies, select it explicitly with
`--skill-root <dir>` (the shell wrapper accepts the same option). The installer
verifies `SKILL.md` and every Skill script referenced by the canonical command
bodies before writing commands.
Because the selected root is embedded inside quoted shell examples, roots with
shell-interpolation characters (for example `$`, backticks, quotes, `%`, `!`,
control characters, or literal backslashes after canonicalization) are rejected
before any install write. Spaces and ordinary Unicode remain supported.

## What it does

Before creating control files, `create-loop` checks whether durable recovery,
dependency control, or material risk justifies a Loop. If not, it executes as an
ordinary task. For admitted work, select either the v1 compatibility protocol
described below or the explicit v2 protocol in
[`protocol_v2.md`](skills/create-loop/references/protocol_v2.md).

Given a short goal, `create-loop` runs a **Charter interview** (Layer 0) to fix
the control profile, emits a **`loop.plan v0`** (Layer 1) of design-time-invariant
governance nodes, and grows **runtime subgraphs** (Layer 2) inside those nodes as
concrete work becomes knowable. Four principles govern execution:

- **Autonomy-first** — the loop resolves branches, unknowns, and blockers by
  spawning exploration and diagnostic subgraphs and gathering evidence; it asks
  the user only at genuine boundaries (goal, authorization, irreversibility,
  cost, risk, value).
- **Live Loop Semantics** — the top-level goal and governance skeleton stay
  stable while the execution path grows from evidence: evidence-driven
  completeness growth, not scope creep.
- **Recursive Planning ⇄ Immersive Execution** — the loop recursively switches
  between a global whole-graph planning view and a local immersive per-node
  execution view; when a node proves complex it descends into a subgraph or
  child subloop, then writes products, evidence, and decisions back to the
  parent, which re-plans and advances.
- **Layered Execution Chain** — the runner descends a ladder of execution layers
  (Top-level Loop → Node → Subgraph → Subloop → Action Plan → Immersive Action →
  Return) and uses a leaf-action test to decide when to stop planning and act,
  avoiding both premature execution and over-planning.

The plan, checkpoints, evidence ledger, and per-node contracts are plain files,
so any fresh agent can resume across sessions with no runtime, database, or
daemon. The plan is recursive: non-trivial child work is materialized as
isolated child loop directories under `.agents/loops/.../_loops/`
(`L<seq>-<slug>/`), distinct from lightweight inline subgraphs, so each child
loop is independently governed, rescheduled, and replayable.

## Repository layout

```
create-loop/
├── LICENSE                     custom source-available license terms
├── README.md                   this file
├── package.json                standalone installer package (bin: create-loop)
├── bin/create-loop.js          standalone installer CLI (skill + commands, hash-tracked upgrade)
├── install-commands.sh         thin wrapper over the Node installer's commands-only mode
├── command/                    CANONICAL slash-command source (manifest.json + bodies)
├── test/                       installer regression tests
├── .opencode/command/          rendered OpenCode commands (loop-new/run/resume/status)
├── .claude/commands/           rendered Claude Code commands (loop-new/run/resume/status)
└── skills/
    └── create-loop/            the installable skill
        ├── SKILL.md            core protocol (progressive disclosure)
        ├── README.md           full usage / maintain / extend guide
        ├── references/         runtime protocol docs plus the migration workflow runbook
        ├── templates/          v1 artifacts plus four v2 core templates
        ├── schemas/            v1 Draft-07 and v2 Draft 2020-12 contracts
        ├── scripts/            v1 validators plus v2 projector/validator/migrator
        ├── examples/           v1 worked loops plus v2 light/persistent fixtures
        ├── tests/              legacy specs plus frozen/offline Phase 5 experiment infrastructure
        └── tests_py/           executable v1/v2 safety plus workspace/evaluation/guard regressions
```

Phase 5 includes `workspace_builder.py` for deterministic reality-bound
fixtures, `deterministic_runner.py` for the frozen validator control catalog,
`evaluation.py` for canonical blind assignment, authoritative deterministic
reruns, exact oracle/reviewer input validation, and fail-closed metric/gate
formulas, and
`execution_guard.py` for immutable grants, ledger replay, reservations,
receipts, and spend summaries. Focused coverage is
in `test_experiment_workspace.py`, `test_experiment_evaluation.py`, and
`test_experiment_execution_guard.py`.

This infrastructure is not evidence that v2 outperforms v1. Phase 5 now includes
an opt-in six-pair Pilot execution chain: authority-first adapter and runner paths
validate the canonical grant and a separate OS-enforced provider-only network
boundary before reading credentials, initializing or reserving ledger budget, or
launching Codex. Raw provider request identity and token usage, workspace and
evidence manifests, receipts, settlement, traces, oracle results, and blind-review
seals are cross-validated. The repository remains fail-closed because the Linux
reviewer Codex `0.144.1` identity and authenticated OS-level network boundary are
unresolved, so no real provider call has occurred. Pilot and hard limits are
frozen at 23 calls / 1.33M tokens / 20,100 seconds and 126 calls / 7.56M tokens /
113,400 seconds; USD remains `not-measured`. The legacy 42-pair / 84-run plan is
prospective only. `formal_execution_enabled` remains false, and no default-version
or v2-superiority conclusion exists.

The slash commands have a **single source of truth** in
[`command/`](command/): `command/manifest.json` declares each command's
metadata and points at a frontmatter-free body. The host-specific files under
`.opencode/command/` and `.claude/commands/` are **rendered artifacts** —
regenerate them with `npx github:D1ChangGeng/create-loop render` (or
`node bin/create-loop.js render`) after editing anything in `command/`. See
[`command/README.md`](command/README.md).

Use `node bin/create-loop.js render --check` in CI. It renders into a temporary
directory, compares the exact expected filename set and LF-normalized bytes,
and exits nonzero on drift without changing the worktree.

`npx skills add` installs only `skills/create-loop/`. The slash commands are a
separate agent concept, so they ship at the repo root — install them with the
standalone installer (Path A), `./install-commands.sh`, or by hand. See
[`skills/create-loop/references/command_system.md`](skills/create-loop/references/command_system.md).

## License

`create-loop` uses the repository's custom source-available Business Source
License terms. These are not the standard SPDX `BUSL-1.1` text. The current
terms permit the uses described in [`LICENSE`](LICENSE), impose their own
commercial and derivative-work restrictions, and convert the work to Apache
License 2.0 on **2030-07-02**. Read `LICENSE` for the controlling terms.
