import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../../workspace/src/cache/client.ts', import.meta.url), 'utf8');
assert.doesNotMatch(source, /globalThis\.redis/);
assert.match(source, /sharedClient/);
