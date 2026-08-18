import assert from 'node:assert/strict';
import { total } from '../../workspace/src/invoice/total.ts';

assert.equal(total([0.335, 0.335]), 0.67);
assert.equal(total([1.005, 1.005]), 2.01);
