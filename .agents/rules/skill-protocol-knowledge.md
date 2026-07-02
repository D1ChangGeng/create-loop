---
description: "Read skill-protocol knowledge before modifying files in this scope"
globs:
  - "skills/create-loop/SKILL.md"
  - "skills/create-loop/references/**"
  - "skills/create-loop/templates/**"
  - "skills/create-loop/examples/**"
---
Before making changes in this area, read `.agents/knowledge/domains/skill-protocol.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- `SKILL.md` MUST stay under 1000 lines — depth goes in `references/`.
- The 15 node statuses and 8 subgraph statuses are DISJOINT — never apply one set to the other.
- Every node carries all 21 fields; `child_loops` is REQUIRED (empty sentinel `[]`).
- Source-of-truth order: `references/loop_plan_spec.md` + `state_model.md` → recursion refs → `schemas/*.json` → `scripts/checks/__init__.py` → `SKILL.md`.
- The skill MUST NOT write into `.agents/knowledge/` (transient/durable boundary).

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
