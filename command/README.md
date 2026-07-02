# command/ — canonical slash-command source

This directory is the **single source of truth** for the create-loop slash
commands (`/loop-new`, `/loop-run`, `/loop-resume`, `/loop-status`). Edit
commands here, then regenerate the host-specific files.

## Layout

| File | Role |
|------|------|
| `manifest.json` | Declares each command: `id`, `description`, optional `argumentHint`, and the path to its body. |
| `manifest.schema.json` | JSON Schema (Draft-07) for `manifest.json`. |
| `<id>.md` | The frontmatter-free command **body**, shared verbatim across every host. |

Frontmatter is **not** stored in the bodies. Each host needs different
frontmatter (OpenCode uses `agent: build`; Claude Code uses `argument-hint`),
so the installer generates it per host from the manifest metadata. Storing the
body once and rendering the frontmatter keeps the two hosts from drifting.

## Rendering the host files

The committed files under `../.opencode/command/` and `../.claude/commands/`
are generated artifacts. After editing anything here, regenerate them:

```bash
node ../bin/create-loop.js render
# or, from the repo root:
npm run render
```

`render` is deterministic: running it on an unchanged `command/` reproduces the
committed host files byte-for-byte (the installer test asserts this).

## Adding a command

1. Add a body file, e.g. `command/loop-foo.md` (no frontmatter).
2. Add an entry to `manifest.json` with a unique `id`, a `description`, an
   optional `argumentHint`, and `"body": "loop-foo.md"`.
3. Run `node ../bin/create-loop.js render` to regenerate the host files.
4. Run `node ../test/installer.test.js` to confirm everything still passes.
5. Commit `command/` **and** the regenerated `.opencode/`/`.claude/` files.

## How these reach a host

`npx skills add` installs only the skill directory, never a host's command dir.
The commands are installed separately by:

- the standalone installer — `npx github:D1ChangGeng/create-loop` (Path A), which
  renders these entries directly into each detected host and tracks them for
  idempotent upgrade; or
- `../install-commands.sh` (Path B), which copies the already-rendered
  `.opencode/command/` and `.claude/commands/` files into a host.

Both reuse each host's **native** slash-command support (OpenCode reads
`.opencode/command/*.md`, Claude Code reads `.claude/commands/*.md`). A host
without a slash-command convention gets no command files; the skill still
activates from natural language.
