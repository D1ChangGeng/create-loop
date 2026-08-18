---
type: domain
confidence: verified
scope: ["bin/", "install-commands.sh", "test/", "package.json"]
sources: ["bin/create-loop.js", "install-commands.sh", "test/installer.test.js", "package.json"]
last_verified: 2026-07-31
created: 2026-07-03
---

# Installer and delivery machinery

The Node CLI is the sole implementation of skill/command installation, tracked upgrade, uninstall, and host command rendering. `install-commands.sh` is now only a compatibility argument adapter into the CLI's `--commands-only` path [source: install-commands.sh:1-3] [source: install-commands.sh:40].

## Core Invariants

- The installer remains zero-runtime-dependency and imports only Node built-ins `fs`, `path`, `os`, and `crypto`; the published engine floor is Node `>=18` [source: bin/create-loop.js:5-8] [source: package.json:29-30].
- Install state format is v2. It binds the state root and project root, while every host record binds resolved skill/command roots and their allowed anchors; a moved v2 state or changed root configuration fails closed instead of being silently reused [source: bin/create-loop.js:250-395].
- A v1 state import preserves a byte-for-byte `install-state.v1.backup.json` before the v2 state is committed [source: bin/create-loop.js:387-395] [source: bin/create-loop.js:574-586] [source: test/installer.test.js:1432-1439].
- Pre-existing identical files are recorded as `adopted`, not `owned`; uninstall never removes adopted or legacy-unknown files, even under `--force` [source: bin/create-loop.js:611-637] [source: bin/create-loop.js:1702-1749] [source: test/installer.test.js:189-214] [source: test/installer.test.js:1711-1718].
- Managed writes and removals are confined to a host-specific root under a recorded anchor. Existing symlink, junction, reparse-point, or non-regular path components are rejected before use [source: bin/create-loop.js:94-228].
- Windows path identity is case-insensitive throughout root binding, containment, and tracked-file reconciliation. Equivalent path spellings are normalized back onto the current managed roots so ownership is neither lost nor duplicated [source: bin/create-loop.js:99-111] [source: bin/create-loop.js:272-297] [source: bin/create-loop.js:308-383] [source: bin/create-loop.js:601-609].
- Install/uninstall take one state-root lock. Install validates every pending transaction, resolves the selected hosts' command Skill root, and validates the current request's complete plan before any recovery mutation; after recovery it rereads state and replans before applying new work [source: bin/create-loop.js:422-569] [source: bin/create-loop.js:1556-1691].
- Every persisted transaction carries normalized pre-operation and post-operation install state. Before recovery touches a destination, a write must match the post-state's exact path, kind, hash, and ownership, while a delete must match a pre-state `owned` record that is absent from post-state. Untracked, adopted, or state-inconsistent injected operations fail closed [source: bin/create-loop.js:780-895] [source: bin/create-loop.js:897-1157].
- Install state also anchors each transaction by `txId`, phase, and a SHA-256 digest of its immutable canonical mutation intent. That intent binds the selected kinds, staging root, ordered operations (destination, kind, payload/stage hash, prior hash, and force authorization), pre/post-state digests, managed roots, and command Skill root. Pending recovery requires the exact pre-state; committed recovery performs cleanup only after the current state matches the immutable post-state projection, with one narrow exception for a reality-checked new file conservatively downgraded from `owned` to `adopted` [source: bin/create-loop.js:690-749] [source: bin/create-loop.js:897-1157] [source: bin/create-loop.js:1159-1235] [source: test/installer.test.js:817-879].
- Pending and committed recovery share one operation validator before cleanup or destination mutation. Each write stage must be the canonical `<transaction stageDir>/<operation index>.stage`; deletes require `stage:null`, destinations remain confined and unique, and committed cleanup unlinks only those validated canonical stage files. A forged external stage path remains rejected even when the attacker also updates the state-held intent digest [source: bin/create-loop.js:827-895] [source: bin/create-loop.js:897-1157] [source: test/installer.test.js:1257-1327].
- Command-bearing transactions and current install plans validate the projected Skill identity before mutation: `SKILL.md` must declare exactly one `name: create-loop`, and every script referenced by canonical commands must remain a regular contained file. Transaction-touched required files must also match staged, recovered-state, and package hashes; untouched user-edited scripts keep their bytes as long as identity, type, and containment still hold [source: bin/create-loop.js:1277-1452] [source: bin/create-loop.js:1580-1635] [source: test/installer.test.js:345-368] [source: test/installer.test.js:410-543].
- A forced interrupted write/delete is recoverable only when the new invocation again supplies `--force`; stale transaction metadata cannot grant force authority by itself [source: bin/create-loop.js:859-895] [source: bin/create-loop.js:897-1157] [source: test/installer.test.js:632-706] [source: test/installer.test.js:884-992].

