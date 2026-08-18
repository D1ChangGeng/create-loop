---
type: domain
confidence: observed
scope: ["skills/create-loop/SKILL.md", "skills/create-loop/references/", "skills/create-loop/templates/", "skills/create-loop/examples/"]
sources: ["skills/create-loop/AGENTS.md", "skills/create-loop/README.md", "skills/create-loop/SKILL.md", "skills/create-loop/references/protocol_v2.md", "skills/create-loop/scripts/project_loop.py", "skills/create-loop/scripts/migrate_v1.py", "skills/create-loop/tests_py/", "README.md"]
last_verified: 2026-07-31
created: 2026-07-03
---
# Skill Protocol (create-loop skill proper)

Covers the installable protocol payload. The repository now carries a repaired
v1 compatibility protocol and a smaller, explicitly selected v2 protocol; it
does not silently mix or convert their write paths.

## Core Invariants

- v1 remains the default and compatibility path. v2 is opt-in only when the user explicitly selects it or an existing Loop is identified by `goal.json` with `schema_version: "2.0"`; an existing Loop's artifacts determine its protocol [source: skills/create-loop/SKILL.md:34-43].
- Short, low-risk, single-session work with no durable recovery or dependency-control need should not create a Loop. Every created Loop needs an auditable admission reason, and the presence of v2 code is not a default switch [source: skills/create-loop/SKILL.md:45-50].
- Programs verify deterministic structure and references; the acting model remains responsible for meaning, evidence adequacy, trade-offs, and semantic completion [source: skills/create-loop/references/protocol_v2.md:3-6].
- v2 has one authority chain: immutable `goal.json`; immutable `plans/plan-vN.json` selected and hash-bound by `plan_activated`; append-only, gapless `journal.jsonl`; disposable, projector-owned `resume.json` [source: skills/create-loop/references/protocol_v2.md:23-34].
- v2 completion is an explicit journal fact, never an aggregation of node states. A later `reopen` preserves the completion record and restores the Loop to active [source: skills/create-loop/references/protocol_v2.md:62-64].
- The v1 `Recursive Planning -> Immersive Execution` rhythm and `Layered Execution Chain` are behavioral policies over the existing action/subgraph/subloop vocabulary, not extra schema tiers. Adding or renumbering a named v1 principle is therefore a cross-reference change: update the Skill section, reference map, canonical principle enumeration, command consumers, and both rendered hosts together [source: skills/create-loop/SKILL.md:302-448] [source: skills/create-loop/SKILL.md:820-821] [source: skills/create-loop/references/live_loop_semantics.md:377-378] [source: command/loop-new.md:52-53] [source: command/loop-run.md:68-69].

## Protocol Selection and Admission

- v1 uses the existing YAML plan/checkpoint/ledger protocol. v2 uses the JSON/JSONL protocol in `references/protocol_v2.md`; Mode A explicitly exits the v1 create procedure when v2 is selected [source: skills/create-loop/SKILL.md:36-43] [source: skills/create-loop/SKILL.md:446-454].
- v2 admission has four levels: ordinary task with no Loop files; lightweight with goal plus immutable plan; persistent with journal and generated resume; governed with only the optional modules triggered by actual concurrency, effects, children, artifact versioning, or independent review [source: skills/create-loop/references/protocol_v2.md:8-21].
- Lightweight has one legal durability bridge: activate `plan-v1`, append one control-only observation, append the matching `control_mode_upgrade` decision with explicit `plan_change:null`, and immediately activate `plan-v2`. The bridge may change only plan identity/version/time/control metadata; the goal binding and entire node graph remain identical, and semantic changes require a fresh plan-v3 replan [source: skills/create-loop/references/protocol_v2.md:19-33] [source: command/loop-run.md:22-40].
- v2 has six node states: `pending`, `active`, `waiting`, `verifying`, `done`, `closed`. Readiness is derived, and retry/escalation/verification failure/cancellation/supersession are reasons or decisions rather than extra states [source: skills/create-loop/references/protocol_v2.md:42-60].
- Loop lifecycle is `active`, `waiting`, `completed`, or `closed`. Before top-level completion, a stale `done` node returns to `active` through a node-local counterevidence transition; only a previously completed Loop uses a top-level `reopen` record. Imported unverified legacy `done` nodes use the bounded `legacy_reverification` exception before fresh work [source: skills/create-loop/references/protocol_v2.md:56-68] [source: skills/create-loop/references/protocol_v2.md:91-101].

## Journal and Runtime

