# create-loop

A meta-skill for long-running AI work. You give it a short goal for a task
that cannot finish in one sitting, and it produces a `loop.plan`: a recursive
execution-control DAG plus evidence gates plus a persistent state contract
that a fresh agent can resume from a blank session, with zero prior chat
memory. The paradigm is **"write the loop, not the prompt."**

The skill itself lives in [`skills/create-loop/`](skills/create-loop/). Its
full documentation is in [`skills/create-loop/README.md`](skills/create-loop/README.md).

## Install

Using the [`skills`](https://github.com/vercel-labs/skills) CLI (OpenCode,
Claude Code, Codex, Cursor, and more):

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
daemon.

## Repository layout

```
create-loop/
├── LICENSE                     Business Source License 1.1
├── README.md                   this file
└── skills/
    └── create-loop/            the installable skill
        ├── SKILL.md            core protocol (progressive disclosure)
        ├── README.md           full usage / maintain / extend guide
        ├── references/         concepts, spec, state model, live-loop, etc.
        ├── templates/          fill-in run artifacts
        ├── schemas/            JSON Schemas for the artifacts
        ├── scripts/            validators + DAG renderer
        ├── examples/           two end-to-end worked loops
        └── tests/              acceptance + failure-mode specs
```

## License

`create-loop` is licensed under the **Business Source License 1.1** (BSL-1.1),
the same license as the companion
[`self-evolution`](https://github.com/D1ChangGeng/self-evolution) skill. Free
for personal, open-source, small-company (< 10 employees), and educational use;
derivative works must be open source and non-commercial. On **2030-07-02** the
work converts to Apache License 2.0. See [`LICENSE`](LICENSE) for the full text.