## Reconciliation and Ownership

- `planManaged` computes `created`, `updated`, `unchanged`, `adopted`, `skipped-user`, or dry-run results without performing the destination write [source: bin/create-loop.js:611-637].
- An owned file is safely upgraded only when its current hash still matches the recorded hash; otherwise it is preserved unless `--force` is explicit [source: bin/create-loop.js:611-637].
- Forced replacement of an untracked or adopted file never grants uninstall ownership: the post-state remains `adopted`, including across interrupted recovery. Obsolete adopted records stay tracked while their files are preserved [source: bin/create-loop.js:611-685] [source: bin/create-loop.js:897-1157] [source: test/installer.test.js:161-214] [source: test/installer.test.js:817-944].
- Partial `--commands-only` and `--skill-only` operations carry forward records of the unselected kind, so one install path no longer erases the other's ownership [source: bin/create-loop.js:1580-1625] [source: test/installer.test.js:181-187].
- Obsolete files are eligible for removal only when selected, still owned, confined, and either unchanged or explicitly forced; unsafe paths and user-edited files remain recorded and are preserved [source: bin/create-loop.js:653-684].
- Dry-run executes path, type, state, transaction, Skill identity, and plan preflight but does not create a lock, transaction, destination, backup, or state file [source: bin/create-loop.js:422-569] [source: bin/create-loop.js:859-1157] [source: bin/create-loop.js:1638-1691] [source: test/installer.test.js:370-372] [source: test/installer.test.js:1228-1255].
- Cleanup only prunes the known ancestor chain for a just-removed managed file or transaction. Each candidate is checked with `lstat` and realpath, and pruning stops at a junction, symlink, reparse redirect, non-directory, non-empty directory, or the allowed boundary [source: bin/create-loop.js:1159-1235] [source: bin/create-loop.js:1762-1774] [source: test/installer.test.js:267-283].

## Renderer and Package

- `render --check` builds both host outputs in a temporary tree and compares exact directory snapshots without writing [source: bin/create-loop.js:1776-1858].
- Normal render preflights both target directories before changing either, rejects unsafe non-regular entries, and skips replacement entirely when bytes and exact file sets already match [source: bin/create-loop.js:1776-1858].
- `package.json.files` is a per-file exact allowlist. The expected pack is that declared set plus npm's generated `package.json`; undeclared files anywhere in the payload must remain absent [source: package.json:37-214] [source: test/installer.test.js:1720-1753].
- Phase 5 source, schemas, fixtures, and executable experiment tests remain exact package payloads, but generated `protocol-bundles/` and run/review/receipt outputs are evaluator state rather than distributable source and must stay outside the npm tarball [source: package.json] [source: test/installer.test.js].
- `install-commands.sh` defaults to both supported hosts and maps `--runtime both` to the explicit host list instead of invoking host auto-detection [source: install-commands.sh:5-15] [source: install-commands.sh:40].

## Verification

- The zero-dependency installer suite covers ownership, partial installs, path and reparse escape, corrupt/relocated state, state-root locking, renderer exact sets, interrupted recovery, Skill-root authority, v1 backup, staged hosts, uninstall force semantics, and package contents [source: test/installer.test.js:145-1759].
- Recovery tests reject injected untracked user-file deletes and writes, wrong current Skill identity, required-script deletion, and unselected-host root substitution. Controls resume valid pending roots and preserve untouched user-edited required scripts [source: test/installer.test.js:345-610] [source: test/installer.test.js:625-706].
- Transaction-anchor tests reject forged prior hashes, operation metadata/order, missing state anchors, post-crash reality edits, and committed-state changes outside the conservative create downgrade. Crash recovery also proves that transaction bytes remain unchanged while adopted ownership survives a committed-state interruption [source: test/installer.test.js:625-780] [source: test/installer.test.js:817-879].
- Windows regressions exercise an alternate-casing re-run/uninstall and an unknown `.create-loop` junction whose external directories and marker must survive uninstall [source: test/installer.test.js:232-287].
- Package tests compare two sorted `npm pack --dry-run --json` manifests, require exact path equality with the declared payload plus `package.json`, assert required JSONL/TXT/shell/license files, reject cache/dependency/pyc entries, and detect npm-mandatory root documents outside the declaration [source: test/installer.test.js:1720-1753].
- `test/node-matrix.js` provisions only pinned official Node archives into a user cache, verifies the published SHA-256, and runs the renderer/installer gates under Node 18.20.8 and 24.13.0 without committing runtime binaries [source: test/node-matrix.js].
- The suite derives its final `passed, 0 failed` summary dynamically rather than pinning a hand-maintained assertion count [source: test/installer.test.js:13-18] [source: test/installer.test.js:1755-1759].

## Common Mistakes