- v2 journal records include plan activation, transitions, immutable evidence and relations, decisions, context, exact effect pairs, completion, reopen, lifecycle, and conservative legacy import [source: skills/create-loop/references/protocol_v2.md:66-85].
- Evidence currentness changes through `supersedes`, `invalidates`, `challenges`, or `confirms` relations, not observation edits. A relation source must be newer than its target, active, unchallenged, and bound to the active exact check definition when check-specific; its downstream effects are derived and retract if the source later expires, becomes invalid, is challenged, or is made stale by replan. Independent review depends on a delivered-context manifest rather than actor labels or file mtimes [source: skills/create-loop/references/protocol_v2.md:86-94] [source: skills/create-loop/references/protocol_v2.md:119-134].
- A check ID is only a plan-local label, not durable evidence identity. Every check-specific observation binds `plan_version`, node ID, check ID, and the hash of the complete canonical check object; replan may reuse it only when the active check definition is byte-canonically identical, while review-context evidence is always recollected after replan [source: skills/create-loop/references/protocol_v2.md:77-81] [source: skills/create-loop/references/protocol_v2.md:106-119].
- The runtime cycle is ORIENT -> DIAGNOSE -> DECIDE -> WORK -> EVIDENCE -> JUDGE -> COMMIT. COMMIT appends evidence/decision before transitions and atomically regenerates `resume.json` [source: skills/create-loop/references/protocol_v2.md:94-106].
- External effects use `effect_pre` fsync -> real operation -> reality observation -> `effect_post` fsync; recovery checks reality before retrying an unmatched pre-record [source: skills/create-loop/references/protocol_v2.md:108-110].
- Replan and Loop closure are both forbidden while an effect is in doubt. Replan preserves the goal hash and activates a newly validated immutable plan; resume replays the full valid journal; recover is read-only until reality is known; reopen begins with counterevidence; complete leaves the semantic decision to the model after the deterministic gate [source: skills/create-loop/references/protocol_v2.md:124-147].
- Ordinary plan activation is a causal act: an old-plan `plan_replacement` decision binds exact old/new plan versions and hashes through `plan_change`, and its active unchallenged evidence set must exactly equal the activation refs. The program validates this structural causal envelope without deciding semantic sufficiency. Node IDs remain Loop-global and cannot be reused after removal [source: skills/create-loop/references/protocol_v2.md:91-103] [source: skills/create-loop/references/protocol_v2.md:198-211].
- The artifact registry preserves validated historical versions as well as the one current selection. Every artifact evidence record also retains its immutable path/hash binding, so historical reality remains checkable after the active plan disables the module or removes the live index; evidence relations, rather than registry status alone, decide whether that observation is current [source: skills/create-loop/references/protocol_v2.md:149-166] [source: skills/create-loop/scripts/validate_loop_dir.py:419-462].
- v2 outputs use one shared canonical POSIX path contract across planning, child returns, migration, projection, and whole-loop validation. Windows-invalid characters and control bytes fail closed; Windows case identity uses length-preserving OS mapping rather than Unicode `casefold()`, and file or directory deliverables are both valid while `sha256` remains file-only [source: skills/create-loop/references/protocol_v2.md:240-253] [source: skills/create-loop/scripts/project_loop.py:116-155] [source: skills/create-loop/scripts/project_loop.py:1455-1490].

## Compatibility and Migration

- v1 remains usable during the transition and is not retired merely because v2 artifacts, schemas, or tools exist [source: skills/create-loop/SKILL.md:34-50].
- `migrate_v1.py` is an explicit conservative conversion to a sibling directory. It never writes in place, rejects malformed goal-authority fields, converts one immutable byte snapshot, binds its source hashes into the journal/report, rechecks the live source before publication, validates mapped outputs and statuses fail closed, and does not manufacture a v2 completion from legacy completion. Dry-run staging stays outside the source Loop ancestry; real publication stages beside the destination for a same-filesystem rename [source: skills/create-loop/scripts/migrate_v1.py:59-91] [source: skills/create-loop/scripts/migrate_v1.py:451-651] [source: skills/create-loop/scripts/migrate_v1.py:716-764] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:989-1068].
- Lexically equivalent or Windows-case-equivalent legacy outputs keep one earliest owner and an immutable warning for later producers; genuinely distinct Unicode paths and legitimate directory outputs remain representable [source: skills/create-loop/scripts/migrate_v1.py:211-254] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:478-626].
- Migrated v1 completed nodes become legacy `done` facts with unverified warnings; conflicting legacy active evidence is not selected as current and cannot authorize completion [source: skills/create-loop/scripts/migrate_v1.py:597-622] [source: skills/create-loop/references/protocol_v2.md:91-101].

## Common Mistakes

- Silently switching an existing v1 Loop to v2 or writing v1 and v2 artifacts into one active protocol path [source: skills/create-loop/SKILL.md:38-43].
- Treating all nodes being done, a structurally valid directory, or a validator exit code as semantic proof that the user's goal is achieved [source: skills/create-loop/references/protocol_v2.md:3-6] [source: skills/create-loop/references/protocol_v2.md:62-64].
- Treating a behavioral reference's own section numbers as if they were the section numbers of `SKILL.md`, or changing a numbered Skill section without auditing command/reference consumers. These links are semantic routing, so a syntactically valid Markdown link can still land on the wrong instruction [source: skills/create-loop/SKILL.md:302-448] [source: command/loop-new.md:52-53] [source: command/loop-run.md:68-69].
- Editing `goal.json`, an activated plan, journal history, or `resume.json` directly [source: skills/create-loop/references/protocol_v2.md:23-34].
- Reusing old evidence merely because a new plan retained the same `check_ref`; changed instructions or expectations make that evidence stale even when the check ID is unchanged [source: skills/create-loop/references/protocol_v2.md:112-119].
- Enabling claims, effects, child Loops, artifact indexes, or independent review by default instead of only when the active plan enables the relevant governed module [source: skills/create-loop/references/protocol_v2.md:129-142].

