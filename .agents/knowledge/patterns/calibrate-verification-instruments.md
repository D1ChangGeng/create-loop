---
type: pattern
confidence: observed
scope: ["skills/create-loop/tests/", "skills/create-loop/tests_py/", "skills/create-loop/scripts/", "test/"]
sources: [".agents/knowledge/inbox/2026-07.md", "skills/create-loop/tests/failure_mode_tests.md", "skills/create-loop/tests/acceptance_tests.md", "skills/create-loop/tests_py/test_v1_safety.py"]
first_observed: 2026-07-30
observation_count: 6
application_count: 1
last_applied: 2026-07-31
last_verified: 2026-07-31
---

# Calibrate verification instruments before trusting regressions

## Pattern

Before using a script, shell wrapper, grep, fixture sweep, or metric as evidence
of a regression, run it against one case whose outcome is already known to
reject and one case whose outcome is already known to pass. Verify that the
instrument reads the same signal the assertion names: validator exit code,
printed fixture token, invariant tag, parsed field, or runtime artifact shape.

Only investigate product code after this calibration succeeds. If calibration
fails, repair the instrument or narrow the claim; do not "fix" the artifact to
match a broken measurement.

## When to Apply

- A new or edited harness aggregates several validators or fixture styles.
- A measurement reports a broad or surprising regression in previously green artifacts.
- A shell wrapper transforms exit status into printed output.
- A validator can receive several artifact kinds through a selector such as `--kind`.
- A template and the runtime artifact use different serialization shapes.

## When NOT to Apply

- A direct deterministic unit test already asserts the exact function result with a reject and control in the same test.
- The failure is a syntax or import error emitted directly by the tool being tested and no wrapper changes its signal.
- Calibration would perform an external side effect; substitute an isolated fake or read-only fixture instead.

## Evidence

- The historical v1 Markdown harness uses `cmd && echo FAIL || echo PASS-rejected`; the wrapper's final shell status belongs to `echo`, so the printed token rather than `$?` carries its fixture verdict [source: skills/create-loop/tests/failure_mode_tests.md:1184-1191].
- The same specification includes an explicit R49 mismatch plus passing control and distinguishes the invariant tag from the control's zero exit [source: skills/create-loop/tests/failure_mode_tests.md:3059-3137].
- The v1 acceptance document is explicitly a historical compatibility sequence, while executable cross-protocol coverage lives in `tests_py`; treating the prose sequence as the current release gate would measure the wrong surface [source: skills/create-loop/tests/acceptance_tests.md:1-9].
- Executable v1 tests encode reject/control pairs directly for effect identity and transition behavior [source: skills/create-loop/tests_py/test_v1_safety.py:28-119].
- Six recorded measurement errors in one implementation session all arose from reading a proxy instead of the artifact, including the wrong field name, wrong selector, wrong heading parser, and wrapper exit status [source: .agents/knowledge/inbox/2026-07.md:667-686] [source: .agents/knowledge/inbox/2026-07.md:797-829].

## Examples

- For a failure fixture, assert all three separately when applicable: validator exits nonzero, output contains the expected invariant family/tag, and the paired control exits zero.
- Before counting templates, invoke the validator with each artifact's actual selector; do not run a heterogeneous file list through the default plan kind.
- Before claiming JSONL coverage, test a real bare-object-per-line log in addition to any wrapper template.
- Before accepting an aggregate metric, compare one hand-calculated trace with the script's result and document what the metric cannot observe.
