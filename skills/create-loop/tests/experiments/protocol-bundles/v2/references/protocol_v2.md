# create-loop protocol v2

Protocol v2 is a smaller execution-control core that can coexist with v1. It
does not reinterpret a structurally valid artifact as proof that the real goal
was achieved. Programs enforce deterministic facts; the acting model judges
meaning, evidence adequacy, trade-offs, and completion.

## Admission

Do not create a Loop for a short, low-risk, single-session task. Use:

| Mode | Required artifacts | Admission boundary |
|---|---|---|
| ordinary task | none | no durable recovery or dependency control needed |
| lightweight | `goal.json`, `plans/plan-vN.json` | stable multi-step plan, expected single session |
| persistent | lightweight core plus `journal.jsonl`, generated `resume.json` | cross-session recovery, replan, or durable evidence |
| governed | persistent core plus only the triggered optional modules | real concurrency, effects, children, artifact versioning, or independent review |

`control.admission_reason` explains why the selected mode is worth its control
cost. Scores are not part of admission. A lightweight Loop upgrades before its
first replan or cross-session handoff. The atomic upgrade creates
`journal.jsonl` with exactly this prefix: activate the existing lightweight
`plan-v1`; append one control-only `evidence` record with
`subject_refs:["loop:control_mode"]`, `source_class:"control_trigger"`, and
`observed_result:"observation"`; append one `decision` with
`question:"control_mode_upgrade"`, outcome `persistent` or `governed`, and that
single evidence ref and `plan_change:null`; then immediately activate `plan-v2`
with the same evidence and decision refs. The bridge may change only
`plan_id`, `plan_version`, `created_at`, and `control`; the goal binding and
complete node graph must remain identical. Any semantic plan change requires a
fresh ordinary replan after the bridge. No work, node transition, effect, or
other runtime fact may appear before the upgrade activation.

## Authority and immutability

- `goal.json` is immutable within one Loop. Changing goal, scope, success
  criteria, or authorization boundaries creates a user-approved successor.
- Every `plans/plan-vN.json` is immutable. The journal's latest valid
  `plan_activated` record selects the active plan and binds its SHA-256.
- `journal.jsonl` is the only ordered runtime fact stream. Records are appended,
  never edited. Sequence numbers start at 1 and increase without gaps.
- `resume.json` is a disposable projection. Its source hashes and journal tail
  must match a fresh projection; the model must not edit it.
- Deliverables remain in the actual workspace. The protocol stores bounded
  evidence, paths, and hashes rather than copies of ordinary project state.
- Workspace-relative paths use one shared canonical identity across plans,
  claims, artifact records, child returns, and migration. They reject path
  escape, non-canonical segments/suffixes, Win32-invalid characters and reserved
  device basenames; Unicode names that Windows does not equate remain distinct.
- An authorization boundary names exactly one reserved actor type: `user`,
  `model`, `tool`, or `reviewer`. An authorizing decision's `authority` and
  record `actor.type` must both equal that boundary value. `actor.id` is only an
  identity label and never grants an authority class.

JSON Schemas use Draft 2020-12. The bundled standard-library validator supports
the exact keyword subset used by the shipped schemas and fails closed on an
unknown keyword. Semantic invariants use stable families (`SCHEMA`, `GRAPH`,
`JOURNAL`, `EFFECT`, `EVIDENCE`, `CLAIM`, `CHILD`, `ARTIFACT`) rather than the v1
linear R-number sequence.

## Node and Loop state

The only node states are `pending`, `active`, `waiting`, `verifying`, `done`,
and `closed`.

| From | Legal destinations |
|---|---|
| pending | active, waiting, closed |
| active | verifying, waiting, closed |
| waiting | pending, active, closed |
| verifying | done, active, waiting, closed |
| done | active, closed |
| closed | none |

