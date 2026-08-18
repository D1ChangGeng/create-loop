---
type: domain
confidence: verified
scope: ["command/", ".opencode/command/", ".claude/commands/"]
sources: ["command/manifest.json", "command/manifest.schema.json", "command/AGENTS.md", "command/README.md", "command/loop-new.md", "command/loop-run.md", "command/loop-resume.md", "command/loop-status.md", "bin/create-loop.js", "test/installer.test.js"]
last_verified: 2026-07-31
created: 2026-07-03
---

# Slash commands: canonical source and rendered hosts

The repository exposes four commands. Their frontmatter-free bodies and metadata live in `command/`; OpenCode and Claude files are generated views [source: command/AGENTS.md:1-10].

## Core Invariants

- `command/` is the sole editable command source. Changes must be rendered into both `.opencode/command/` and `.claude/commands/`, checked, tested, and committed together [source: command/AGENTS.md:12-16].
- Canonical bodies contain no frontmatter. OpenCode receives `description`; Claude receives `description` plus optional `argument-hint` [source: command/AGENTS.md:18-20] [source: bin/create-loop.js:40-69].
- The manifest is version 1, has no unknown object properties, and declares `id`, `body`, `description`, and optional `argumentHint` [source: command/manifest.schema.json:6-19] [source: command/manifest.schema.json:20-42].
- Runtime validation is stricter than the schema alone: each body must be exactly `<id>.md`, IDs/bodies must be unique, body paths must resolve to regular contained files, and body frontmatter is rejected [source: bin/create-loop.js:1241-1274].
- `render --check` is read-only and compares a temporary exact set; normal render does nothing when already identical [source: command/README.md:21-35] [source: bin/create-loop.js:1776-1858].

## Protocol Routing

- All four commands accept optional `--protocol v1|v2`; v1 remains the default for creation, while existing Loop artifacts must agree with any explicit selector [source: command/manifest.json:7-28] [source: command/loop-new.md:11-19] [source: command/loop-run.md:10-13].
- `/loop-new` applies admission before either protocol. Its v2 path creates immutable JSON artifacts and runs `validate_loop_dir.py`; its v1 path retains the YAML Mode A workflow [source: command/loop-new.md:15-44] [source: command/loop-new.md:46-77].
- `/loop-run` detects v2 from `goal.json` schema 2.0 and v1 from `loop.plan.yaml`; mixed or ambiguous write paths fail instead of auto-migrating [source: command/loop-run.md:10-20].
- `/loop-resume` treats v2 journal/plan/goal as authority and `resume.json` as generated cache, while the v1 branch retains checkpoint/event/ledger recovery [source: command/loop-resume.md:10-30] [source: command/loop-resume.md:32-59].
- A lightweight v2 Loop cannot append ordinary runtime facts. Before a replan or cross-session handoff, `/loop-run` creates one bounded four-record prefix: activate the existing plan, append the control trigger observation, append the matching `control_mode_upgrade` decision, then immediately activate the new persistent/governed plan. `/loop-resume` routes a journal-free lightweight Loop to that upgrade path rather than fabricating history [source: command/loop-run.md:23-36] [source: command/loop-resume.md:23-29].
- `/loop-status` is strictly read-only for both protocols; v2 reconciliation happens in memory and must not regenerate stale resume data [source: command/loop-status.md:8-25].
- Canonical command prose defines `CREATE_LOOP_SKILL_ROOT` as the directory of the `SKILL.md` actually loaded by the host; it never assumes a repository-relative `skills/create-loop` path [source: command/loop-new.md:5-9] [source: command/loop-resume.md:5-8].
- At delivery time the installer binds rendered commands to one concrete root. `--skill-root` is authoritative; otherwise discovery requires exactly one valid selected-host candidate, while a selected pending command transaction supplies its previously validated root before normal discovery. Roots from unselected hosts cannot influence the current command output [source: bin/create-loop.js:1479-1511] [source: bin/create-loop.js:1556-1577] [source: test/installer.test.js:493-543] [source: test/installer.test.js:1454-1500].
- A command Skill root is valid only when its contained `SKILL.md` declares exactly one `name: create-loop`, all referenced scripts are regular files under that root, and the path can be safely embedded in shell examples [source: bin/create-loop.js:80-87] [source: bin/create-loop.js:1312-1351] [source: test/installer.test.js:1502-1538].
- Every rendered validator invocation quotes both the resolved Skill script path and user-supplied Loop/plan/checkpoint paths, so staged installs remain executable when either root contains spaces [source: command/loop-new.md:38-73] [source: command/loop-resume.md:22-56] [source: test/installer.test.js:1492-1500] [source: test/installer.test.js:1700-1709].

## Authoring and Delivery