- Do not delete or relocate `install-state.json` to fix a root mismatch. The mismatch is intentionally fail-closed; use an explicit future relocation/import procedure or uninstall from the original roots [source: bin/create-loop.js:308-383].
- Do not make the shell wrapper copy files independently. This would restore a second ownership implementation and bypass state v2 and transaction recovery [source: install-commands.sh:1-3] [source: install-commands.sh:40].
- Do not test manifest failures by editing canonical repository files in place. The suite creates copied package roots for renderer and malformed-manifest fixtures [source: test/installer.test.js:93-117] [source: test/installer.test.js:294-321].
- Do not add recursive deletion back to renderer exact-set reconciliation. Unexpected directories and redirected roots are safety failures, not stale generated artifacts [source: bin/create-loop.js:1776-1858].
- Do not recursively walk arbitrary state-root leftovers during uninstall cleanup. An unknown junction under `.create-loop` is not installer ownership and must never become a traversal root [source: bin/create-loop.js:1762-1774] [source: test/installer.test.js:267-283].
- Do not recover an old transaction and only then validate the new invocation. Packaged source, every pending transaction, the selected command root, and the current request plan must all pass deterministic preflight before the first recovery write [source: bin/create-loop.js:1556-1691] [source: test/installer.test.js:410-543].

## Open Questions

- A portable Node implementation cannot fully eliminate a malicious same-user TOCTOU swap between the final path check and rename/unlink. The current contract rejects every visible redirect immediately before operations; should a future release use a platform-specific native helper for handle-relative deletion? [source: bin/create-loop.js:113-225] [source: bin/create-loop.js:387-413] [source: bin/create-loop.js:827-1157] [ASK USER]
- State v2 deliberately fails closed on root relocation, but no user-facing `relocate`/`import-state` command exists yet [source: bin/create-loop.js:308-385]. [TODO]
- Recovery transactions are per host rather than one atomic transaction across all hosts; prior hosts may be committed before a later host is interrupted, but each host is recoverable [source: bin/create-loop.js:897-1235] [source: bin/create-loop.js:1638-1688]. Is cross-host all-or-nothing behavior worth its extra rollback complexity? [ASK USER]

## Correction History

- 2026-07-31: Replaced the obsolete state-v1/shell-copier/15-test description. Current source uses state v2 root binding, adopted ownership, a state-root lock, fail-closed path checks, per-host recovery transactions, a thin shell wrapper, exact-set renderer preflight, and a dynamic zero-failure delivery gate [source: bin/create-loop.js:250-395] [source: bin/create-loop.js:422-569] [source: bin/create-loop.js:690-749] [source: bin/create-loop.js:897-1235] [source: test/installer.test.js:145-1759].
- 2026-07-31: Unified Windows-equivalent path semantics across confinement and ownership recovery, and replaced arbitrary recursive empty-directory cleanup with bounded upward pruning that refuses redirects [source: bin/create-loop.js:99-111] [source: bin/create-loop.js:308-383] [source: bin/create-loop.js:1762-1774] [source: test/installer.test.js:232-287].
- 2026-07-31: Bound crash-recovery operations to transaction-owned pre/post state so a tampered transaction cannot turn managed-root containment plus a matching file hash into authority to overwrite or delete an untracked user file [source: bin/create-loop.js:690-895] [source: bin/create-loop.js:897-1157] [source: test/installer.test.js:399-706].
- 2026-07-31: Replaced the former extension/directory package description with the actual per-file exact allowlist and full pack-path equality gate [source: package.json:37-214] [source: test/installer.test.js:1720-1753].
- 2026-07-31: Made recovery atomic with current-request validation: pending roots are host-scoped, all transactions and the complete new plan are checked before recovery, and untouched user-edited required scripts are preserved without weakening exact validation for transaction-touched files [source: bin/create-loop.js:1237-1699] [source: test/installer.test.js:345-585].
- 2026-07-31: Added a state-held transaction-intent anchor and documented conservative ownership under force. Recovery now proves that the transaction being resumed is the one state authorized, while forced adoption never escalates into uninstall ownership [source: bin/create-loop.js:690-749] [source: bin/create-loop.js:897-1157] [source: test/installer.test.js:631-780] [source: test/installer.test.js:854-960].
- 2026-07-31: Removed the recovery-time transaction rewrite that could leave a new intent paired with an old pending anchor after a crash. The transaction is now immutable; committed cleanup accepts only the exact authorized state projection plus the single safe `owned -> adopted` create downgrade [source: bin/create-loop.js:726-749] [source: bin/create-loop.js:897-1157] [source: test/installer.test.js:817-944].

## Related

- [commands.md](commands.md) - canonical and rendered command contract
- [tech-stack.md](tech-stack.md) - runtime and package constraints
- [../reference/code-map.md](../reference/code-map.md) - entry-point routing
