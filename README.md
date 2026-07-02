# create-loop

A meta-skill for long-running AI work. You give it a short goal for a task
that cannot finish in one sitting, and it produces a `loop.plan`: a recursive
execution-control DAG plus evidence gates plus a persistent state contract
that a fresh agent can resume from a blank session, with zero prior chat
memory. The paradigm is **"write the loop, not the prompt."**

The skill itself lives in [`skills/create-loop/`](skills/create-loop/). Its
full documentation is in [`skills/create-loop/README.md`](skills/create-loop/README.md).

## Install

There are two ways to install, depending on whether you want the slash commands
too. The difference matters because `npx skills add` installs **only the skill
directory** — it has no post-install hook and never writes a host's command
directory. The commands are a separate, per-host concept.

### Path A — one command, skill + slash commands (recommended)

The standalone installer copies the skill **and** renders the
`/loop-new`, `/loop-run`, `/loop-resume`, `/loop-status` commands into each
detected host, then records a manifest so a re-run upgrades in place. No npm
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
are preserved (pass `--force` to overwrite). `npx github:D1ChangGeng/create-loop
uninstall` removes exactly what it wrote. Full flags: `--help`.

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
# Option 1 — bundled shell installer (from a clone of this repo, at its root).
git clone https://github.com/D1ChangGeng/create-loop.git
cd create-loop
./install-commands.sh              # current project, both hosts
./install-commands.sh --global     # user-level, both hosts

# Option 2 — standalone installer, commands only (no clone needed).
npx github:D1ChangGeng/create-loop --commands-only        # current project
npx github:D1ChangGeng/create-loop --commands-only -g     # global
```

## What it does

Given a short goal, `create-loop` runs a **Charter interview** (Layer 0) to fix
the control profile, emits a **`loop.plan v0`** (Layer 1) of design-time-invariant
governance nodes, and grows **runtime subgraphs** (Layer 2) inside those nodes as
concrete work becomes knowable. Two principles govern execution:

- **Autonomy-first** — the loop resolves branches, unknowns, and blockers by
  spawning exploration and diagnostic subgraphs and gathering evidence; it asks
  the user only at genuine boundaries (goal, authorization, irreversibility,
  cost, risk, value).
- **Live Loop Semantics** — the top-level goal and governance skeleton stay
  stable while the execution path grows from evidence: evidence-driven
  completeness growth, not scope creep.

The plan, checkpoints, evidence ledger, and per-node contracts are plain files,
so any fresh agent can resume across sessions with no runtime, database, or
daemon. The plan is recursive: non-trivial child work is materialized as
isolated child loop directories under `.agents/loops/.../_loops/`
(`L<seq>-<slug>/`), distinct from lightweight inline subgraphs, so each child
loop is independently governed, rescheduled, and replayable.

## Repository layout

```
create-loop/
├── LICENSE                     Business Source License 1.1
├── README.md                   this file
├── package.json                standalone installer package (bin: create-loop)
├── bin/create-loop.js          standalone installer CLI (skill + commands, hash-tracked upgrade)
├── install-commands.sh         copies the slash commands into an agent's command dir (Path B)
├── command/                    CANONICAL slash-command source (manifest.json + bodies)
├── test/                       installer regression tests
├── .opencode/command/          rendered OpenCode commands (loop-new/run/resume/status)
├── .claude/commands/           rendered Claude Code commands (loop-new/run/resume/status)
└── skills/
    └── create-loop/            the installable skill
        ├── SKILL.md            core protocol (progressive disclosure)
        ├── README.md           full usage / maintain / extend guide
        ├── references/         concepts, spec, state model, live-loop, recursive-loops, subgraph/subloop policy, command system
        ├── templates/          fill-in run artifacts
        ├── schemas/            JSON Schemas for the artifacts (11)
        ├── scripts/            validators (checks/*) + integrity gate + DAG renderer
        ├── examples/           three worked loops (incl. recursive child-loop tree)
        └── tests/              acceptance + failure-mode specs
```

The slash commands have a **single source of truth** in
[`command/`](command/): `command/manifest.json` declares each command's
metadata and points at a frontmatter-free body. The host-specific files under
`.opencode/command/` and `.claude/commands/` are **rendered artifacts** —
regenerate them with `npx github:D1ChangGeng/create-loop render` (or
`node bin/create-loop.js render`) after editing anything in `command/`. See
[`command/README.md`](command/README.md).

`npx skills add` installs only `skills/create-loop/`. The slash commands are a
separate agent concept, so they ship at the repo root — install them with the
standalone installer (Path A), `./install-commands.sh`, or by hand. See
[`skills/create-loop/references/command_system.md`](skills/create-loop/references/command_system.md).

## License

`create-loop` is licensed under the **Business Source License 1.1** (BSL-1.1),
the same license as the companion
[`self-evolution`](https://github.com/D1ChangGeng/self-evolution) skill. Free
for personal, open-source, small-company (< 10 employees), and educational use;
derivative works must be open source and non-commercial. On **2030-07-02** the
work converts to Apache License 2.0. See [`LICENSE`](LICENSE) for the full text.