- Add/edit command metadata in `manifest.json`, edit a frontmatter-free body, run `node bin/create-loop.js render`, then `render --check` and `node test/installer.test.js` [source: command/AGENTS.md:12-20].
- Host-specific files are generated directly from manifest/body content by the Node CLI; `install-commands.sh` delegates to that same renderer/install ownership path rather than copying committed files itself [source: command/README.md:46-55] [source: install-commands.sh:40].
- The rendered filename is `<id>.md`, and the manifest currently declares `loop-new`, `loop-run`, `loop-resume`, and `loop-status` [source: command/manifest.json:5-29] [source: bin/create-loop.js:1241-1274].

## Common Mistakes

- Do not hand-edit rendered host files; deterministic render will replace their content or remove stale regular files from the exact generated set [source: command/AGENTS.md:22-25] [source: bin/create-loop.js:1776-1858].
- Do not infer protocol solely from a user selector. Existing durable artifacts are authoritative and conflicting selectors are errors [source: command/loop-run.md:10-13] [source: command/loop-status.md:8-10].
- Do not paste repository-relative validator paths into command bodies. Installed OpenCode and Claude skill roots differ [source: command/loop-new.md:5-9].
- Do not use an arbitrary same-named directory or an unselected host's pending root to render commands. Discovery is finite and identity/script validation is part of installer preflight [source: bin/create-loop.js:1312-1351] [source: bin/create-loop.js:1479-1511] [source: bin/create-loop.js:1565-1577].
- Do not add manifest aliases where `body` differs from `<id>.md`; runtime validation rejects them even though the Draft-07 pattern would accept another valid slug [source: command/manifest.schema.json:26-29] [source: bin/create-loop.js:1241-1274].
- When `SKILL.md` numbered sections move, audit every command reference that names a Skill section. A filename reference to a behavioral document must use that document's own anchor, or no section tag; the Skill's section number is not the reference file's section number [source: skills/create-loop/SKILL.md:302-448] [source: command/loop-new.md:52-53] [source: command/loop-run.md:68-69].

## Verification

- The delivery suite tests read-only render checking, unchanged-tree no-op rendering, LF output, manifest traversal rejection in a copied package, unsafe exact-set entries, redirected render roots, zero/multiple/explicit Skill-root discovery, identity/script failures, shell embedding, pending-root reuse, and cross-host isolation [source: test/installer.test.js:294-340] [source: test/installer.test.js:493-543] [source: test/installer.test.js:1441-1538] [source: test/installer.test.js:1691-1709].

## Open Questions

- Only OpenCode and Claude Code have host adapters and rendered targets [source: bin/create-loop.js:41-70] [source: bin/create-loop.js:1776-1780]. Should a new host be added only after it has a native command convention and an installed skill-root discovery contract? [ASK USER]
- Command prose routes v1/v2 semantically, but no executable test currently parses every instruction block to prove it stays aligned with `protocol_v2.md` and v1 references [source: command/loop-new.md:21-77]. [TODO]

## Correction History

- 2026-07-31: Corrected the prior v1-only command map. Commands now support explicit opt-in v2, artifact-based protocol detection, installed skill-root discovery, and a read-only exact-set render check [source: command/manifest.json:7-28] [source: command/loop-run.md:10-30] [source: command/README.md:32-35].
- 2026-07-31: Recorded the installed-command quoting contract and its spaced-root staged fixture; command examples must quote both script and workspace arguments, not only discover the correct Skill root [source: command/loop-run.md:26-58] [source: test/installer.test.js:1492-1500] [source: test/installer.test.js:1700-1709].
- 2026-07-31: Separated command-runtime semantics from installer binding. Canonical prose follows the loaded Skill, while installation chooses one validated concrete root, scopes pending-root fallback to selected hosts, and rejects missing, ambiguous, wrong-identity, missing-script, or shell-unsafe roots before mutation [source: bin/create-loop.js:1312-1511] [source: bin/create-loop.js:1556-1577] [source: test/installer.test.js:493-543] [source: test/installer.test.js:1441-1538].
- 2026-07-31: Replaced the previously unencodable lightweight upgrade prose with the executable bounded four-record prefix shared by `/loop-run`, `/loop-resume`, the projector, and whole-loop validation [source: command/loop-run.md:23-36] [source: skills/create-loop/tests_py/test_v2_protocol.py:215-329].
- 2026-07-31: Absorbed the earlier section-renumbering incident as a standing command-consumer rule: Markdown links can resolve while still targeting the wrong semantic section, so numbered Skill references require manual routing review before render [source: skills/create-loop/SKILL.md:302-448] [source: command/loop-new.md:52-53] [source: command/loop-run.md:68-69].

## Related

- [installer.md](installer.md) - renderer, state, and installation safety
- [skill-protocol.md](skill-protocol.md) - v1/v2 protocol meaning
- [../reference/code-map.md](../reference/code-map.md) - repository routing
