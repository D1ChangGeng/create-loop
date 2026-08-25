# v1 → v2 migration runbook

This runbook governs user-approved v1 → v2 conversions and maintenance of the
migrator. It defines the sibling artifact boundary, source snapshot,
conservative mapping, publication, and post-migration verification.

Runtime create/run/resume/status routes by durable protocol artifacts. Imported
Loops additionally validate their migration bindings through the v2 projector
and whole-loop gate.

## Preconditions and command

Run from the installed Skill root (the directory containing `SKILL.md`):

```bash
python scripts/migrate_v1.py <v1-loop-dir> [v2-sibling-dir] --dry-run
python scripts/migrate_v1.py <v1-loop-dir> <v2-sibling-dir>
```

Migration uses Python 3.10+ and PyYAML. The source Loop must be readable and
must not be modified by the migrator. Choose a destination that is distinct
from the source, is not inside the source tree or one of its `_loops/`
descendants, and is not an existing active Loop. The sibling is a new v2
artifact and protocol boundary even when it preserves the source `loop_id`; it
is not an in-place write-path switch.

The dry run performs the same conversion and validation as publication, but
stages outside the source ancestry and removes the temporary tree before
returning. Review its warnings and report before authorizing real publication.

## Source snapshot and fail-closed rules

The migrator first rejects source roots or members that are symlinks, junctions,
reparse points, redirected paths, or non-regular files before reading them. It
then takes one immutable byte snapshot of the complete source inventory and
records a SHA-256 for every imported file. Canonical path safety for converted
outputs is enforced separately during conversion.

The required source authority is the checkpoint-declared `event_log.jsonl`.
The migrator replays that log, reconciles the node state and event tail with
`checkpoint.yaml`, and rejects disagreement rather than guessing which file is
current. Journal sequence and timestamp order must remain valid. The source
snapshot is rechecked immediately before publication; if any source byte,
member, path, or relevant metadata changed, the staged destination is discarded
and the destination remains absent.

The migration report repeats the source inventory, source hashes, warnings,
reconciled event tail, and the hash of the complete imported journal prefix
through the migration tail. This report is not a narrative substitute for the
source files: it is a tamper-evident binding used by the v2 projector and whole-
Loop validator.

## Conversion contract

The conversion produces the v2 core artifacts:

- immutable `goal.json` from the authoritative v1 goal, intent, scope,
  criteria, constraints, authorization boundaries, and stop conditions;
- immutable `plans/plan-v1.json` with canonical v2 output paths, dependencies,
  checks, and criterion references;
- append-only `journal.jsonl` beginning with exactly one `legacy_import` record
  at `seq=1`, immediately followed by the initial `plan_activated` record;
- generated `resume.json` and a `migration-report.json` bound to the imported
  source and journal prefix.

The goal boundary is not silently broadened. Missing or malformed goal-
authority fields fail closed. Legacy plan nodes are mapped to the six v2 node
states conservatively; unknown v1 statuses are rejected instead of being
coerced.

### Status and completion mapping

- `undiscovered`, `discovered`, `needs_clarification`, `pending`, and `ready`
  become `pending` plus structured context where a question remains open.
- `running` becomes `active`.
- `waiting_external`, `waiting_user`, `blocked`, and `retry_pending` become
  `waiting` with a specific reason.
- `verifying` remains `verifying`.
- `verification_failed` becomes `waiting` with a decision-required reason.
- `completed` becomes an unverified v2 `done` fact with a
  `legacy_completion_unverified` warning.
- `cancelled` and `deprecated` become `closed` with their reason.

Imported `done` is never current completion evidence. It cannot authorize a
v2 node completion or top-level `completion`. To re-verify it, append the exact
node-local `done → active` transition with reason code
`legacy_reverification`, perform fresh work and checks, then append a new
`active → verifying → done` chain with current evidence. Until that succeeds,
the imported node cannot be removed, renamed, or silently closed by a replan.

### Evidence and effects

Legacy evidence is copied as immutable audit history and is not selected as the
current v2 evidence head when it is ambiguous, conflicting, expired, or lacks a
safe provenance binding. The migration never edits a legacy observation to make
it current; later evidence relations remain append-only.

Effect records are paired by exact `effect_id`, `attempt_id`, and node identity.
A conclusively paired legacy effect is retained under
`legacy_import.closed_effects` as a non-authorizing audit fact. An unmatched
idempotent effect may become a real v2 `effect_pre` only when the imported
checkpoint already places its node in `active`; it then remains visible in
`resume.projection.in_doubt_effect_ids`. Ambiguous, orphaned, unmatched
non-idempotent, or state-incompatible effects fail closed. The migrator never
fabricates an active state or silently drops an in-doubt operation.

Replan and Loop closure are forbidden while an effect remains in doubt. Recovery
must inspect the real postcondition before appending a conclusive `effect_post`,
retry decision, or compensation action.

### Output identity

Every legacy `produces` path is normalized to the shared canonical POSIX
relative path contract:

- backslashes become `/`;
- repeated separators and `.` segments are removed;
- absolute, drive-qualified, parent-traversing, control-character,
  Win32-reserved, and platform-ambiguous names fail closed;
- Windows case identity uses length-preserving OS mapping, so ordinary case
  variants collide while distinct Unicode names remain distinct;
- a file output may carry a SHA-256, while a directory output must not pretend
  to have a file hash.

If multiple legacy nodes claim the same canonical output, the earliest
flattened producer remains the sole v2 owner and later producer relationships
are preserved as immutable import warnings. No output claim is silently
discarded.

## Publication and rollback boundary

The dry-run staging area is outside the source ancestry. A real migration stages
beside the requested destination so validation and publication can use a
same-filesystem atomic rename. The destination is published only after:

1. schema, graph, path, status, evidence, effect, and source-binding checks;
2. the source snapshot recheck;
3. `validate_loop_dir.py` succeeds on the staged v2 directory; and
4. the generated resume projection matches the staged goal, active plan, and
   journal tail.

Handled exceptions, validation errors, and source drift remove unpublished
staging. A hard process or host termination can leave an unpublished staging
directory beside the destination; recovery removes it after confirming its
staging identity and ownership. The v1 source remains intact, and the final
rename publishes the sibling as one complete protocol tree. Preserve the source
v1 directory for rollback and comparison after publication.

## Post-migration checks

Run these checks against the new sibling before using it:

```bash
python scripts/validate_loop_dir.py <v2-sibling-dir>
python scripts/render_resume.py <v2-sibling-dir> --check
```

Then inspect `migration-report.json`, `resume.json`, open contexts,
`legacy_completion_unverified` nodes, active evidence, and
`in_doubt_effect_ids`. A successful deterministic gate proves only structural
and causal facts. The model must independently judge whether the migrated Loop
still serves the user goal and what fresh work is required.

Do not delete the v1 source as part of migration. Archive or retire it only
after the user has confirmed the sibling's deliverables, evidence, and recovery
behavior. If the goal, scope, criteria, or authorization boundary must change,
create a user-approved successor Loop rather than using migration to rewrite
the goal.

## Runtime compatibility after migration

The v2 projector and validator recognize a migrated tree through one
`legacy_import` record at the start of its journal, authored by a `migrator`,
followed by the initial plan activation, and bound to the source inventory and
migration report. Protocol detection uses durable artifacts, and every runtime
write follows the detected protocol. Existing migration bindings are checked
when a migrated Loop is read.
