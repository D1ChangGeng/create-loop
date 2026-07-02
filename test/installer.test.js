#!/usr/bin/env node
/*
 * Regression tests for the create-loop installer's file reconciliation.
 * Zero-dep, self-contained. Run: node test/installer.test.js
 *
 * Exercises the behavior that matters for "re-run == upgrade":
 *   1. fresh install creates files + a manifest
 *   2. re-run is idempotent (unchanged)
 *   3. an old-version file WE wrote is updated
 *   4. a user-edited file is preserved
 *   5. --force overwrites a user-edited file
 *   6. render reproduces the committed host command files byte-for-byte
 *   7. uninstall removes tracked files but preserves user-edited ones
 *   8. dry-run writes nothing
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const PKG_ROOT = path.resolve(__dirname, '..');
const CLI = path.join(PKG_ROOT, 'bin', 'create-loop.js');

let passed = 0, failed = 0;
function ok(cond, msg) { if (cond) { passed++; console.log('  ok  - ' + msg); } else { failed++; console.error('  FAIL- ' + msg); } }
function sha(p) { return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'); }
function exists(p) { try { fs.statSync(p); return true; } catch (_) { return false; } }

function mkTmp() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'cl-test-'));
  return d;
}
function run(args, env) {
  return execFileSync('node', [CLI, ...args], { encoding: 'utf8', env: Object.assign({}, process.env, env || {}) });
}

function main() {
  const home = mkTmp();
  const proj = mkTmp();
  const env = { HOME: home };
  const cmd = path.join(proj, '.opencode', 'command', 'loop-status.md');
  const skillMd = path.join(proj, '.agents', 'skills', 'create-loop', 'SKILL.md');
  const stateJson = path.join(proj, '.create-loop', 'install-state.json');

  console.log('installer reconciliation');

  // 1. fresh install
  run(['install', '-p', proj, '--host', 'opencode', '-q'], env);
  ok(exists(cmd), 'fresh install writes a command file');
  ok(exists(skillMd), 'fresh install writes the skill');
  ok(exists(stateJson), 'fresh install writes the install-state file');

  // 2. idempotent
  let out = run(['install', '-p', proj, '--host', 'opencode'], env);
  ok(/unchanged/.test(out) && !/created|updated/.test(out), 're-run is idempotent (all unchanged)');

  // 3. old version we wrote -> update
  fs.writeFileSync(cmd, 'OLD MANAGED v1\n');
  const oldHash = sha(cmd);
  const state = JSON.parse(fs.readFileSync(stateJson, 'utf8'));
  state.hosts.opencode.files[cmd].hash = oldHash; // pretend we wrote this old content
  fs.writeFileSync(stateJson, JSON.stringify(state, null, 2));
  out = run(['install', '-p', proj, '--host', 'opencode'], env);
  ok(/updated/.test(out), 'old managed file is updated');
  ok(!/OLD MANAGED v1/.test(fs.readFileSync(cmd, 'utf8')), 'updated file holds real command content');

  // 4. user-edited -> preserve
  fs.writeFileSync(cmd, 'USER HAND EDIT\n');
  out = run(['install', '-p', proj, '--host', 'opencode'], env);
  ok(/preserved/.test(out), 'user-edited file reported preserved');
  ok(/USER HAND EDIT/.test(fs.readFileSync(cmd, 'utf8')), 'user-edited content survives re-run');

  // 5. --force overwrites
  out = run(['install', '-p', proj, '--host', 'opencode', '--force'], env);
  ok(/updated/.test(out), '--force reports updated');
  ok(!/USER HAND EDIT/.test(fs.readFileSync(cmd, 'utf8')), '--force overwrites user edit');

  // 6. render reproduces committed host files byte-for-byte
  const before = {};
  for (const rel of ['.opencode/command', '.claude/commands']) {
    const dir = path.join(PKG_ROOT, rel);
    if (!exists(dir)) continue;
    for (const f of fs.readdirSync(dir)) before[path.join(rel, f)] = sha(path.join(dir, f));
  }
  run(['render'], env);
  let renderStable = true;
  for (const [rel, h] of Object.entries(before)) if (sha(path.join(PKG_ROOT, rel)) !== h) renderStable = false;
  ok(renderStable, 'render reproduces committed host command files byte-for-byte');

  // 7. dry-run writes nothing
  const proj2 = mkTmp();
  run(['install', '-p', proj2, '--host', 'opencode', '--dry-run'], env);
  ok(fs.readdirSync(proj2).length === 0, 'dry-run writes nothing');

  // 8. uninstall removes tracked, preserves user-edited
  fs.writeFileSync(cmd, 'USER EDIT AGAIN\n');
  run(['uninstall', '-p', proj, '--host', 'opencode'], env);
  ok(exists(cmd), 'uninstall preserves a user-edited file');
  ok(!exists(skillMd), 'uninstall removes tracked skill files');
  // force uninstall clears the rest
  run(['uninstall', '-p', proj, '--host', 'opencode', '--force'], env);
  ok(!exists(cmd), 'uninstall --force removes the user-edited file too');

  // cleanup
  for (const d of [home, proj, proj2]) fs.rmSync(d, { recursive: true, force: true });

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
}

main();
