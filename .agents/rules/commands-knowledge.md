---
description: "Read commands knowledge before modifying files in this scope"
globs:
  - "command/**"
  - ".opencode/command/**"
  - ".claude/commands/**"
---
Before making changes in this area, read `.agents/knowledge/domains/commands.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- `command/` is the ONE source of truth; `.opencode/command/` and `.claude/commands/` are RENDERED — never hand-edit them.
- Command bodies are frontmatter-FREE; the renderer injects per-host frontmatter (opencode: `agent: build`; claude: `argument-hint`).
- Mandatory sequence: edit `command/` → `node bin/create-loop.js render` → `node test/installer.test.js` → commit all three dirs together.
- `render` must stay byte-for-byte deterministic (asserted by the installer test).

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