`ready` is derived: a pending node is ready when all dependencies are `done`.
Retry, escalation, verification failure, cancellation, and supersession are
reason codes or decisions, not additional states. `verifying -> done` must cite
active passing evidence for every declared node check. In an active or waiting
Loop, `done -> active` is a node-local reopen: it must cite the exact current
fail or inconclusive evidence that invalidated the node. The sole import-time
exception is an unverified legacy `done`, which uses reason code
`legacy_reverification` without treating legacy evidence as current. The
top-level `reopen` record is reserved for restoring a previously completed Loop.

Loop lifecycle is `active`, `waiting`, `completed`, or `closed`. Completion is
created only by a `completion` record; it is never inferred from all nodes being
done. A later `reopen` preserves the completion record and restores `active`.

## Journal

Every record has `schema_version`, `seq`, `record_id`, `ts`, `kind`, `actor`,
optional `plan_version`/`node_id`, and a kind-specific `payload`.

- `plan_activated`: immutable plan reference, hash, previous version, reason.
  Every non-initial activation cites active causal evidence and a prior decision
  that cites exactly the same evidence; neither reference may be omitted. For an
  ordinary replan, the decision uses `question:"plan_replacement"` and a
  `plan_change` object that binds the exact old and candidate plan versions and
  SHA-256 hashes. The decision must have been recorded under the old active plan,
  and control-only upgrade triggers cannot authorize an ordinary replan.
  A lightweight upgrade uses the bounded four-record prefix defined in
  Admission: the original v1 activation, control trigger, matching mode
  decision, and immediate v2 activation.
- `transition`: exact `from`/`to`, reason, evidence and decision references.
- `evidence`: immutable observation, source, subject, check, result, limits,
  optional expiry/recheck and review-context manifest. Check-specific evidence
  is bound at record time to the exact canonical check object by
  `check_binding {plan_version,node_id,check_id,check_sha256}`. A non-null
  `check_ref` without that exact binding is schema-invalid.
- `evidence_relation`: `supersedes`, `invalidates`, `challenges`, or `confirms`.
  For every relation, the source evidence must have been recorded after the
  target evidence; an older observation cannot retire or resolve a newer one.
  The source must also be current: active, not itself challenged, and, when it
  has a `check_ref`, bound to the active plan's exact check definition. Because
  a relation changes the currentness of the whole target record, the source
  must cover every target `subject_ref`; evidence about only one shared subject
  cannot hide conclusions the target also made about other subjects. Both ends
  must also share one exact evidence identity: either neither is check-specific,
  or both bind the same node, check ID, and canonical check hash. A
  `supersedes` source must have a pass, fail, or inconclusive result; a pure
  observation cannot retire a conclusive result. Relation effects are projected
  from immutable relation facts, not stored as permanent
  verdict changes: if a source later expires, is invalidated, is challenged, or
  becomes incompatible with the active plan, its downstream effects retract;
  resolving that source's exact challenge can make them effective again.
  Completion validity is derived from this same current relation graph. A
  post-completion challenge requires `reopen` only while its counterevidence or
  effect remains current; resolving the exact challenge first restores the
  cited completion evidence without leaving a permanent reopen obligation.
- `decision`: question, outcome, rationale, authority, evidence, optional exact
  authorization or failed-evidence override, and optional `plan_change`. When it
  names an authorization boundary, its authority and the record actor type must
  exactly match it. `plan_change` is deterministic causal metadata, not a program
  judgment that the cited evidence is semantically sufficient.
- `context`: open/resolved assumption, blocker, risk, or failed path.
- `effect_pre`/`effect_post`: exact `effect_id + attempt_id + node_id` pair.
  `unknown` observations keep the attempt in doubt; later reality checks may
  append another `unknown` or one conclusive `succeeded`, `failed`, or
  `cancelled` post. No post may follow a conclusive outcome.
- `completion`: deliverables and an exact active-evidence map for every goal
  criterion, deterministic checks, reviews, risks, scope, and authorization.
