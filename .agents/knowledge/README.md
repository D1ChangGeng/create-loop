# Project Knowledge Evolution System

## What This System Is

This is a project knowledge evolution system.

It is not a static documentation archive. Knowledge here is expected to change as the project changes. Entries have lifecycle states, confidence levels, and evidence trails. That means a note captured today can later be refined, verified, promoted, superseded, or archived.

The goal is simple: preserve useful project understanding in a form that helps future work without pretending every statement is equally trustworthy.

This system exists to help humans and AI sessions work with the same evolving body of project knowledge.

## What This System Is Not

This system is not a replacement for code, tests, or runtime verification.

It is not automatically correct. A knowledge file can be incomplete, stale, or wrong.

It is not a permanent archive for every observation ever made. Some notes are temporary, some become patterns, and some should be retired.

## Directory Structure

### `inbox/`

Raw capture goes here first, usually in monthly files. Use it for observations that are worth saving but not yet organized. Treat it as intake, not final form.

### `domains/`

Working knowledge lives here, organized by task area. Each domain file merges conventions, anti-patterns, and operational notes for a focused area of the project. One domain file per concern prevents hunting across multiple files.

### `reference/`

Low-churn reference documentation lives here. API route tables, architecture diagrams, companion project docs, comprehensive code maps. Content that rarely changes but needs to be accessible when working in specific areas.

### `decisions/`

Architectural and operational decisions live here in ADR form. Use this directory when the team has explicitly chosen a path and the reasoning should remain visible.

### `patterns/`

Verified conventions and repeated practices live here. A pattern file should describe when something applies, when it does not, and the evidence behind it.

### `crystallized/`

Executable best practices live here. These files should describe repeatable workflows with prerequisites, decision points, and verification steps.

### `archive/`

Retired or superseded knowledge moves here. Archive content is still useful for historical context, but it should not be treated as current guidance.

## How to Read Knowledge

Use this discovery protocol when starting work:

1. Check `AGENTS.md` and its `Where to Look` table for your task area.
2. If there is no obvious match, scan `manifest.json` inventory entries for files whose scope matches your work.
3. If you still do not have a match, search `domains/` for keywords related to the task.
4. Check `inbox/` for recent observations that may not be organized yet.
5. Before trusting any entry, note its `confidence` level and `last_verified` date.

Do not treat every file as equally authoritative. The confidence ladder matters.

## How to Write Knowledge

Use this capture protocol after non-trivial tasks.

Append observations to `inbox/{YYYY-MM}.md`.

Use this format:

```md
## {date} {time} — {context}
- {observation}
- [source: {file:line}]
```

No classification is required at capture time. Just write it down clearly.

Capture knowledge when any of these conditions are true:

1. You discovered how something works.
2. You fixed a bug that revealed a hidden assumption.
3. You made a constraining decision.
4. You noticed a cross-file pattern.
5. You found that existing knowledge was wrong.

Raw capture is better than losing the insight.

## Confidence Levels

### `observed`

Seen once, or based on a single source. This can still be useful, but use it with awareness that it may be wrong.

### `verified`

Corroborated by two or more sources, or checked directly against code, tests, or authoritative documentation. This is usually safe to rely on.

### `canonical`

Source of truth. Canonical knowledge belongs in root `AGENTS.md` and should only change through an explicit decision.

All AI-generated knowledge starts as `observed`. No exceptions.

## When Knowledge Conflicts

If two entries conflict:

1. Surface both versions explicitly in the relevant topic file.
2. Mark the conflict clearly so it is visible, not buried in prose.
3. Note the evidence for each side.
4. Flag the issue for human arbitration if both sides have comparable evidence.
5. Do not silently pick one side and erase the other.

Conflict that is made explicit can be resolved. Conflict that is hidden becomes misinformation.

## Promotion and Lifecycle

Typical progression looks like this:

1. Capture an observation in `inbox/`.
2. Move or summarize it into a `domains/` file when the area becomes important.
3. Promote repeated and supported guidance into `patterns/` or `crystallized/`.
4. Promote only durable source-of-truth knowledge into root `AGENTS.md`.
5. Archive files that are no longer current.

Not every note needs promotion. Some observations are only useful in the short term.

## Security

Never store secrets, API keys, passwords, tokens, or credentials as knowledge.

If sensitive context matters, reference it by location, such as `see .env` or `see deployment secret store`, not by value.

Treat knowledge files as durable project memory. Write them as if they may be read broadly.

## When to Ask a Human

Ask a human when any of these conditions apply:

- There is an unresolvable conflict between knowledge entries.
- You want to promote something to canonical status in `AGENTS.md`.
- A decision has significant architectural consequences.
- Your confidence in your own judgment is low.

Human arbitration is part of the system, not a failure of the system.

## Maintenance Expectations

Keep entries concise, specific, and evidence-linked.

Prefer corrections over silent drift.

When you learn that a file is outdated, update it or mark it clearly. A stale knowledge base is worse than a small one.

## Quick Summary

- Capture first.
- Verify when possible.
- Promote carefully.
- Mark confidence honestly.
- Never hide conflicts.
- Never store secrets.
