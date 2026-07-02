#!/bin/sh
# Hook: compact-recovery — re-inject AGENTS.md re-read instruction after context compaction
# Fires on SessionStart with matcher "compact" (only after compaction, not normal starts).
# Outputs a directive to stdout that gets injected into the agent's context.
# Always exits 0 — never blocks session resumption.
set -u

# Output the re-read directive — this text is injected into the agent's context
cat << 'DIRECTIVE'
CONTEXT WAS COMPACTED. Before continuing:
1. Re-read AGENTS.md — focus on CORE INVARIANTS and CRITICAL ANTI-PATTERNS
2. Re-read the domain file for your current task area (check WHERE TO LOOK table)
3. State which invariants and anti-patterns apply to your current work before proceeding
DIRECTIVE

exit 0
