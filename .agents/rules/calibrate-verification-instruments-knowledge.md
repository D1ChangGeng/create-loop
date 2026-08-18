---
description: "Calibrate test and measurement harnesses before trusting regressions"
globs:
  - "skills/create-loop/tests/**"
  - "skills/create-loop/tests_py/**"
  - "skills/create-loop/scripts/**"
  - "test/**"
---
Before changing validators or artifacts in response to a surprising result, read `.agents/knowledge/patterns/calibrate-verification-instruments.md`.

Key invariants for this area:
- Calibrate every new aggregate instrument with one known reject and one known control.
- Distinguish validator exit code, shell-wrapper token, invariant tag, selector, and runtime artifact shape.
- Repair a broken measurement before changing healthy product artifacts.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
