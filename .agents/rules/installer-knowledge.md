---
description: "Read installer knowledge before modifying files in this scope"
globs:
  - "bin/**"
  - "install-commands.sh"
  - "test/**"
  - "package.json"
---
Before making changes in this area, read `.agents/knowledge/domains/installer.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- Zero runtime dependencies (Node stdlib only), Node >=18 — never add an npm dep to bin/.
- `writeManaged` is the single reconciliation path; user-edited files (hash mismatch vs recorded) are preserved unless `--force`.
- Install state (sha256 per file) lives OUTSIDE host dirs: `~/.config/create-loop/` or `<proj>/.create-loop/`.
- `install-commands.sh` copies pre-rendered files; it does NOT render from `command/`.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
