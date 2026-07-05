# command/ — CANONICAL slash-command source

Single source of truth for the four slash commands (`/loop-new`, `/loop-run`, `/loop-resume`, `/loop-status`) mapping to skill Modes A/B/C + status. The host-specific files under `../.opencode/command/` and `../.claude/commands/` are RENDERED from here.

## LAYOUT
| File | Role |
|------|------|
| `manifest.json` | Declares each command: `id`, `body`, `description`, optional `argumentHint`. |
| `manifest.schema.json` | Draft-07 schema for `manifest.json` (`version` const 1; `id` matches `^[a-z0-9][a-z0-9-]*$`; `body` ends `.md`; `additionalProperties:false`). |
| `<id>.md` | Frontmatter-FREE command body, shared verbatim across every host. |

## EDIT → RENDER → COMMIT (mandatory sequence)
1. Edit a body in `command/<id>.md` (NO frontmatter) and/or metadata in `manifest.json`.
2. `node ../bin/create-loop.js render` (or `npm run render` from repo root).
3. `node ../test/installer.test.js` — asserts render is byte-for-byte deterministic.
4. Commit `command/` **AND** the regenerated `../.opencode/command/` + `../.claude/commands/` together.

## CONVENTIONS
- Frontmatter is injected per host by the renderer, NOT stored here: OpenCode gets `description` only (no `agent` — the command inherits the user's current agent, per OpenCode's optional-`agent` default); Claude Code gets `description` + `argument-hint`. Storing the body once prevents the two hosts from drifting.
- Adding a command: add `command/loop-foo.md` (no frontmatter) → add a `manifest.json` entry (`id`, `description`, optional `argumentHint`, `"body":"loop-foo.md"`) → render → test → commit all three dirs.

## ANTI-PATTERNS
- NEVER put frontmatter in a `command/<id>.md` body — the renderer owns it.
- NEVER edit the rendered `../.opencode/command/` or `../.claude/commands/` files — they are overwritten on every `render`.
- NEVER change a body or `manifest.json` without re-rendering and committing the host artifacts in the same change.
