import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const assessment = await readFile(new URL('../../workspace/resume-assessment.md', import.meta.url), 'utf8');
assert.match(assessment, /inspect-current-refund-policy/);
assert.doesNotMatch(assessment, /verify-refund-boundary[^\s]*\s+is\s+current/i);
