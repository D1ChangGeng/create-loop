---
description: "Read validator-engine knowledge before modifying files in this scope"
globs:
  - "skills/create-loop/scripts/**"
  - "skills/create-loop/schemas/**"
  - "skills/create-loop/tests/**"
---
Before making changes in this area, read `.agents/knowledge/domains/validator-engine.md` for conventions, invariants, and known pitfalls.

Key invariants for this area:
- `scripts/checks/__init__.py` is the ONLY place enums/regexes/required-field tuples live — import from there, never hard-code inline.
- The Python validator is authoritative; `schemas/*.json` must mirror it and never disagree on an enum/required field.
- Validator scripts are READ-ONLY — never mutate an artifact.
- Adding a token: edit `checks/__init__.py` FIRST, then the rule module, then keep schemas in lockstep; add a failure fixture and re-run the acceptance gate.
- Rule numbers (Rn) are never renumbered, only appended.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
