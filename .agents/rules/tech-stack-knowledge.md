---
description: "Read tech-stack knowledge before modifying files in this scope"
globs:
  - "package.json"
  - "bin/**"
  - "test/**"
  - "skills/create-loop/scripts/**"
---
Before making changes in this area, read `.agents/knowledge/domains/tech-stack.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- Installer stays zero-runtime-dependency (Node stdlib only), Node >=18.
- Two toolchains: Node.js (installer/tests/render) + Python 3.8+ (skill validators, needs PyYAML; jsonschema optional).
- Only two npm scripts exist: `render` and `test`. No test framework — the installer suite is a hand-rolled zero-dep harness.
- License is BUSL-1.1; keep new files consistent.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
