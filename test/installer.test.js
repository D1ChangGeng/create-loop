#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { execFileSync, spawn, spawnSync } = require('child_process');

const PKG_ROOT = path.resolve(__dirname, '..');
const CLI = path.join(PKG_ROOT, 'bin', 'create-loop.js');
let passed = 0;
let failed = 0;

function ok(condition, message) {
  if (condition) { passed++; console.log('  ok   - ' + message); }
  else { failed++; console.error('  FAIL - ' + message); }
}
function exists(p) { try { fs.statSync(p); return true; } catch (_) { return false; } }
function sha(p) { return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'); }
function stableObject(value) {
  if (Array.isArray(value)) return value.map(stableObject);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableObject(value[key])]));
}
function stateDigest(state) {
  const logical = stableObject(state);
  delete logical.createdAt;
  delete logical.updatedAt;
  delete logical.transactions;
  for (const host of Object.values(logical.hosts || {})) {
    delete host.installedAt;
    delete host.updatedAt;
    for (const group of ['roots', 'anchors']) {
      for (const key of Object.keys(host[group] || {})) {
        const resolved = path.resolve(host[group][key]);
        host[group][key] = process.platform === 'win32' ? resolved.toLowerCase() : resolved;
      }
    }
    host.files = Object.fromEntries(Object.entries(host.files || {}).map(([file, meta]) => {
      const resolved = path.resolve(file);
      return [process.platform === 'win32' ? resolved.toLowerCase() : resolved, meta];
    }).sort(([left], [right]) => left.localeCompare(right)));
  }
  const stateRoot = path.resolve(logical.stateRoot);
  logical.stateRoot = process.platform === 'win32' ? stateRoot.toLowerCase() : stateRoot;
  if (logical.projectRoot !== null) {
    const projectRoot = path.resolve(logical.projectRoot);
    logical.projectRoot = process.platform === 'win32' ? projectRoot.toLowerCase() : projectRoot;
  }
  return crypto.createHash('sha256').update(JSON.stringify(stableObject(logical))).digest('hex');
}
function canonicalDigestPath(value) {
  const resolved = path.resolve(value);
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}
function transactionIntentDigest(tx) {
  const intent = {
    version: tx.version,
    txId: tx.txId,
    host: tx.host,
    kinds: [...tx.kinds],
    stageDir: canonicalDigestPath(tx.stageDir),
    operations: tx.operations.map((op) => ({
      action: op.action,
      dst: canonicalDigestPath(op.dst),
      kind: op.kind,
      hash: op.hash,
      stage: op.stage === null ? null : canonicalDigestPath(op.stage),
      beforeHash: op.beforeHash,
      forceAuthorized: op.forceAuthorized,
    })),
    preStateSha256: tx.preStateSha256,
    postStateSha256: tx.postStateSha256,
    roots: Object.fromEntries(Object.entries(tx.roots)
      .map(([kind, root]) => [kind, canonicalDigestPath(root)])),
    commandSkillRoot: tx.commandSkillRoot ? canonicalDigestPath(tx.commandSkillRoot) : null,
  };
  return crypto.createHash('sha256').update(JSON.stringify(stableObject(intent))).digest('hex');
}
function tmp(prefix = 'cl-test-') { return fs.mkdtempSync(path.join(os.tmpdir(), prefix)); }
function envFor(home) { return { ...process.env, HOME: home, USERPROFILE: home, XDG_CONFIG_HOME: path.join(home, '.config'), CLAUDE_CONFIG_DIR: path.join(home, '.claude') }; }
let DEFAULT_COMMAND_SKILL_ROOT = null;
function commandSkillArgs(args) {
  return DEFAULT_COMMAND_SKILL_ROOT && args.includes('--commands-only') && args[0] !== 'uninstall'
    && !args.includes('--skill-root') ? [...args, '--skill-root', DEFAULT_COMMAND_SKILL_ROOT] : args;
}
function cliArgs(args) { return [CLI, ...commandSkillArgs(args)]; }
function run(args, env) { return execFileSync(process.execPath, [CLI, ...commandSkillArgs(args)], { encoding: 'utf8', env }); }
function attempt(args, env) { return spawnSync(process.execPath, [CLI, ...commandSkillArgs(args)], { encoding: 'utf8', env }); }
function rawRun(args, env) { return execFileSync(process.execPath, [CLI, ...args], { encoding: 'utf8', env }); }
function rawAttempt(args, env) { return spawnSync(process.execPath, [CLI, ...args], { encoding: 'utf8', env }); }
function snapshot(root) {
  const result = {};
  if (!exists(root)) return result;
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else result[path.relative(root, full)] = sha(full);
    }
  })(root);
  return result;
}
function copyTree(src, dst) {
  fs.cpSync(src, dst, {
    recursive: true,
    filter: (item) => !/[\\/]\.git(?:[\\/]|$)/.test(item) && !/[\\/]node_modules(?:[\\/]|$)/.test(item),
  });
}
function packageCli(make) {
  const root = make('cl-package-');
  copyTree(PKG_ROOT, root);
  return { root, cli: path.join(root, 'bin', 'create-loop.js') };
}
function schemaStringAccepts(schema, value) {
  if (typeof value !== 'string') return false;
  if (schema.minLength !== undefined && [...value].length < schema.minLength) return false;
  const patterns = [schema.pattern, ...(schema.allOf || []).map((entry) => entry.pattern)].filter(Boolean);
  return patterns.every((pattern) => new RegExp(pattern, 'u').test(value));
}
function runCli(cli, args, env) { return execFileSync(process.execPath, [cli, ...args], { encoding: 'utf8', env }); }
function attemptCli(cli, args, env) { return spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8', env }); }
function waitFor(p, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (!exists(p) && Date.now() < deadline) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
  return exists(p);
}
function npmPackEntries(root) {
  const command = process.platform === 'win32'
    ? { file: process.env.ComSpec || 'cmd.exe', args: ['/d', '/s', '/c', 'npm pack --dry-run --json'] }
    : { file: 'npm', args: ['pack', '--dry-run', '--json'] };
  const output = execFileSync(command.file, command.args, { cwd: root, encoding: 'utf8' });
  return JSON.parse(output)[0].files
    .map((entry) => ({ path: entry.path, size: entry.size }))
    .sort((left, right) => left.path.localeCompare(right.path));
}
function npmPackFiles(root) {
  return npmPackEntries(root).map((entry) => entry.path);
}
function expectedPackFiles(root) {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  return [...new Set(['package.json', ...pkg.files])].sort((left, right) => left.localeCompare(right));
}
function seedSkillRoot(root) {
  const target = path.resolve(root);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.cpSync(path.join(PKG_ROOT, 'skills', 'create-loop'), target, { recursive: true });
  return target;
}
async function main() {
  const dirs = [];
  const make = (prefix) => { const d = tmp(prefix); dirs.push(d); return d; };
  try {
  const home = make('cl-home-');
  const project = make('cl-project-');
  const env = envFor(home);
  const sharedSkillRoot = seedSkillRoot(path.join(make('cl-shared-skill-'), 'create-loop'));
  DEFAULT_COMMAND_SKILL_ROOT = sharedSkillRoot;
  const command = path.join(project, '.opencode', 'command', 'loop-status.md');
  const skill = path.join(project, '.agents', 'skills', 'create-loop', 'SKILL.md');
  const stateFile = path.join(project, '.create-loop', 'install-state.json');

  console.log('installer state v2 and reconciliation');
  run(['install', '-p', project, '--host', 'opencode', '-q'], env);
  ok(exists(command) && exists(skill) && exists(stateFile), 'fresh install writes skill, commands, and state');
  let state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  ok(state.manifestVersion === 2 && state.hosts.opencode.files[command].ownership === 'owned', 'state v2 records owned files');

  let out = run(['install', '-p', project, '--host', 'opencode'], env);
  ok(/unchanged/.test(out) && !/\d+ (created|updated|obsolete)/.test(out)
    && !exists(path.join(project, '.create-loop', 'install.lock')), 're-run is idempotent');

  fs.writeFileSync(command, 'OLD MANAGED\n');
  state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  state.hosts.opencode.files[command].hash = sha(command);
  fs.writeFileSync(stateFile, JSON.stringify(state));
  out = run(['install', '-p', project, '--host', 'opencode'], env);
  ok(/updated/.test(out) && !/OLD MANAGED/.test(fs.readFileSync(command, 'utf8')), 'owned old content upgrades');

  fs.writeFileSync(command, 'USER EDIT\n');
  out = run(['install', '-p', project, '--host', 'opencode'], env);
  ok(/skipped-user/.test(out) && /USER EDIT/.test(fs.readFileSync(command, 'utf8')), 'user edit is preserved');
  run(['install', '-p', project, '--host', 'opencode', '--force'], env);
  ok(!/USER EDIT/.test(fs.readFileSync(command, 'utf8')), '--force overwrites user-edited owned content');

  const skillOnlyHash = sha(skill);
  run(['install', '-p', project, '--host', 'opencode', '--commands-only', '-q'], env);
  state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  ok(state.hosts.opencode.files[skill] && sha(skill) === skillOnlyHash, 'commands-only preserves skill ownership');
  run(['install', '-p', project, '--host', 'opencode', '--skill-only', '-q'], env);
  state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  ok(state.hosts.opencode.files[command], 'skill-only preserves command ownership');

  const adoptedProject = make('cl-adopted-');
  const adoptedCommand = path.join(adoptedProject, '.opencode', 'command', 'loop-status.md');
  fs.mkdirSync(path.dirname(adoptedCommand), { recursive: true });
  fs.copyFileSync(path.join(PKG_ROOT, '.opencode', 'command', 'loop-status.md'), adoptedCommand);
  run(['install', '-p', adoptedProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const adoptedState = JSON.parse(fs.readFileSync(path.join(adoptedProject, '.create-loop', 'install-state.json'), 'utf8'));
  ok(adoptedState.hosts.opencode.files[adoptedCommand].ownership === 'adopted', 'pre-existing identical file is recorded as adopted');
  run(['uninstall', '-p', adoptedProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  ok(exists(adoptedCommand), 'pre-existing identical file is never removed, even with --force');

  const adoptedObsoleteProject = make('cl-adopted-obsolete-');
  const adoptedObsolete = path.join(adoptedObsoleteProject, '.opencode', 'command', 'obsolete.md');
  fs.mkdirSync(path.dirname(adoptedObsolete), { recursive: true });
  fs.writeFileSync(adoptedObsolete, 'pre-existing obsolete\n');
  run(['install', '-p', adoptedObsoleteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const adoptedObsoleteStatePath = path.join(adoptedObsoleteProject, '.create-loop', 'install-state.json');
  const adoptedObsoleteState = JSON.parse(fs.readFileSync(adoptedObsoleteStatePath, 'utf8'));
  adoptedObsoleteState.hosts.opencode.files[adoptedObsolete] = {
    hash: sha(adoptedObsolete), kind: 'command', ownership: 'adopted',
  };
  fs.writeFileSync(adoptedObsoleteStatePath, JSON.stringify(adoptedObsoleteState));
  run(['install', '-p', adoptedObsoleteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const adoptedObsoleteAfter = JSON.parse(fs.readFileSync(adoptedObsoleteStatePath, 'utf8'));
  ok(exists(adoptedObsolete)
    && adoptedObsoleteAfter.hosts.opencode.files[adoptedObsolete].ownership === 'adopted',
  'obsolete adopted files remain recorded while being preserved');

  const obsolete = path.join(project, '.opencode', 'command', 'obsolete.md');
  fs.writeFileSync(obsolete, 'obsolete\n');
  state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  state.hosts.opencode.files[obsolete] = { hash: sha(obsolete), kind: 'command', ownership: 'owned' };
  fs.writeFileSync(stateFile, JSON.stringify(state));
  run(['install', '-p', project, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(!exists(obsolete), 'install removes obsolete unchanged owned files of the selected kind');

  const outside = path.join(project, 'outside.txt');
  fs.writeFileSync(outside, 'outside\n');
  state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  state.hosts.opencode.files[outside] = { hash: sha(outside), kind: 'command', ownership: 'owned' };
  fs.writeFileSync(stateFile, JSON.stringify(state));
  const unsafe = attempt(['uninstall', '-p', project, '--host', 'opencode', '--commands-only', '--force'], env);
  ok(unsafe.status === 0 && exists(outside) && /outside managed command root/.test(unsafe.stderr), 'uninstall refuses tracked paths outside the managed root');

  if (process.platform === 'win32') {
    const caseProject = make('cl-case-project-');
    const caseVariant = caseProject.replace(/[A-Za-z]/, (letter) => (
      letter === letter.toLowerCase() ? letter.toUpperCase() : letter.toLowerCase()
    ));
    const caseCommand = path.join(caseProject, '.opencode', 'command', 'loop-status.md');
    run(['install', '-p', caseProject, '--host', 'opencode', '--commands-only', '-q'], env);
    const caseRerun = run(['install', '-p', caseVariant, '--host', 'opencode', '--commands-only'], env);
    const caseState = JSON.parse(fs.readFileSync(path.join(caseProject, '.create-loop', 'install-state.json'), 'utf8'));
    const caseRecords = Object.entries(caseState.hosts.opencode.files)
      .filter(([tracked]) => tracked.toLowerCase() === caseCommand.toLowerCase());
    ok(/unchanged/.test(caseRerun) && !/\d+ (created|updated|adopted|obsolete|skipped-user)/.test(caseRerun)
      && caseRecords.length === 1 && caseRecords[0][1].ownership === 'owned', 'Windows-equivalent project casing preserves owned file identity on re-run');
    run(['uninstall', '-p', caseVariant, '--host', 'opencode', '--commands-only', '-q'], env);
    ok(!exists(caseCommand), 'Windows-equivalent project casing remains uninstallable through the alternate spelling');

    const leafCaseProject = make('cl-leaf-case-project-');
    const leafCaseCommand = path.join(leafCaseProject, '.opencode', 'command', 'loop-status.md');
    const leafCaseStatePath = path.join(leafCaseProject, '.create-loop', 'install-state.json');
    run(['install', '-p', leafCaseProject, '--host', 'opencode', '--commands-only', '-q'], env);
    const leafCaseState = JSON.parse(fs.readFileSync(leafCaseStatePath, 'utf8'));
    const leafCaseVariant = path.join(path.dirname(leafCaseCommand), 'LOOP-STATUS.md');
    leafCaseState.hosts.opencode.files[leafCaseVariant] = leafCaseState.hosts.opencode.files[leafCaseCommand];
    delete leafCaseState.hosts.opencode.files[leafCaseCommand];
    fs.writeFileSync(leafCaseStatePath, JSON.stringify(leafCaseState));
    const leafCaseRerun = run(['install', '-p', leafCaseProject, '--host', 'opencode', '--commands-only'], env);
    const leafCaseReconciled = JSON.parse(fs.readFileSync(leafCaseStatePath, 'utf8'));
    const leafCaseRecords = Object.entries(leafCaseReconciled.hosts.opencode.files)
      .filter(([tracked]) => tracked.toLowerCase() === leafCaseCommand.toLowerCase());
    ok(/unchanged/.test(leafCaseRerun) && !/\d+ (created|updated|adopted|obsolete|skipped-user)/.test(leafCaseRerun)
      && exists(leafCaseCommand) && leafCaseRecords.length === 1
      && leafCaseRecords[0][0] === leafCaseCommand && leafCaseRecords[0][1].ownership === 'owned', 'Windows-equivalent managed filename casing preserves one canonical owned identity');
    run(['uninstall', '-p', leafCaseProject, '--host', 'opencode', '--commands-only', '-q'], env);
    ok(!exists(leafCaseCommand), 'Windows-equivalent managed filename casing remains uninstallable');

    const junctionProject = make('cl-uninstall-junction-');
    const junctionOutside = make('cl-uninstall-junction-outside-');
    const outsideEmpty = path.join(junctionOutside, 'empty', 'nested');
    const outsideMarker = path.join(junctionOutside, 'marker.txt');
    const rogueJunction = path.join(junctionProject, '.create-loop', 'rogue');
    fs.mkdirSync(outsideEmpty, { recursive: true });
    fs.writeFileSync(outsideMarker, 'outside\n');
    run(['install', '-p', junctionProject, '--host', 'opencode', '--commands-only', '-q'], env);
    let uninstallJunctionCreated = false;
    try {
      fs.symlinkSync(junctionOutside, rogueJunction, 'junction');
      uninstallJunctionCreated = true;
    } catch (_) {}
    if (uninstallJunctionCreated) {
      run(['uninstall', '-p', junctionProject, '--host', 'opencode', '--commands-only', '-q'], env);
      ok(fs.lstatSync(rogueJunction).isSymbolicLink() && exists(outsideEmpty) && exists(outsideMarker), 'uninstall pruning preserves unknown junctions and every external directory');
    } else {
      console.log('  skip - uninstall junction creation unavailable');
    }
  } else {
    console.log('  skip - Windows path-casing and uninstall junction regressions');
  }

  fs.writeFileSync(stateFile, '{bad json');
  const corrupt = attempt(['install', '-p', project, '--host', 'opencode'], env);
  ok(corrupt.status !== 0 && /corrupt; refusing/.test(corrupt.stderr), 'corrupt state fails closed');

  console.log('\nrenderer and manifest');
  const renderPackage = packageCli(make);
  const renderedRoots = [path.join(renderPackage.root, '.opencode', 'command'), path.join(renderPackage.root, '.claude', 'commands')];
  const renderSnapshot = () => renderedRoots.map(snapshot);
  const beforeRender = renderSnapshot();
  runCli(renderPackage.cli, ['render', '--check'], env);
  ok(JSON.stringify(renderSnapshot()) === JSON.stringify(beforeRender), 'render --check is read-only');
  runCli(renderPackage.cli, ['render'], env);
  ok(JSON.stringify(renderSnapshot()) === JSON.stringify(beforeRender), 'render is deterministic and leaves an up-to-date tree unchanged');
  ok(fs.readFileSync(path.join(renderPackage.root, '.opencode', 'command', 'loop-new.md'), 'utf8').indexOf('\r') === -1, 'rendered commands use LF');

  const manifestPath = path.join(renderPackage.root, 'command', 'manifest.json');
  const bad = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  bad.commands[0].body = '../README.md';
  fs.writeFileSync(manifestPath, JSON.stringify(bad));
  const contained = attemptCli(renderPackage.cli, ['render', '--check'], env);
  ok(contained.status !== 0 && /must be exactly/.test(contained.stderr), 'manifest body traversal is rejected');

  const yamlPackage = packageCli(make);
  const yamlManifestPath = path.join(yamlPackage.root, 'command', 'manifest.json');
  const yamlManifest = JSON.parse(fs.readFileSync(yamlManifestPath, 'utf8'));
  yamlManifest.commands[0].description = 'bad: yaml # value';
  fs.writeFileSync(yamlManifestPath, JSON.stringify(yamlManifest));
  runCli(yamlPackage.cli, ['render'], env);
  const yamlOpen = fs.readFileSync(path.join(yamlPackage.root, '.opencode', 'command', 'loop-new.md'), 'utf8');
  const yamlClaude = fs.readFileSync(path.join(yamlPackage.root, '.claude', 'commands', 'loop-new.md'), 'utf8');
  ok(yamlOpen.includes('description: "bad: yaml # value"')
    && yamlClaude.includes('description: "bad: yaml # value"'), 'renderer quotes YAML-special frontmatter strings');

  const parityPackage = packageCli(make);
  const parityManifestPath = path.join(parityPackage.root, 'command', 'manifest.json');
  const parityManifestSource = fs.readFileSync(parityManifestPath, 'utf8');
  const manifestSchema = JSON.parse(fs.readFileSync(path.join(parityPackage.root, 'command', 'manifest.schema.json'), 'utf8'));
  const manifestStringFields = [
    ['$schema', manifestSchema.properties.$schema, (manifest, value) => { manifest.$schema = value; }],
    ['description', manifestSchema.properties.description, (manifest, value) => { manifest.description = value; }],
    ['commands[0].description', manifestSchema.properties.commands.items.properties.description,
      (manifest, value) => { manifest.commands[0].description = value; }],
    ['commands[0].argumentHint', manifestSchema.properties.commands.items.properties.argumentHint,
      (manifest, value) => { manifest.commands[0].argumentHint = value; }],
  ];
  for (const [field, fieldSchema, assign] of manifestStringFields) {
    const acceptedManifest = JSON.parse(parityManifestSource);
    assign(acceptedManifest, '  useful text  ');
    fs.writeFileSync(parityManifestPath, JSON.stringify(acceptedManifest));
    const accepted = attemptCli(parityPackage.cli, ['render'], env);
    ok(schemaStringAccepts(fieldSchema, '  useful text  ') && accepted.status === 0,
      `manifest schema and renderer accept non-empty ${field} with surrounding spaces`);
    for (const [label, value] of [['spaces', ' '], ['tab', '\t']]) {
      const whitespaceManifest = JSON.parse(parityManifestSource);
      assign(whitespaceManifest, value);
      fs.writeFileSync(parityManifestPath, JSON.stringify(whitespaceManifest));
      const refusedWhitespace = attemptCli(parityPackage.cli, ['render', '--check'], env);
      ok(!schemaStringAccepts(fieldSchema, value)
        && refusedWhitespace.status !== 0 && /must be a non-empty string/.test(refusedWhitespace.stderr),
      `manifest schema and renderer reject ${label}-only ${field}`);
    }
  }

  for (const [label, separator] of [
    ['C0 control', '\u0000'], ['NEL', '\u0085'], ['line separator', '\u2028'], ['paragraph separator', '\u2029'],
  ]) {
    const controlPackage = packageCli(make);
    const controlManifestPath = path.join(controlPackage.root, 'command', 'manifest.json');
    const controlManifest = JSON.parse(fs.readFileSync(controlManifestPath, 'utf8'));
    controlManifest.commands[0].description = `unsafe${separator}frontmatter`;
    fs.writeFileSync(controlManifestPath, JSON.stringify(controlManifest));
    const refusedControl = attemptCli(controlPackage.cli, ['render', '--check'], env);
    ok(!schemaStringAccepts(manifestSchema.properties.commands.items.properties.description,
      controlManifest.commands[0].description)
      && refusedControl.status !== 0 && /without control or YAML line-separator/.test(refusedControl.stderr),
      `manifest rejects ${label} in frontmatter strings`);
  }

  const unsafePackage = packageCli(make);
  const unsafeRenderDir = path.join(unsafePackage.root, '.opencode', 'command');
  fs.mkdirSync(path.join(unsafeRenderDir, 'unexpected-directory'));
  const unsafeRender = attemptCli(unsafePackage.cli, ['render'], env);
  ok(unsafeRender.status !== 0 && /unsafe non-regular entry/.test(unsafeRender.stderr), 'renderer refuses unknown directories instead of recursively deleting them');

  const linkPackage = packageCli(make);
  const linkTarget = make('cl-link-target-');
  const linkRoot = path.join(linkPackage.root, '.opencode', 'command');
  fs.rmSync(linkRoot, { recursive: true, force: true });
  let linkCreated = false;
  try {
    fs.symlinkSync(linkTarget, linkRoot, process.platform === 'win32' ? 'junction' : 'dir');
    linkCreated = true;
  } catch (_) {}
  if (linkCreated) {
    const linkedRender = attemptCli(linkPackage.cli, ['render'], env);
    ok(linkedRender.status !== 0 && /symlink|junction|reparse-point/.test(linkedRender.stderr), 'renderer refuses a redirected render root');
  } else {
    console.log('  skip - symlink/junction creation unavailable');
  }

  const missingScriptPackage = packageCli(make);
  fs.rmSync(path.join(missingScriptPackage.root, 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'));
  const missingScriptTarget = make('cl-missing-packaged-script-');
  const missingScriptBefore = snapshot(missingScriptTarget);
  const missingScriptInstall = attemptCli(
    missingScriptPackage.cli, ['install', '-p', missingScriptTarget, '--host', 'opencode'], env
  );
  ok(missingScriptInstall.status !== 0
    && /packaged Skill source missing a regular contained command dependency/.test(missingScriptInstall.stderr)
    && JSON.stringify(snapshot(missingScriptTarget)) === JSON.stringify(missingScriptBefore),
  'full install rejects an incomplete packaged Skill before writing');

  const missingSkillOnlyPackage = packageCli(make);
  const missingSkillOnlyTarget = make('cl-missing-skill-only-script-');
  runCli(missingSkillOnlyPackage.cli, ['install', '-p', missingSkillOnlyTarget, '--host', 'opencode', '-q'], env);
  fs.rmSync(path.join(missingSkillOnlyPackage.root, 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'));
  const missingSkillOnlyBefore = snapshot(missingSkillOnlyTarget);
  const missingSkillOnlyInstall = attemptCli(
    missingSkillOnlyPackage.cli, ['install', '-p', missingSkillOnlyTarget, '--host', 'opencode', '--skill-only'], env
  );
  ok(missingSkillOnlyInstall.status !== 0
    && /packaged Skill source missing a regular contained command dependency/.test(missingSkillOnlyInstall.stderr)
    && JSON.stringify(snapshot(missingSkillOnlyTarget)) === JSON.stringify(missingSkillOnlyBefore),
  'skill-only rejects an incomplete packaged Skill without changing an existing install');

  const dry = make('cl-dry-');
  run(['install', '-p', dry, '--host', 'opencode', '--dry-run'], env);
  ok(fs.readdirSync(dry).length === 0, 'dry-run writes nothing');

  const linkedProject = make('cl-linked-project-');
  const linkedOutside = make('cl-linked-outside-');
  fs.mkdirSync(path.join(linkedProject, '.opencode'), { recursive: true });
  let projectLinkCreated = false;
  try {
    fs.symlinkSync(linkedOutside, path.join(linkedProject, '.opencode', 'command'), process.platform === 'win32' ? 'junction' : 'dir');
    projectLinkCreated = true;
  } catch (_) {}
  if (projectLinkCreated) {
    const linkedInstall = attempt(['install', '-p', linkedProject, '--host', 'opencode', '--commands-only'], env);
    ok(linkedInstall.status !== 0 && /symlink|junction|reparse-point/.test(linkedInstall.stderr)
      && fs.readdirSync(linkedOutside).length === 0, 'installer refuses a redirected managed root');
  } else {
    console.log('  skip - project junction creation unavailable');
  }

  const failureProject = make('cl-failure-');
  const injected = attempt(['install', '-p', failureProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const failureTx = path.join(failureProject, '.create-loop', 'transactions', 'opencode.json');
  ok(injected.status !== 0 && exists(failureTx)
    && JSON.parse(fs.readFileSync(failureTx, 'utf8')).preState, 'injected failure leaves a recovery transaction with prior ownership state');
  run(['install', '-p', failureProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(exists(path.join(failureProject, '.opencode', 'command', 'loop-status.md'))
    && !exists(failureTx), 'next run completes and commits an interrupted host transaction');

  const projectedSkillPackage = packageCli(make);
  fs.appendFileSync(path.join(projectedSkillPackage.root, 'skills', 'create-loop', 'README.md'), '\nRECOVERY UPDATE A\n');
  fs.appendFileSync(path.join(projectedSkillPackage.root, 'skills', 'create-loop', 'references', 'command_system.md'), '\nRECOVERY UPDATE B\n');
  fs.appendFileSync(path.join(projectedSkillPackage.root, 'command', 'loop-status.md'), '\nRECOVERY COMMAND UPDATE\n');
  const projectedSkillProject = make('cl-projected-skill-recovery-');
  runCli(projectedSkillPackage.cli, ['install', '-p', projectedSkillProject, '--host', 'opencode', '-q'], env);
  fs.appendFileSync(path.join(projectedSkillPackage.root, 'skills', 'create-loop', 'README.md'), '\nRECOVERY UPDATE C\n');
  fs.appendFileSync(path.join(projectedSkillPackage.root, 'skills', 'create-loop', 'references', 'command_system.md'), '\nRECOVERY UPDATE D\n');
  fs.appendFileSync(path.join(projectedSkillPackage.root, 'command', 'loop-status.md'), '\nRECOVERY COMMAND UPDATE 2\n');
  const projectedSkillFailure = attemptCli(
    projectedSkillPackage.cli, ['install', '-p', projectedSkillProject, '--host', 'opencode'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const projectedSkillTx = path.join(projectedSkillProject, '.create-loop', 'transactions', 'opencode.json');
  const projectedSkillScript = path.join(
    projectedSkillProject, '.agents', 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'
  );
  fs.rmSync(projectedSkillScript);
  const projectedSkillBeforeRecovery = snapshot(projectedSkillProject);
  const refusedProjectedSkill = attemptCli(
    projectedSkillPackage.cli, ['install', '-p', projectedSkillProject, '--host', 'opencode'], env
  );
  ok(projectedSkillFailure.status !== 0 && refusedProjectedSkill.status !== 0
    && /recovered transaction command Skill root missing a regular contained command dependency/.test(refusedProjectedSkill.stderr)
    && exists(projectedSkillTx)
    && JSON.stringify(snapshot(projectedSkillProject)) === JSON.stringify(projectedSkillBeforeRecovery),
  'mixed recovery validates the projected Skill before mutating any pending destination');

  const projectedDeletePackage = packageCli(make);
  const projectedDeleteProject = make('cl-projected-skill-delete-');
  runCli(projectedDeletePackage.cli, ['install', '-p', projectedDeleteProject, '--host', 'opencode', '-q'], env);
  fs.appendFileSync(path.join(projectedDeletePackage.root, 'command', 'loop-status.md'), '\nPROJECTED DELETE UPDATE\n');
  const projectedDeleteFailure = attemptCli(
    projectedDeletePackage.cli, ['install', '-p', projectedDeleteProject, '--host', 'opencode'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const projectedDeleteTxPath = path.join(projectedDeleteProject, '.create-loop', 'transactions', 'opencode.json');
  const projectedDeleteTx = JSON.parse(fs.readFileSync(projectedDeleteTxPath, 'utf8'));
  const projectedDeleteScript = path.join(
    projectedDeleteProject, '.agents', 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'
  );
  const projectedDeleteMeta = projectedDeleteTx.preState.hosts.opencode.files[projectedDeleteScript];
  delete projectedDeleteTx.state.hosts.opencode.files[projectedDeleteScript];
  projectedDeleteTx.kinds = ['command', 'skill'];
  projectedDeleteTx.operations.push({
    action: 'delete', dst: projectedDeleteScript, kind: 'skill', hash: null,
    stage: null, beforeHash: projectedDeleteMeta.hash, forceAuthorized: false,
  });
  fs.writeFileSync(projectedDeleteTxPath, JSON.stringify(projectedDeleteTx));
  const projectedDeleteBeforeRecovery = snapshot(projectedDeleteProject);
  const refusedProjectedDelete = attemptCli(
    projectedDeletePackage.cli, ['install', '-p', projectedDeleteProject, '--host', 'opencode'], env
  );
  ok(projectedDeleteFailure.status !== 0 && refusedProjectedDelete.status !== 0
    && /post-state digest mismatch|not anchored by install state/.test(refusedProjectedDelete.stderr)
    && exists(projectedDeleteTxPath) && exists(projectedDeleteScript)
    && JSON.stringify(snapshot(projectedDeleteProject)) === JSON.stringify(projectedDeleteBeforeRecovery),
  'mixed recovery rejects a projected required-script delete without mutating transaction state');

  const pendingBrokenPackage = packageCli(make);
  const pendingBrokenProject = make('cl-pending-broken-package-');
  runCli(pendingBrokenPackage.cli, ['install', '-p', pendingBrokenProject, '--host', 'opencode', '-q'], env);
  const pendingBrokenSkillRoot = path.join(pendingBrokenProject, '.agents', 'skills', 'create-loop');
  fs.appendFileSync(path.join(pendingBrokenPackage.root, 'command', 'loop-status.md'), '\nPENDING BROKEN PACKAGE UPDATE\n');
  const pendingBrokenFailure = attemptCli(
    pendingBrokenPackage.cli,
    ['install', '-p', pendingBrokenProject, '--host', 'opencode', '--commands-only', '--skill-root', pendingBrokenSkillRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingBrokenTx = path.join(pendingBrokenProject, '.create-loop', 'transactions', 'opencode.json');
  fs.rmSync(path.join(pendingBrokenPackage.root, 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'));
  const pendingBrokenBeforeRecovery = snapshot(pendingBrokenProject);
  const refusedPendingBroken = attemptCli(
    pendingBrokenPackage.cli, ['install', '-p', pendingBrokenProject, '--host', 'opencode'], env
  );
  ok(pendingBrokenFailure.status !== 0 && refusedPendingBroken.status !== 0
    && /packaged Skill source missing a regular contained command dependency/.test(refusedPendingBroken.stderr)
    && exists(pendingBrokenTx)
    && JSON.stringify(snapshot(pendingBrokenProject)) === JSON.stringify(pendingBrokenBeforeRecovery),
  'full install validates a broken packaged Skill before recovering an older command transaction');

  const wrongDestinationProject = make('cl-wrong-destination-skill-');
  const wrongDestinationSkill = path.join(wrongDestinationProject, '.agents', 'skills', 'create-loop');
  fs.mkdirSync(wrongDestinationSkill, { recursive: true });
  fs.writeFileSync(path.join(wrongDestinationSkill, 'SKILL.md'), '---\nname: not-create-loop\n---\n');
  const wrongDestinationBefore = snapshot(wrongDestinationProject);
  const refusedWrongDestination = attempt(
    ['install', '-p', wrongDestinationProject, '--host', 'opencode'], env
  );
  ok(refusedWrongDestination.status !== 0
    && /planned opencode Skill root SKILL\.md must declare exactly one name: create-loop/.test(refusedWrongDestination.stderr)
    && JSON.stringify(snapshot(wrongDestinationProject)) === JSON.stringify(wrongDestinationBefore),
  'full install rejects an incompatible pre-existing Skill identity before any host transaction');

  const pendingExplicitProject = make('cl-pending-explicit-root-');
  const pendingExplicitGoodRoot = seedSkillRoot(path.join(make('cl-pending-explicit-good-'), 'create-loop'));
  const pendingExplicitFailure = attempt(
    ['install', '-p', pendingExplicitProject, '--host', 'opencode', '--commands-only', '--skill-root', pendingExplicitGoodRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingExplicitTx = path.join(pendingExplicitProject, '.create-loop', 'transactions', 'opencode.json');
  const pendingExplicitBadRoot = seedSkillRoot(path.join(make('cl-pending-explicit-bad-'), 'create-loop'));
  fs.writeFileSync(path.join(pendingExplicitBadRoot, 'SKILL.md'), '---\nname: not-create-loop\n---\n');
  const pendingExplicitBefore = snapshot(pendingExplicitProject);
  const refusedPendingExplicit = attempt(
    ['install', '-p', pendingExplicitProject, '--host', 'opencode', '--commands-only', '--skill-root', pendingExplicitBadRoot], env
  );
  ok(pendingExplicitFailure.status !== 0 && refusedPendingExplicit.status !== 0
    && /explicit Skill root SKILL\.md must declare exactly one name: create-loop/.test(refusedPendingExplicit.stderr)
    && exists(pendingExplicitTx)
    && JSON.stringify(snapshot(pendingExplicitProject)) === JSON.stringify(pendingExplicitBefore),
  'commands-only validates a new explicit Skill root before recovering an older transaction');

  const pendingImplicitProject = make('cl-pending-implicit-root-');
  const pendingImplicitRoot = seedSkillRoot(path.join(make('cl-pending-implicit-source-'), 'create-loop'));
  const pendingImplicitFailure = attemptCli(
    CLI, ['install', '-p', pendingImplicitProject, '--host', 'opencode', '--commands-only', '--skill-root', pendingImplicitRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingImplicitTx = path.join(pendingImplicitProject, '.create-loop', 'transactions', 'opencode.json');
  const pendingImplicitCommand = path.join(pendingImplicitProject, '.opencode', 'command', 'loop-new.md');
  const resumedPendingImplicit = attemptCli(
    CLI, ['install', '-p', pendingImplicitProject, '--host', 'opencode', '--commands-only', '-q'], env
  );
  ok(pendingImplicitFailure.status !== 0 && resumedPendingImplicit.status === 0
    && !exists(pendingImplicitTx)
    && fs.readFileSync(pendingImplicitCommand, 'utf8').includes(fs.realpathSync(pendingImplicitRoot).replace(/\\/g, '/')),
  'commands-only reuses a pending transaction Skill root before normal discovery');

  const pendingOtherHostProject = make('cl-pending-other-host-root-');
  const pendingOtherHostRoot = seedSkillRoot(path.join(pendingOtherHostProject, '.claude', 'skills', 'create-loop'));
  const pendingOtherHostFailure = attemptCli(
    CLI, ['install', '-p', pendingOtherHostProject, '--host', 'claude', '--commands-only', '--skill-root', pendingOtherHostRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingOtherHostTx = path.join(pendingOtherHostProject, '.create-loop', 'transactions', 'claude.json');
  const pendingOtherHostBefore = snapshot(pendingOtherHostProject);
  const refusedOtherHostRoot = attemptCli(
    CLI, ['install', '-p', pendingOtherHostProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(pendingOtherHostFailure.status !== 0 && refusedOtherHostRoot.status !== 0
    && /could not find a valid create-loop Skill root/.test(refusedOtherHostRoot.stderr)
    && exists(pendingOtherHostTx)
    && JSON.stringify(snapshot(pendingOtherHostProject)) === JSON.stringify(pendingOtherHostBefore),
  'an unselected host pending transaction cannot supply the current command Skill root');

  const pendingWrongTargetProject = make('cl-pending-wrong-target-');
  const pendingWrongTargetRoot = seedSkillRoot(path.join(make('cl-pending-wrong-target-source-'), 'create-loop'));
  const pendingWrongTargetFailure = attemptCli(
    CLI, ['install', '-p', pendingWrongTargetProject, '--host', 'opencode', '--commands-only', '--skill-root', pendingWrongTargetRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingWrongTargetTx = path.join(pendingWrongTargetProject, '.create-loop', 'transactions', 'opencode.json');
  const pendingWrongTargetSkill = path.join(pendingWrongTargetProject, '.agents', 'skills', 'create-loop');
  fs.mkdirSync(pendingWrongTargetSkill, { recursive: true });
  fs.writeFileSync(path.join(pendingWrongTargetSkill, 'SKILL.md'), '---\nname: not-create-loop\n---\n');
  const pendingWrongTargetBefore = snapshot(pendingWrongTargetProject);
  const refusedPendingWrongTarget = attemptCli(
    CLI, ['install', '-p', pendingWrongTargetProject, '--host', 'opencode'], env
  );
  ok(pendingWrongTargetFailure.status !== 0 && refusedPendingWrongTarget.status !== 0
    && /planned opencode Skill root SKILL\.md must declare exactly one name: create-loop/.test(refusedPendingWrongTarget.stderr)
    && exists(pendingWrongTargetTx)
    && JSON.stringify(snapshot(pendingWrongTargetProject)) === JSON.stringify(pendingWrongTargetBefore),
  'full install validates its current Skill target before recovering an older command transaction');

  const preservedScriptPackage = packageCli(make);
  const preservedScriptProject = make('cl-preserved-script-recovery-');
  runCli(preservedScriptPackage.cli, ['install', '-p', preservedScriptProject, '--host', 'opencode', '-q'], env);
  const preservedScript = path.join(
    preservedScriptProject, '.agents', 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'
  );
  fs.appendFileSync(preservedScript, '\n# USER PRESERVED SCRIPT EDIT\n');
  fs.appendFileSync(path.join(preservedScriptPackage.root, 'skills', 'create-loop', 'AGENTS.md'), '\npreserved recovery skill change\n');
  fs.appendFileSync(path.join(preservedScriptPackage.root, 'command', 'loop-status.md'), '\npreserved recovery command change\n');
  const preservedScriptFailure = attemptCli(
    preservedScriptPackage.cli, ['install', '-p', preservedScriptProject, '--host', 'opencode'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const preservedScriptTx = path.join(preservedScriptProject, '.create-loop', 'transactions', 'opencode.json');
  const resumedPreservedScript = attemptCli(
    preservedScriptPackage.cli, ['install', '-p', preservedScriptProject, '--host', 'opencode', '-q'], env
  );
  ok(preservedScriptFailure.status !== 0 && resumedPreservedScript.status === 0
    && !exists(preservedScriptTx)
    && /USER PRESERVED SCRIPT EDIT/.test(fs.readFileSync(preservedScript, 'utf8')),
  'mixed recovery preserves an untouched user-edited command script');

  const pendingSkillDeleteProject = make('cl-pending-skill-delete-');
  run(['install', '-p', pendingSkillDeleteProject, '--host', 'opencode', '-q'], env);
  const pendingSkillDeleteFailure = attempt(
    ['uninstall', '-p', pendingSkillDeleteProject, '--host', 'opencode', '--skill-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingSkillDeleteTx = path.join(
    pendingSkillDeleteProject, '.create-loop', 'transactions', 'opencode.json'
  );
  const pendingSkillDeleteBefore = snapshot(pendingSkillDeleteProject);
  const refusedCommandsAfterSkillDelete = spawnSync(
    process.execPath,
    [CLI, 'install', '-p', pendingSkillDeleteProject, '--host', 'opencode', '--commands-only'],
    { encoding: 'utf8', env }
  );
  ok(pendingSkillDeleteFailure.status !== 0 && refusedCommandsAfterSkillDelete.status !== 0
    && /projected current command Skill root SKILL\.md must declare exactly one name: create-loop/.test(refusedCommandsAfterSkillDelete.stderr)
    && exists(pendingSkillDeleteTx)
    && JSON.stringify(snapshot(pendingSkillDeleteProject)) === JSON.stringify(pendingSkillDeleteBefore),
  'commands-only install rejects a pending Skill deletion before recovery mutation');
  run(['uninstall', '-p', pendingSkillDeleteProject, '--host', 'opencode', '--skill-only', '-q'], env);
  ok(!exists(pendingSkillDeleteTx)
    && !exists(path.join(pendingSkillDeleteProject, '.agents', 'skills', 'create-loop', 'SKILL.md')),
  'matching skill-only uninstall safely recovers a pending Skill deletion');
  run(['install', '-p', pendingSkillDeleteProject, '--host', 'opencode', '-q'], env);
  ok(exists(path.join(pendingSkillDeleteProject, '.agents', 'skills', 'create-loop', 'SKILL.md')),
  'full install can restore the Skill after the pending deletion is resolved');

  const invalidUninstallHostProject = make('cl-invalid-uninstall-host-');
  const invalidUninstallHostFailure = attempt(
    ['install', '-p', invalidUninstallHostProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const invalidUninstallHostTx = path.join(
    invalidUninstallHostProject, '.create-loop', 'transactions', 'opencode.json'
  );
  const invalidUninstallHostBefore = snapshot(invalidUninstallHostProject);
  const refusedInvalidUninstallHost = attempt(
    ['uninstall', '-p', invalidUninstallHostProject, '--host', 'not-a-host', '--commands-only'], env
  );
  ok(invalidUninstallHostFailure.status !== 0 && refusedInvalidUninstallHost.status !== 0
    && /unknown host/.test(refusedInvalidUninstallHost.stderr) && exists(invalidUninstallHostTx)
    && JSON.stringify(snapshot(invalidUninstallHostProject)) === JSON.stringify(invalidUninstallHostBefore),
  'uninstall validates an explicit host before recovering pending transactions');

  const injectedDeleteProject = make('cl-injected-delete-');
  const injectedDeleteFailure = attempt(['install', '-p', injectedDeleteProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const injectedDeleteTxPath = path.join(injectedDeleteProject, '.create-loop', 'transactions', 'opencode.json');
  const injectedDeleteTarget = path.join(injectedDeleteProject, '.opencode', 'command', 'user-private.md');
  fs.writeFileSync(injectedDeleteTarget, 'USER PRIVATE\n');
  const injectedDeleteTx = JSON.parse(fs.readFileSync(injectedDeleteTxPath, 'utf8'));
  injectedDeleteTx.operations.push({ action: 'delete', dst: injectedDeleteTarget, kind: 'command', hash: null, stage: null, beforeHash: sha(injectedDeleteTarget), forceAuthorized: false });
  fs.writeFileSync(injectedDeleteTxPath, JSON.stringify(injectedDeleteTx));
  const refusedInjectedDelete = attempt(['install', '-p', injectedDeleteProject, '--host', 'opencode', '--commands-only'], env);
  ok(injectedDeleteFailure.status !== 0 && refusedInjectedDelete.status !== 0
    && /not anchored by install state/.test(refusedInjectedDelete.stderr)
    && exists(injectedDeleteTarget) && exists(injectedDeleteTxPath), 'recovery rejects an injected delete of an untracked user file');

  const injectedWriteProject = make('cl-injected-write-');
  const injectedWriteFailure = attempt(['install', '-p', injectedWriteProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const injectedWriteTxPath = path.join(injectedWriteProject, '.create-loop', 'transactions', 'opencode.json');
  const injectedWriteTarget = path.join(injectedWriteProject, '.opencode', 'command', 'user-private.md');
  fs.writeFileSync(injectedWriteTarget, 'USER PRIVATE\n');
  const injectedWriteTx = JSON.parse(fs.readFileSync(injectedWriteTxPath, 'utf8'));
  const injectedStage = path.join(injectedWriteTx.stageDir, `${injectedWriteTx.operations.length}.stage`);
  fs.writeFileSync(injectedStage, 'INJECTED\n');
  injectedWriteTx.operations.push({ action: 'write', dst: injectedWriteTarget, kind: 'command', hash: sha(injectedStage), stage: injectedStage, beforeHash: sha(injectedWriteTarget), forceAuthorized: false });
  fs.writeFileSync(injectedWriteTxPath, JSON.stringify(injectedWriteTx));
  const refusedInjectedWrite = attempt(['install', '-p', injectedWriteProject, '--host', 'opencode', '--commands-only'], env);
  ok(injectedWriteFailure.status !== 0 && refusedInjectedWrite.status !== 0
    && /not anchored by install state/.test(refusedInjectedWrite.stderr)
    && fs.readFileSync(injectedWriteTarget, 'utf8') === 'USER PRIVATE\n' && exists(injectedWriteTxPath), 'recovery rejects an injected write to an untracked user file');

  const tamperedBeforeHashProject = make('cl-tampered-before-hash-');
  const tamperedBeforeHashFailure = attempt(
    ['install', '-p', tamperedBeforeHashProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const tamperedBeforeHashTxPath = path.join(tamperedBeforeHashProject, '.create-loop', 'transactions', 'opencode.json');
  const tamperedBeforeHashTx = JSON.parse(fs.readFileSync(tamperedBeforeHashTxPath, 'utf8'));
  const tamperedBeforeHashOp = tamperedBeforeHashTx.operations.find((op) => op.action === 'write');
  tamperedBeforeHashOp.beforeHash = '0'.repeat(64);
  fs.writeFileSync(tamperedBeforeHashTxPath, JSON.stringify(tamperedBeforeHashTx));
  const tamperedBeforeHashBefore = snapshot(tamperedBeforeHashProject);
  const refusedTamperedBeforeHash = attempt(
    ['install', '-p', tamperedBeforeHashProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(tamperedBeforeHashFailure.status !== 0 && refusedTamperedBeforeHash.status !== 0
    && /not anchored by install state/.test(refusedTamperedBeforeHash.stderr)
    && JSON.stringify(snapshot(tamperedBeforeHashProject)) === JSON.stringify(tamperedBeforeHashBefore),
  'install-state intent anchor rejects a forged write beforeHash without mutation');

  const forgedRealityProject = make('cl-forged-reality-before-hash-');
  const forgedRealityTarget = path.join(forgedRealityProject, '.opencode', 'command', 'loop-status.md');
  fs.mkdirSync(path.dirname(forgedRealityTarget), { recursive: true });
  fs.writeFileSync(forgedRealityTarget, 'PRE-EXISTING DIFFERENT FILE\n');
  const forgedRealityFailure = attempt(
    ['install', '-p', forgedRealityProject, '--host', 'opencode', '--commands-only', '--force'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const forgedRealityTxPath = path.join(forgedRealityProject, '.create-loop', 'transactions', 'opencode.json');
  const forgedRealityStatePath = path.join(forgedRealityProject, '.create-loop', 'install-state.json');
  const forgedRealityTx = JSON.parse(fs.readFileSync(forgedRealityTxPath, 'utf8'));
  const forgedRealityOp = forgedRealityTx.operations.find((op) => op.dst === forgedRealityTarget);
  fs.writeFileSync(forgedRealityTarget, 'POST-CRASH USER CHANGE\n');
  forgedRealityOp.beforeHash = sha(forgedRealityTarget);
  fs.writeFileSync(forgedRealityTxPath, JSON.stringify(forgedRealityTx));
  const forgedRealityAnchor = JSON.parse(fs.readFileSync(forgedRealityStatePath, 'utf8')).transactions.opencode;
  const forgedRealityBefore = snapshot(forgedRealityProject);
  const refusedForgedReality = attempt(
    ['install', '-p', forgedRealityProject, '--host', 'opencode', '--commands-only', '--force'], env
  );
  const forgedRealityState = JSON.parse(fs.readFileSync(forgedRealityStatePath, 'utf8'));
  ok(forgedRealityFailure.status !== 0 && forgedRealityOp && forgedRealityOp.forceAuthorized
    && refusedForgedReality.status !== 0 && /not anchored by install state/.test(refusedForgedReality.stderr)
    && JSON.stringify(snapshot(forgedRealityProject)) === JSON.stringify(forgedRealityBefore)
    && exists(forgedRealityTxPath)
    && JSON.stringify(forgedRealityState.transactions.opencode) === JSON.stringify(forgedRealityAnchor)
    && fs.readFileSync(forgedRealityTarget, 'utf8') === 'POST-CRASH USER CHANGE\n',
  'intent anchor rejects a forged beforeHash matching changed post-crash reality');

  const tamperedDeleteProject = make('cl-tampered-delete-intent-');
  run(['install', '-p', tamperedDeleteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const tamperedDeleteFailure = attempt(
    ['uninstall', '-p', tamperedDeleteProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const tamperedDeleteTxPath = path.join(tamperedDeleteProject, '.create-loop', 'transactions', 'opencode.json');
  const tamperedDeleteTx = JSON.parse(fs.readFileSync(tamperedDeleteTxPath, 'utf8'));
  const tamperedDeleteOp = tamperedDeleteTx.operations.find((op) => op.action === 'delete');
  tamperedDeleteOp.beforeHash = '1'.repeat(64);
  fs.writeFileSync(tamperedDeleteTxPath, JSON.stringify(tamperedDeleteTx));
  const tamperedDeleteBefore = snapshot(tamperedDeleteProject);
  const refusedTamperedDelete = attempt(
    ['uninstall', '-p', tamperedDeleteProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(tamperedDeleteFailure.status !== 0 && refusedTamperedDelete.status !== 0
    && /not anchored by install state/.test(refusedTamperedDelete.stderr)
    && JSON.stringify(snapshot(tamperedDeleteProject)) === JSON.stringify(tamperedDeleteBefore),
  'install-state intent anchor rejects a forged delete beforeHash without mutation');

  const tamperedOperationProject = make('cl-tampered-operation-intent-');
  const tamperedOperationFailure = attempt(
    ['install', '-p', tamperedOperationProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const tamperedOperationTxPath = path.join(tamperedOperationProject, '.create-loop', 'transactions', 'opencode.json');
  const tamperedOperationTx = JSON.parse(fs.readFileSync(tamperedOperationTxPath, 'utf8'));
  tamperedOperationTx.operations.reverse();
  tamperedOperationTx.operations[0].kind = 'skill';
  fs.writeFileSync(tamperedOperationTxPath, JSON.stringify(tamperedOperationTx));
  const tamperedOperationBefore = snapshot(tamperedOperationProject);
  const refusedTamperedOperation = attempt(
    ['install', '-p', tamperedOperationProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(tamperedOperationFailure.status !== 0 && refusedTamperedOperation.status !== 0
    && /not anchored by install state/.test(refusedTamperedOperation.stderr)
    && JSON.stringify(snapshot(tamperedOperationProject)) === JSON.stringify(tamperedOperationBefore),
  'install-state intent anchor rejects a forged transaction operation without mutation');

  const reorderedOperationProject = make('cl-reordered-operation-intent-');
  const reorderedOperationFailure = attempt(
    ['install', '-p', reorderedOperationProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const reorderedOperationTxPath = path.join(reorderedOperationProject, '.create-loop', 'transactions', 'opencode.json');
  const reorderedOperationTx = JSON.parse(fs.readFileSync(reorderedOperationTxPath, 'utf8'));
  reorderedOperationTx.operations.reverse();
  fs.writeFileSync(reorderedOperationTxPath, JSON.stringify(reorderedOperationTx));
  const reorderedOperationBefore = snapshot(reorderedOperationProject);
  const refusedReorderedOperation = attempt(
    ['install', '-p', reorderedOperationProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(reorderedOperationFailure.status !== 0 && refusedReorderedOperation.status !== 0
    && /not anchored by install state/.test(refusedReorderedOperation.stderr)
    && JSON.stringify(snapshot(reorderedOperationProject)) === JSON.stringify(reorderedOperationBefore),
  'install-state intent anchor binds operation order');

  const unanchoredProject = make('cl-unanchored-transaction-');
  const unanchoredFailure = attempt(
    ['install', '-p', unanchoredProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const unanchoredStatePath = path.join(unanchoredProject, '.create-loop', 'install-state.json');
  const unanchoredState = JSON.parse(fs.readFileSync(unanchoredStatePath, 'utf8'));
  delete unanchoredState.transactions.opencode;
  fs.writeFileSync(unanchoredStatePath, JSON.stringify(unanchoredState));
  const unanchoredBefore = snapshot(unanchoredProject);
  const refusedUnanchored = attempt(
    ['install', '-p', unanchoredProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(unanchoredFailure.status !== 0 && refusedUnanchored.status !== 0
    && /not anchored by install state/.test(refusedUnanchored.stderr)
    && JSON.stringify(snapshot(unanchoredProject)) === JSON.stringify(unanchoredBefore),
  'an unanchored transaction fails closed with zero recovery mutation');

  const preparedProject = make('cl-prepared-transaction-');
  const preparedFailure = attempt(
    ['install', '-p', preparedProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_TX_PREPARE: '1' }
  );
  const preparedRoot = path.join(preparedProject, '.create-loop', 'transactions');
  const preparedFiles = fs.readdirSync(preparedRoot).filter((name) => name.endsWith('.prepared.json'));
  const preparedTargetsBefore = snapshot(path.join(preparedProject, '.opencode'));
  run(['install', '-p', preparedProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(preparedFailure.status !== 0 && preparedFiles.length === 1
    && Object.keys(preparedTargetsBefore).length === 0
    && !fs.readdirSync(path.join(preparedProject, '.create-loop')).some((name) => name === 'transactions')
    && exists(path.join(preparedProject, '.opencode', 'command', 'loop-status.md')),
  'an unanchored prepared transaction is cleaned only before any destination mutation');

  const anchoredPreparedProject = make('cl-anchored-prepared-transaction-');
  const anchoredPreparedFailure = attempt(
    ['install', '-p', anchoredPreparedProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_TX_ANCHOR_WRITE: '1' }
  );
  run(['install', '-p', anchoredPreparedProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(anchoredPreparedFailure.status !== 0
    && exists(path.join(anchoredPreparedProject, '.opencode', 'command', 'loop-status.md'))
    && !JSON.parse(fs.readFileSync(path.join(anchoredPreparedProject, '.create-loop', 'install-state.json'), 'utf8')).transactions.opencode,
  'an anchored prepared transaction is promoted and recovered instead of being discarded');

  const planRaceProject = make('cl-plan-race-');
  const planRaceTarget = path.join(planRaceProject, '.opencode', 'command', 'loop-status.md');
  const refusedPlanRace = attempt(
    ['install', '-p', planRaceProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_MUTATE_DESTINATION_PHASE: 'after-plan',
      CREATE_LOOP_TEST_MUTATE_DESTINATION_PATH: planRaceTarget,
      CREATE_LOOP_TEST_MUTATE_DESTINATION_CONTENT: 'USER WON PLAN RACE\n' }
  );
  ok(refusedPlanRace.status !== 0 && /changed after planning/.test(refusedPlanRace.stderr)
    && fs.readFileSync(planRaceTarget, 'utf8') === 'USER WON PLAN RACE\n',
  'apply rejects a destination created after planning without overwriting it');

  const applyRaceProject = make('cl-apply-race-');
  const applyRaceTarget = path.join(applyRaceProject, '.opencode', 'command', 'loop-status.md');
  const refusedApplyRace = attempt(
    ['install', '-p', applyRaceProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_MUTATE_DESTINATION_PHASE: 'after-transaction-authorization',
      CREATE_LOOP_TEST_MUTATE_DESTINATION_PATH: applyRaceTarget,
      CREATE_LOOP_TEST_MUTATE_DESTINATION_CONTENT: 'USER WON APPLY RACE\n' }
  );
  ok(refusedApplyRace.status !== 0 && /changed after transaction authorization/.test(refusedApplyRace.stderr)
    && fs.readFileSync(applyRaceTarget, 'utf8') === 'USER WON APPLY RACE\n',
  'mutation-time reality check rejects a destination changed after transaction authorization');

  const recoveryRaceProject = make('cl-recovery-race-');
  const recoveryRaceFailure = attempt(
    ['install', '-p', recoveryRaceProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_TX_ANCHOR: '1' }
  );
  const recoveryRaceTarget = path.join(recoveryRaceProject, '.opencode', 'command', 'loop-status.md');
  const refusedRecoveryRace = attempt(
    ['install', '-p', recoveryRaceProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_MUTATE_DESTINATION_PHASE: 'after-recovery-validation',
      CREATE_LOOP_TEST_MUTATE_DESTINATION_PATH: recoveryRaceTarget,
      CREATE_LOOP_TEST_MUTATE_DESTINATION_CONTENT: 'USER WON RECOVERY RACE\n' }
  );
  ok(recoveryRaceFailure.status !== 0 && refusedRecoveryRace.status !== 0
    && /changed after recovery validation/.test(refusedRecoveryRace.stderr)
    && fs.readFileSync(recoveryRaceTarget, 'utf8') === 'USER WON RECOVERY RACE\n',
  'recovery rechecks reality immediately before applying a pending mutation');

  const injectedStateDeleteProject = make('cl-injected-state-delete-');
  const injectedStateDeleteFailure = attempt(['install', '-p', injectedStateDeleteProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const injectedStateDeleteTxPath = path.join(injectedStateDeleteProject, '.create-loop', 'transactions', 'opencode.json');
  const injectedStateDeleteTarget = path.join(injectedStateDeleteProject, '.opencode', 'command', 'user-private.md');
  fs.writeFileSync(injectedStateDeleteTarget, 'USER PRIVATE\n');
  const injectedStateDeleteTx = JSON.parse(fs.readFileSync(injectedStateDeleteTxPath, 'utf8'));
  injectedStateDeleteTx.preState.hosts.opencode = injectedStateDeleteTx.preState.hosts.opencode || injectedStateDeleteTx.state.hosts.opencode;
  injectedStateDeleteTx.preState.hosts.opencode.files[injectedStateDeleteTarget] = {
    hash: sha(injectedStateDeleteTarget), kind: 'command', ownership: 'owned',
  };
  injectedStateDeleteTx.preStateSha256 = stateDigest(injectedStateDeleteTx.preState);
  delete injectedStateDeleteTx.state.hosts.opencode.files[injectedStateDeleteTarget];
  injectedStateDeleteTx.operations.push({ action: 'delete', dst: injectedStateDeleteTarget, kind: 'command', hash: null, stage: null, beforeHash: sha(injectedStateDeleteTarget), forceAuthorized: false });
  fs.writeFileSync(injectedStateDeleteTxPath, JSON.stringify(injectedStateDeleteTx));
  const refusedInjectedStateDelete = attempt(['install', '-p', injectedStateDeleteProject, '--host', 'opencode', '--commands-only'], env);
  ok(injectedStateDeleteFailure.status !== 0 && refusedInjectedStateDelete.status !== 0
    && /prior-state digest mismatch|prior state no longer matches/.test(refusedInjectedStateDelete.stderr)
    && exists(injectedStateDeleteTarget) && exists(injectedStateDeleteTxPath), 'recovery rejects jointly forged ownership state and delete operations');

  const injectedPostStateProject = make('cl-injected-post-state-');
  const injectedPostStateFailure = attempt(['install', '-p', injectedPostStateProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const injectedPostStateTxPath = path.join(injectedPostStateProject, '.create-loop', 'transactions', 'opencode.json');
  const injectedPostStateTarget = path.join(injectedPostStateProject, '.opencode', 'command', 'user-private.md');
  fs.writeFileSync(injectedPostStateTarget, 'USER PRIVATE\n');
  const injectedPostStateTx = JSON.parse(fs.readFileSync(injectedPostStateTxPath, 'utf8'));
  injectedPostStateTx.state.hosts.opencode.files[injectedPostStateTarget] = {
    hash: sha(injectedPostStateTarget), kind: 'command', ownership: 'owned',
  };
  fs.writeFileSync(injectedPostStateTxPath, JSON.stringify(injectedPostStateTx));
  const refusedInjectedPostState = attempt(['install', '-p', injectedPostStateProject, '--host', 'opencode', '--commands-only'], env);
  ok(injectedPostStateFailure.status !== 0 && refusedInjectedPostState.status !== 0
    && /post-state digest mismatch|not anchored by install state/.test(refusedInjectedPostState.stderr)
    && exists(injectedPostStateTarget) && exists(injectedPostStateTxPath), 'recovery rejects an unauthorized owned post-state injection without a matching operation');

  const adoptedRecoveryProject = make('cl-adopted-recovery-');
  const adoptedRecoveryTarget = path.join(adoptedRecoveryProject, '.opencode', 'command', 'loop-status.md');
  fs.mkdirSync(path.dirname(adoptedRecoveryTarget), { recursive: true });
  fs.copyFileSync(path.join(PKG_ROOT, '.opencode', 'command', 'loop-status.md'), adoptedRecoveryTarget);
  const adoptedRecoveryFailure = attempt(['install', '-p', adoptedRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const adoptedRecoveryTx = path.join(adoptedRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  run(['install', '-p', adoptedRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const adoptedRecoveryState = JSON.parse(fs.readFileSync(path.join(adoptedRecoveryProject, '.create-loop', 'install-state.json'), 'utf8'));
  ok(adoptedRecoveryFailure.status !== 0 && !exists(adoptedRecoveryTx)
    && adoptedRecoveryState.hosts.opencode.files[adoptedRecoveryTarget].ownership === 'adopted', 'recovery accepts a reality-checked adopted no-op delta after another write crashes');

  const conservativeCommitProject = make('cl-conservative-commit-crash-');
  const conservativeCommitTarget = path.join(conservativeCommitProject, '.opencode', 'command', 'loop-status.md');
  fs.mkdirSync(path.dirname(conservativeCommitTarget), { recursive: true });
  fs.copyFileSync(path.join(PKG_ROOT, '.opencode', 'command', 'loop-status.md'), conservativeCommitTarget);
  const conservativeCommitFailure = attempt(
    ['install', '-p', conservativeCommitProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const conservativeCommitTx = path.join(conservativeCommitProject, '.create-loop', 'transactions', 'opencode.json');
  const conservativeCommitTxBefore = fs.readFileSync(conservativeCommitTx);
  const conservativeCommitRecoveryFailure = attempt(
    ['install', '-p', conservativeCommitProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_RECOVERY_STATE: '1' }
  );
  const conservativeCommitStatePath = path.join(conservativeCommitProject, '.create-loop', 'install-state.json');
  const conservativeCommitTxAfter = fs.readFileSync(conservativeCommitTx);
  const conservativeCommitState = JSON.parse(fs.readFileSync(conservativeCommitStatePath, 'utf8'));
  const conservativeCommitTargetHash = sha(conservativeCommitTarget);
  run(['install', '-p', conservativeCommitProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const conservativeCommitFinal = JSON.parse(fs.readFileSync(conservativeCommitStatePath, 'utf8'));
  ok(conservativeCommitFailure.status !== 0 && conservativeCommitRecoveryFailure.status !== 0
    && conservativeCommitTxAfter.equals(conservativeCommitTxBefore)
    && !exists(conservativeCommitTx)
    && conservativeCommitState.hosts.opencode.files[conservativeCommitTarget].ownership === 'adopted'
    && conservativeCommitFinal.hosts.opencode.files[conservativeCommitTarget].ownership === 'adopted'
    && sha(conservativeCommitTarget) === conservativeCommitTargetHash,
  'recovery keeps transaction intent immutable and preserves adopted ownership across a committed-state crash');

  const committedStateTamperProject = make('cl-committed-state-tamper-');
  const committedStateTamperFailure = attempt(
    ['install', '-p', committedStateTamperProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' }
  );
  const committedStateTamperTx = path.join(
    committedStateTamperProject, '.create-loop', 'transactions', 'opencode.json'
  );
  const committedStateTamperPath = path.join(committedStateTamperProject, '.create-loop', 'install-state.json');
  const committedStateTamperState = JSON.parse(fs.readFileSync(committedStateTamperPath, 'utf8'));
  const committedStateTamperTarget = path.join(
    committedStateTamperProject, '.opencode', 'command', 'loop-status.md'
  );
  committedStateTamperState.hosts.opencode.files[committedStateTamperTarget].ownership = 'legacy-unknown';
  fs.writeFileSync(committedStateTamperPath, JSON.stringify(committedStateTamperState));
  const committedStateTamperBefore = snapshot(committedStateTamperProject);
  const refusedCommittedStateTamper = attempt(
    ['install', '-p', committedStateTamperProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(committedStateTamperFailure.status !== 0 && refusedCommittedStateTamper.status !== 0
    && /state does not match its authorized projection/.test(refusedCommittedStateTamper.stderr)
    && exists(committedStateTamperTx)
    && JSON.stringify(snapshot(committedStateTamperProject)) === JSON.stringify(committedStateTamperBefore),
  'committed recovery rejects ownership changes outside the conservative create downgrade');

  const forcedUntrackedProject = make('cl-force-untracked-recovery-');
  const forcedUntrackedTarget = path.join(forcedUntrackedProject, '.opencode', 'command', 'loop-new.md');
  fs.mkdirSync(path.dirname(forcedUntrackedTarget), { recursive: true });
  fs.writeFileSync(forcedUntrackedTarget, 'PRE-EXISTING DIFFERENT FILE\n');
  const forcedUntrackedFailure = attempt(
    ['install', '-p', forcedUntrackedProject, '--host', 'opencode', '--commands-only', '--force'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const forcedUntrackedTx = path.join(forcedUntrackedProject, '.create-loop', 'transactions', 'opencode.json');
  const refusedForcedUntrackedWithoutFlag = attempt(
    ['install', '-p', forcedUntrackedProject, '--host', 'opencode', '--commands-only'], env
  );
  run(['install', '-p', forcedUntrackedProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  const forcedUntrackedState = JSON.parse(fs.readFileSync(
    path.join(forcedUntrackedProject, '.create-loop', 'install-state.json'), 'utf8'
  ));
  run(['uninstall', '-p', forcedUntrackedProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  ok(forcedUntrackedFailure.status !== 0 && refusedForcedUntrackedWithoutFlag.status !== 0
    && /requires --force to recover/.test(refusedForcedUntrackedWithoutFlag.stderr)
    && !exists(forcedUntrackedTx)
    && forcedUntrackedState.hosts.opencode.files[forcedUntrackedTarget].ownership === 'adopted'
    && exists(forcedUntrackedTarget),
  'forced overwrite of an untracked file recovers without taking uninstall ownership');

  const forcedAdoptedProject = make('cl-force-adopted-recovery-');
  const forcedAdoptedTarget = path.join(forcedAdoptedProject, '.opencode', 'command', 'loop-new.md');
  fs.mkdirSync(path.dirname(forcedAdoptedTarget), { recursive: true });
  fs.copyFileSync(path.join(PKG_ROOT, '.opencode', 'command', 'loop-new.md'), forcedAdoptedTarget);
  run(['install', '-p', forcedAdoptedProject, '--host', 'opencode', '--commands-only', '-q'], env);
  fs.writeFileSync(forcedAdoptedTarget, 'USER EDITED ADOPTED FILE\n');
  const forcedAdoptedFailure = attempt(
    ['install', '-p', forcedAdoptedProject, '--host', 'opencode', '--commands-only', '--force'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const forcedAdoptedTx = path.join(forcedAdoptedProject, '.create-loop', 'transactions', 'opencode.json');
  const refusedForcedAdoptedWithoutFlag = attempt(
    ['install', '-p', forcedAdoptedProject, '--host', 'opencode', '--commands-only'], env
  );
  run(['install', '-p', forcedAdoptedProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  const forcedAdoptedState = JSON.parse(fs.readFileSync(
    path.join(forcedAdoptedProject, '.create-loop', 'install-state.json'), 'utf8'
  ));
  run(['uninstall', '-p', forcedAdoptedProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  ok(forcedAdoptedFailure.status !== 0 && refusedForcedAdoptedWithoutFlag.status !== 0
    && /requires --force to recover/.test(refusedForcedAdoptedWithoutFlag.stderr)
    && !exists(forcedAdoptedTx)
    && forcedAdoptedState.hosts.opencode.files[forcedAdoptedTarget].ownership === 'adopted'
    && exists(forcedAdoptedTarget),
  'forced overwrite of an adopted file preserves adopted ownership across recovery');

  const forgedAdoptedProject = make('cl-forged-adopted-');
  const forgedAdoptedTarget = path.join(forgedAdoptedProject, '.opencode', 'command', 'loop-status.md');
  fs.mkdirSync(path.dirname(forgedAdoptedTarget), { recursive: true });
  fs.copyFileSync(path.join(PKG_ROOT, '.opencode', 'command', 'loop-status.md'), forgedAdoptedTarget);
  const forgedAdoptedFailure = attempt(['install', '-p', forgedAdoptedProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const forgedAdoptedTxPath = path.join(forgedAdoptedProject, '.create-loop', 'transactions', 'opencode.json');
  const forgedAdoptedTx = JSON.parse(fs.readFileSync(forgedAdoptedTxPath, 'utf8'));
  forgedAdoptedTx.state.hosts.opencode.files[forgedAdoptedTarget].ownership = 'owned';
  fs.writeFileSync(forgedAdoptedTxPath, JSON.stringify(forgedAdoptedTx));
  const refusedForgedAdopted = attempt(['install', '-p', forgedAdoptedProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(forgedAdoptedFailure.status !== 0 && refusedForgedAdopted.status !== 0
    && /post-state digest mismatch|not anchored by install state/.test(refusedForgedAdopted.stderr)
    && exists(forgedAdoptedTarget) && exists(forgedAdoptedTxPath),
  'recovery rejects a forged post-state escalation from adopted to owned');

  const ownedWriteRecoveryProject = make('cl-owned-write-recovery-');
  const ownedWriteRecoveryTarget = path.join(ownedWriteRecoveryProject, '.opencode', 'command', 'loop-status.md');
  const ownedWriteRecoveryStatePath = path.join(ownedWriteRecoveryProject, '.create-loop', 'install-state.json');
  run(['install', '-p', ownedWriteRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  fs.writeFileSync(ownedWriteRecoveryTarget, 'OLD MANAGED\n');
  const ownedWriteRecoveryPrior = JSON.parse(fs.readFileSync(ownedWriteRecoveryStatePath, 'utf8'));
  ownedWriteRecoveryPrior.hosts.opencode.files[ownedWriteRecoveryTarget].hash = sha(ownedWriteRecoveryTarget);
  fs.writeFileSync(ownedWriteRecoveryStatePath, JSON.stringify(ownedWriteRecoveryPrior));
  const ownedWriteRecoveryFailure = attempt(['install', '-p', ownedWriteRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  run(['install', '-p', ownedWriteRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const ownedWriteRecoveryState = JSON.parse(fs.readFileSync(ownedWriteRecoveryStatePath, 'utf8'));
  run(['uninstall', '-p', ownedWriteRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(ownedWriteRecoveryFailure.status !== 0
    && ownedWriteRecoveryState.hosts.opencode.files[ownedWriteRecoveryTarget].ownership === 'owned'
    && !exists(ownedWriteRecoveryTarget), 'recovery preserves owned authority for a prior tracked write');

  const forceWriteProject = make('cl-force-write-recovery-');
  const forceWriteTarget = path.join(forceWriteProject, '.opencode', 'command', 'loop-status.md');
  run(['install', '-p', forceWriteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  fs.writeFileSync(forceWriteTarget, 'USER EDIT FOR FORCE WRITE\n');
  const forceWriteFailure = attempt(
    ['install', '-p', forceWriteProject, '--host', 'opencode', '--commands-only', '--force'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const forceWriteTxPath = path.join(forceWriteProject, '.create-loop', 'transactions', 'opencode.json');
  const forceWriteTx = JSON.parse(fs.readFileSync(forceWriteTxPath, 'utf8'));
  const refusedForceWriteWithoutFlag = attempt(['install', '-p', forceWriteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  run(['install', '-p', forceWriteProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  ok(forceWriteFailure.status !== 0 && refusedForceWriteWithoutFlag.status !== 0
    && /requires --force to recover/.test(refusedForceWriteWithoutFlag.stderr)
    && forceWriteTx.operations.some((op) => op.forceAuthorized)
    && !exists(forceWriteTxPath) && !/USER EDIT FOR FORCE WRITE/.test(fs.readFileSync(forceWriteTarget, 'utf8')),
  'force overwrite authorization survives a crash and recovers the exact owned write');

  const forceDeleteProject = make('cl-force-delete-recovery-');
  const forceDeleteTarget = path.join(forceDeleteProject, '.opencode', 'command', 'loop-status.md');
  run(['install', '-p', forceDeleteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  fs.writeFileSync(forceDeleteTarget, 'USER EDIT FOR FORCE DELETE\n');
  const forceDeleteFailure = attempt(
    ['uninstall', '-p', forceDeleteProject, '--host', 'opencode', '--commands-only', '--force'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const forceDeleteTxPath = path.join(forceDeleteProject, '.create-loop', 'transactions', 'opencode.json');
  const forceDeleteTx = JSON.parse(fs.readFileSync(forceDeleteTxPath, 'utf8'));
  const refusedForceDeleteWithoutFlag = attempt(['uninstall', '-p', forceDeleteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  run(['uninstall', '-p', forceDeleteProject, '--host', 'opencode', '--commands-only', '--force', '-q'], env);
  ok(forceDeleteFailure.status !== 0 && refusedForceDeleteWithoutFlag.status !== 0
    && /requires --force to recover/.test(refusedForceDeleteWithoutFlag.stderr)
    && forceDeleteTx.operations.some((op) => op.forceAuthorized)
    && !exists(forceDeleteTxPath) && !exists(forceDeleteTarget),
  'force delete authorization survives a crash and recovers the exact owned delete');

  const missingRecoveryProject = make('cl-missing-recovery-');
  run(['install', '-p', missingRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const missingRecoveryTarget = path.join(missingRecoveryProject, '.opencode', 'command', 'loop-new.md');
  fs.unlinkSync(missingRecoveryTarget);
  const missingRecoveryFailure = attempt(['uninstall', '-p', missingRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const missingRecoveryTx = path.join(missingRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  run(['uninstall', '-p', missingRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(missingRecoveryFailure.status !== 0 && !exists(missingRecoveryTx)
    && !exists(missingRecoveryTarget) && !exists(path.join(missingRecoveryProject, '.create-loop', 'install-state.json')), 'recovery accepts removal of an already missing tracked file after another delete crashes');

  const forgedCanonicalProject = make('cl-forged-canonical-');
  const forgedCanonicalTarget = path.join(forgedCanonicalProject, '.opencode', 'command', 'loop-status.md');
  fs.mkdirSync(path.dirname(forgedCanonicalTarget), { recursive: true });
  fs.writeFileSync(forgedCanonicalTarget, 'USER CANONICAL CONTENT\n');
  const forgedCanonicalFailure = attempt(['install', '-p', forgedCanonicalProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const forgedCanonicalTxPath = path.join(forgedCanonicalProject, '.create-loop', 'transactions', 'opencode.json');
  const forgedCanonicalTx = JSON.parse(fs.readFileSync(forgedCanonicalTxPath, 'utf8'));
  const forgedCanonicalStage = path.join(forgedCanonicalTx.stageDir, `${forgedCanonicalTx.operations.length}.stage`);
  fs.copyFileSync(path.join(PKG_ROOT, '.opencode', 'command', 'loop-status.md'), forgedCanonicalStage);
  forgedCanonicalTx.state.hosts.opencode.files[forgedCanonicalTarget] = {
    hash: sha(forgedCanonicalStage), kind: 'command', ownership: 'owned',
  };
  forgedCanonicalTx.operations.push({
    action: 'write', dst: forgedCanonicalTarget, kind: 'command', hash: sha(forgedCanonicalStage),
    stage: forgedCanonicalStage, beforeHash: sha(forgedCanonicalTarget), forceAuthorized: false,
  });
  fs.writeFileSync(forgedCanonicalTxPath, JSON.stringify(forgedCanonicalTx));
  const refusedForgedCanonical = attempt(['install', '-p', forgedCanonicalProject, '--host', 'opencode', '--commands-only'], env);
  ok(forgedCanonicalFailure.status !== 0 && refusedForgedCanonical.status !== 0
    && /post-state digest mismatch|not anchored by install state/.test(refusedForgedCanonical.stderr)
    && fs.readFileSync(forgedCanonicalTarget, 'utf8') === 'USER CANONICAL CONTENT\n'
    && exists(forgedCanonicalTxPath), 'recovery rejects a forged same-kind canonical write without prior owned authority');

  const forgedEditedDeleteProject = make('cl-forged-edited-delete-');
  run(['install', '-p', forgedEditedDeleteProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const forgedEditedDeleteTarget = path.join(forgedEditedDeleteProject, '.opencode', 'command', 'loop-status.md');
  fs.writeFileSync(forgedEditedDeleteTarget, 'USER EDIT PRESERVED\n');
  const forgedEditedDeleteFailure = attempt(['uninstall', '-p', forgedEditedDeleteProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const forgedEditedDeleteTxPath = path.join(forgedEditedDeleteProject, '.create-loop', 'transactions', 'opencode.json');
  const forgedEditedDeleteTx = JSON.parse(fs.readFileSync(forgedEditedDeleteTxPath, 'utf8'));
  forgedEditedDeleteTx.state.hosts.opencode.files = Object.fromEntries(
    Object.entries(forgedEditedDeleteTx.state.hosts.opencode.files).filter(([file]) => file !== forgedEditedDeleteTarget)
  );
  forgedEditedDeleteTx.operations.push({
    action: 'delete', dst: forgedEditedDeleteTarget, kind: 'command', hash: null,
    stage: null, beforeHash: sha(forgedEditedDeleteTarget), forceAuthorized: false,
  });
  fs.writeFileSync(forgedEditedDeleteTxPath, JSON.stringify(forgedEditedDeleteTx));
  const refusedForgedEditedDelete = attempt(['uninstall', '-p', forgedEditedDeleteProject, '--host', 'opencode', '--commands-only'], env);
  ok(forgedEditedDeleteFailure.status !== 0 && refusedForgedEditedDelete.status !== 0
    && /post-state digest mismatch|not anchored by install state/.test(refusedForgedEditedDelete.stderr)
    && fs.readFileSync(forgedEditedDeleteTarget, 'utf8') === 'USER EDIT PRESERVED\n'
    && exists(forgedEditedDeleteTxPath), 'recovery rejects a forged delete of a user-edited owned file');

  if (process.platform === 'win32') {
    const casingRecoveryProject = make('cl-casing-recovery-');
    const casingRecoveryFailure = attempt(['install', '-p', casingRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
    const casingRecoveryTx = path.join(casingRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
    const alternateCasing = casingRecoveryProject.toUpperCase();
    run(['install', '-p', alternateCasing, '--host', 'opencode', '--commands-only', '-q'], env);
    ok(casingRecoveryFailure.status !== 0 && !exists(casingRecoveryTx)
      && exists(path.join(casingRecoveryProject, '.opencode', 'command', 'loop-status.md')), 'Windows-equivalent project casing recovers a pending transaction');
  }

  const injectedKindProject = make('cl-injected-kind-');
  const injectedKindFailure = attempt(['install', '-p', injectedKindProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const injectedKindTxPath = path.join(injectedKindProject, '.create-loop', 'transactions', 'opencode.json');
  const injectedKindTarget = path.join(injectedKindProject, '.agents', 'skills', 'create-loop', 'SKILL.md');
  fs.mkdirSync(path.dirname(injectedKindTarget), { recursive: true });
  fs.writeFileSync(injectedKindTarget, 'USER SKILL\n');
  const injectedKindTx = JSON.parse(fs.readFileSync(injectedKindTxPath, 'utf8'));
  const injectedKindStage = path.join(injectedKindTx.stageDir, `${injectedKindTx.operations.length}.stage`);
  fs.writeFileSync(injectedKindStage, fs.readFileSync(path.join(PKG_ROOT, 'skills', 'create-loop', 'SKILL.md')));
  injectedKindTx.state.hosts.opencode.files[injectedKindTarget] = {
    hash: sha(injectedKindStage), kind: 'skill', ownership: 'owned',
  };
  injectedKindTx.operations.push({
    action: 'write', dst: injectedKindTarget, kind: 'skill', hash: sha(injectedKindStage),
    stage: injectedKindStage, beforeHash: sha(injectedKindTarget), forceAuthorized: false,
  });
  fs.writeFileSync(injectedKindTxPath, JSON.stringify(injectedKindTx));
  const refusedInjectedKind = attempt(['install', '-p', injectedKindProject, '--host', 'opencode', '--commands-only'], env);
  ok(injectedKindFailure.status !== 0 && refusedInjectedKind.status !== 0
    && /post-state digest mismatch|not anchored by install state/.test(refusedInjectedKind.stderr)
    && fs.readFileSync(injectedKindTarget, 'utf8') === 'USER SKILL\n'
    && exists(injectedKindTxPath), 'commands-only recovery rejects an injected canonical skill write');

  const staleReplayProject = make('cl-stale-replay-');
  const staleReplayFailure = attempt(['install', '-p', staleReplayProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const staleReplayTxPath = path.join(staleReplayProject, '.create-loop', 'transactions', 'opencode.json');
  const staleReplayTx = JSON.parse(fs.readFileSync(staleReplayTxPath, 'utf8'));
  const staleReplayStages = staleReplayTx.operations
    .filter((op) => op.stage)
    .map((op) => ({ name: path.basename(op.stage), bytes: fs.readFileSync(op.stage) }));
  run(['install', '-p', staleReplayProject, '--host', 'opencode', '--commands-only', '-q'], env);
  run(['install', '-p', staleReplayProject, '--host', 'claude', '--commands-only', '-q'], env);
  fs.mkdirSync(staleReplayTx.stageDir, { recursive: true });
  for (const item of staleReplayStages) fs.writeFileSync(path.join(staleReplayTx.stageDir, item.name), item.bytes);
  fs.writeFileSync(staleReplayTxPath, JSON.stringify(staleReplayTx));
  const staleReplayClaude = path.join(staleReplayProject, '.claude', 'commands', 'loop-status.md');
  const refusedStaleReplay = attempt(['install', '-p', staleReplayProject, '--host', 'opencode', '--commands-only'], env);
  const staleReplayState = JSON.parse(fs.readFileSync(path.join(staleReplayProject, '.create-loop', 'install-state.json'), 'utf8'));
  ok(staleReplayFailure.status !== 0 && refusedStaleReplay.status !== 0
    && /not anchored by install state|prior state no longer matches current install state/.test(refusedStaleReplay.stderr)
    && exists(staleReplayClaude) && staleReplayState.hosts.claude, 'stale transaction replay cannot erase newer cross-host ownership');

  const committedRecoveryProject = make('cl-committed-recovery-');
  const committedRecoveryFailure = attempt(['install', '-p', committedRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' });
  const committedRecoveryTx = path.join(committedRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  const committedRecoveryState = path.join(committedRecoveryProject, '.create-loop', 'install-state.json');
  run(['install', '-p', committedRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const committedRecoveryStateValue = JSON.parse(fs.readFileSync(committedRecoveryState, 'utf8'));
  ok(committedRecoveryFailure.status !== 0 && !exists(committedRecoveryTx)
    && committedRecoveryStateValue.hosts.opencode
    && !committedRecoveryStateValue.transactions.opencode
    && exists(path.join(committedRecoveryProject, '.opencode', 'command', 'loop-status.md')), 'recovery recognizes an already committed transaction and only cleans it up');

  const committedReceiptProject = make('cl-committed-receipt-only-');
  const committedReceiptFailure = attempt(
    ['install', '-p', committedReceiptProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_TX_CLEANUP: '1' }
  );
  const committedReceiptStatePath = path.join(committedReceiptProject, '.create-loop', 'install-state.json');
  const committedReceiptTarget = path.join(committedReceiptProject, '.opencode', 'command', 'loop-status.md');
  const committedReceiptTargetHash = sha(committedReceiptTarget);
  const committedReceiptStateBefore = JSON.parse(fs.readFileSync(committedReceiptStatePath, 'utf8'));
  const committedReceiptResume = attempt(
    ['uninstall', '-p', committedReceiptProject, '--host', 'opencode', '--skill-only'], env
  );
  const committedReceiptStateAfter = JSON.parse(fs.readFileSync(committedReceiptStatePath, 'utf8'));
  ok(committedReceiptFailure.status !== 0 && committedReceiptResume.status === 0
    && committedReceiptStateBefore.transactions.opencode.phase === 'committed'
    && !committedReceiptStateAfter.transactions.opencode
    && sha(committedReceiptTarget) === committedReceiptTargetHash,
  'a committed receipt without its transaction clears safely without mutating destinations');

  const dryCommittedReceiptProject = make('cl-dry-committed-receipt-');
  const dryCommittedReceiptFailure = attempt(
    ['install', '-p', dryCommittedReceiptProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_TX_CLEANUP: '1' }
  );
  const dryCommittedReceiptBefore = snapshot(dryCommittedReceiptProject);
  const refusedDryCommittedReceipt = attempt(
    ['uninstall', '-p', dryCommittedReceiptProject, '--host', 'opencode', '--skill-only', '--dry-run'], env
  );
  ok(dryCommittedReceiptFailure.status !== 0 && refusedDryCommittedReceipt.status !== 0
    && /cleanup is pending; dry-run made no changes/.test(refusedDryCommittedReceipt.stderr)
    && JSON.stringify(snapshot(dryCommittedReceiptProject)) === JSON.stringify(dryCommittedReceiptBefore),
  'dry-run reports a committed receipt without clearing it or mutating destinations');

  const pendingReceiptProject = make('cl-pending-receipt-only-');
  const pendingReceiptFailure = attempt(
    ['install', '-p', pendingReceiptProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const pendingReceiptTx = path.join(pendingReceiptProject, '.create-loop', 'transactions', 'opencode.json');
  fs.unlinkSync(pendingReceiptTx);
  const pendingReceiptBefore = snapshot(pendingReceiptProject);
  const refusedPendingReceipt = attempt(
    ['uninstall', '-p', pendingReceiptProject, '--host', 'opencode', '--skill-only'], env
  );
  ok(pendingReceiptFailure.status !== 0 && refusedPendingReceipt.status !== 0
    && /anchor has no transaction file/.test(refusedPendingReceipt.stderr)
    && JSON.stringify(snapshot(pendingReceiptProject)) === JSON.stringify(pendingReceiptBefore),
  'a pending receipt without its transaction fails closed for uninstall with zero mutation');

  const deleteRecoveryProject = make('cl-delete-recovery-');
  run(['install', '-p', deleteRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const deleteRecoveryFailure = attempt(['uninstall', '-p', deleteRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const deleteRecoveryTx = path.join(deleteRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  run(['uninstall', '-p', deleteRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(deleteRecoveryFailure.status !== 0 && !exists(deleteRecoveryTx)
    && !exists(path.join(deleteRecoveryProject, '.opencode', 'command', 'loop-status.md')), 'recovery completes an authorized delete of previously owned files');

  const dryRecoveryProject = make('cl-dry-recovery-');
  const dryRecoveryFailure = attempt(['install', '-p', dryRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const dryRecoveryTx = path.join(dryRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  const beforeDryRecovery = snapshot(dryRecoveryProject);
  const refusedDryRecovery = attempt(['install', '-p', dryRecoveryProject, '--host', 'claude', '--commands-only', '--dry-run'], env);
  ok(dryRecoveryFailure.status !== 0 && refusedDryRecovery.status !== 0
    && /dry-run made no changes/.test(refusedDryRecovery.stderr) && exists(dryRecoveryTx)
    && JSON.stringify(snapshot(dryRecoveryProject)) === JSON.stringify(beforeDryRecovery), 'dry-run validates but never recovers a pending transaction');

  const crossHostRecoveryProject = make('cl-cross-host-recovery-');
  const crossHostFailure = attempt(['install', '-p', crossHostRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const crossHostTx = path.join(crossHostRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  const crossHostOpenCommand = path.join(crossHostRecoveryProject, '.opencode', 'command', 'loop-status.md');
  const crossHostClaudeCommand = path.join(crossHostRecoveryProject, '.claude', 'commands', 'loop-status.md');
  ok(crossHostFailure.status !== 0 && exists(crossHostTx), 'cross-host recovery fixture leaves an OpenCode transaction');
  run(['install', '-p', crossHostRecoveryProject, '--host', 'claude', '--commands-only', '-q'], env);
  const crossHostState = JSON.parse(fs.readFileSync(path.join(crossHostRecoveryProject, '.create-loop', 'install-state.json'), 'utf8'));
  ok(exists(crossHostOpenCommand) && exists(crossHostClaudeCommand) && !exists(crossHostTx)
    && crossHostState.hosts.opencode.files[crossHostOpenCommand]
    && crossHostState.hosts.claude.files[crossHostClaudeCommand], 'install recovers every host transaction before preserving cross-host ownership');
  run(['uninstall', '-p', crossHostRecoveryProject, '--host', 'opencode,claude', '--commands-only', '-q'], env);
  ok(!exists(crossHostOpenCommand) && !exists(crossHostClaudeCommand), 'cross-host recovered ownership remains uninstallable');

  const concurrentProject = make('cl-concurrent-');
  const concurrentLock = path.join(concurrentProject, '.create-loop', 'install.lock');
  const firstConcurrent = spawn(process.execPath, cliArgs(['install', '-p', concurrentProject, '--host', 'opencode', '--commands-only', '-q']), {
    env: { ...env, CREATE_LOOP_TEST_HOLD_LOCK_MS: '750' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let firstConcurrentErr = '';
  const firstConcurrentDone = new Promise((resolve) => firstConcurrent.on('close', resolve));
  firstConcurrent.stdout.resume();
  firstConcurrent.stderr.on('data', (chunk) => { firstConcurrentErr += chunk; });
  ok(waitFor(concurrentLock), 'first concurrent installer acquires the state-root lock');
  const secondConcurrent = attempt(['install', '-p', concurrentProject, '--host', 'claude', '--commands-only', '-q'], env);
  const firstConcurrentExit = await firstConcurrentDone;
  const concurrentState = JSON.parse(fs.readFileSync(path.join(concurrentProject, '.create-loop', 'install-state.json'), 'utf8'));
  ok(firstConcurrentExit === 0 && !firstConcurrentErr && secondConcurrent.status !== 0
    && /lock is held by active pid/.test(secondConcurrent.stderr)
    && concurrentState.hosts.opencode && !concurrentState.hosts.claude, 'same-root concurrent installer fails closed instead of losing ownership');

  const staleLockProject = make('cl-stale-lock-');
  const staleLockDir = path.join(staleLockProject, '.create-loop');
  const staleLockPath = path.join(staleLockDir, 'install.lock');
  fs.mkdirSync(staleLockDir, { recursive: true });
  fs.writeFileSync(staleLockPath, JSON.stringify({
    version: 1,
    tool: 'create-loop',
    pid: 2147483647,
    token: 'a'.repeat(32),
    stateRoot: staleLockDir,
    createdAt: new Date().toISOString(),
  }));
  run(['install', '-p', staleLockProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(!exists(staleLockPath) && exists(path.join(staleLockProject, '.opencode', 'command', 'loop-new.md')), 'installer reclaims a valid lock only after proving its owner pid is dead');

  const dryStaleLockProject = make('cl-dry-stale-lock-');
  const dryStaleLockDir = path.join(dryStaleLockProject, '.create-loop');
  const dryStaleLockPath = path.join(dryStaleLockDir, 'install.lock');
  fs.mkdirSync(dryStaleLockDir, { recursive: true });
  fs.writeFileSync(dryStaleLockPath, JSON.stringify({
    version: 1,
    tool: 'create-loop',
    pid: 2147483647,
    token: 'b'.repeat(32),
    stateRoot: dryStaleLockDir,
    createdAt: new Date().toISOString(),
  }));
  const dryStaleLockBefore = snapshot(dryStaleLockProject);
  const refusedDryStaleLock = attempt(['install', '-p', dryStaleLockProject, '--host', 'opencode', '--commands-only', '--dry-run'], env);
  ok(refusedDryStaleLock.status !== 0 && /lock is stale; dry-run made no changes/.test(refusedDryStaleLock.stderr)
    && JSON.stringify(snapshot(dryStaleLockProject)) === JSON.stringify(dryStaleLockBefore), 'dry-run reports but never reclaims a stale lock');

  const corruptLockProject = make('cl-corrupt-lock-');
  const corruptLockDir = path.join(corruptLockProject, '.create-loop');
  const corruptLockPath = path.join(corruptLockDir, 'install.lock');
  fs.mkdirSync(corruptLockDir, { recursive: true });
  fs.writeFileSync(corruptLockPath, '{bad lock');
  const corruptLockBefore = snapshot(corruptLockProject);
  const refusedCorruptLock = attempt(['install', '-p', corruptLockProject, '--host', 'opencode', '--commands-only'], env);
  const refusedDryCorruptLock = attempt(['install', '-p', corruptLockProject, '--host', 'opencode', '--commands-only', '--dry-run'], env);
  ok(refusedCorruptLock.status !== 0 && refusedDryCorruptLock.status !== 0
    && /lock is corrupt/.test(refusedCorruptLock.stderr + refusedDryCorruptLock.stderr)
    && JSON.stringify(snapshot(corruptLockProject)) === JSON.stringify(corruptLockBefore), 'corrupt lock fails closed for real and dry-run installs without mutation');

  const exactStageProject = make('cl-exact-stage-');
  const exactStageFailure = attempt(['install', '-p', exactStageProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const exactStageTxPath = path.join(exactStageProject, '.create-loop', 'transactions', 'opencode.json');
  const exactStageTx = JSON.parse(fs.readFileSync(exactStageTxPath, 'utf8'));
  const stagedWrite = exactStageTx.operations.find((op) => op.action === 'write');
  const rogueStage = path.join(exactStageTx.stageDir, 'rogue.stage');
  fs.copyFileSync(stagedWrite.stage, rogueStage);
  stagedWrite.stage = rogueStage;
  fs.writeFileSync(exactStageTxPath, JSON.stringify(exactStageTx));
  const refusedExactStage = attempt(['install', '-p', exactStageProject, '--host', 'opencode', '--commands-only'], env);
  ok(exactStageFailure.status !== 0 && refusedExactStage.status !== 0
    && /not anchored by install state/.test(refusedExactStage.stderr) && exists(rogueStage), 'recovery binds every staged write to its exact transaction-owned filename');

  const committedStageEscapeProject = make('cl-committed-stage-escape-');
  const committedStageEscapeFailure = attempt(
    ['install', '-p', committedStageEscapeProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' }
  );
  const committedStageEscapeTxPath = path.join(
    committedStageEscapeProject, '.create-loop', 'transactions', 'opencode.json'
  );
  const committedStageEscapeStatePath = path.join(
    committedStageEscapeProject, '.create-loop', 'install-state.json'
  );
  const committedStageEscapeTx = JSON.parse(fs.readFileSync(committedStageEscapeTxPath, 'utf8'));
  const committedStageEscapeIndex = committedStageEscapeTx.operations.findIndex((op) => op.action === 'write');
  const committedStageEscapeRoot = make('cl-committed-stage-outside-');
  const committedStageEscapeMarker = path.join(committedStageEscapeRoot, `${committedStageEscapeIndex}.stage`);
  fs.writeFileSync(committedStageEscapeMarker, 'EXTERNAL MARKER\n');
  const committedStageEscapeHash = sha(committedStageEscapeMarker);
  committedStageEscapeTx.operations[committedStageEscapeIndex].stage = committedStageEscapeMarker;
  fs.writeFileSync(committedStageEscapeTxPath, JSON.stringify(committedStageEscapeTx));
  const committedStageEscapeState = JSON.parse(fs.readFileSync(committedStageEscapeStatePath, 'utf8'));
  committedStageEscapeState.transactions.opencode.intentSha256 = transactionIntentDigest(committedStageEscapeTx);
  fs.writeFileSync(committedStageEscapeStatePath, JSON.stringify(committedStageEscapeState));
  const committedStageEscapeBefore = snapshot(committedStageEscapeProject);
  const refusedCommittedStageEscape = attempt(
    ['install', '-p', committedStageEscapeProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(committedStageEscapeFailure.status !== 0 && refusedCommittedStageEscape.status !== 0
    && /invalid staging path/.test(refusedCommittedStageEscape.stderr)
    && exists(committedStageEscapeMarker) && sha(committedStageEscapeMarker) === committedStageEscapeHash
    && exists(committedStageEscapeTxPath)
    && JSON.stringify(snapshot(committedStageEscapeProject)) === JSON.stringify(committedStageEscapeBefore),
  'committed recovery rejects an anchored stage path outside its transaction directory without mutation');

  const committedStageControlProject = make('cl-committed-stage-control-');
  const committedStageControlFailure = attempt(
    ['install', '-p', committedStageControlProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' }
  );
  const committedStageControlTxPath = path.join(
    committedStageControlProject, '.create-loop', 'transactions', 'opencode.json'
  );
  const committedStageControlTarget = path.join(
    committedStageControlProject, '.opencode', 'command', 'loop-status.md'
  );
  const committedStageControlHash = sha(committedStageControlTarget);
  run(['install', '-p', committedStageControlProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(committedStageControlFailure.status !== 0 && !exists(committedStageControlTxPath)
    && sha(committedStageControlTarget) === committedStageControlHash,
  'committed recovery cleans canonical transaction-owned stage paths without mutating destinations');

  const extraStageProject = make('cl-extra-stage-');
  const extraStageFailure = attempt(['install', '-p', extraStageProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' });
  const extraStageTxPath = path.join(extraStageProject, '.create-loop', 'transactions', 'opencode.json');
  const extraStageTx = JSON.parse(fs.readFileSync(extraStageTxPath, 'utf8'));
  const extraStageEntry = path.join(extraStageTx.stageDir, 'untracked.stage');
  fs.writeFileSync(extraStageEntry, 'UNTRACKED STAGE\n');
  const refusedExtraStage = attempt(['install', '-p', extraStageProject, '--host', 'opencode', '--commands-only'], env);
  ok(extraStageFailure.status !== 0 && refusedExtraStage.status !== 0
    && /staging directory has unexpected entries/.test(refusedExtraStage.stderr)
    && exists(extraStageEntry) && exists(extraStageTxPath), 'recovery fails closed and preserves its pointer when staging has an extra entry');

  const partialCleanupProject = make('cl-partial-stage-cleanup-');
  const partialCleanupFailure = attempt(
    ['install', '-p', partialCleanupProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' }
  );
  const partialCleanupTxPath = path.join(partialCleanupProject, '.create-loop', 'transactions', 'opencode.json');
  const partialCleanupTx = JSON.parse(fs.readFileSync(partialCleanupTxPath, 'utf8'));
  const removedCommittedStage = partialCleanupTx.operations.find((op) => op.action === 'write').stage;
  fs.rmSync(removedCommittedStage);
  run(['install', '-p', partialCleanupProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(partialCleanupFailure.status !== 0 && !exists(partialCleanupTxPath)
    && exists(path.join(partialCleanupProject, '.opencode', 'command', 'loop-status.md')),
  'committed recovery tolerates a partially completed stage cleanup');

  const missingStageDirProject = make('cl-missing-stage-dir-cleanup-');
  const missingStageDirFailure = attempt(
    ['install', '-p', missingStageDirProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' }
  );
  const missingStageDirTxPath = path.join(missingStageDirProject, '.create-loop', 'transactions', 'opencode.json');
  const missingStageDirTx = JSON.parse(fs.readFileSync(missingStageDirTxPath, 'utf8'));
  fs.rmSync(missingStageDirTx.stageDir, { recursive: true, force: true });
  run(['install', '-p', missingStageDirProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(missingStageDirFailure.status !== 0 && !exists(missingStageDirTxPath)
    && exists(path.join(missingStageDirProject, '.opencode', 'command', 'loop-status.md')),
  'committed recovery tolerates a missing staging directory');

  const committedExternalRootProject = make('cl-committed-external-root-');
  const committedExternalRoot = seedSkillRoot(path.join(make('cl-committed-external-source-'), 'create-loop'));
  const committedExternalFailure = attempt(
    ['install', '-p', committedExternalRootProject, '--host', 'opencode', '--commands-only', '--skill-root', committedExternalRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_STATE: '1' }
  );
  const committedExternalTx = path.join(committedExternalRootProject, '.create-loop', 'transactions', 'opencode.json');
  fs.rmSync(committedExternalRoot, { recursive: true, force: true });
  rawRun(['uninstall', '-p', committedExternalRootProject, '--host', 'opencode', '--skill-only', '-q'], env);
  ok(committedExternalFailure.status !== 0 && !exists(committedExternalTx)
    && exists(path.join(committedExternalRootProject, '.opencode', 'command', 'loop-status.md')),
  'committed recovery cleans up without requiring its external Skill root to remain');

  const linkedStageProject = make('cl-linked-stage-');
  const linkedStageFailure = attempt(['install', '-p', linkedStageProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const linkedStageTxPath = path.join(linkedStageProject, '.create-loop', 'transactions', 'opencode.json');
  const linkedStageTx = JSON.parse(fs.readFileSync(linkedStageTxPath, 'utf8'));
  const outsideStage = make('cl-outside-stage-');
  fs.rmSync(outsideStage, { recursive: true, force: true });
  fs.renameSync(linkedStageTx.stageDir, outsideStage);
  let stageLinkCreated = false;
  try {
    fs.symlinkSync(outsideStage, linkedStageTx.stageDir, process.platform === 'win32' ? 'junction' : 'dir');
    stageLinkCreated = true;
  } catch (_) {}
  if (stageLinkCreated) {
    const outsideStageBefore = snapshot(outsideStage);
    const refusedLinkedStage = attempt(['install', '-p', linkedStageProject, '--host', 'claude', '--commands-only'], env);
    ok(linkedStageFailure.status !== 0 && refusedLinkedStage.status !== 0
      && /symlink|junction|reparse-point/.test(refusedLinkedStage.stderr)
      && JSON.stringify(snapshot(outsideStage)) === JSON.stringify(outsideStageBefore), 'recovery rejects redirected staging trees without deleting outside files');
  } else {
    console.log('  skip - transaction stage junction creation unavailable');
  }

  const tamperedRecoveryProject = make('cl-tampered-recovery-');
  const tampered = attempt(['install', '-p', tamperedRecoveryProject, '--host', 'opencode', '--commands-only'], { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' });
  const tamperedTx = path.join(tamperedRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  const tamperedTarget = path.join(tamperedRecoveryProject, '.opencode', 'command', 'loop-run.md');
  ok(tampered.status !== 0 && exists(tamperedTx), 'recovery tamper fixture leaves a pending transaction');
  fs.mkdirSync(path.dirname(tamperedTarget), { recursive: true });
  fs.writeFileSync(tamperedTarget, 'USER CREATED DURING INTERRUPTION\n');
  const refusedRecovery = attempt(['install', '-p', tamperedRecoveryProject, '--host', 'opencode', '--commands-only'], env);
  ok(refusedRecovery.status !== 0 && /changed after interruption; refusing overwrite/.test(refusedRecovery.stderr)
    && /USER CREATED/.test(fs.readFileSync(tamperedTarget, 'utf8')) && exists(tamperedTx), 'recovery refuses to overwrite a post-crash user file');

  const corruptTxProject = make('cl-corrupt-transaction-');
  const corruptTxState = path.join(corruptTxProject, '.create-loop', 'transactions');
  fs.mkdirSync(corruptTxState, { recursive: true });
  fs.writeFileSync(path.join(corruptTxState, 'opencode.json'), JSON.stringify({ version: 1, host: 'opencode', operations: [], state: { tool: 'create-loop', manifestVersion: 2, hosts: {} } }));
  const corruptTx = attempt(['install', '-p', corruptTxProject, '--host', 'opencode', '--commands-only'], env);
  ok(corruptTx.status !== 0 && /unsupported installer transaction version 1; expected 4/.test(corruptTx.stderr)
    && /manual recovery/.test(corruptTx.stderr)
    && exists(path.join(corruptTxState, 'opencode.json')), 'recovery gives an explicit manual-recovery message and preserves an old transaction');

  const v3Project = make('cl-v3-transaction-');
  const v3Failure = attempt(
    ['install', '-p', v3Project, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const v3TxPath = path.join(v3Project, '.create-loop', 'transactions', 'opencode.json');
  const v3Tx = JSON.parse(fs.readFileSync(v3TxPath, 'utf8'));
  v3Tx.version = 3;
  delete v3Tx.txId;
  delete v3Tx.postStateSha256;
  delete v3Tx.roots;
  fs.writeFileSync(v3TxPath, JSON.stringify(v3Tx));
  const v3Before = snapshot(v3Project);
  const refusedV3 = attempt(['install', '-p', v3Project, '--host', 'opencode', '--commands-only'], env);
  ok(v3Failure.status !== 0 && refusedV3.status !== 0
    && /unsupported installer transaction version 3; expected 4/.test(refusedV3.stderr)
    && JSON.stringify(snapshot(v3Project)) === JSON.stringify(v3Before),
  'legacy v3 pending transactions fail closed and remain preserved');

  const legacyProject = make('cl-legacy-');
  const legacyStateDir = path.join(legacyProject, '.create-loop');
  fs.mkdirSync(legacyStateDir, { recursive: true });
  const legacyBytes = Buffer.from(JSON.stringify({ manifestVersion: 1, tool: 'create-loop', scope: 'project', hosts: {} }, null, 2) + '\n');
  fs.writeFileSync(path.join(legacyStateDir, 'install-state.json'), legacyBytes);
  run(['install', '-p', legacyProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const legacyBackup = path.join(legacyStateDir, 'install-state.v1.backup.json');
  ok(exists(legacyBackup) && fs.readFileSync(legacyBackup).equals(legacyBytes), 'v1 state migration preserves a byte-for-byte backup');

  const staged = make('cl-staged-');
  run(['install', '-p', staged, '--host', 'opencode,claude', '-q'], env);
  const stagedOpen = fs.readFileSync(path.join(staged, '.opencode', 'command', 'loop-new.md'), 'utf8');
  const stagedClaude = fs.readFileSync(path.join(staged, '.claude', 'commands', 'loop-resume.md'), 'utf8');
  const stagedOpenRoot = fs.realpathSync(path.join(staged, '.agents', 'skills', 'create-loop')).replace(/\\/g, '/');
  const stagedClaudeRoot = fs.realpathSync(path.join(staged, '.claude', 'skills', 'create-loop')).replace(/\\/g, '/');
  ok(exists(path.join(staged, '.agents', 'skills', 'create-loop', 'SKILL.md'))
    && exists(path.join(staged, '.claude', 'skills', 'create-loop', 'SKILL.md')), 'staged smoke installs both host skill roots');
  ok(stagedOpen.includes(stagedOpenRoot) && stagedClaude.includes(stagedClaudeRoot)
    && !/[<]CREATE_LOOP_SKILL_ROOT[>]/.test(stagedOpen + stagedClaude), 'staged commands embed each installed host skill root');
  ok(exists(path.join(stagedOpenRoot, 'scripts', 'validate_loop_dir.py'))
    && exists(path.join(stagedClaudeRoot, 'scripts', 'check_loop_integrity.py')), 'staged command validator paths resolve to installed files');

  console.log('\ncommands-only Skill-root authority');
  DEFAULT_COMMAND_SKILL_ROOT = null;
  const noSkillProject = make('cl-no-skill-');
  const noSkill = attempt(['install', '-p', noSkillProject, '--host', 'opencode', '--commands-only'], env);
  ok(noSkill.status !== 0 && /could not find a valid create-loop Skill root/.test(noSkill.stderr)
    && /--skill-root <dir>/.test(noSkill.stderr) && fs.readdirSync(noSkillProject).length === 0,
  'commands-only rejects zero valid Skill roots without writing');

  const discoveredOpenProject = make('cl-discover-open-');
  const discoveredOpenRoot = seedSkillRoot(path.join(discoveredOpenProject, '.agents', 'skills', 'create-loop'));
  run(['install', '-p', discoveredOpenProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const discoveredOpenCommand = fs.readFileSync(path.join(discoveredOpenProject, '.opencode', 'command', 'loop-run.md'), 'utf8');
  ok(discoveredOpenCommand.includes(fs.realpathSync(discoveredOpenRoot).replace(/\\/g, '/')),
    'project OpenCode commands-only discovers the shared .agents Skill root');

  const ignoredClaudeProject = make('cl-ignore-claude-');
  const ignoredSharedRoot = seedSkillRoot(path.join(ignoredClaudeProject, '.agents', 'skills', 'create-loop'));
  seedSkillRoot(path.join(ignoredClaudeProject, '.claude', 'skills', 'create-loop'));
  run(['install', '-p', ignoredClaudeProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const ignoredClaudeCommand = fs.readFileSync(path.join(ignoredClaudeProject, '.opencode', 'command', 'loop-new.md'), 'utf8');
  ok(ignoredClaudeCommand.includes(fs.realpathSync(ignoredSharedRoot).replace(/\\/g, '/')),
    'OpenCode discovery ignores an unrelated Claude-native Skill copy');

  const discoveredClaudeProject = make('cl-discover-claude-');
  const discoveredClaudeRoot = seedSkillRoot(path.join(discoveredClaudeProject, '.claude', 'skills', 'create-loop'));
  run(['install', '-p', discoveredClaudeProject, '--host', 'claude', '--commands-only', '-q'], env);
  const discoveredClaudeCommand = fs.readFileSync(path.join(discoveredClaudeProject, '.claude', 'commands', 'loop-resume.md'), 'utf8');
  ok(discoveredClaudeCommand.includes(fs.realpathSync(discoveredClaudeRoot).replace(/\\/g, '/')),
    'project Claude commands-only discovers its native Skill root');

  const ambiguousProject = make('cl-ambiguous-skill-');
  const ambiguousShared = seedSkillRoot(path.join(ambiguousProject, '.agents', 'skills', 'create-loop'));
  const ambiguousClaude = seedSkillRoot(path.join(ambiguousProject, '.claude', 'skills', 'create-loop'));
  const ambiguous = attempt(['install', '-p', ambiguousProject, '--host', 'claude', '--commands-only'], env);
  ok(ambiguous.status !== 0 && /found multiple create-loop Skill roots/.test(ambiguous.stderr)
    && ambiguous.stderr.includes(fs.realpathSync(ambiguousShared)) && ambiguous.stderr.includes(fs.realpathSync(ambiguousClaude)),
  'Claude commands-only rejects multiple distinct valid roots');

  const explicitProject = make('cl-explicit-skill-');
  const explicitRoot = seedSkillRoot(path.join(make('cl-explicit root with spaces-'), 'create-loop'));
  run(['install', '-p', explicitProject, '--host', 'opencode,claude', '--commands-only', '--skill-root', explicitRoot, '-q'], env);
  const explicitDisplay = fs.realpathSync(explicitRoot).replace(/\\/g, '/');
  const explicitOpen = fs.readFileSync(path.join(explicitProject, '.opencode', 'command', 'loop-run.md'), 'utf8');
  const explicitClaude = fs.readFileSync(path.join(explicitProject, '.claude', 'commands', 'loop-resume.md'), 'utf8');
  ok(explicitOpen.includes(`python "${explicitDisplay}/scripts/validate_loop_dir.py"`)
    && explicitClaude.includes(`python3 "${explicitDisplay}/scripts/check_loop_integrity.py"`),
  'explicit spaced Skill root is authoritative for both hosts and remains quoted');

  const brokenRoot = seedSkillRoot(path.join(make('cl-broken-skill-'), 'create-loop'));
  fs.rmSync(path.join(brokenRoot, 'scripts', 'validate_loop_dir.py'));
  const brokenProject = make('cl-broken-project-');
  const broken = attempt(['install', '-p', brokenProject, '--host', 'opencode', '--commands-only', '--skill-root', brokenRoot], env);
  ok(broken.status !== 0 && /missing a regular contained command dependency: scripts\/validate_loop_dir\.py/.test(broken.stderr)
    && fs.readdirSync(brokenProject).length === 0, 'commands-only rejects a Skill missing a referenced script');

  const brokenReferenceRoot = seedSkillRoot(path.join(make('cl-broken-reference-'), 'create-loop'));
  fs.rmSync(path.join(brokenReferenceRoot, 'references', 'protocol_v2.md'));
  const brokenReferenceProject = make('cl-broken-reference-project-');
  const brokenReference = attempt(
    ['install', '-p', brokenReferenceProject, '--host', 'opencode', '--commands-only', '--skill-root', brokenReferenceRoot], env
  );
  ok(brokenReference.status !== 0
    && /missing a regular contained command dependency: references\/protocol_v2\.md/.test(brokenReference.stderr)
    && fs.readdirSync(brokenReferenceProject).length === 0,
  'commands-only rejects a Skill missing a referenced non-script dependency');

  for (const explicit of [false, true]) {
    const wrongNameProject = make(`cl-wrong-skill-name-${explicit ? 'explicit' : 'discovered'}-`);
    const wrongNameRoot = seedSkillRoot(path.join(wrongNameProject, '.agents', 'skills', 'create-loop'));
    const wrongSkillFile = path.join(wrongNameRoot, 'SKILL.md');
    fs.writeFileSync(wrongSkillFile, fs.readFileSync(wrongSkillFile, 'utf8').replace('name: create-loop', 'name: not-create-loop'));
    const wrongNameBefore = snapshot(wrongNameProject);
    const wrongNameArgs = ['install', '-p', wrongNameProject, '--host', 'opencode', '--commands-only'];
    if (explicit) wrongNameArgs.push('--skill-root', wrongNameRoot);
    const wrongName = attempt(wrongNameArgs, env);
    ok(wrongName.status !== 0 && /SKILL\.md must declare exactly one name: create-loop/.test(wrongName.stderr)
      && JSON.stringify(snapshot(wrongNameProject)) === JSON.stringify(wrongNameBefore),
    `commands-only rejects a ${explicit ? 'explicit' : 'discovered'} Skill with the wrong identity`);
  }

  for (const dangerousName of ['create-loop-$(touch injected)', 'create-loop-`touch injected`']) {
    const dangerousRoot = seedSkillRoot(path.join(make('cl-dangerous-parent-'), dangerousName));
    const dangerousProject = make('cl-dangerous-target-');
    const dangerousBefore = snapshot(dangerousProject);
    const dangerous = attempt(['install', '-p', dangerousProject, '--host', 'opencode', '--commands-only', '--skill-root', dangerousRoot], env);
    ok(dangerous.status !== 0 && /cannot be embedded safely/.test(dangerous.stderr)
      && JSON.stringify(snapshot(dangerousProject)) === JSON.stringify(dangerousBefore),
    `commands-only rejects shell-interpolated Skill root ${JSON.stringify(dangerousName)} before writing`);
  }

  const dangerousFullProject = make('cl-full-$(unsafe)-');
  const dangerousFullBefore = snapshot(dangerousFullProject);
  const dangerousFull = attempt(['install', '-p', dangerousFullProject, '--host', 'opencode'], env);
  ok(dangerousFull.status !== 0 && /cannot be embedded safely/.test(dangerousFull.stderr)
    && JSON.stringify(snapshot(dangerousFullProject)) === JSON.stringify(dangerousFullBefore),
  'full install rejects a shell-interpolated Skill destination before writing');

  let sameRootLinkCreated = false;
  const sameRootProject = make('cl-same-root-link-');
  const sameRootShared = seedSkillRoot(path.join(sameRootProject, '.agents', 'skills', 'create-loop'));
  const sameRootClaude = path.join(sameRootProject, '.claude', 'skills', 'create-loop');
  fs.mkdirSync(path.dirname(sameRootClaude), { recursive: true });
  try {
    fs.symlinkSync(sameRootShared, sameRootClaude, process.platform === 'win32' ? 'junction' : 'dir');
    sameRootLinkCreated = true;
  } catch (_) {}
  if (sameRootLinkCreated) {
    run(['install', '-p', sameRootProject, '--host', 'claude', '--commands-only', '-q'], env);
    ok(exists(path.join(sameRootProject, '.claude', 'commands', 'loop-status.md')),
      'discovery deduplicates candidates that resolve to the same real Skill root');
  } else {
    console.log('  skip - same-root discovery link unavailable');
  }

  const removedSkillProject = make('cl-removed-skill-');
  const removedSkillRoot = seedSkillRoot(path.join(removedSkillProject, '.agents', 'skills', 'create-loop'));
  run(['install', '-p', removedSkillProject, '--host', 'opencode', '--commands-only', '-q'], env);
  fs.rmSync(removedSkillRoot, { recursive: true, force: true });
  run(['uninstall', '-p', removedSkillProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(!exists(path.join(removedSkillProject, '.opencode', 'command', 'loop-status.md')),
    'commands-only uninstall does not require the selected Skill root to remain');

  const removedSkillRecoveryProject = make('cl-removed-skill-recovery-');
  const removedSkillRecoveryRoot = seedSkillRoot(path.join(removedSkillRecoveryProject, '.agents', 'skills', 'create-loop'));
  const removedSkillRecoveryCommand = path.join(removedSkillRecoveryProject, '.opencode', 'command', 'loop-status.md');
  run(['install', '-p', removedSkillRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  const removedSkillDeleteFailure = attempt(
    ['uninstall', '-p', removedSkillRecoveryProject, '--host', 'opencode', '--commands-only'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const removedSkillDeleteTx = path.join(removedSkillRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  fs.rmSync(removedSkillRecoveryRoot, { recursive: true, force: true });
  run(['uninstall', '-p', removedSkillRecoveryProject, '--host', 'opencode', '--commands-only', '-q'], env);
  ok(removedSkillDeleteFailure.status !== 0 && !exists(removedSkillDeleteTx)
    && !exists(removedSkillRecoveryCommand)
    && !exists(path.join(removedSkillRecoveryProject, '.create-loop', 'install-state.json')),
  'delete-only command transaction recovers and commits after its Skill root is removed');

  const removedWriteRootProject = make('cl-removed-write-root-recovery-');
  const removedWriteRoot = seedSkillRoot(path.join(make('cl-removed-write-root-source-'), 'create-loop'));
  const removedWriteRootFailure = attempt(
    ['install', '-p', removedWriteRootProject, '--host', 'opencode', '--commands-only', '--skill-root', removedWriteRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const removedWriteRootTx = path.join(removedWriteRootProject, '.create-loop', 'transactions', 'opencode.json');
  const removedWriteRootState = path.join(removedWriteRootProject, '.create-loop', 'install-state.json');
  const removedWriteRootBefore = snapshot(removedWriteRootProject);
  fs.rmSync(removedWriteRoot, { recursive: true, force: true });
  const refusedRemovedWriteRoot = attempt(
    ['install', '-p', removedWriteRootProject, '--host', 'opencode', '--commands-only'], env
  );
  ok(removedWriteRootFailure.status !== 0 && refusedRemovedWriteRoot.status !== 0
    && /transaction command Skill root not a directory/.test(refusedRemovedWriteRoot.stderr)
    && exists(removedWriteRootTx) && exists(removedWriteRootState)
    && JSON.stringify(snapshot(removedWriteRootProject)) === JSON.stringify(removedWriteRootBefore),
  'pending command writes refuse a missing Skill root without committing recovery');

  const removedWriteScriptProject = make('cl-removed-write-script-recovery-');
  const removedWriteScriptRoot = seedSkillRoot(path.join(make('cl-removed-write-script-source-'), 'create-loop'));
  const removedWriteScriptFailure = attempt(
    ['install', '-p', removedWriteScriptProject, '--host', 'opencode', '--commands-only', '--skill-root', removedWriteScriptRoot],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const removedWriteScriptTx = path.join(removedWriteScriptProject, '.create-loop', 'transactions', 'opencode.json');
  fs.rmSync(path.join(removedWriteScriptRoot, 'scripts', 'validate_loop_dir.py'));
  const removedWriteScriptBefore = snapshot(removedWriteScriptProject);
  const refusedRemovedWriteScript = attempt(
    ['install', '-p', removedWriteScriptProject, '--host', 'opencode', '--commands-only', '--skill-root', removedWriteScriptRoot], env
  );
  ok(removedWriteScriptFailure.status !== 0 && refusedRemovedWriteScript.status !== 0
    && /transaction command Skill root missing a regular contained command dependency/.test(refusedRemovedWriteScript.stderr)
    && exists(removedWriteScriptTx)
    && JSON.stringify(snapshot(removedWriteScriptProject)) === JSON.stringify(removedWriteScriptBefore),
  'pending command writes revalidate referenced scripts before recovery');

  const projectedRecoveryPackage = packageCli(make);
  const projectedRecoveryProject = make('cl-projected-root-recovery-');
  runCli(projectedRecoveryPackage.cli, ['install', '-p', projectedRecoveryProject, '--host', 'opencode', '-q'], env);
  fs.appendFileSync(path.join(projectedRecoveryPackage.root, 'skills', 'create-loop', 'AGENTS.md'), '\nprojected recovery change A\n');
  fs.appendFileSync(path.join(projectedRecoveryPackage.root, 'skills', 'create-loop', 'README.md'), '\nprojected recovery change B\n');
  fs.appendFileSync(path.join(projectedRecoveryPackage.root, 'command', 'loop-status.md'), '\nProjected recovery command change.\n');
  const projectedRecoveryFailure = attemptCli(
    projectedRecoveryPackage.cli, ['install', '-p', projectedRecoveryProject, '--host', 'opencode'],
    { ...env, CREATE_LOOP_TEST_FAIL_AFTER_OP: '1' }
  );
  const projectedRecoveryTx = path.join(projectedRecoveryProject, '.create-loop', 'transactions', 'opencode.json');
  fs.rmSync(path.join(projectedRecoveryProject, '.agents', 'skills', 'create-loop', 'scripts', 'validate_loop_dir.py'));
  const projectedRecoveryBefore = snapshot(projectedRecoveryProject);
  const refusedProjectedRecovery = attemptCli(
    projectedRecoveryPackage.cli, ['install', '-p', projectedRecoveryProject, '--host', 'opencode'], env
  );
  ok(projectedRecoveryFailure.status !== 0 && refusedProjectedRecovery.status !== 0
    && /missing a regular contained command dependency: scripts\/validate_loop_dir\.py/.test(refusedProjectedRecovery.stderr)
    && exists(projectedRecoveryTx)
    && JSON.stringify(snapshot(projectedRecoveryProject)) === JSON.stringify(projectedRecoveryBefore),
  'mixed recovery validates the projected Skill before applying any remaining writes');

  const fullMissingTarget = make('cl-full-missing-target-');
  run(['install', '-p', fullMissingTarget, '--host', 'opencode', '-q'], env);
  ok(exists(path.join(fullMissingTarget, '.agents', 'skills', 'create-loop', 'SKILL.md'))
    && exists(path.join(fullMissingTarget, '.opencode', 'command', 'loop-new.md')),
  'full install bypasses commands-only discovery before creating its target Skill');

  const globalDiscoveryHome = make('cl-global-discovery-home-');
  const globalDiscoveryEnv = envFor(globalDiscoveryHome);
  const globalDiscoveryRoot = seedSkillRoot(path.join(globalDiscoveryHome, '.agents', 'skills', 'create-loop'));
  run(['install', '-g', '--host', 'opencode,claude', '--commands-only', '-q'], globalDiscoveryEnv);
  const globalDiscoveryOpen = fs.readFileSync(path.join(globalDiscoveryHome, '.config', 'opencode', 'command', 'loop-new.md'), 'utf8');
  const globalDiscoveryClaude = fs.readFileSync(path.join(globalDiscoveryHome, '.claude', 'commands', 'loop-resume.md'), 'utf8');
  ok(globalDiscoveryOpen.includes(fs.realpathSync(globalDiscoveryRoot).replace(/\\/g, '/'))
    && globalDiscoveryClaude.includes(fs.realpathSync(globalDiscoveryRoot).replace(/\\/g, '/')),
  'global commands-only shares one discovered .agents Skill root across selected hosts');

  const wrapperProject = make('cl-wrapper-project-');
  const wrapperRoot = seedSkillRoot(path.join(make('cl-wrapper root with spaces-'), 'create-loop'));
  const wrapperEnv = envFor(make('cl-wrapper-home-'));
  const wrapperScript = path.join(PKG_ROOT, 'install-commands.sh').replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, drive) => `/mnt/${drive.toLowerCase()}`);
  const wrapperProjectArg = wrapperProject.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, drive) => `/mnt/${drive.toLowerCase()}`);
  const wrapperRootArg = wrapperRoot.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, drive) => `/mnt/${drive.toLowerCase()}`);
  const bashExe = process.platform === 'win32' ? 'C:\\Windows\\System32\\bash.exe' : 'bash';
  const wrapper = spawnSync(bashExe, [wrapperScript, '--runtime', 'claude', '--project', wrapperProjectArg, '--skill-root', wrapperRootArg], {
    encoding: 'utf8', env: wrapperEnv,
  });
  const wrapperClaudeCommand = path.join(wrapperProject, '.claude', 'commands', 'loop-new.md');
  const wrapperOpenCommand = path.join(wrapperProject, '.opencode', 'command', 'loop-new.md');
  const wrapperCommandBytes = exists(wrapperClaudeCommand) ? fs.readFileSync(wrapperClaudeCommand, 'utf8') : '';
  const wrapperRootDisplay = process.platform === 'win32'
    ? wrapperRootArg : fs.realpathSync(wrapperRoot).replace(/\\/g, '/');
  const wrapperStatePath = path.join(wrapperProject, '.create-loop', 'install-state.json');
  const wrapperState = exists(wrapperStatePath) ? JSON.parse(fs.readFileSync(wrapperStatePath, 'utf8')) : null;
  if (!(wrapper.status === 0 && exists(wrapperClaudeCommand) && !exists(wrapperOpenCommand)
      && wrapperCommandBytes.includes(wrapperRootDisplay) && !wrapperCommandBytes.includes('<CREATE_LOOP_SKILL_ROOT>')
      && wrapperState && wrapperState.hosts.claude && !wrapperState.hosts.opencode
      && !exists(path.join(wrapperProject, '.claude', 'skills', 'create-loop', 'SKILL.md')))) {
    console.error('  wrapper debug:', JSON.stringify({
      status: wrapper.status, error: wrapper.error && wrapper.error.message, stdout: wrapper.stdout, stderr: wrapper.stderr,
      claude: exists(wrapperClaudeCommand), open: exists(wrapperOpenCommand), root: wrapperRootDisplay,
      embedded: wrapperCommandBytes.includes(wrapperRootDisplay), placeholder: wrapperCommandBytes.includes('<CREATE_LOOP_SKILL_ROOT>'),
      state: wrapperState, skillWritten: exists(path.join(wrapperProject, '.claude', 'skills', 'create-loop', 'SKILL.md')),
    }));
  }
  ok(wrapper.status === 0 && exists(wrapperClaudeCommand) && !exists(wrapperOpenCommand)
    && wrapperCommandBytes.includes(wrapperRootDisplay) && !wrapperCommandBytes.includes('<CREATE_LOOP_SKILL_ROOT>')
    && wrapperState && wrapperState.hosts.claude && !wrapperState.hosts.opencode
    && !exists(path.join(wrapperProject, '.claude', 'skills', 'create-loop', 'SKILL.md')),
  'shell wrapper forwards --skill-root and host selection to the Node installer');
  DEFAULT_COMMAND_SKILL_ROOT = sharedSkillRoot;

  const globalHome = make('cl-global-home-');
  const globalEnv = envFor(globalHome);
  run(['install', '-g', '--host', 'opencode', '-q'], globalEnv);
  const globalOpen = fs.readFileSync(path.join(globalHome, '.config', 'opencode', 'command', 'loop-run.md'), 'utf8');
  const globalOpenRoot = fs.realpathSync(path.join(globalHome, '.agents', 'skills', 'create-loop')).replace(/\\/g, '/');
  ok(globalOpen.includes(globalOpenRoot)
    && !globalOpen.includes(path.join(globalHome, '.config', '.agents').replace(/\\/g, '/')), 'global OpenCode commands embed the actual user skill root');
  ok(exists(path.join(globalOpenRoot, 'scripts', 'validate_loop_dir.py')), 'global OpenCode embedded validator path resolves to an installed file');

  const spaced = make('cl-staged with spaces-');
  run(['install', '-p', spaced, '--host', 'opencode,claude', '-q'], env);
  const spacedOpen = fs.readFileSync(path.join(spaced, '.opencode', 'command', 'loop-run.md'), 'utf8');
  const spacedClaude = fs.readFileSync(path.join(spaced, '.claude', 'commands', 'loop-resume.md'), 'utf8');
  const spacedOpenRoot = fs.realpathSync(path.join(spaced, '.agents', 'skills', 'create-loop')).replace(/\\/g, '/');
  const spacedClaudeRoot = fs.realpathSync(path.join(spaced, '.claude', 'skills', 'create-loop')).replace(/\\/g, '/');
  ok(spacedOpen.includes(`python "${spacedOpenRoot}/scripts/validate_loop_dir.py" "<loop-dir>"`)
    && spacedOpen.includes(`python3 "${spacedOpenRoot}/scripts/check_loop_integrity.py" "<loop-dir>"`)
    && spacedClaude.includes(`python "${spacedClaudeRoot}/scripts/validate_loop_dir.py" "<loop-dir>"`)
    && spacedClaude.includes(`python3 "${spacedClaudeRoot}/scripts/check_loop_integrity.py" "<loop-dir>"`), 'installed commands quote skill and workspace paths under roots containing spaces');

  const ownedProject = make('cl-uninstall-');
  const ownedCommand = path.join(ownedProject, '.opencode', 'command', 'loop-status.md');
  run(['install', '-p', ownedProject, '--host', 'opencode', '-q'], env);
  fs.writeFileSync(ownedCommand, 'USER EDIT AGAIN\n');
  run(['uninstall', '-p', ownedProject, '--host', 'opencode', '-q'], env);
  ok(exists(ownedCommand) && !exists(path.join(ownedProject, '.agents', 'skills', 'create-loop', 'SKILL.md')), 'uninstall removes owned files and preserves user edits');
  run(['uninstall', '-p', ownedProject, '--host', 'opencode', '--force', '-q'], env);
  ok(!exists(ownedCommand), 'uninstall --force removes user-edited owned files');

  const pkg = JSON.parse(fs.readFileSync(path.join(PKG_ROOT, 'package.json'), 'utf8'));
  ok(pkg.license === 'SEE LICENSE IN LICENSE', 'package metadata points to the custom LICENSE text');
  ok(pkg.files.some((entry) => entry === 'skills/create-loop/LICENSE'), 'package allowlist carries a skill-local license');
  ok(fs.readFileSync(path.join(PKG_ROOT, 'LICENSE')).equals(fs.readFileSync(path.join(PKG_ROOT, 'skills', 'create-loop', 'LICENSE'))),
    'root and Skill-local license payloads are byte-identical');
  const packedEntriesOnce = npmPackEntries(PKG_ROOT);
  const packedEntriesTwice = npmPackEntries(PKG_ROOT);
  const packedOnce = packedEntriesOnce.map((entry) => entry.path);
  const expectedPacked = expectedPackFiles(PKG_ROOT);
  const requiredPayloads = [
    'LICENSE',
    'skills/create-loop/LICENSE',
    'skills/create-loop/templates/journal.jsonl',
    'skills/create-loop/examples/example_v2_persistent/journal.jsonl',
    'skills/create-loop/tests/baseline_green.sh',
    'skills/create-loop/tests/pointer_baseline.txt',
    'skills/create-loop/tests/experiments/authorization-grant.schema.json',
    'skills/create-loop/tests/experiments/baseline-source.json',
    'skills/create-loop/tests/experiments/baseline-source.tar',
    'skills/create-loop/tests/experiments/blind-review-manifest.schema.json',
    'skills/create-loop/tests/experiments/blind-review-result.schema.json',
    'skills/create-loop/tests/experiments/candidate-source.json',
    'skills/create-loop/tests/experiments/deterministic-authoritative-run.schema.json',
    'skills/create-loop/tests/experiments/deterministic-case-result.schema.json',
    'skills/create-loop/tests/experiments/deterministic-fixture-catalog.json',
    'skills/create-loop/tests/experiments/deterministic-fixture-catalog.schema.json',
    'skills/create-loop/tests/experiments/deterministic_runner.py',
    'skills/create-loop/tests/experiments/deterministic-suite-result.schema.json',
    'skills/create-loop/tests/experiments/evaluation-input-manifest.schema.json',
    'skills/create-loop/tests/experiments/evaluation-spec.json',
    'skills/create-loop/tests/experiments/evaluation-spec.schema.json',
    'skills/create-loop/tests/experiments/evaluation.py',
    'skills/create-loop/tests/experiments/execution-ledger-record.schema.json',
    'skills/create-loop/tests/experiments/execution_guard.py',
    'skills/create-loop/tests/experiments/experiment_harness.py',
    'skills/create-loop/tests/experiments/freeze_experiment.py',
    'skills/create-loop/tests/experiments/instrument-manifest.json',
    'skills/create-loop/tests/experiments/instrument-manifest.schema.json',
    'skills/create-loop/tests/experiments/oracle-result.schema.json',
    'skills/create-loop/tests/experiments/preregistration.json',
    'skills/create-loop/tests/experiments/preregistration.schema.json',
    'skills/create-loop/tests/experiments/presented-artifact.schema.json',
    'skills/create-loop/tests/experiments/report.schema.json',
    'skills/create-loop/tests/experiments/scenarios.json',
    'skills/create-loop/tests/experiments/scenarios.schema.json',
    'skills/create-loop/tests/experiments/snapshot_tools.py',
    'skills/create-loop/tests/experiments/source-snapshot.schema.json',
    'skills/create-loop/tests/experiments/spend-summary.schema.json',
    'skills/create-loop/tests/experiments/tool-profile.schema.json',
    'skills/create-loop/tests/experiments/tool-profiles/local-full-no-publish.json',
    'skills/create-loop/tests/experiments/trace.schema.json',
    'skills/create-loop/tests/experiments/usage-receipt.schema.json',
    'skills/create-loop/tests/experiments/workspace-manifest.schema.json',
    'skills/create-loop/tests/experiments/workspace_builder.py',
    'skills/create-loop/tests_py/test_experiment_deterministic_runner.py',
    'skills/create-loop/tests_py/test_experiment_evaluation.py',
    'skills/create-loop/tests_py/test_experiment_execution_guard.py',
    'skills/create-loop/tests_py/test_experiment_harness.py',
    'skills/create-loop/tests_py/test_experiment_snapshots.py',
    'skills/create-loop/tests_py/test_experiment_workspace.py',
  ];
  const phase5Payloads = [
    ...Object.keys(snapshot(path.join(PKG_ROOT, 'skills', 'create-loop', 'tests', 'experiments')))
      .filter((item) => !/(?:^|[\\/])__pycache__(?:[\\/]|$)|\.pyc$/.test(item)
        && !/^protocol-bundles[\\/]/.test(item))
      .map((item) => `skills/create-loop/tests/experiments/${item.replace(/\\/g, '/')}`),
    ...Object.keys(snapshot(path.join(PKG_ROOT, 'skills', 'create-loop', 'tests_py')))
      .filter((item) => /^test_experiment_[^/\\]+\.py$/.test(item))
      .map((item) => `skills/create-loop/tests_py/${item.replace(/\\/g, '/')}`),
  ].sort((left, right) => left.localeCompare(right));
  const declaredPhase5Payloads = pkg.files
    .filter((item) => item.startsWith('skills/create-loop/tests/experiments/')
      || /^skills\/create-loop\/tests_py\/test_experiment_[^/]+\.py$/.test(item))
    .sort((left, right) => left.localeCompare(right));
  ok(JSON.stringify(packedEntriesOnce) === JSON.stringify(packedEntriesTwice), 'npm package path and size manifest is stable across dry runs');
  ok(JSON.stringify(packedOnce) === JSON.stringify(expectedPacked), 'npm package path set exactly matches the declared payload plus package.json');
  ok(JSON.stringify(declaredPhase5Payloads) === JSON.stringify(phase5Payloads), 'package Phase 5 allowlist exactly covers live source, fixture, schema, and test files');
  ok(requiredPayloads.every((item) => packedOnce.includes(item)), 'npm package includes required jsonl, txt, shell, and license payloads');
  ok(!packedOnce.some((item) => /(?:^|\/)(__pycache__|node_modules)(?:\/|$)|\.pyc$/.test(item)), 'npm package excludes caches, dependencies, and pyc files');
  ok(!packedOnce.some((item) => item.startsWith('skills/create-loop/tests/experiments/protocol-bundles/')),
    'npm package excludes generated frozen protocol bundles');
  ok(!packedOnce.some((item) => /(?:^|\/)(?:raw-output|raw-outputs|results?|runs|receipts?|reviews?)(?:\/|$)/i.test(item)),
    'npm package excludes raw experiment outputs and receipts');
  const packagePayload = packageCli(make);
  const accidentalDoc = path.join(packagePayload.root, 'skills', 'create-loop', 'tests', 'should-not-ship.md');
  fs.writeFileSync(accidentalDoc, '# accidental package file\n');
  const accidentalScript = path.join(packagePayload.root, 'skills', 'create-loop', 'scripts', 'should-not-ship.py');
  fs.writeFileSync(accidentalScript, '# accidental package file\n');
  const accidentalPack = npmPackFiles(packagePayload.root);
  ok(JSON.stringify(accidentalPack) === JSON.stringify(expectedPackFiles(packagePayload.root))
    && !accidentalPack.includes('skills/create-loop/tests/should-not-ship.md')
    && !accidentalPack.includes('skills/create-loop/scripts/should-not-ship.py'), 'package exact allowlist rejects undeclared files across payload areas');

  const mandatoryPayload = packageCli(make);
  fs.writeFileSync(path.join(mandatoryPayload.root, 'COPYING'), 'unexpected npm mandatory document\n');
  ok(JSON.stringify(npmPackFiles(mandatoryPayload.root)) !== JSON.stringify(expectedPackFiles(mandatoryPayload.root)), 'package exact-set gate detects npm mandatory root documents outside the declaration');

  console.log(`\n${passed} passed, ${failed} failed`);
  } finally {
    for (const dir of dirs) fs.rmSync(dir, { recursive: true, force: true });
  }
  process.exitCode = failed ? 1 : 0;
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
