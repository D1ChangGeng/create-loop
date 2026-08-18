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
- Command bodies are frontmatter-FREE; OpenCode receives `description`, while Claude receives `description` plus optional `argument-hint`.
- Mandatory sequence: edit `command/` → render → read-only `render --check` → installer test → commit all three dirs together.
- `render --check` must remain read-only and exact-set deterministic across LF/CRLF worktrees.
- Installed commands bind to one validated concrete Skill root: explicit `--skill-root`, one finite discovery result, or the selected host's pending transaction root. Unselected hosts never supply it.
- A command Skill root must contain exactly one `name: create-loop` identity and every referenced script as a regular contained file.
- A lightweight v2 Loop upgrades with the exact four-record control prefix before replan, handoff, durable evidence, effects, or other runtime facts.
- Installed command examples quote both the resolved Skill script and every Loop/plan/checkpoint path so roots containing spaces remain executable.
- When numbered Skill sections move, audit all command references; a reference document's own anchor is not the same as the Skill section that links to it.

After completing work, capture observations to `.agents/knowledge/inbox/{YYYY-MM}.md`.