- `reopen`: completion, counterevidence, affected criteria/nodes, and action.
- `loop_lifecycle`: waiting/resume/close facts.
- `legacy_import`: conservative v1 state snapshot, source hashes, and validated
  audit summaries for conclusively closed legacy effect pairs. It is the
  unique first record (`seq=1`), is written by a `migrator`, and is followed
  immediately by the initial `plan_activated`. It never manufactures a v2
  completion or treats legacy evidence as current. Every imported `done` node
  remains `legacy_completion_unverified`: it cannot support completion until an
  explicit `done -> active` transition with reason code
  `legacy_reverification` starts fresh work, followed by a new
  `active -> verifying -> done` chain with current passing check evidence.
  Until that chain succeeds, the node cannot be removed/renamed by replan or
  transitioned to `closed`; closing the Loop itself remains an explicit
  non-completion outcome.
  Its source binding names `event_log.jsonl`, binds that file and
  `checkpoint.yaml` to the imported hash inventory, and records the reconciled
  event-log tail. Closed-effect audit rows must reference nodes in the initial
  active plan and source sequence numbers within that bound tail. The generated
  migration report repeats the source inventory and hashes the complete imported
  journal prefix through its recorded migration tail; later valid appends do not
  change that prefix. A generic v2 validator therefore rejects a copied or
  hand-edited `legacy_import` whose report no longer binds the imported bytes.

Evidence is immutable. Relations, not edits, change which observations are
current. Invalidated or superseded evidence cannot authorize `done` or
completion. Challenged evidence blocks those actions until resolved. Independent
review is a property of its delivered-context manifest, not an actor label or
file modification time. Overriding failed evidence requires a decision that
names the exact evidence record; the subsequent action names that decision.
Reusing check-specific evidence after replan additionally requires its bound
canonical check hash to match the active node's complete check definition. A
reused check ID alone is never sufficient. The same binding rule scopes
check-specific failures, criterion evidence, and `deterministic_check_refs`.
Review evidence is also bound, but a review context is plan-specific and must be
recollected after replan even when the node check definition is unchanged.
Evidence without a `check_ref` remains governed by its subjects, currentness,
relations, expiry, and review metadata.
These rules also govern top-level reopen counterevidence and generated
`current_evidence_refs`/`confirmed_evidence` recovery projections.

## Execution cycle

1. **ORIENT** validates goal, active plan, journal tail, and resume freshness.
2. **DIAGNOSE** identifies the highest-value unknown, blocker, conflict, risk,
   or deliverable gap.
3. **DECIDE** selects an authorized, executable action. No control record is
   written until the decision is final.
4. **WORK** changes the real workspace. Before a non-idempotent external action,
   append and fsync `effect_pre`.
5. **EVIDENCE** captures direct tool/user/reality observations and their limits.
6. **JUDGE** chooses continue, fix, wait, replan, verify, reopen, or complete.
7. **COMMIT** appends evidence/decision before transition, then atomically
   regenerates `resume.json`.

For an external effect the order is strict: `effect_pre` fsync, real operation,
reality observation, `effect_post` fsync. Recovery never blindly repeats an
unmatched pre-record; it first checks the real postcondition or waits. A Loop
cannot replan or close while an effect remains in doubt.

## Replan, resume, recover, reopen, complete

- Replan first resolves every in-doubt effect, records active evidence that
  invalidated the old plan and a prior decision that selects the replacement,
  binds that decision to the exact old/new plan versions and hashes, verifies the
  goal hash is unchanged, writes and validates a new immutable plan, then appends
  `plan_activated` with the identical causal evidence set and decision ref. An
  unactivated plan is an ignorable orphan. Node IDs are globally unique within
  a Loop: once an ID leaves an active plan it cannot be reintroduced later.
- Resume parses the full valid journal, validates the active plan hash, projects
  states/evidence/context/effects, and rebuilds a stale resume. A fresh agent
  treats the prior next-action decision as advice with actor/time, not a command.
  A generated resume timestamp cannot precede the journal tail it represents.
  Projection also verifies every immutable artifact evidence binding against the
  current workspace path and hash, so resume rendering fails closed on drift.
- Recover is read-only until reality is known. It reports trailing/corrupt JSONL,
  broken hashes/chains, expired claims, and in-doubt effects without truncation.
- Reopen of a completed Loop first appends counterevidence, then names the exact
  completion/criteria/nodes, then uses explicit node transitions or a replan.
  Before completion, a stale done node uses the node-local transition rule above
  and does not manufacture a top-level reopen record.
