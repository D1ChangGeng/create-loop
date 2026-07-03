---
type: reference
confidence: observed
scope: ["bin/", "command/", ".opencode/command/", ".claude/commands/", "install-commands.sh", "test/", "skills/create-loop/"]
sources: ["bin/create-loop.js", "command/manifest.json", "skills/create-loop/AGENTS.md", "skills/create-loop/scripts/AGENTS.md", ".agents/knowledge/reference/.project-scan.txt", "README.md"]
last_verified: 2026-07-03
created: 2026-07-03
---

# Code Map

## Overview

Full directory map + task→location routing for `create-loop`. The repo has two artifact classes: **delivery machinery** (Node installer + rendered host commands) and **the packaged skill** (`skills/create-loop/`). Consult this to find where a given change belongs. For the authoritative editing workflow of any area, see the linked domain file.

## Directory tree (excludes `.git/`, `node_modules/`, `.omo/`, `.codegraph/`, `__pycache__/`)

```
create-loop/
├── AGENTS.md                         root project knowledge base (augmented by self-evolution)
├── README.md                         user-facing install + concept guide
├── LICENSE                           BUSL-1.1 (→ Apache-2.0 on 2030-07-02)
├── package.json                      installer package: bin, engines node>=18, scripts {render,test}
├── bin/
│   └── create-loop.js                556-line zero-dep installer CLI (Path A)
├── install-commands.sh               134-line shell copier (Path B, commands only)
├── test/
│   └── installer.test.js             114-line regression suite (8 scenarios, 15 assertions)
├── command/                          CANONICAL slash-command source
│   ├── manifest.json                 declares 4 commands (id, body, description, argumentHint)
│   ├── manifest.schema.json          Draft-07 schema for manifest.json
│   ├── AGENTS.md                     edit→render→commit rules
│   ├── README.md                     command-authoring guide
│   └── loop-{new,run,resume,status}.md   frontmatter-FREE bodies
├── .opencode/command/                RENDERED OpenCode commands (agent: build) — do not hand-edit
├── .claude/commands/                 RENDERED Claude Code commands (argument-hint) — do not hand-edit
└── skills/create-loop/               THE INSTALLABLE SKILL (copied verbatim by installer)
    ├── SKILL.md                      699-line entrypoint (≤1000-line hard budget)
    ├── AGENTS.md                     locked vocabulary + anti-patterns
    ├── README.md                     usage / maintain / extend guide
    ├── references/                   19 docs — locked vocabulary + policy
    ├── templates/                    19 fill-in run artifacts
    ├── schemas/                      11 Draft-07 JSON Schemas (mirror the Python enums)
    ├── scripts/                      Python validator engine (R1–R41)
    │   ├── validate_loop_plan.py     dispatcher over 10 --kind artifact types
    │   ├── validate_checkpoint.py    checkpoint↔plan reconciliation
    │   ├── check_loop_integrity.py   whole-loop-dir anti-corruption gate
    │   ├── render_dag.py             plan → Mermaid + Graphviz DOT
    │   └── checks/__init__.py        SINGLE SOURCE OF TRUTH for enums/regexes/required tuples
    ├── examples/                     3 worked loops (incl. recursive child-loop tree)
    └── tests/                        acceptance_tests.md + failure_mode_tests.md
```

## Where to Look (task → location)

| Task | Start here | Deep knowledge |
|------|-----------|----------------|
| Change install/upgrade/uninstall behavior | [bin/create-loop.js](../../../bin/create-loop.js) | [domains/installer.md](../domains/installer.md) |
| Add/edit a slash command | [command/manifest.json](../../../command/manifest.json) + `command/<id>.md` → then `render` | [domains/commands.md](../domains/commands.md) |
| Understand source-vs-rendered commands | [command/AGENTS.md](../../../command/AGENTS.md) | [domains/commands.md](../domains/commands.md) |
| Change the skill protocol / vocabulary | [skills/create-loop/SKILL.md](../../../skills/create-loop/SKILL.md) + `references/` | [domains/skill-protocol.md](../domains/skill-protocol.md) |
| Locked enums / statuses / fields | `skills/create-loop/references/loop_plan_spec.md` + `state_model.md` | [domains/skill-protocol.md](../domains/skill-protocol.md) |
| Add/modify a validator rule (R1–R41) | [skills/create-loop/scripts/checks/__init__.py](../../../skills/create-loop/scripts/checks/__init__.py) first | [domains/validator-engine.md](../domains/validator-engine.md) |
| Regression gate (installer) | [test/installer.test.js](../../../test/installer.test.js) | [domains/installer.md](../domains/installer.md) |
| Acceptance gate (skill) | `skills/create-loop/tests/acceptance_tests.md` | [domains/validator-engine.md](../domains/validator-engine.md) |
| Runtime loop layout / recursion | `skills/create-loop/references/recursive_loops.md` | [domains/skill-protocol.md](../domains/skill-protocol.md) |

## Key entry-point line references

| Symbol | File:line | Role |
|--------|-----------|------|
| `HOSTS` registry | bin/create-loop.js:73-121 | Per-host adapters (opencode, claude) |
| `writeManaged` | bin/create-loop.js:237-264 | 3-way file reconciliation |
| `loadCommandManifest` | bin/create-loop.js:267-280 | Reads manifest + bodies |
| `cmdInstall` | bin/create-loop.js:293-364 | Install/upgrade |
| `cmdUninstall` | bin/create-loop.js:366-407 | Uninstall |
| `cmdRender` | bin/create-loop.js:429-449 | Regenerate committed host commands |
| `main` dispatch | bin/create-loop.js:543-554 | CLI routing |
| render determinism test | test/installer.test.js:81-91 | Byte-for-byte assertion |
| canonical enums | skills/create-loop/scripts/checks/__init__.py:15-114 | 15 node / 8 subgraph statuses, regexes, required tuples |

## Open Questions

- Full per-doc map of the 19 `references/` files is not yet built — only the 4 locked-vocabulary docs were read at init. [TODO]
- Which of R1–R41 are implemented vs reserved is not confirmed. [TODO]

## Intent vs Reality

- README.md and both AGENTS.md files agree with the code on the source-vs-rendered command model and the zero-dep installer — no divergences found at init. The one nuance worth noting: `install-commands.sh` copies pre-rendered files and does NOT render, whereas `bin/create-loop.js` renders; README describes both paths correctly [source: README.md:69-83, install-commands.sh:92-99].

## Maintenance

- Re-verify the tree and line references after any change to `bin/create-loop.js`, the `command/` set, or the skill's `scripts/`. Reference staleness threshold is 90 days.
