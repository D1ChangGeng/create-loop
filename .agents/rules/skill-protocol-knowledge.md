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
- Select the protocol first: v1 remains the compatibility default; v2 is explicit opt-in or detected from existing v2 authority artifacts, and write paths never mix.
- v1 retains its 15 node states, 8 subgraph states, and locked field vocabulary; v2 instead uses six node states and no independently editable subgraph state.
- v2 authority is immutable `goal.json`, journal-activated immutable plans, append-only `journal.jsonl`, and projector-owned `resume.json`.
- Lightweight may gain durability only through the bounded plan-v1 activation -> control trigger -> `plan_change:null` mode decision -> node-identical plan-v2 activation prefix.
- Ordinary replans require active unchallenged evidence and an old-plan `plan_replacement` decision binding exact old/new versions and hashes; removed node IDs are never reusable.
- Deterministic validators never decide semantic completion; the acting model judges evidence adequacy against the immutable goal and authorization boundary.
- V1 named principles are behavioral policies over existing vocabulary; adding or renumbering one requires auditing the Skill reference map, canonical principle list, command consumers, and rendered hosts together.
- Artifact evidence retains its own immutable path/hash binding. v1 migration validates one source snapshot, keeps dry-run staging outside Loop ancestry, and publishes real output from a destination-sibling staging tree.
- v2 output identity is canonical and cross-platform-safe; distinct Unicode names remain distinct, while unmaterializable Win32 paths fail closed.
- The skill MUST NOT write into `.agents/knowledge/` (transient/durable boundary).

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