- Complete runs `validate_loop_dir.py`, maps every criterion to active passing
  evidence, resolves effects/authorization/conflicts, performs required reviews,
  and leaves the semantic completion decision to the model. The validator only
  verifies record shape, references, hashes, and deterministic prerequisites.

## Optional modules

- `concurrency`: only with two or more real writers; claims bind loop, plan,
  node, owner, path scope, and expiry.
- `effects`: only for external, irreversible, approval-gated, or non-idempotent
  operations.
- `children`: only for an independently resumable goal/authority/return boundary.
- `artifacts`: only when multiple versions require a current-selection authority.
- `independent_review`: only when costly error needs a genuinely distinct
  evidence path and explicit context manifest.

Module records/files are invalid unless the active plan enables that module.
Conversely, enabled artifact selection requires its index. Child Loops use the
same v2 core, live under the declaring parent Loop's `_loops/` directory, and
return through the parent plan contract plus child completion. A materialized
child with an unreadable goal fails the parent whole-loop gate; it is not
silently treated as uncreated. Returned deliverables use the shared path
identity rather than literal spelling.
The artifact index retains validated historical versions as well as the single
current selection. Every version has a distinct immutable canonical path so
its recorded hash remains verifiable; no two registry entries may share one
path identity. Evidence that names a registry artifact also binds that
artifact's canonical path and SHA-256 in the immutable evidence record. The
binding remains independently verifiable after a later plan disables current
artifact selection and removes the optional index. An immutable evidence record
may continue to name a superseded registry artifact; evidence relations, not
the registry status, determine whether that observation remains current.

## Command-line tools

```text
python scripts/validate_loop_dir.py <loop-dir>
python scripts/render_resume.py <loop-dir> [--check]
python scripts/migrate_v1.py <v1-loop-dir> [v2-destination] [--dry-run]
```

`validate_loop_dir.py` is read-only. `render_resume.py` uses atomic replacement.
Migration rejects an in-place or child destination, hashes every source file,
writes only a new sibling directory, requires the checkpoint-declared
`event_log.jsonl`, and rejects disagreement between its replayed node/tail
projection and the checkpoint snapshot. Journal timestamps never move backward
with sequence order; imported runtime records use the migration commit time.
Migration also rejects node states outside the locked v1 status vocabulary
instead of guessing a v2 state, and rejects malformed or unsafe legacy
`produces` paths instead of silently dropping outputs. It maps
legacy completion conservatively. A conclusively paired v1 effect is retained
as a non-authorizing `legacy_import.closed_effects` audit fact. An unmatched
idempotent effect is emitted as a real v2 `effect_pre` only when the imported
checkpoint already places its node in `active`; it then remains visible in
`resume.projection.in_doubt_effect_ids`. Ambiguous, orphaned, unmatched
non-idempotent, or state-incompatible effects fail closed rather than being
dropped or forcing a fabricated state transition. Migration discards its
unpublished staging tree if the source changes; the destination remains absent.
Dry-run validation stages in the system temporary area outside the source Loop
ancestry and always removes that tree. A real migration stages beside its
destination so publication remains a same-filesystem atomic rename.
Output identity is the canonical POSIX relative file path: legacy backslashes
are converted to `/`, repeated separators and `.` segments are removed, and
absolute, drive-qualified, parent-traversing, Win32-reserved characters,
control characters, or platform-ambiguous suffixes fail closed. A v2 plan must
already store this canonical form. On Windows, identity uses the operating
system's length-preserving invariant case mapping rather than Unicode
`casefold()`, so ordinary case variants collide without merging distinct names
such as `straße.txt` and `strasse.txt`. When multiple legacy nodes claim the
same canonical output identity, the earliest flattened producer remains the
sole v2 owner and every later producer relationship is preserved explicitly in
immutable import warnings. This retains the source fact without violating the
v2 plan's single-owner output invariant. A declared output may be a file or a
directory; completion hashes are file-only, while a directory deliverable is
accepted only without `sha256`.
