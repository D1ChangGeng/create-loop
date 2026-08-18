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
- The Node CLI is the sole install/render/uninstall implementation; `install-commands.sh` is only a `--commands-only` compatibility wrapper.
- Install state v2 lives outside host directories, binds its configured roots/anchors, and must fail closed when state or recovery transactions are invalid.
- Every transaction is anchored in install state by transaction ID, phase, and a digest of its ordered mutation intent; neither a contained transaction file nor matching reality is authority by itself.
- Transaction intent is immutable through recovery. Committed cleanup accepts only its exact state projection, except the narrowly proven `owned -> adopted` downgrade for an indistinguishable newly created file.
- Committed cleanup validates every operation first and deletes only canonical transaction-owned `<index>.stage` files; a state-anchored external stage path is never cleanup authority.
- Packaged source, all pending transactions, the selected command Skill root, and the current install plan must validate before any recovery mutation.
- Command writes require exact `name: create-loop` identity and contained referenced scripts; projected mixed recovery validates touched files exactly while preserving valid untouched user edits.
- User-edited or pre-existing files are preserved unless an explicit safe ownership rule or `--force` authorizes replacement; uninstall remains confined to canonical allowed roots.
- Forced replacement of an untracked or adopted file remains `adopted`, and recovery requires the new invocation to repeat `--force`; crash metadata never escalates ownership or force authority.
- `package.json.files` is a per-file exact set; package tests compare the complete dry-run pack path set with that declaration plus `package.json`.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