## Verified Facts

- `SKILL.md` remains below its enforced 1000-line entrypoint ceiling; exact line count is deliberately measured by the acceptance gate rather than pinned in knowledge [source: skills/create-loop/tests/acceptance_tests.md:215-225] [source: skills/create-loop/tests/baseline_green.sh:52-57].
- The Skill tool map lists both v1 tools and the v2 whole-loop validator, projector, resume renderer, and migration tool [source: skills/create-loop/SKILL.md:870-880].
- v2 uses Draft 2020-12 schemas and stable invariant families rather than extending the v1 linear R-number sequence [source: skills/create-loop/references/protocol_v2.md:36-40].

## Open Questions

- When will paired real-task validation be sufficient to change v2 from explicit opt-in to the default? The current Skill intentionally leaves v1 as default [source: skills/create-loop/SKILL.md:45-50].
- What measured replay size or latency should trigger journal segmentation? The current v2 authority contract uses one ordered journal [source: skills/create-loop/references/protocol_v2.md:29-32].
- When should the legacy v1 writer be retired after the compatibility window? Current sources define migration behavior but not a final removal release [source: skills/create-loop/SKILL.md:34-50].

## Correction History

- 2026-07-31: Removed the stale exact `SKILL.md` line count and retained only the executable 1000-line ceiling plus explicit v1/v2 protocol selection [source: skills/create-loop/tests/acceptance_tests.md:215-225] [source: skills/create-loop/SKILL.md:32-50].
- 2026-07-31: Clarified the distinction between node-local `done -> active`, top-level completed-Loop `reopen`, and the bounded legacy reverification path; also recorded effect-before-replan/close and historical-artifact semantics [source: skills/create-loop/references/protocol_v2.md:56-68] [source: skills/create-loop/references/protocol_v2.md:91-101] [source: skills/create-loop/references/protocol_v2.md:124-166].
- 2026-07-31: Replaced the v1-only three-layer description as the complete system model. It remains relevant to v1, while v2 now has a separate admission, authority, journal, state, and tool contract [source: skills/create-loop/SKILL.md:446-454] [source: skills/create-loop/references/protocol_v2.md:8-40].
- 2026-07-31: Recorded exact check-definition evidence binding so same-ID semantic changes cannot reuse historical pass/fail/review records for node or Loop judgments [source: skills/create-loop/references/protocol_v2.md:77-81] [source: skills/create-loop/references/protocol_v2.md:112-119].
- 2026-07-31: Closed output-path portability and fidelity gaps: shared canonicalization rejects unmaterializable Win32 names, Windows identity no longer over-folds Unicode or truncates non-BMP names, migration preserves distinct producers, and completion accepts directory deliverables without pretending they have a file hash [source: skills/create-loop/scripts/project_loop.py:116-155] [source: skills/create-loop/tests_py/test_v2_migration_hardening.py:478-626] [source: skills/create-loop/tests_py/test_v2_projector_hardening.py:1883-2000].
- 2026-07-31: Recorded the causal boundary for replans, Loop-global retirement of removed node IDs, durable artifact evidence bindings, and snapshot-consistent migration publication [source: skills/create-loop/references/protocol_v2.md:83-85] [source: skills/create-loop/references/protocol_v2.md:181-188] [source: skills/create-loop/scripts/validate_loop_dir.py:419-462] [source: skills/create-loop/scripts/migrate_v1.py:722-731].
- 2026-07-31: Closed the lightweight-to-persistent deadlock with a bounded four-record journal prefix and executable reject/control coverage; the exception permits only control-plane upgrade facts, not lightweight runtime history [source: skills/create-loop/scripts/project_loop.py:744-895] [source: skills/create-loop/scripts/validate_loop_dir.py:157-235] [source: skills/create-loop/tests_py/test_v2_protocol.py:215-329].
- 2026-07-31: Absorbed the earlier named-principle work as v1 compatibility knowledge. The durable rule is the cross-consumer update contract, while the historical line counts and section-count narratives remain only in the inbox record [source: skills/create-loop/SKILL.md:302-448] [source: skills/create-loop/SKILL.md:820-821] [source: skills/create-loop/references/live_loop_semantics.md:377-378].

## Related

- [domains/validator-engine.md](validator-engine.md) — executable v1 safety and v2 deterministic gates
- [skills/create-loop/SKILL.md](../../../skills/create-loop/SKILL.md)
- [skills/create-loop/references/protocol_v2.md](../../../skills/create-loop/references/protocol_v2.md)
