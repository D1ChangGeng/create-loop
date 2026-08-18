#!/usr/bin/env node
/* create-loop standalone installer. Zero runtime dependencies; Node >= 18. */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

const PKG_ROOT = path.resolve(__dirname, '..');
const SKILL_SRC = path.join(PKG_ROOT, 'skills', 'create-loop');
const COMMAND_SRC = path.join(PKG_ROOT, 'command');
const COMMAND_MANIFEST = path.join(COMMAND_SRC, 'manifest.json');
const SKILL_NAME = 'create-loop';
const STATE_BASENAME = 'install-state.json';
const STATE_V1_BACKUP = 'install-state.v1.backup.json';
const LOCK_BASENAME = 'install.lock';
const TRANSACTION_DIR = 'transactions';
const TRANSACTION_VERSION = 4;
const MANIFEST_VERSION = 2;
const COMMAND_SKILL_ROOT_PLACEHOLDER = '<CREATE_LOOP_SKILL_ROOT>';
const OWNED = 'owned';
const ADOPTED = 'adopted';
const LEGACY_UNKNOWN = 'legacy-unknown';
// Per-process cache for duplicate read-only prefix scans. Managed destinations
// still take an uncached full-component check on every plan/apply/recovery path.
const STATIC_LINK_COMPONENT_CACHE = new Map();

let PKG_VERSION = '0.0.0';
try { PKG_VERSION = require(path.join(PKG_ROOT, 'package.json')).version || PKG_VERSION; } catch (_) {}
const ACTIVE_LOCKS = new Map();

function configHome() {
  return process.env.XDG_CONFIG_HOME && process.env.XDG_CONFIG_HOME.trim()
    ? path.resolve(process.env.XDG_CONFIG_HOME)
    : path.join(os.homedir(), '.config');
}
function claudeHome() {
  return process.env.CLAUDE_CONFIG_DIR && process.env.CLAUDE_CONFIG_DIR.trim()
    ? path.resolve(process.env.CLAUDE_CONFIG_DIR)
    : path.join(os.homedir(), '.claude');
}

const HOSTS = {
  opencode: {
    label: 'OpenCode',
    skillDir: (scope, project) => scope === 'global'
      ? path.join(os.homedir(), '.agents', 'skills', SKILL_NAME)
      : path.join(project, '.agents', 'skills', SKILL_NAME),
    commandDir: (scope, project) => scope === 'global'
      ? path.join(configHome(), 'opencode', 'command')
      : path.join(project, '.opencode', 'command'),
    detect: (scope, project) => dirExists(scope === 'global'
      ? path.join(configHome(), 'opencode')
      : path.join(project, '.opencode')),
    renderCommand: (cmd, body, context = {}) => frontmatter([['description', quote(cmd.description)]])
      + renderCommandBody(body, context.skillRoot),
  },
  claude: {
    label: 'Claude Code',
    skillDir: (scope, project) => scope === 'global'
      ? path.join(claudeHome(), 'skills', SKILL_NAME)
      : path.join(project, '.claude', 'skills', SKILL_NAME),
    commandDir: (scope, project) => scope === 'global'
      ? path.join(claudeHome(), 'commands')
      : path.join(project, '.claude', 'commands'),
    detect: (scope, project) => dirExists(scope === 'global' ? claudeHome() : path.join(project, '.claude')),
    renderCommand: (cmd, body, context = {}) => frontmatter([
      ['description', quote(cmd.description)],
      ...(cmd.argumentHint ? [['argument-hint', quote(cmd.argumentHint)]] : []),
    ]) + renderCommandBody(body, context.skillRoot),
  },
};

function dirExists(p) { try { return fs.statSync(p).isDirectory(); } catch (_) { return false; } }
function fileExists(p) { try { return fs.statSync(p).isFile(); } catch (_) { return false; } }
function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }
function readFile(p) { return fs.readFileSync(p); }
function sha256(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function quote(s) { return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"'; }
function frontmatter(pairs) { return `---\n${pairs.map(([k, v]) => `${k}: ${v}`).join('\n')}\n---\n\n`; }
function normalizeLf(s) { return String(s).replace(/\r\n?/g, '\n').replace(/^\uFEFF/, '').replace(/\n*$/, '\n'); }
function renderCommandBody(body, skillRoot) {
  if (skillRoot === undefined) return body;
  if (typeof skillRoot !== 'string' || !skillRoot) fail('invalid installed skill root');
  const display = canonicalDisplayPath(skillRoot);
  if (/[\u0000-\u001f\u007f$`"%!\\]/.test(display)) {
    fail(`Skill root cannot be embedded safely in shell command examples: ${display}`);
  }
  return body.replaceAll(COMMAND_SKILL_ROOT_PLACEHOLDER, display);
}
function canonicalDisplayPath(value) {
  const absolute = path.resolve(value);
  const existing = nearestExisting(absolute);
  const canonical = existing
    ? path.resolve(realpathNative(existing), path.relative(existing, absolute))
    : absolute;
  return canonical.split(path.sep).join('/');
}
function isPlainObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function hasOnlyKeys(value, allowed) { return Object.keys(value).every((key) => allowed.has(key)); }
function isWithin(root, candidate) {
  const rel = path.relative(path.resolve(root), path.resolve(candidate));
  const normalized = process.platform === 'win32' ? rel.toLowerCase() : rel;
  return normalized !== '' && !normalized.startsWith('..' + path.sep)
    && normalized !== '..' && !path.isAbsolute(rel);
}
function isWithinOrEqual(root, candidate) {
  return samePath(root, candidate) || isWithin(root, candidate);
}
function samePath(a, b) {
  const left = path.resolve(a);
  const right = path.resolve(b);
  return process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;
}
function lstatMaybe(p) { try { return fs.lstatSync(p); } catch (e) { if (e.code === 'ENOENT') return null; throw e; } }
function realpathNative(p) { return fs.realpathSync.native ? fs.realpathSync.native(p) : fs.realpathSync(p); }
function pathIdentity(value) {
  const resolved = path.resolve(value);
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}
function linkComponentError(target, label, options = {}) {
  const absolute = path.resolve(target);
  const cacheKey = options.static ? pathIdentity(absolute) : null;
  if (cacheKey && STATIC_LINK_COMPONENT_CACHE.has(cacheKey)) {
    const redirected = STATIC_LINK_COMPONENT_CACHE.get(cacheKey);
    return redirected ? `${label} contains a symlink, junction, or reparse-point redirect: ${redirected}` : null;
  }
  const parsed = path.parse(absolute);
  let current = parsed.root;
  const parts = absolute.slice(parsed.root.length).split(path.sep).filter(Boolean);
  for (const part of parts) {
    current = path.join(current, part);
    const stat = lstatMaybe(current);
    if (!stat) break;
    if (stat.isSymbolicLink() || !samePath(realpathNative(current), current)) {
      if (cacheKey) STATIC_LINK_COMPONENT_CACHE.set(cacheKey, current);
      return `${label} contains a symlink, junction, or reparse-point redirect: ${current}`;
    }
  }
  if (cacheKey) STATIC_LINK_COMPONENT_CACHE.set(cacheKey, null);
  return null;
}
function assertNoLinkComponents(target, label) {
  const error = linkComponentError(target, label);
  if (error) fail(error);
}
function assertNoStaticLinkComponents(target, label) {
  const error = linkComponentError(target, label, { static: true });
  if (error) fail(error);
}
function assertRegularFileOrMissing(file, label) {
  const stat = lstatMaybe(file);
  if (stat && !stat.isFile()) fail(`${label} must be a regular file: ${file}`);
}
function nearestExistingDirectory(target) {
  let current = path.resolve(target);
  while (true) {
    const stat = lstatMaybe(current);
    if (stat) {
      if (!stat.isDirectory()) fail(`path ancestor is not a directory: ${current}`);
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) fail(`no existing directory ancestor for: ${target}`);
    current = parent;
  }
}
function assertWritableDestination(target, label) {
  const parent = nearestExistingDirectory(path.dirname(target));
  try { fs.accessSync(parent, fs.constants.W_OK); }
  catch (_) { fail(`${label} parent is not writable: ${parent}`); }
  const stat = lstatMaybe(target);
  if (stat) {
    if (!stat.isFile()) fail(`${label} must be a regular file: ${target}`);
    try { fs.accessSync(target, fs.constants.W_OK); }
    catch (_) { fail(`${label} is not writable: ${target}`); }
  }
}
function ensureSafeDirectory(target, label) {
  const absolute = path.resolve(target);
  const parsed = path.parse(absolute);
  let current = parsed.root;
  const parts = absolute.slice(parsed.root.length).split(path.sep).filter(Boolean);
  for (const part of parts) {
    current = path.join(current, part);
    let stat = lstatMaybe(current);
    if (!stat) {
      fs.mkdirSync(current);
      stat = fs.lstatSync(current);
    }
    if (!stat.isDirectory() || stat.isSymbolicLink() || !samePath(realpathNative(current), current)) {
      fail(`${label} contains an unsafe directory component: ${current}`);
    }
  }
}
function nearestExisting(p) {
  let cur = path.resolve(p);
  while (!fs.existsSync(cur)) {
    const parent = path.dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
  return cur;
}
function resolvesWithin(root, candidate) {
  if (!isWithin(root, candidate)) return false;
  const rootAncestor = nearestExisting(root);
  const candidateAncestor = nearestExisting(candidate);
  if (!rootAncestor || !candidateAncestor) return true;
  const realRoot = fs.realpathSync(rootAncestor);
  const realCandidate = fs.realpathSync(candidateAncestor);
  return realCandidate === realRoot || isWithin(realRoot, realCandidate);
}

function hostPaths(hostKey, opts) {
  const host = HOSTS[hostKey];
  const projectAnchor = path.resolve(opts.project);
  const roots = {
    skill: path.resolve(host.skillDir(opts.scope, opts.project)),
    command: path.resolve(host.commandDir(opts.scope, opts.project)),
  };
  const anchors = opts.scope === 'project'
    ? { skill: projectAnchor, command: projectAnchor }
    : hostKey === 'opencode'
      ? { skill: path.resolve(os.homedir()), command: path.resolve(configHome()) }
      : { skill: path.resolve(claudeHome()), command: path.resolve(claudeHome()) };
  return { roots, anchors };
}
function assertManagedLocation(anchor, root, target, label) {
  const error = managedLocationError(anchor, root, target, label);
  if (error) fail(error);
}
function assertManagedLocationWithStaticRoots(anchor, root, target, label) {
  // Caching only removes the duplicate anchor/root scans; managedLocationError
  // still re-walks `target` (including those prefixes) without the cache.
  const error = managedLocationError(anchor, root, target, label, { staticRoots: true });
  if (error) fail(error);
}
function managedLocationError(anchor, root, target, label, options = {}) {
  if (!isWithinOrEqual(anchor, root)) return `${label} root is outside its allowed anchor: ${root}`;
  if (!isWithin(root, target)) return `${label} target is outside its managed root: ${target}`;
  const linkError = linkComponentError(anchor, `${label} anchor`, { static: Boolean(options.staticRoots) })
    || linkComponentError(root, `${label} root`, { static: Boolean(options.staticRoots) })
    || linkComponentError(target, `${label} target`);
  if (linkError) return linkError;
  const stat = lstatMaybe(target);
  if (stat && !stat.isFile()) return `${label} must be a regular file: ${target}`;
  return null;
}

function listFilesRecursive(root) {
  const out = [];
  const excludedDirs = new Set(['.git', '__pycache__', '__pypackages__', 'node_modules']);
  const excludedFiles = new Set(['metadata.json', '.DS_Store']);
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!excludedDirs.has(entry.name)) walk(full);
      } else if (entry.isFile() && !excludedFiles.has(entry.name) && !entry.name.endsWith('.pyc')) {
        out.push(full);
      }
    }
  })(root);
  return out.sort();
}

let QUIET = false;
function info(msg) { if (!QUIET) process.stdout.write(msg + '\n'); }
function warn(msg) { process.stderr.write('warning: ' + msg + '\n'); }
function fail(msg) { process.stderr.write('error: ' + msg + '\n'); process.exit(1); }

function stateDir(opts) {
  return opts.scope === 'global' ? path.join(configHome(), 'create-loop') : path.join(opts.project, '.create-loop');
}
function statePath(opts) { return path.join(stateDir(opts), STATE_BASENAME); }
function lockPath(opts) { return path.join(stateDir(opts), LOCK_BASENAME); }
function stateAnchor(opts) { return opts.scope === 'global' ? path.resolve(configHome()) : path.resolve(opts.project); }
function newState(opts) {
  return {
    manifestVersion: MANIFEST_VERSION,
    tool: 'create-loop',
    scope: opts.scope,
    stateRoot: path.resolve(stateDir(opts)),
    projectRoot: opts.scope === 'project' ? path.resolve(opts.project) : null,
    hosts: {},
    transactions: {},
  };
}
function stableObject(value) {
  if (Array.isArray(value)) return value.map(stableObject);
  if (!isPlainObject(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableObject(value[key])]));
}
function canonicalDigestPath(value) {
  const resolved = path.resolve(value);
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
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
        host[group][key] = canonicalDigestPath(host[group][key]);
      }
    }
    host.files = Object.fromEntries(
      Object.entries(host.files || {})
        .map(([file, meta]) => [canonicalDigestPath(file), meta])
        .sort(([left], [right]) => left.localeCompare(right))
    );
  }
  logical.stateRoot = canonicalDigestPath(logical.stateRoot);
  if (logical.projectRoot !== null) logical.projectRoot = canonicalDigestPath(logical.projectRoot);
  return sha256(Buffer.from(JSON.stringify(stableObject(logical)), 'utf8'));
}
function currentState(opts) {
  return readState(opts);
}
function validateFileMeta(meta) {
  return isPlainObject(meta)
    && /^[a-f0-9]{64}$/.test(meta.hash)
    && ['skill', 'command'].includes(meta.kind)
    && [OWNED, ADOPTED, LEGACY_UNKNOWN].includes(meta.ownership);
}
function normalizeState(raw, opts, stateFile) {
  if (!isPlainObject(raw) || raw.tool !== 'create-loop' || !isPlainObject(raw.hosts)) {
    fail(`install state is invalid; refusing to continue: ${stateFile}`);
  }
  if (raw.scope && raw.scope !== opts.scope) fail(`install state scope mismatch: ${stateFile}`);
  if (raw.manifestVersion !== 1 && raw.manifestVersion !== MANIFEST_VERSION) {
    fail(`unsupported install state version ${raw.manifestVersion}: ${stateFile}`);
  }
  if (raw.manifestVersion === MANIFEST_VERSION) {
    if (!raw.stateRoot || !samePath(raw.stateRoot, stateDir(opts))) {
      fail(`install state root mismatch; explicit relocation/import is required: ${stateFile}`);
    }
    if (opts.scope === 'project' && (!raw.projectRoot || !samePath(raw.projectRoot, opts.project))) {
      fail(`install state project root mismatch: ${stateFile}`);
    }
  }
  const state = newState(opts);
  state.createdAt = raw.createdAt || raw.updatedAt;
  state.updatedAt = raw.updatedAt;
  if (raw.transactions !== undefined) {
    if (raw.manifestVersion !== MANIFEST_VERSION || !isPlainObject(raw.transactions)) {
      fail(`install state has invalid transaction anchors: ${stateFile}`);
    }
    for (const [hostKey, anchor] of Object.entries(raw.transactions)) {
      const allowed = new Set(['txId', 'phase', 'intentSha256']);
      if (!HOSTS[hostKey] || !isPlainObject(anchor) || !hasOnlyKeys(anchor, allowed)
          || !/^[a-f0-9]{32}$/.test(anchor.txId)
          || !['pending', 'committed'].includes(anchor.phase)
          || !/^[a-f0-9]{64}$/.test(anchor.intentSha256)) {
        fail(`install state has an invalid transaction anchor (${hostKey}): ${stateFile}`);
      }
      state.transactions[hostKey] = { ...anchor };
    }
  }
  for (const [hostKey, rec] of Object.entries(raw.hosts)) {
    if (!HOSTS[hostKey] || !isPlainObject(rec) || !isPlainObject(rec.files)
        || (rec.host && rec.host !== hostKey) || (rec.scope && rec.scope !== opts.scope)) {
      fail(`install state has an invalid host record (${hostKey}): ${stateFile}`);
    }
    const next = {
      host: hostKey,
      scope: opts.scope,
      installerVersion: rec.installerVersion || 'unknown',
      installedAt: rec.installedAt || raw.updatedAt || new Date(0).toISOString(),
      updatedAt: rec.updatedAt || raw.updatedAt || new Date(0).toISOString(),
      roots: hostPaths(hostKey, opts).roots,
      anchors: hostPaths(hostKey, opts).anchors,
      files: {},
    };
    if (raw.manifestVersion === MANIFEST_VERSION) {
      if (!isPlainObject(rec.roots) || !isPlainObject(rec.anchors)
          || !samePath(rec.roots.skill, next.roots.skill) || !samePath(rec.roots.command, next.roots.command)
          || !samePath(rec.anchors.skill, next.anchors.skill) || !samePath(rec.anchors.command, next.anchors.command)) {
        fail(`install state managed roots changed for ${hostKey}; explicit relocation/import is required: ${stateFile}`);
      }
    }
    for (const [abs, meta] of Object.entries(rec.files)) {
      if (!path.isAbsolute(abs) || !isPlainObject(meta) || !/^[a-f0-9]{64}$/.test(meta.hash) || !['skill', 'command'].includes(meta.kind)) {
        fail(`install state has an invalid file record (${abs}): ${stateFile}`);
      }
      const normalized = { hash: meta.hash, kind: meta.kind, ownership: meta.ownership || LEGACY_UNKNOWN };
      if (!validateFileMeta(normalized)) fail(`install state has invalid ownership metadata (${abs}): ${stateFile}`);
      let normalizedPath = path.resolve(abs);
      if (raw.manifestVersion === MANIFEST_VERSION) {
        const recordedRoot = rec.roots[normalized.kind];
        const currentRoot = next.roots[normalized.kind];
        if (isWithin(recordedRoot, normalizedPath)) {
          normalizedPath = path.resolve(currentRoot, path.relative(recordedRoot, normalizedPath));
        }
      }
      if (Object.keys(next.files).some((tracked) => samePath(tracked, normalizedPath))) {
        fail(`install state has duplicate file records (${normalizedPath}): ${stateFile}`);
      }
      next.files[normalizedPath] = normalized;
    }
    state.hosts[hostKey] = next;
  }
  return state;
}
function readState(opts) {
  const p = statePath(opts);
  if (!fileExists(p)) return newState(opts);
  let raw;
  let bytes;
  try { bytes = fs.readFileSync(p); raw = JSON.parse(bytes.toString('utf8')); }
  catch (e) { fail(`install state is corrupt; refusing to continue: ${p} (${e.message})`); }
  if (raw.manifestVersion === 1) opts._legacyStateBytes = bytes;
  return normalizeState(raw, opts, p);
}
function writeAtomic(file, content) {
  ensureSafeDirectory(path.dirname(file), 'atomic write directory');
  assertNoLinkComponents(file, 'atomic write target');
  assertRegularFileOrMissing(file, 'atomic write target');
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${crypto.randomBytes(6).toString('hex')}.tmp`);
  let fd;
  try {
    fd = fs.openSync(tmp, 'wx', 0o600);
    fs.writeFileSync(fd, content);
    fs.fsyncSync(fd);
    fs.closeSync(fd);
    fd = undefined;
    fs.renameSync(tmp, file);
  } finally {
    if (fd !== undefined) try { fs.closeSync(fd); } catch (_) {}
    try { fs.unlinkSync(tmp); } catch (_) {}
  }
}
function writeState(opts, state) {
  const now = new Date().toISOString();
  state.manifestVersion = MANIFEST_VERSION;
  state.updatedAt = now;
  if (!state.createdAt) state.createdAt = now;
  writeAtomic(statePath(opts), JSON.stringify(state, null, 2) + '\n');
}
function preflightStateStorage(opts) {
  const anchor = stateAnchor(opts);
  const dir = path.resolve(stateDir(opts));
  const file = path.resolve(statePath(opts));
  if (!isWithin(anchor, dir)) fail(`state directory is outside its allowed anchor: ${dir}`);
  assertNoLinkComponents(anchor, 'state anchor');
  assertNoLinkComponents(dir, 'state directory');
  assertNoLinkComponents(file, 'state file');
  assertRegularFileOrMissing(file, 'state file');
  assertWritableDestination(file, 'state file');
}
function parseStateLock(bytes, opts, file) {
  let lock;
  try { lock = JSON.parse(bytes.toString('utf8')); }
  catch (e) { fail(`installer lock is corrupt; refusing to continue: ${file} (${e.message})`); }
  const allowed = new Set(['version', 'tool', 'pid', 'token', 'stateRoot', 'createdAt']);
  if (!isPlainObject(lock) || !hasOnlyKeys(lock, allowed) || lock.version !== 1 || lock.tool !== 'create-loop'
      || !Number.isSafeInteger(lock.pid) || lock.pid <= 0 || !/^[a-f0-9]{32}$/.test(lock.token)
      || typeof lock.stateRoot !== 'string' || !samePath(lock.stateRoot, stateDir(opts))
      || typeof lock.createdAt !== 'string' || !Number.isFinite(Date.parse(lock.createdAt))) {
    fail(`installer lock is invalid; refusing to continue: ${file}`);
  }
  return lock;
}
function readStateLock(opts) {
  const file = lockPath(opts);
  assertNoLinkComponents(path.dirname(file), 'installer lock directory');
  assertNoLinkComponents(file, 'installer lock file');
  assertRegularFileOrMissing(file, 'installer lock file');
  if (!fileExists(file)) return null;
  const bytes = readFile(file);
  return { file, bytes, lock: parseStateLock(bytes, opts, file) };
}
function processAlive(pid) {
  try { process.kill(pid, 0); return true; }
  catch (e) { if (e && e.code === 'ESRCH') return false; return null; }
}
function inspectStateLock(opts) {
  const existing = readStateLock(opts);
  if (!existing) return;
  const alive = processAlive(existing.lock.pid);
  const status = alive === true ? 'active' : alive === false ? 'stale' : 'unverifiable';
  fail(`installer lock is ${status}; dry-run made no changes: ${existing.file}`);
}
function removeStaleStateLock(opts, existing) {
  assertNoLinkComponents(existing.file, 'installer lock file');
  const claimed = path.join(path.dirname(existing.file), `.install.lock.stale.${process.pid}.${crypto.randomBytes(6).toString('hex')}`);
  try { fs.renameSync(existing.file, claimed); }
  catch (e) {
    if (e.code === 'ENOENT') return false;
    fail(`unable to claim stale installer lock safely: ${existing.file} (${e.message})`);
  }
  try {
    assertNoLinkComponents(claimed, 'claimed stale installer lock');
    assertRegularFileOrMissing(claimed, 'claimed stale installer lock');
    const current = readFile(claimed);
    if (!current.equals(existing.bytes)) fail(`installer lock changed while claiming stale owner: ${existing.file}`);
    fs.unlinkSync(claimed);
  } catch (e) {
    try { if (!fileExists(existing.file)) fs.renameSync(claimed, existing.file); } catch (_) {}
    throw e;
  }
  return true;
}
function acquireStateLock(opts) {
  const anchor = stateAnchor(opts);
  const root = path.resolve(stateDir(opts));
  if (!isWithin(anchor, root)) fail(`state directory is outside its allowed anchor: ${root}`);
  assertNoLinkComponents(anchor, 'state anchor');
  ensureSafeDirectory(root, 'installer state directory');
  const file = lockPath(opts);
  assertNoLinkComponents(file, 'installer lock file');
  assertRegularFileOrMissing(file, 'installer lock file');
  for (let attempt = 0; attempt < 2; attempt++) {
    const token = crypto.randomBytes(16).toString('hex');
    const lock = {
      version: 1,
      tool: 'create-loop',
      pid: process.pid,
      token,
      stateRoot: path.resolve(stateDir(opts)),
      createdAt: new Date().toISOString(),
    };
    const bytes = Buffer.from(JSON.stringify(lock, null, 2) + '\n');
    let fd;
    try {
      fd = fs.openSync(file, 'wx', 0o600);
      fs.writeFileSync(fd, bytes);
      fs.fsyncSync(fd);
      fs.closeSync(fd);
      fd = undefined;
      const owned = { file, token, stateRoot: root, anchor };
      ACTIVE_LOCKS.set(file, owned);
      return owned;
    } catch (e) {
      if (fd !== undefined) try { fs.closeSync(fd); } catch (_) {}
      if (e.code !== 'EEXIST') {
        fail(`unable to create installer lock; refusing to continue: ${file} (${e.message})`);
      }
      const existing = readStateLock(opts);
      if (!existing) continue;
      const alive = processAlive(existing.lock.pid);
      if (alive === false) {
        removeStaleStateLock(opts, existing);
        continue;
      }
      if (alive === true) fail(`installer lock is held by active pid ${existing.lock.pid}: ${file}`);
      fail(`installer lock owner cannot be verified; refusing to continue: ${file}`);
    }
  }
  fail(`unable to acquire installer lock after stale-lock recovery: ${file}`);
}
function releaseStateLock(owned) {
  if (!owned) return;
  try {
    const linkError = linkComponentError(owned.file, 'installer lock file');
    const stat = lstatMaybe(owned.file);
    if (linkError || (stat && !stat.isFile())) {
      warn(`${linkError || `installer lock is not a regular file: ${owned.file}`}; preserved for manual recovery`);
      return;
    }
    const bytes = readFile(owned.file);
    const raw = JSON.parse(bytes.toString('utf8'));
    if (!isPlainObject(raw) || raw.token !== owned.token || raw.pid !== process.pid) {
      warn(`installer lock changed before release; preserved for manual recovery: ${owned.file}`);
      return;
    }
    fs.unlinkSync(owned.file);
  } catch (e) {
    if (e.code !== 'ENOENT') warn(`unable to release installer lock: ${owned.file} (${e.message})`);
  } finally {
    ACTIVE_LOCKS.delete(owned.file);
  }
  pruneUpwards(owned.stateRoot, owned.anchor);
}
function withStateLock(opts, operation) {
  if (opts.dryRun) {
    inspectStateLock(opts);
    return operation();
  }
  const owned = acquireStateLock(opts);
  try {
    const holdMs = Number(process.env.CREATE_LOOP_TEST_HOLD_LOCK_MS || 0);
    if (Number.isFinite(holdMs) && holdMs > 0) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, holdMs);
    return operation();
  } finally {
    releaseStateLock(owned);
  }
}
process.on('exit', () => {
  for (const owned of ACTIVE_LOCKS.values()) releaseStateLock(owned);
});
function prepareLegacyBackup(opts) {
  if (!opts._legacyStateBytes || opts.dryRun) return;
  const backup = path.join(stateDir(opts), STATE_V1_BACKUP);
  assertNoLinkComponents(backup, 'v1 state backup');
  const existing = lstatMaybe(backup);
  if (existing) {
    if (!existing.isFile() || sha256(readFile(backup)) !== sha256(opts._legacyStateBytes)) {
      fail(`v1 state backup already exists with different content: ${backup}`);
    }
    return;
  }
  writeAtomic(backup, opts._legacyStateBytes);
}
function emptyHostRecord(host, scope, prev) {
  const now = new Date().toISOString();
  return {
    host,
    scope,
    installerVersion: PKG_VERSION,
    installedAt: prev && prev.installedAt ? prev.installedAt : now,
    updatedAt: now,
    roots: null,
    anchors: null,
    files: {},
  };
}

function fileRecord(hash, kind, ownership) { return { hash, kind, ownership }; }
function destinationHash(target) {
  const stat = lstatMaybe(target);
  if (!stat) return null;
  if (!stat.isFile()) fail(`installer destination must be a regular file: ${target}`);
  return sha256(readFile(target));
}
function assertDestinationMatchesBefore(op, context) {
  const actual = destinationHash(op.dst);
  if (actual !== op.beforeHash) {
    fail(`installer destination changed ${context}; refusing ${op.action}: ${op.dst}`);
  }
}
function injectTestDestinationMutation(phase) {
  if (process.env.CREATE_LOOP_TEST_MUTATE_DESTINATION_PHASE !== phase) return;
  const target = process.env.CREATE_LOOP_TEST_MUTATE_DESTINATION_PATH;
  if (!target || !path.isAbsolute(target)) throw new Error('invalid injected destination mutation path');
  if (process.env.CREATE_LOOP_TEST_MUTATE_DESTINATION_ACTION === 'delete') {
    try { fs.unlinkSync(target); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    return;
  }
  ensureDir(path.dirname(target));
  fs.writeFileSync(target, process.env.CREATE_LOOP_TEST_MUTATE_DESTINATION_CONTENT || 'INJECTED DESTINATION MUTATION\n');
}
function trackedEntry(files, target) {
  return Object.entries(files || {}).find(([tracked]) => samePath(tracked, target)) || null;
}
function setTrackedFile(files, target, meta) {
  for (const tracked of Object.keys(files)) {
    if (samePath(tracked, target) && tracked !== target) delete files[tracked];
  }
  files[target] = meta;
}
function planManaged(absPath, content, kind, prev, next, opts) {
  const dst = path.resolve(absPath);
  const expectedRoot = kind === 'skill' ? opts._roots.skill : opts._roots.command;
  const expectedAnchor = kind === 'skill' ? opts._anchors.skill : opts._anchors.command;
  assertManagedLocationWithStaticRoots(expectedAnchor, expectedRoot, dst, kind);
  assertWritableDestination(dst, `${kind} destination`);
  const newHash = sha256(content);
  const oldEntry = prev && trackedEntry(prev.files, dst);
  const old = oldEntry ? oldEntry[1] : null;
  const beforeHash = destinationHash(dst);
  let safeOwnedUpdate = false;
  if (beforeHash !== null) {
    if (beforeHash === newHash) {
      setTrackedFile(next.files, dst, fileRecord(newHash, kind, old ? old.ownership : ADOPTED));
      return { action: old ? 'unchanged' : 'adopted', dst, content: null, kind, forceAuthorized: false };
    }
    safeOwnedUpdate = Boolean(old && old.ownership === OWNED && old.hash === beforeHash);
    if (!safeOwnedUpdate && !opts.force) {
      setTrackedFile(next.files, dst, old || fileRecord(beforeHash, kind, ADOPTED));
      return { action: 'skipped-user', dst, content: null, kind, forceAuthorized: false };
    }
  }
  const existed = beforeHash !== null;
  const forceAuthorized = Boolean(existed && !safeOwnedUpdate && opts.force);
  const ownership = old ? old.ownership : (existed ? ADOPTED : OWNED);
  setTrackedFile(next.files, dst, fileRecord(newHash, kind, ownership));
  return {
    action: opts.dryRun ? 'dry' : (existed ? 'updated' : 'created'),
    dst, content, kind, beforeHash, forceAuthorized,
  };
}

function expectedRoot(host, kind, opts) {
  return kind === 'skill' ? host.skillDir(opts.scope, opts.project) : host.commandDir(opts.scope, opts.project);
}
function expectedAnchor(hostKey, kind, opts) {
  const locations = hostPaths(hostKey, opts);
  return kind === 'skill' ? locations.anchors.skill : locations.anchors.command;
}
function safeTrackedPath(host, abs, meta, opts) {
  const root = expectedRoot(host, meta.kind, opts);
  const hostKey = Object.keys(HOSTS).find((key) => HOSTS[key] === host);
  const anchor = expectedAnchor(hostKey, meta.kind, opts);
  return !managedLocationError(anchor, root, abs, `tracked ${meta.kind}`, { staticRoots: true });
}
function planObsolete(hostKey, host, prev, next, selectedKinds, desiredPaths, stats, opts, operations, emitWarnings = true) {
  if (!prev) return;
  for (const [abs, meta] of Object.entries(prev.files)) {
    if (!selectedKinds.has(meta.kind) || [...desiredPaths].some((desired) => samePath(desired, abs))) continue;
    const root = expectedRoot(host, meta.kind, opts);
    const anchor = expectedAnchor(hostKey, meta.kind, opts);
    if (managedLocationError(anchor, root, abs, `tracked ${meta.kind}`, { staticRoots: true })) {
      next.files[abs] = meta;
      stats.unsafe++;
      if (emitWarnings) warn(`preserved unsafe tracked path: ${abs}`);
      continue;
    }
    if (!fileExists(abs)) continue;
    const curHash = sha256(readFile(abs));
    if (meta.ownership !== OWNED) {
      next.files[abs] = meta;
      stats.preserved++;
      continue;
    }
    if (curHash !== meta.hash && !opts.force) {
      next.files[abs] = meta;
      stats.preserved++;
      if (emitWarnings) warn(`preserved obsolete user-edited file: ${abs}`);
      continue;
    }
    assertWritableDestination(abs, `obsolete ${meta.kind}`);
    if (!opts.dryRun) operations.push({
      action: 'delete', dst: abs, kind: meta.kind,
      beforeHash: curHash,
      forceAuthorized: Boolean(curHash !== meta.hash && opts.force),
    });
    stats.obsolete++;
  }
}

function transactionPath(opts, hostKey) {
  return path.join(stateDir(opts), TRANSACTION_DIR, `${hostKey}.json`);
}
function preparedTransactionPath(opts, hostKey, txId) {
  return path.join(stateDir(opts), TRANSACTION_DIR, `${hostKey}-${txId}.prepared.json`);
}
function transactionIntent(tx) {
  const normalizedOperations = tx.operations.map((op) => ({
    action: op.action,
    dst: canonicalDigestPath(op.dst),
    kind: op.kind,
    hash: op.hash,
    stage: op.stage === null ? null : canonicalDigestPath(op.stage),
    beforeHash: op.beforeHash,
    forceAuthorized: op.forceAuthorized,
  }));
  return {
    version: tx.version,
    txId: tx.txId,
    host: tx.host,
    kinds: [...tx.kinds],
    stageDir: canonicalDigestPath(tx.stageDir),
    operations: normalizedOperations,
    preStateSha256: tx.preStateSha256,
    postStateSha256: tx.postStateSha256,
    roots: Object.fromEntries(Object.entries(tx.roots).map(([kind, root]) => [kind, canonicalDigestPath(root)])),
    commandSkillRoot: tx.commandSkillRoot ? canonicalDigestPath(tx.commandSkillRoot) : null,
  };
}
function transactionIntentSha256(tx) {
  return sha256(Buffer.from(JSON.stringify(stableObject(transactionIntent(tx))), 'utf8'));
}
function transactionAnchor(state, hostKey) {
  return state.transactions && state.transactions[hostKey] ? state.transactions[hostKey] : null;
}
function assertTransactionAnchor(state, hostKey, tx, phase, txFile) {
  const anchor = transactionAnchor(state, hostKey);
  if (!anchor || anchor.txId !== tx.txId || anchor.phase !== phase
      || anchor.intentSha256 !== transactionIntentSha256(tx)) {
    fail(`installer transaction is not anchored by install state (${phase}): ${txFile}`);
  }
}
function committedStateMatchesTransaction(current, expected, preState, hostKey, operations) {
  const actual = JSON.parse(JSON.stringify(current));
  const projected = JSON.parse(JSON.stringify(expected));
  actual.transactions = {};
  projected.transactions = {};
  const actualFiles = actual.hosts[hostKey]?.files || {};
  const expectedFiles = projected.hosts[hostKey]?.files || {};
  const preFiles = preState.hosts[hostKey]?.files || {};
  for (const op of operations) {
    if (op.action !== 'write' || op.beforeHash !== null || trackedMeta(preFiles, op.dst)) continue;
    const actualEntry = trackedEntry(actualFiles, op.dst);
    const expectedEntry = trackedEntry(expectedFiles, op.dst);
    if (!actualEntry || !expectedEntry) continue;
    const actualMeta = actualEntry[1];
    const expectedMeta = expectedEntry[1];
    if (expectedMeta.ownership === OWNED && actualMeta.ownership === ADOPTED
        && actualMeta.kind === expectedMeta.kind && actualMeta.hash === expectedMeta.hash) {
      actualMeta.ownership = OWNED;
    }
  }
  return stateDigest(actual) === stateDigest(projected);
}
function trackedMeta(files, target) {
  const entry = Object.entries(files).find(([tracked]) => samePath(tracked, target));
  return entry ? entry[1] : null;
}
function mappedValueByPath(values, target) {
  const entry = [...values.entries()].find(([candidate]) => samePath(candidate, target));
  return entry ? entry[1] : null;
}
function expectedManagedPayloads(hostKey, opts, kinds, commandSkillRoot) {
  const host = HOSTS[hostKey];
  const locations = hostPaths(hostKey, opts);
  const payloads = new Map();
  if (kinds.has('skill') && dirExists(SKILL_SRC)) {
    for (const src of listFilesRecursive(SKILL_SRC)) {
      const dst = path.resolve(locations.roots.skill, path.relative(SKILL_SRC, src));
      payloads.set(dst, { kind: 'skill', hash: sha256(readFile(src)) });
    }
  }
  if (kinds.has('command')) {
    if (!commandSkillRoot) return payloads;
    for (const cmd of loadCommandManifest()) {
      const dst = path.resolve(locations.roots.command, `${cmd.id}.md`);
      payloads.set(dst, {
        kind: 'command',
        hash: sha256(Buffer.from(host.renderCommand(cmd, cmd._body, {
          skillRoot: commandSkillRoot,
        }), 'utf8')),
      });
    }
  }
  return payloads;
}
function validateHostStateDelta(hostKey, preState, postState, txFile) {
  const preHost = preState.hosts[hostKey] || null;
  const postHost = postState.hosts[hostKey] || null;
  const topLevel = ['manifestVersion', 'tool', 'scope', 'stateRoot', 'projectRoot'];
  for (const key of topLevel) {
    if (JSON.stringify(preState[key] ?? null) !== JSON.stringify(postState[key] ?? null)) {
      fail(`installer transaction changes immutable state metadata (${key}): ${txFile}`);
    }
  }
  if (Object.keys(preState.transactions || {}).length || Object.keys(postState.transactions || {}).length) {
    fail(`installer transaction embeds nested transaction anchors: ${txFile}`);
  }
  for (const key of Object.keys(HOSTS)) {
    if (key === hostKey) continue;
    if (JSON.stringify(stableObject(preState.hosts[key] || null))
        !== JSON.stringify(stableObject(postState.hosts[key] || null))) {
      fail(`installer transaction changes another host state (${key}): ${txFile}`);
    }
  }
  return {
    preFiles: preHost ? preHost.files : {},
    postFiles: postHost ? postHost.files : {},
  };
}
function validateTransactionFileDelta(preFiles, postFiles, operations, expectedPayloads, txFile, committed) {
  const targets = operations.map((op) => path.resolve(op.dst));
  const paths = new Set([...Object.keys(preFiles), ...Object.keys(postFiles)]);
  for (const file of paths) {
    if (targets.some((target) => samePath(target, file))) continue;
    const before = trackedMeta(preFiles, file);
    const after = trackedMeta(postFiles, file);
    if (JSON.stringify(stableObject(before)) === JSON.stringify(stableObject(after))) continue;
    const actualHash = fileExists(file) ? sha256(readFile(file)) : null;
    const expectedPayload = mappedValueByPath(expectedPayloads, file);
    const safelyDroppedMissing = before && !after && actualHash === null;
    const matchesExpected = committed || (expectedPayload
      && expectedPayload.kind === after?.kind && expectedPayload.hash === after?.hash);
    const safelyAdoptedIdentical = !before && after && after.ownership === ADOPTED
      && matchesExpected && actualHash === after.hash;
    const safelyRefreshedTracked = before && after
      && before.kind === after.kind && before.ownership === after.ownership
      && matchesExpected && actualHash === after.hash;
    if (!safelyDroppedMissing && !safelyAdoptedIdentical && !safelyRefreshedTracked) {
      fail(`installer transaction has an unauthorized file-state delta: ${file} (${txFile})`);
    }
  }
}
function validateTransactionStageDir(tx, txFile, hostKey, allowMissing = false) {
  const transactionRoot = path.resolve(path.dirname(txFile));
  if (typeof tx.stageDir !== 'string' || !path.isAbsolute(tx.stageDir)) {
    fail(`invalid installer transaction stage directory: ${txFile}`);
  }
  const stageDir = path.resolve(tx.stageDir);
  const stageName = path.basename(stageDir);
  if (!samePath(path.dirname(stageDir), transactionRoot)
      || !new RegExp(`^${hostKey}-[0-9]+-[a-f0-9]{8}$`).test(stageName)) {
    fail(`invalid installer transaction stage directory: ${txFile}`);
  }
  assertNoLinkComponents(transactionRoot, 'transaction directory');
  assertNoLinkComponents(stageDir, 'transaction staging directory');
  const stat = lstatMaybe(stageDir);
  if (!stat) {
    if (allowMissing) return null;
    fail(`transaction staging directory is missing or invalid: ${stageDir}`);
  }
  if (!stat.isDirectory()) fail(`transaction staging directory is missing or invalid: ${stageDir}`);
  return stageDir;
}
function validateTransactionStageSet(stageDir, operations, txFile, committed) {
  if (stageDir === null && committed) return;
  const expected = new Set(
    operations.filter((op) => op.action === 'write').map((op) => path.basename(op.stage))
  );
  const entries = fs.readdirSync(stageDir, { withFileTypes: true });
  if (entries.some((entry) => !entry.isFile() || !expected.has(entry.name))
      || (!committed && entries.length !== expected.size)) {
    fail(`installer transaction staging directory has unexpected entries: ${txFile}`);
  }
}
function removePreparedTransaction(preparedFile, tx, opts, hostKey) {
  const canonical = transactionPath(opts, hostKey);
  if (fileExists(canonical)) {
    fail(`prepared installer transaction conflicts with a canonical transaction: ${preparedFile}`);
  }
  const state = readState(opts);
  if (transactionAnchor(state, hostKey)) {
    fail(`prepared installer transaction has an install-state anchor but no canonical transaction: ${preparedFile}`);
  }
  if (stateDigest(state) !== tx.preStateSha256) {
    fail(`prepared installer transaction prior state no longer matches current install state: ${preparedFile}`);
  }
  const transactionKinds = new Set(tx.kinds);
  const stageDir = validateTransactionStageDir(tx, preparedFile, hostKey);
  const validated = validateTransactionOperations(tx, preparedFile, hostKey, transactionKinds, opts);
  validateTransactionStageSet(stageDir, tx.operations, preparedFile, false);
  for (const { op, stagePath } of validated) {
    assertDestinationMatchesBefore(op, 'since transaction preparation');
    if (stagePath && sha256(readFile(stagePath)) !== op.hash) {
      fail(`prepared installer transaction has a corrupt staging file: ${op.dst}`);
    }
  }
  if (opts.dryRun) {
    fail(`prepared installer transaction cleanup is pending; dry-run made no changes: ${preparedFile}`);
  }
  for (const { stagePath } of validated) if (stagePath) fs.unlinkSync(stagePath);
  fs.unlinkSync(preparedFile);
  pruneUpwards(stageDir, path.join(stateDir(opts), TRANSACTION_DIR));
  pruneUpwards(path.dirname(preparedFile), stateDir(opts));
}
function reconcilePreparedTransactions(opts) {
  const root = path.join(stateDir(opts), TRANSACTION_DIR);
  const stat = lstatMaybe(root);
  if (!stat) return;
  if (!stat.isDirectory()) fail(`transaction directory must be a directory: ${root}`);
  assertNoLinkComponents(root, 'transaction directory');
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.name.endsWith('.prepared.json')) continue;
    if (!entry.isFile()) fail(`prepared installer transaction must be a regular file: ${path.join(root, entry.name)}`);
    const match = /^([a-z0-9-]+)-([a-f0-9]{32})\.prepared\.json$/.exec(entry.name);
    if (!match || !HOSTS[match[1]]) fail(`invalid prepared installer transaction filename: ${path.join(root, entry.name)}`);
    const preparedFile = path.join(root, entry.name);
    let tx;
    try { tx = JSON.parse(readFile(preparedFile).toString('utf8')); }
    catch (e) { fail(`prepared installer transaction is corrupt; refusing to continue: ${preparedFile} (${e.message})`); }
    if (!isPlainObject(tx) || tx.version !== TRANSACTION_VERSION || tx.host !== match[1] || tx.txId !== match[2]
        || !Array.isArray(tx.operations) || !isPlainObject(tx.preState) || !isPlainObject(tx.state)
        || !Array.isArray(tx.kinds) || !isPlainObject(tx.roots)
        || stateDigest(normalizeState(tx.preState, opts, preparedFile)) !== tx.preStateSha256
        || stateDigest(normalizeState(tx.state, opts, preparedFile)) !== tx.postStateSha256) {
      fail(`invalid prepared installer transaction: ${preparedFile}`);
    }
    const canonical = transactionPath(opts, match[1]);
    if (fileExists(canonical)) {
      fail(`prepared installer transaction conflicts with a canonical transaction: ${preparedFile}`);
    }
    const state = readState(opts);
    const anchor = transactionAnchor(state, match[1]);
    if (anchor) {
      assertTransactionAnchor(state, match[1], tx, 'pending', preparedFile);
      if (stateDigest(state) !== tx.preStateSha256) {
        fail(`prepared installer transaction prior state no longer matches current install state: ${preparedFile}`);
      }
      fs.renameSync(preparedFile, canonical);
      continue;
    }
    removePreparedTransaction(preparedFile, tx, opts, match[1]);
  }
}
function validateTransactionOperations(tx, txFile, hostKey, transactionKinds, opts) {
  const operationTargets = [];
  return tx.operations.map((op, index) => {
    if (!isPlainObject(op)
        || !hasOnlyKeys(op, new Set(['action', 'dst', 'kind', 'hash', 'stage', 'beforeHash', 'forceAuthorized']))
        || !['write', 'delete'].includes(op.action)
        || !['skill', 'command'].includes(op.kind) || !path.isAbsolute(op.dst)
        || typeof op.forceAuthorized !== 'boolean'
        || !Object.prototype.hasOwnProperty.call(op, 'beforeHash')
        || (op.beforeHash !== null && !/^[a-f0-9]{64}$/.test(op.beforeHash))) {
      fail(`invalid installer transaction operation: ${txFile}`);
    }
    if (!transactionKinds.has(op.kind)) {
      fail(`installer transaction operation kind was not selected: ${op.kind} (${txFile})`);
    }
    const host = HOSTS[hostKey];
    const root = expectedRoot(host, op.kind, opts);
    const anchor = expectedAnchor(hostKey, op.kind, opts);
    assertManagedLocationWithStaticRoots(anchor, root, op.dst, `transaction ${op.kind}`);
    if (operationTargets.some((target) => samePath(target, op.dst))) {
      fail(`installer transaction repeats a destination: ${op.dst}`);
    }
    operationTargets.push(op.dst);
    if (op.action === 'delete') {
      if (op.hash !== null || op.stage !== null) fail(`invalid transaction delete operation: ${txFile}`);
      return { op, stagePath: null };
    }
    const expectedStage = path.join(path.resolve(tx.stageDir), `${index}.stage`);
    if (!/^[a-f0-9]{64}$/.test(op.hash) || typeof op.stage !== 'string'
        || !path.isAbsolute(op.stage) || !samePath(op.stage, expectedStage)) {
      fail(`transaction write has an invalid staging path: ${op.dst}`);
    }
    assertNoLinkComponents(op.stage, 'transaction stage file');
    const stageStat = lstatMaybe(op.stage);
    if (stageStat && !stageStat.isFile()) fail(`transaction stage must be a regular file: ${op.stage}`);
    return { op, stagePath: expectedStage };
  });
}
function recoverTransaction(opts, hostKey, options = {}) {
  const txFile = transactionPath(opts, hostKey);
  assertNoLinkComponents(path.dirname(txFile), 'transaction directory');
  assertNoLinkComponents(txFile, 'transaction file');
  assertRegularFileOrMissing(txFile, 'transaction file');
  if (!fileExists(txFile)) return;
  let tx;
  try { tx = JSON.parse(readFile(txFile).toString('utf8')); }
  catch (e) { fail(`installer transaction is corrupt; refusing to continue: ${txFile} (${e.message})`); }
  if (isPlainObject(tx) && Number.isSafeInteger(tx.version) && tx.version !== TRANSACTION_VERSION) {
    fail(`unsupported installer transaction version ${tx.version}; expected ${TRANSACTION_VERSION}. No recovery changes were made; inspect and remove the transaction only after manual recovery: ${txFile}`);
  }
  if (!isPlainObject(tx) || tx.version !== TRANSACTION_VERSION || tx.host !== hostKey
      || !/^[a-f0-9]{32}$/.test(tx.txId)
      || !Array.isArray(tx.operations) || !isPlainObject(tx.preState)
      || !isPlainObject(tx.state) || !Array.isArray(tx.kinds)
      || tx.kinds.length === 0 || new Set(tx.kinds).size !== tx.kinds.length
      || tx.kinds.some((kind) => !['skill', 'command'].includes(kind))
      || !isPlainObject(tx.roots) || !hasOnlyKeys(tx.roots, new Set(tx.kinds))
      || tx.kinds.some((kind) => typeof tx.roots[kind] !== 'string' || !path.isAbsolute(tx.roots[kind]))
      || (tx.commandSkillRoot !== undefined && (typeof tx.commandSkillRoot !== 'string' || !path.isAbsolute(tx.commandSkillRoot)))
      || !/^[a-f0-9]{64}$/.test(tx.preStateSha256)
      || !/^[a-f0-9]{64}$/.test(tx.postStateSha256)) {
    fail(`invalid installer transaction: ${txFile}`);
  }
  const transactionKinds = new Set(tx.kinds);
  const transactionPreState = normalizeState(tx.preState, opts, txFile);
  const recoveredState = normalizeState(tx.state, opts, txFile);
  if (stateDigest(transactionPreState) !== tx.preStateSha256) {
    fail(`installer transaction prior-state digest mismatch: ${txFile}`);
  }
  if (stateDigest(recoveredState) !== tx.postStateSha256) {
    fail(`installer transaction post-state digest mismatch: ${txFile}`);
  }
  const locations = hostPaths(hostKey, opts);
  for (const kind of tx.kinds) {
    if (!samePath(tx.roots[kind], locations.roots[kind])) {
      fail(`installer transaction managed root mismatch (${kind}): ${txFile}`);
    }
  }
  const diskState = currentState(opts);
  const diskDigest = stateDigest(diskState);
  const recoveredDigest = stateDigest(recoveredState);
  const anchor = transactionAnchor(diskState, hostKey);
  if (!anchor) {
    fail(`installer transaction is not anchored by install state: ${txFile}`);
  }
  const committed = anchor.phase === 'committed';
  if (!['pending', 'committed'].includes(anchor.phase)) {
    fail(`installer transaction has an invalid install-state phase: ${txFile}`);
  }
  assertTransactionAnchor(diskState, hostKey, tx, anchor.phase, txFile);
  if (!committed && diskDigest !== tx.preStateSha256) {
    fail(`installer transaction prior state no longer matches current install state: ${txFile}`);
  }
  if (committed && !committedStateMatchesTransaction(
    diskState, recoveredState, transactionPreState, hostKey, tx.operations
  )) {
    fail(`committed installer transaction state does not match its authorized projection: ${txFile}`);
  }
  const { preFiles, postFiles: recoveredFiles } = validateHostStateDelta(
    hostKey, transactionPreState, recoveredState, txFile
  );
  const expectedPayloads = committed
    ? new Map()
    : expectedManagedPayloads(hostKey, opts, transactionKinds, tx.commandSkillRoot);
  if (tx.operations.some((op) => op && op.action === 'write' && op.kind === 'command') && !tx.commandSkillRoot) {
    fail(`installer transaction is missing its command Skill root: ${txFile}`);
  }
  const stageDir = validateTransactionStageDir(tx, txFile, hostKey, committed);
  const validatedOperations = validateTransactionOperations(
    tx, txFile, hostKey, transactionKinds, opts
  );
  if (committed) {
    validateTransactionStageSet(stageDir, tx.operations, txFile, true);
    const inspection = {
      hostKey,
      txFile,
      commandSkillRoot: null,
      committed: true,
      operations: tx.operations,
    };
    if (options.validateOnly) return inspection;
    if (opts.dryRun) {
      fail(`pending installer transaction requires recovery; dry-run made no changes: ${txFile}`);
    }
    for (const { stagePath } of validatedOperations) {
      if (!stagePath) continue;
      assertNoLinkComponents(stagePath, 'transaction stage file');
      assertRegularFileOrMissing(stagePath, 'transaction stage file');
      try { fs.unlinkSync(stagePath); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    }
    fs.unlinkSync(txFile);
    const cleared = currentState(opts);
    assertTransactionAnchor(cleared, hostKey, tx, 'committed', txFile);
    delete cleared.transactions[hostKey];
    writeState(opts, cleared);
    if (stageDir) pruneUpwards(stageDir, path.join(stateDir(opts), TRANSACTION_DIR));
    pruneUpwards(path.dirname(txFile), stateDir(opts));
    return inspection;
  }
  const pending = [];
  const stagedFiles = [];
  for (const { op, stagePath } of validatedOperations) {
    if (op.forceAuthorized && !opts.force) {
      fail(`installer transaction requires --force to recover: ${op.dst}`);
    }
    if (op.action === 'write') {
      const previousMeta = trackedMeta(preFiles, op.dst);
      const recoveredMeta = trackedMeta(recoveredFiles, op.dst);
      const expectedPayload = mappedValueByPath(expectedPayloads, op.dst);
      const expectedOwnership = previousMeta
        ? previousMeta.ownership
        : (op.beforeHash === null ? OWNED : ADOPTED);
      const matchesPayload = committed || (expectedPayload
        && expectedPayload.kind === op.kind && expectedPayload.hash === op.hash);
      if ((previousMeta && previousMeta.kind !== op.kind) || !recoveredMeta
          || recoveredMeta.kind !== op.kind || recoveredMeta.hash !== op.hash
          || recoveredMeta.ownership !== expectedOwnership || !matchesPayload) {
        fail(`transaction write is not authorized by recovered install state: ${op.dst}`);
      }
      const destinationHash = fileExists(op.dst) ? sha256(readFile(op.dst)) : null;
      const expectedForce = op.beforeHash !== null && (
        !previousMeta || previousMeta.ownership !== OWNED || op.beforeHash !== previousMeta.hash
      );
      if (op.forceAuthorized !== expectedForce) {
        fail(`installer transaction force authorization does not match prior state: ${op.dst}`);
      }
      if (op.forceAuthorized && !opts.force) {
        fail(`installer transaction requires --force to recover: ${op.dst}`);
      }
      if (!previousMeta && op.beforeHash === null && diskDigest === tx.preStateSha256
          && destinationHash === op.hash) {
        // A completed create and a pre-existing identical file are indistinguishable after a crash.
        recoveredMeta.ownership = ADOPTED;
      }
      const stageStat = lstatMaybe(stagePath);
      if (stageStat) stagedFiles.push(stagePath);
      if (destinationHash === op.hash) {
        if (stageStat && sha256(readFile(stagePath)) !== op.hash) {
          fail(`transaction write has a corrupt staging file: ${op.dst}`);
        }
        continue;
      }
      if (diskDigest === recoveredDigest) {
        fail(`committed installer transaction is missing its written destination: ${op.dst}`);
      }
      if (!stageStat || sha256(readFile(stagePath)) !== op.hash) {
        fail(`transaction write cannot be recovered; manual recovery required: ${op.dst}`);
      }
      if (fileExists(op.dst)) {
        const currentHash = sha256(readFile(op.dst));
        if (currentHash !== op.beforeHash) {
          fail(`transaction destination changed after interruption; refusing overwrite: ${op.dst}`);
        }
      } else if (op.beforeHash !== null) {
        fail(`transaction destination disappeared after interruption; refusing overwrite: ${op.dst}`);
      }
      pending.push(op);
    }
    if (op.action === 'delete') {
      const previousMeta = trackedMeta(preFiles, op.dst);
      const recoveredMeta = trackedMeta(recoveredFiles, op.dst);
      if (!previousMeta || previousMeta.kind !== op.kind || previousMeta.ownership !== OWNED || recoveredMeta) {
        fail(`transaction delete is not authorized by prior install ownership: ${op.dst}`);
      }
      if (op.forceAuthorized !== (op.beforeHash !== previousMeta.hash)) {
        fail(`installer transaction force authorization does not match prior state: ${op.dst}`);
      }
      if (!op.forceAuthorized && op.beforeHash !== previousMeta.hash) {
        fail(`transaction delete lacks unchanged prior owned authority: ${op.dst}`);
      }
      if (!fileExists(op.dst)) continue;
      if (diskDigest === recoveredDigest) {
        fail(`committed installer transaction still has its deleted destination: ${op.dst}`);
      }
      if (sha256(readFile(op.dst)) !== op.beforeHash) {
        fail(`transaction destination changed after interruption; refusing delete: ${op.dst}`);
      }
      pending.push(op);
    }
  }
  validateTransactionStageSet(stageDir, tx.operations, txFile, committed);
  validateTransactionFileDelta(
    preFiles, recoveredFiles, tx.operations, expectedPayloads, txFile, committed
  );
  const commandWriteIndexes = [];
  const skillWriteIndexes = [];
  const skillOperationIndexes = [];
  for (let index = 0; index < tx.operations.length; index++) {
    const op = tx.operations[index];
    if (op.kind === 'skill') skillOperationIndexes.push(index);
    if (op.action !== 'write') continue;
    if (op.kind === 'command') commandWriteIndexes.push(index);
    if (op.kind === 'skill') skillWriteIndexes.push(index);
  }
  const commands = commandWriteIndexes.length ? loadCommandManifest() : [];
  if (!committed && commandWriteIndexes.length && !skillOperationIndexes.length) {
    const canonicalRoot = validateCommandSkillRoot(
      tx.commandSkillRoot, commands, 'transaction command Skill root'
    );
    if (!samePath(canonicalRoot, tx.commandSkillRoot)) {
      fail(`transaction command Skill root changed identity: ${tx.commandSkillRoot}`);
    }
  }
  if (!committed && commandWriteIndexes.length && skillOperationIndexes.length) {
    const managedSkillRoot = expectedRoot(HOSTS[hostKey], 'skill', opts);
    if (!samePath(tx.commandSkillRoot, managedSkillRoot)
        || skillWriteIndexes.some((index) => index > commandWriteIndexes[0])) {
      fail(`installer transaction has an unsafe Skill/command recovery order: ${txFile}`);
    }
    validateProjectedCommandSkillRoot(
      tx.commandSkillRoot, commands, tx.operations, recoveredFiles, expectedPayloads,
      'recovered transaction command Skill root'
    );
  }
  const inspection = {
    hostKey,
    txFile,
    commandSkillRoot: !committed && commandWriteIndexes.length ? path.resolve(tx.commandSkillRoot) : null,
    committed,
    operations: tx.operations,
  };
  if (options.validateOnly) return inspection;
  if (opts.dryRun) {
    fail(`pending installer transaction requires recovery; dry-run made no changes: ${txFile}`);
  }
  injectTestDestinationMutation('after-recovery-validation');
  const applyPending = (selected) => {
    for (const op of pending.filter(selected)) {
      assertDestinationMatchesBefore(op, 'after recovery validation');
      if (op.action === 'write') writeAtomic(op.dst, readFile(op.stage));
      else fs.unlinkSync(op.dst);
    }
  };
  if (commandWriteIndexes.length && skillOperationIndexes.length) {
    applyPending((op) => op.kind === 'skill');
    applyPending((op) => op.kind !== 'skill');
  } else {
    applyPending(() => true);
  }
  const committedState = JSON.parse(JSON.stringify(recoveredState));
  committedState.transactions[hostKey] = {
    txId: tx.txId,
    phase: 'committed',
    intentSha256: transactionIntentSha256(tx),
  };
  writeState(opts, committedState);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_RECOVERY_STATE === '1') {
    throw new Error('injected installer failure after recovery state commit');
  }
  for (const stage of stagedFiles) try { fs.unlinkSync(stage); } catch (_) {}
  fs.unlinkSync(txFile);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_TX_CLEANUP === '1') {
    throw new Error('injected installer failure after transaction cleanup');
  }
  const cleared = currentState(opts);
  assertTransactionAnchor(cleared, hostKey, tx, 'committed', txFile);
  delete cleared.transactions[hostKey];
  writeState(opts, cleared);
  pruneUpwards(stageDir, path.join(stateDir(opts), TRANSACTION_DIR));
  pruneUpwards(path.dirname(txFile), stateDir(opts));
  return inspection;
}
function applyHostTransaction(opts, hostKey, preState, state, operations, kinds, commandSkillRoot) {
  if (opts.dryRun) return;
  if (!operations.length) {
    writeState(opts, state);
    return;
  }
  const txFile = transactionPath(opts, hostKey);
  injectTestDestinationMutation('after-plan');
  const txId = crypto.randomBytes(16).toString('hex');
  const preparedFile = preparedTransactionPath(opts, hostKey, txId);
  const stageDir = path.join(stateDir(opts), TRANSACTION_DIR, `${hostKey}-${process.pid}-${txId.slice(0, 8)}`);
  ensureSafeDirectory(stageDir, 'transaction staging directory');
  const txOps = operations.map((op, index) => {
    if (!Object.prototype.hasOwnProperty.call(op, 'beforeHash')) {
      fail(`planned installer operation is missing its before state: ${op.dst}`);
    }
    assertDestinationMatchesBefore(op, 'after planning');
    const beforeHash = op.beforeHash;
    const forceAuthorized = Boolean(op.forceAuthorized);
    if (op.action === 'delete') {
      return { action: 'delete', dst: op.dst, kind: op.kind, hash: null, stage: null, beforeHash, forceAuthorized };
    }
    const stage = path.join(stageDir, `${index}.stage`);
    writeAtomic(stage, op.content);
    return { action: 'write', dst: op.dst, kind: op.kind, hash: sha256(op.content), stage, beforeHash, forceAuthorized };
  });
  const tx = {
    version: TRANSACTION_VERSION,
    txId,
    host: hostKey,
    kinds: [...kinds].sort(),
    stageDir,
    operations: txOps,
    preState,
    preStateSha256: stateDigest(preState),
    state,
    postStateSha256: stateDigest(state),
    roots: Object.fromEntries([...kinds].sort().map((kind) => [kind, expectedRoot(HOSTS[hostKey], kind, opts)])),
    ...(kinds.has('command') && commandSkillRoot ? { commandSkillRoot: path.resolve(commandSkillRoot) } : {}),
  };
  const txBytes = Buffer.from(JSON.stringify(tx, null, 2) + '\n');
  writeAtomic(preparedFile, txBytes);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_TX_PREPARE === '1') {
    throw new Error('injected installer failure after transaction preparation');
  }
  const pendingState = JSON.parse(JSON.stringify(preState));
  pendingState.transactions[hostKey] = {
    txId: tx.txId,
    phase: 'pending',
    intentSha256: transactionIntentSha256(tx),
  };
  writeState(opts, pendingState);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_TX_ANCHOR_WRITE === '1') {
    throw new Error('injected installer failure after transaction anchor write');
  }
  fs.renameSync(preparedFile, txFile);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_TX_ANCHOR === '1') {
    throw new Error('injected installer failure after transaction anchor');
  }
  injectTestDestinationMutation('after-transaction-authorization');
  let completed = 0;
  for (const op of txOps) {
    const root = expectedRoot(HOSTS[hostKey], op.kind, opts);
    const anchor = expectedAnchor(hostKey, op.kind, opts);
    assertManagedLocationWithStaticRoots(anchor, root, op.dst, op.kind);
    assertDestinationMatchesBefore(op, 'after transaction authorization');
    if (op.action === 'delete') fs.unlinkSync(op.dst);
    else writeAtomic(op.dst, readFile(op.stage));
    completed++;
    if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_OP === String(completed)) {
      throw new Error('injected installer failure');
    }
  }
  const committedState = JSON.parse(JSON.stringify(state));
  committedState.transactions[hostKey] = {
    txId: tx.txId,
    phase: 'committed',
    intentSha256: transactionIntentSha256(tx),
  };
  writeState(opts, committedState);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_STATE === '1') {
    throw new Error('injected installer failure after state commit');
  }
  for (const op of txOps) if (op.stage) try { fs.unlinkSync(op.stage); } catch (_) {}
  fs.unlinkSync(txFile);
  if (process.env.CREATE_LOOP_TEST_FAIL_AFTER_TX_CLEANUP === '1') {
    throw new Error('injected installer failure after transaction cleanup');
  }
  const cleared = currentState(opts);
  assertTransactionAnchor(cleared, hostKey, tx, 'committed', txFile);
  delete cleared.transactions[hostKey];
  writeState(opts, cleared);
  pruneUpwards(stageDir, path.join(stateDir(opts), TRANSACTION_DIR));
  pruneUpwards(path.dirname(txFile), stateDir(opts));
  for (const op of operations) if (op.action === 'delete') pruneUpwards(path.dirname(op.dst), expectedRoot(HOSTS[hostKey], op.kind, opts));
}

function validateString(value, name, options = {}) {
  if (typeof value !== 'string' || (!options.allowEmpty && !value.trim())) fail(`command manifest ${name} must be a non-empty string`);
  if (options.singleLine && /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/u.test(value)) {
    fail(`command manifest ${name} must be one line without control or YAML line-separator characters`);
  }
}
function loadCommandManifest() {
  if (!fileExists(COMMAND_MANIFEST)) fail(`command manifest not found: ${COMMAND_MANIFEST}`);
  let manifest;
  try { manifest = JSON.parse(fs.readFileSync(COMMAND_MANIFEST, 'utf8')); }
  catch (e) { fail(`command manifest is not valid JSON: ${e.message}`); }
  const topKeys = new Set(['$schema', 'version', 'description', 'commands']);
  if (!isPlainObject(manifest) || !hasOnlyKeys(manifest, topKeys) || manifest.version !== 1 || !Array.isArray(manifest.commands) || !manifest.commands.length) {
    fail('command manifest must be a version 1 object with a non-empty commands array and no unknown fields');
  }
  if (manifest.$schema !== undefined) validateString(manifest.$schema, '$schema');
  if (manifest.description !== undefined) validateString(manifest.description, 'description');
  const ids = new Set();
  const bodies = new Set();
  const commandRootReal = fs.realpathSync(COMMAND_SRC);
  return manifest.commands.map((cmd, index) => {
    const label = `commands[${index}]`;
    if (!isPlainObject(cmd) || !hasOnlyKeys(cmd, new Set(['id', 'body', 'description', 'argumentHint']))) fail(`${label} has unknown fields`);
    validateString(cmd.id, `${label}.id`);
    validateString(cmd.body, `${label}.body`);
    validateString(cmd.description, `${label}.description`, { singleLine: true });
    if (cmd.argumentHint !== undefined) validateString(cmd.argumentHint, `${label}.argumentHint`, { singleLine: true });
    if (!/^[a-z0-9][a-z0-9-]*$/.test(cmd.id)) fail(`${label}.id is not a valid command slug`);
    if (cmd.body !== `${cmd.id}.md`) fail(`${label}.body must be exactly ${cmd.id}.md`);
    if (ids.has(cmd.id)) fail(`duplicate command id: ${cmd.id}`);
    if (bodies.has(cmd.body)) fail(`duplicate command body: ${cmd.body}`);
    ids.add(cmd.id); bodies.add(cmd.body);
    const bodyPath = path.resolve(COMMAND_SRC, cmd.body);
    if (!isWithin(COMMAND_SRC, bodyPath) || !fileExists(bodyPath) || fs.realpathSync(bodyPath) !== path.join(commandRootReal, cmd.body)) {
      fail(`command body must be a regular contained file: ${cmd.body}`);
    }
    const body = normalizeLf(fs.readFileSync(bodyPath, 'utf8')).replace(/^\s+/, '');
    if (body.startsWith('---\n')) fail(`command body must not contain frontmatter: ${cmd.body}`);
    return { ...cmd, _body: body };
  });
}

function commandSkillRefs(commands) {
  const refs = new Set();
  for (const cmd of commands) {
    const pattern = /(?:<CREATE_LOOP_SKILL_ROOT>\/)?((?:references|schemas|templates|scripts)\/[A-Za-z0-9_][A-Za-z0-9._/-]*)/g;
    for (const match of cmd._body.matchAll(pattern)) {
      refs.add(match[1]);
    }
  }
  return [...refs].sort();
}
function validateCommandSkillRef(relative) {
  const segments = relative.split('/');
  return segments.length >= 2
    && ['references', 'schemas', 'templates', 'scripts'].includes(segments[0])
    && segments.every((segment) => segment && segment !== '.' && segment !== '..' && !segment.includes('\\'));
}

function skillNameFromText(value) {
  const text = normalizeLf(value);
  if (!text.startsWith('---\n')) return null;
  const end = text.indexOf('\n---\n', 4);
  if (end === -1) return null;
  const names = [];
  for (const line of text.slice(4, end).split('\n')) {
    const match = /^name:\s*(.*?)\s*$/.exec(line);
    if (match) names.push(match[1].replace(/^(['"])(.*)\1$/, '$2'));
  }
  return names.length === 1 ? names[0] : null;
}

function skillNameFromFrontmatter(skillFile) {
  return skillNameFromText(fs.readFileSync(skillFile, 'utf8'));
}

function inspectCommandSkillRoot(candidate, commands) {
  const root = path.resolve(candidate);
  let rootStat;
  try { rootStat = fs.statSync(root); } catch (_) { return { error: `not a directory: ${root}` }; }
  if (!rootStat.isDirectory()) return { error: `not a directory: ${root}` };
  let canonicalRoot;
  try { canonicalRoot = realpathNative(root); } catch (e) { return { error: `cannot resolve root: ${root} (${e.message})` }; }
  const skillFile = path.join(root, 'SKILL.md');
  const skillStat = lstatMaybe(skillFile);
  if (!skillStat || !skillStat.isFile()) {
    return { error: `must contain a regular contained SKILL.md: ${root}` };
  }
  let canonicalSkillFile;
  try { canonicalSkillFile = realpathNative(skillFile); } catch (_) {
    return { error: `must contain a regular contained SKILL.md: ${root}` };
  }
  if (!isWithin(canonicalRoot, canonicalSkillFile)) return { error: `must contain a regular contained SKILL.md: ${root}` };
  if (skillNameFromFrontmatter(skillFile) !== SKILL_NAME) {
    return { error: `SKILL.md must declare exactly one name: ${SKILL_NAME} (${root})` };
  }
  for (const relative of commandSkillRefs(commands)) {
    if (!validateCommandSkillRef(relative)) {
      return { error: `command Skill reference is unsafe: ${relative}` };
    }
    const target = path.resolve(root, ...relative.split('/'));
    const stat = lstatMaybe(target);
    let canonicalTarget = null;
    try { if (stat && stat.isFile()) canonicalTarget = realpathNative(target); } catch (_) {}
    if (!stat || !stat.isFile() || !canonicalTarget || !isWithin(canonicalRoot, canonicalTarget)) {
      return { error: `missing a regular contained command dependency: ${relative} (${root})` };
    }
  }
  return { root: canonicalRoot };
}

function validateCommandSkillRoot(candidate, commands, label = 'Skill root') {
  const inspected = inspectCommandSkillRoot(candidate, commands);
  if (inspected.error) fail(`${label} ${inspected.error}`);
  return inspected.root;
}

function validateCommandSkillSource(commands) {
  assertNoStaticLinkComponents(PKG_ROOT, 'package root');
  assertNoStaticLinkComponents(SKILL_SRC, 'packaged Skill source');
  return validateCommandSkillRoot(SKILL_SRC, commands, 'packaged Skill source');
}

function validateCommandSkillProjection(
  root, commands, projected, label, recoveredFiles = null, expectedPayloads = null
) {
  const canonicalRoot = path.resolve(root);
  assertNoLinkComponents(canonicalRoot, label);
  const projectedFile = (relative) => {
    const target = path.resolve(canonicalRoot, ...relative.split('/'));
    if (!isWithin(canonicalRoot, target)) fail(`${label} contains an unsafe path: ${relative}`);
    const projectedEntry = [...projected.entries()].find(([candidate]) => samePath(candidate, target));
    let bytes;
    let touched = false;
    if (projectedEntry) {
      bytes = projectedEntry[1];
      touched = true;
    } else {
      const stat = lstatMaybe(target);
      if (!stat || !stat.isFile()) return null;
      let canonicalTarget;
      try { canonicalTarget = realpathNative(target); } catch (_) { return null; }
      if (!isWithin(canonicalRoot, canonicalTarget)) return null;
      bytes = readFile(target);
    }
    if (!bytes) return null;
    return { target, bytes, touched };
  };
  const validateExpected = (relative, projectedValue) => {
    if (!projectedValue.touched || !recoveredFiles || !expectedPayloads) return;
    const recoveredMeta = trackedMeta(recoveredFiles, projectedValue.target);
    const expectedPayload = mappedValueByPath(expectedPayloads, projectedValue.target);
    const hash = sha256(projectedValue.bytes);
    if (!recoveredMeta || recoveredMeta.kind !== 'skill' || recoveredMeta.hash !== hash
        || !expectedPayload || expectedPayload.kind !== 'skill' || expectedPayload.hash !== hash) {
      fail(`${label} has unexpected content: ${relative} (${canonicalRoot})`);
    }
  };
  const skill = projectedFile('SKILL.md');
  if (!skill || skillNameFromText(skill.bytes) !== SKILL_NAME) {
    fail(`${label} SKILL.md must declare exactly one name: ${SKILL_NAME} (${canonicalRoot})`);
  }
  validateExpected('SKILL.md', skill);
  for (const relative of commandSkillRefs(commands)) {
    if (!validateCommandSkillRef(relative)) fail(`command Skill reference is unsafe: ${relative}`);
    const dependency = projectedFile(relative);
    if (!dependency) {
      fail(`${label} missing a regular contained command dependency: ${relative} (${canonicalRoot})`);
    }
    validateExpected(relative, dependency);
  }
}

function validateProjectedCommandSkillRoot(
  root, commands, operations, recoveredFiles, expectedPayloads, label = 'projected Skill root'
) {
  const canonicalRoot = path.resolve(root);
  const projected = new Map();
  for (const op of operations) {
    if (op.kind !== 'skill') continue;
    const target = path.resolve(op.dst);
    const relative = path.relative(canonicalRoot, target);
    if (!relative || relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) {
      fail(`${label} contains an operation outside its root: ${op.dst}`);
    }
    if (op.action === 'delete') {
      projected.set(target, null);
      continue;
    }
    const stage = lstatMaybe(op.stage);
    const bytes = stage && stage.isFile() ? readFile(op.stage) : readFile(op.dst);
    projected.set(target, bytes);
  }
  validateCommandSkillProjection(root, commands, projected, label, recoveredFiles, expectedPayloads);
}

function validatePlannedCommandSkillRoot(
  root, commands, operations, label = 'planned Skill root', baseProjection = null
) {
  const canonicalRoot = path.resolve(root);
  const projected = new Map(baseProjection || []);
  for (const op of operations) {
    if (op.kind !== 'skill') continue;
    const target = path.resolve(op.dst);
    const relative = path.relative(canonicalRoot, target);
    if (!relative || relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) {
      fail(`${label} contains an operation outside its root: ${op.dst}`);
    }
    if (op.action === 'delete') projected.set(target, null);
    else if (Buffer.isBuffer(op.content)) projected.set(target, op.content);
    else fail(`${label} has an invalid planned write: ${op.dst}`);
  }
  validateCommandSkillProjection(root, commands, projected, label);
}

function pendingOperationProjection(pending) {
  const projected = new Map();
  for (const item of pending) {
    if (item.committed) continue;
    for (const op of item.operations) {
      const target = path.resolve(op.dst);
      if (op.action === 'delete') projected.set(target, null);
      else if (fileExists(op.stage)) projected.set(target, readFile(op.stage));
      else projected.set(target, readFile(op.dst));
    }
  }
  return projected;
}

function packageSkillProjectionForHosts(opts, hosts) {
  const projected = new Map();
  for (const hostKey of hosts) {
    const root = hostPaths(hostKey, opts).roots.skill;
    for (const src of listFilesRecursive(SKILL_SRC)) {
      projected.set(path.resolve(root, path.relative(SKILL_SRC, src)), readFile(src));
    }
  }
  return projected;
}

function commandSkillRootCandidates(opts, hosts) {
  const shared = opts.scope === 'global'
    ? path.join(os.homedir(), '.agents', 'skills', SKILL_NAME)
    : path.join(opts.project, '.agents', 'skills', SKILL_NAME);
  const candidates = [];
  if (hosts.includes('opencode') || hosts.includes('claude')) candidates.push(shared);
  if (!hosts.includes('claude')) return candidates;
  if (opts.scope === 'global') {
    candidates.push(path.join(claudeHome(), 'skills', SKILL_NAME));
  } else {
    candidates.push(path.join(opts.project, '.claude', 'skills', SKILL_NAME));
  }
  return candidates;
}

function discoverCommandSkillRoot(opts, commands, hosts) {
  if (opts.skillRoot) return validateCommandSkillRoot(opts.skillRoot, commands, 'explicit Skill root');
  const candidates = commandSkillRootCandidates(opts, hosts);
  const valid = [];
  const invalid = [];
  for (const candidate of candidates) {
    const inspected = inspectCommandSkillRoot(candidate, commands);
    if (inspected.error) {
      invalid.push(`  - ${path.resolve(candidate)} (${inspected.error})`);
      continue;
    }
    if (!valid.some((existing) => samePath(existing, inspected.root))) valid.push(inspected.root);
  }
  if (valid.length === 1) return valid[0];
  if (!valid.length) {
    fail(`commands-only install could not find a valid create-loop Skill root. Checked:\n${invalid.join('\n')}\nInstall the Skill first or pass --skill-root <dir>.`);
  }
  fail(`commands-only install found multiple create-loop Skill roots:\n${valid.map((item) => `  - ${item}`).join('\n')}\nPass --skill-root <dir> to choose one.`);
}

function resolveHosts(opts) {
  if (opts.hosts && opts.hosts.length) {
    const unique = [...new Set(opts.hosts)];
    for (const h of unique) if (!HOSTS[h]) fail(`unknown host: ${h} (known: ${Object.keys(HOSTS).join(', ')})`);
    return unique;
  }
  const detected = Object.keys(HOSTS).filter((key) => HOSTS[key].detect(opts.scope, opts.project));
  return detected.length ? detected : Object.keys(HOSTS);
}
function selectedKinds(opts) {
  if (opts.commandsOnly) return new Set(['command']);
  if (opts.skillOnly) return new Set(['skill']);
  return new Set(['skill', 'command']);
}

function reconcileTransactionAnchors(opts) {
  const state = readState(opts);
  const committed = [];
  for (const [hostKey, anchor] of Object.entries(state.transactions || {})) {
    if (fileExists(transactionPath(opts, hostKey))) continue;
    if (anchor.phase !== 'committed') {
      fail(`install state transaction anchor has no transaction file (${hostKey}): ${statePath(opts)}`);
    }
    committed.push(hostKey);
  }
  if (!committed.length) return;
  if (opts.dryRun) {
    fail(`committed installer transaction cleanup is pending; dry-run made no changes: ${statePath(opts)}`);
  }
  const current = readState(opts);
  for (const hostKey of committed) {
    const expected = state.transactions[hostKey];
    const actual = current.transactions[hostKey];
    if (!actual || actual.phase !== 'committed' || actual.txId !== expected.txId
        || actual.intentSha256 !== expected.intentSha256) {
      fail(`install state transaction receipt changed before cleanup (${hostKey}): ${statePath(opts)}`);
    }
    delete current.transactions[hostKey];
  }
  writeState(opts, current);
}

function inspectPendingTransactions(opts) {
  reconcilePreparedTransactions(opts);
  reconcileTransactionAnchors(opts);
  const state = readState(opts);
  const inspections = Object.keys(HOSTS)
    .map((hostKey) => recoverTransaction(opts, hostKey, { validateOnly: true }))
    .filter(Boolean);
  return inspections;
}

function resolveInstallCommandSkillRoot(opts, commands, hosts, pending) {
  if (!opts.commandsOnly) return null;
  if (opts.skillRoot) return validateCommandSkillRoot(opts.skillRoot, commands, 'explicit Skill root');
  const roots = [];
  for (const item of pending) {
    if (!hosts.includes(item.hostKey) || !item.commandSkillRoot) continue;
    if (!roots.some((root) => samePath(root, item.commandSkillRoot))) roots.push(item.commandSkillRoot);
  }
  if (roots.length === 1) return roots[0];
  if (roots.length > 1) {
    fail(`pending command transactions reference multiple create-loop Skill roots:\n${roots.map((item) => `  - ${item}`).join('\n')}\nRecover them with an explicit compatible invocation before choosing a new root.`);
  }
  return discoverCommandSkillRoot(opts, commands, hosts);
}

function buildInstallPlans(
  opts, kinds, commands, hosts, state, commandSkillRoot, emitWarnings,
  pendingProjection = null
) {
  const summary = [];
  const plans = [];
  for (const hostKey of hosts) {
    const host = HOSTS[hostKey];
    const prev = state.hosts[hostKey] || null;
    const next = emptyHostRecord(hostKey, opts.scope, prev);
    const locations = hostPaths(hostKey, opts);
    const renderedSkillRoot = commandSkillRoot || locations.roots.skill;
    const hostOpts = { ...opts, _roots: locations.roots, _anchors: locations.anchors };
    next.roots = locations.roots;
    next.anchors = locations.anchors;
    const stats = { created: 0, updated: 0, unchanged: 0, adopted: 0, 'skipped-user': 0, dry: 0, obsolete: 0, preserved: 0, unsafe: 0 };
    const desired = new Set();
    const operations = [];
    if (prev) {
      for (const [abs, meta] of Object.entries(prev.files)) if (!kinds.has(meta.kind)) next.files[abs] = meta;
    }
    if (kinds.has('skill')) {
      if (!dirExists(SKILL_SRC)) fail(`skill source not found: ${SKILL_SRC}`);
      for (const src of listFilesRecursive(SKILL_SRC)) {
        const dst = path.resolve(locations.roots.skill, path.relative(SKILL_SRC, src));
        desired.add(dst);
        const planned = planManaged(dst, readFile(src), 'skill', prev, next, hostOpts);
        stats[planned.action]++;
        if (planned.content) operations.push(planned);
      }
    }
    if (kinds.has('command')) {
      for (const cmd of commands) {
        const dst = path.resolve(locations.roots.command, `${cmd.id}.md`);
        desired.add(dst);
        const planned = planManaged(dst, Buffer.from(host.renderCommand(cmd, cmd._body, {
          skillRoot: renderedSkillRoot,
        }), 'utf8'), 'command', prev, next, hostOpts);
        stats[planned.action]++;
        if (planned.content) operations.push(planned);
      }
    }
    planObsolete(hostKey, host, prev, next, kinds, desired, stats, hostOpts, operations, emitWarnings);
    const parts = Object.entries(stats).filter(([, count]) => count).map(([name, count]) => `${count} ${name}`);
    plans.push({ hostKey, next, operations, parts, commandSkillRoot: kinds.has('command') ? renderedSkillRoot : null });
    summary.push({ host: hostKey, label: host.label, roots: { ...locations.roots }, stats });
  }
  if (kinds.has('skill')) {
    for (const plan of plans) {
      validatePlannedCommandSkillRoot(
        plan.next.roots.skill, commands, plan.operations, `planned ${plan.hostKey} Skill root`,
        pendingProjection
      );
    }
  }
  return { plans, summary };
}

function cmdInstallUnlocked(opts) {
  const kinds = selectedKinds(opts);
  const commands = loadCommandManifest();
  const hosts = resolveHosts(opts);
  const pending = inspectPendingTransactions(opts);
  const commandSkillRoot = resolveInstallCommandSkillRoot(opts, commands, hosts, pending);
  const pendingProjection = pendingOperationProjection(pending);
  if (pending.length && kinds.has('command') && commandSkillRoot) {
    const currentProjection = new Map(pendingProjection);
    if (kinds.has('skill')) {
      for (const [target, bytes] of packageSkillProjectionForHosts(opts, hosts)) {
        currentProjection.set(target, bytes);
      }
    }
    validateCommandSkillProjection(
      commandSkillRoot, commands, currentProjection, 'projected current command Skill root'
    );
  }
  let state = readState(opts);
  let built = buildInstallPlans(
    opts, kinds, commands, hosts, state, commandSkillRoot, pending.length === 0,
    pendingProjection
  );
  if (pending.length) {
    for (const hostKey of Object.keys(HOSTS)) recoverTransaction(opts, hostKey);
    if (kinds.has('command') && commandSkillRoot) {
      const recoveredRoot = validateCommandSkillRoot(
        commandSkillRoot, commands, 'post-recovery command Skill root'
      );
      if (!samePath(recoveredRoot, commandSkillRoot)) {
        fail(`post-recovery command Skill root changed identity: ${commandSkillRoot}`);
      }
    }
    state = readState(opts);
    built = buildInstallPlans(opts, kinds, commands, hosts, state, commandSkillRoot, true);
  }
  const { plans, summary } = built;
  info(`create-loop v${PKG_VERSION} (${opts.scope}${opts.scope === 'project' ? ' @ ' + opts.project : ''}${opts.dryRun ? ', dry-run' : ''})`);
  for (const plan of plans) {
    const host = HOSTS[plan.hostKey];
    info(`\n${host.label}`);
    if (kinds.has('skill')) info(`  skill    -> ${plan.next.roots.skill}`);
    if (kinds.has('command')) info(`  commands -> ${plan.next.roots.command}`);
  }
  prepareLegacyBackup(opts);
  for (const plan of plans) {
    const preState = JSON.parse(JSON.stringify(state));
    state.hosts[plan.hostKey] = plan.next;
    applyHostTransaction(opts, plan.hostKey, preState, state, plan.operations, kinds, plan.commandSkillRoot);
    info('  ' + (plan.parts.length ? plan.parts.join(', ') : 'nothing to do'));
  }
  if (opts.dryRun) info('\ndry-run: no files written.');
  if (opts.json) process.stdout.write(JSON.stringify({ ok: true, version: PKG_VERSION, scope: opts.scope, project: opts.project, dryRun: opts.dryRun, results: summary }, null, 2) + '\n');
  return 0;
}

function cmdInstall(opts) {
  const kinds = selectedKinds(opts);
  const commands = loadCommandManifest();
  if (kinds.has('skill')) validateCommandSkillSource(commands);
  preflightStateStorage(opts);
  return withStateLock(opts, () => cmdInstallUnlocked(opts));
}

function cmdUninstallUnlocked(opts) {
  const kinds = selectedKinds(opts);
  const explicitHosts = opts.hosts && opts.hosts.length ? resolveHosts(opts) : null;
  reconcilePreparedTransactions(opts);
  reconcileTransactionAnchors(opts);
  for (const hostKey of Object.keys(HOSTS)) recoverTransaction(opts, hostKey);
  const state = readState(opts);
  const hosts = explicitHosts
    ? explicitHosts
    : (Object.keys(state.hosts).length ? Object.keys(state.hosts) : resolveHosts(opts));
  const summary = [];
  const plans = [];
  info(`create-loop uninstall (${opts.scope}${opts.scope === 'project' ? ' @ ' + opts.project : ''}${opts.dryRun ? ', dry-run' : ''})`);
  for (const hostKey of hosts) {
    const host = HOSTS[hostKey];
    const rec = state.hosts[hostKey];
    let removed = 0, preserved = 0, unsafe = 0;
    if (!rec) { summary.push({ host: hostKey, removed, preserved, unsafe }); continue; }
    const kept = {};
    const operations = [];
    for (const [abs, meta] of Object.entries(rec.files)) {
      if (!kinds.has(meta.kind)) { kept[abs] = meta; continue; }
      if (!safeTrackedPath(host, abs, meta, opts)) {
        kept[abs] = meta; unsafe++; warn(`refusing to remove path outside managed ${meta.kind} root: ${abs}`); continue;
      }
      if (!fileExists(abs)) continue;
      if (meta.ownership !== OWNED) {
        kept[abs] = meta; preserved++; warn(`preserved pre-existing file (${meta.ownership}): ${abs}`); continue;
      }
      const beforeHash = sha256(readFile(abs));
      const changed = beforeHash !== meta.hash;
      if (changed && !opts.force) { kept[abs] = meta; preserved++; warn(`preserved user-edited file: ${abs}`); continue; }
      assertWritableDestination(abs, `uninstall ${meta.kind}`);
      if (!opts.dryRun) operations.push({
        action: 'delete', dst: abs, kind: meta.kind,
        beforeHash, forceAuthorized: changed && opts.force,
      });
      removed++;
    }
    const nextRecord = Object.keys(kept).length
      ? { ...rec, files: kept, updatedAt: new Date().toISOString() }
      : null;
    info(`\n${host.label}\n  ${removed} removed, ${preserved} preserved${unsafe ? `, ${unsafe} unsafe` : ''}`);
    summary.push({ host: hostKey, removed, preserved, unsafe });
    plans.push({ hostKey, nextRecord, operations });
  }
  prepareLegacyBackup(opts);
  for (const plan of plans) {
    const preState = JSON.parse(JSON.stringify(state));
    if (plan.nextRecord) state.hosts[plan.hostKey] = plan.nextRecord;
    else delete state.hosts[plan.hostKey];
    applyHostTransaction(opts, plan.hostKey, preState, state, plan.operations, kinds);
  }
  if (!opts.dryRun && !Object.keys(state.hosts).length) {
    try { fs.unlinkSync(statePath(opts)); } catch (_) {}
  }
  if (opts.json) process.stdout.write(JSON.stringify({ ok: true, action: 'uninstall', results: summary }, null, 2) + '\n');
  return 0;
}

function cmdUninstall(opts) {
  preflightStateStorage(opts);
  return withStateLock(opts, () => cmdUninstallUnlocked(opts));
}

function pruneUpwards(dir, stopAt) {
  const boundary = path.resolve(stopAt);
  let cur = path.resolve(dir);
  while (isWithin(boundary, cur)) {
    try {
      const stat = fs.lstatSync(cur);
      if (!stat.isDirectory() || stat.isSymbolicLink() || !samePath(realpathNative(cur), cur)) break;
      if (fs.readdirSync(cur).length !== 0) break;
      fs.rmdirSync(cur);
    } catch (_) { break; }
    cur = path.dirname(cur);
  }
}

function renderTargets() {
  return [
    { host: 'opencode', dir: path.join(PKG_ROOT, '.opencode', 'command') },
    { host: 'claude', dir: path.join(PKG_ROOT, '.claude', 'commands') },
  ];
}
function directorySnapshot(dir) {
  if (!dirExists(dir)) return new Map();
  const result = new Map();
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile()) result.set(entry.name + '/', null);
    else result.set(entry.name, readFile(path.join(dir, entry.name)));
  }
  return result;
}
function assertSafeRenderDirectory(dir) {
  const root = path.resolve(PKG_ROOT);
  const target = path.resolve(dir);
  if (!isWithin(root, target)) fail(`render target is outside package root: ${target}`);
  assertNoLinkComponents(root, 'package root');
  assertNoLinkComponents(target, 'render target');
  const stat = lstatMaybe(target);
  if (stat && !stat.isDirectory()) fail(`render target must be a regular directory: ${target}`);
  if (!stat) assertWritableDestination(path.join(target, '.create-loop-preflight'), 'render target');
  else {
    try { fs.accessSync(target, fs.constants.W_OK); } catch (_) { fail(`render target is not writable: ${target}`); }
    for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
      const full = path.join(target, entry.name);
      const item = fs.lstatSync(full);
      if (!item.isFile() || item.isSymbolicLink() || !samePath(realpathNative(full), full)) {
        fail(`render target contains an unsafe non-regular entry: ${full}`);
      }
    }
  }
}
function sameSnapshot(a, b) {
  if (a.size !== b.size) return false;
  for (const [name, content] of a) {
    const other = b.get(name);
    if (!Buffer.isBuffer(content) || !Buffer.isBuffer(other) || !content.equals(other)) return false;
  }
  return true;
}
function replaceDirectoryExact(src, dst) {
  assertSafeRenderDirectory(dst);
  ensureSafeDirectory(dst, 'render target');
  const expected = new Set(fs.readdirSync(src));
  for (const name of fs.readdirSync(dst)) {
    if (!expected.has(name)) fs.unlinkSync(path.join(dst, name));
  }
  for (const name of expected) writeAtomic(path.join(dst, name), readFile(path.join(src, name)));
}
function cmdRender(opts) {
  const commands = loadCommandManifest();
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'create-loop-render-'));
  let drift = false;
  try {
    const targets = renderTargets();
    for (const target of targets) assertSafeRenderDirectory(target.dir);
    for (const target of targets) {
      const tempDir = path.join(tempRoot, target.host);
      ensureDir(tempDir);
      for (const cmd of commands) {
        const content = Buffer.from(HOSTS[target.host].renderCommand(cmd, cmd._body), 'utf8');
        fs.writeFileSync(path.join(tempDir, `${cmd.id}.md`), content);
      }
      const matches = sameSnapshot(directorySnapshot(tempDir), directorySnapshot(target.dir));
      if (!matches) drift = true;
      if (opts.check || opts.dryRun) {
        info(`  ${target.host}: ${matches ? 'up to date' : 'would change'}`);
      } else if (!matches) {
        replaceDirectoryExact(tempDir, target.dir);
        info(`  ${target.host}: rendered ${commands.length} commands`);
      } else {
        info(`  ${target.host}: up to date`);
      }
    }
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
  if (opts.check && drift) fail('rendered command files are out of date; run `node bin/create-loop.js render`');
  if (!opts.check && !opts.dryRun) info(`rendered ${commands.length} commands for ${renderTargets().length} hosts.`);
  return 0;
}

function cmdList(opts) {
  const commands = loadCommandManifest();
  info(`create-loop v${PKG_VERSION} scope=${opts.scope}${opts.scope === 'project' ? ' project=' + opts.project : ''}`);
  info('commands: ' + commands.map((cmd) => '/' + cmd.id).join('  '));
  for (const [key, host] of Object.entries(HOSTS)) {
    info(`\n${host.label}${host.detect(opts.scope, opts.project) ? ' [detected]' : ' [not detected]'}`);
    info(`  skill    ${host.skillDir(opts.scope, opts.project)}`);
    info(`  commands ${host.commandDir(opts.scope, opts.project)}`);
  }
  return 0;
}

function parseArgs(argv) {
  const opts = { command: null, scope: 'project', project: process.cwd(), hosts: null, skillRoot: null, force: false, dryRun: false, json: false, commandsOnly: false, skillOnly: false, check: false };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '-g': case '--global': opts.scope = 'global'; break;
      case '-p': case '--project': if (!argv[i + 1]) fail(`${arg} requires a directory`); opts.scope = 'project'; opts.project = path.resolve(argv[++i]); break;
      case '-H': case '--host': if (!argv[i + 1]) fail(`${arg} requires a host list`); opts.hosts = argv[++i].split(',').map((s) => s.trim()).filter(Boolean); break;
      case '--skill-root': if (!argv[i + 1]) fail(`${arg} requires a directory`); opts.skillRoot = path.resolve(argv[++i]); break;
      case '--commands-only': opts.commandsOnly = true; break;
      case '--skill-only': opts.skillOnly = true; break;
      case '-f': case '--force': opts.force = true; break;
      case '-y': case '--yes': break;
      case '-n': case '--dry-run': opts.dryRun = true; break;
      case '--check': opts.check = true; break;
      case '--json': opts.json = true; break;
      case '-q': case '--quiet': QUIET = true; break;
      case '-h': case '--help': opts.command = 'help'; break;
      case '-v': case '--version': opts.command = 'version'; break;
      default: if (arg.startsWith('-')) fail(`unknown option: ${arg}`); else rest.push(arg);
    }
  }
  if (!opts.command) opts.command = rest.shift() || 'install';
  if (rest.length) fail(`unexpected argument: ${rest[0]}`);
  if (opts.commandsOnly && opts.skillOnly) fail('--commands-only and --skill-only are mutually exclusive');
  if (opts.skillRoot && (opts.command !== 'install' || !opts.commandsOnly || opts.skillOnly)) {
    fail('--skill-root is only valid with install --commands-only');
  }
  if (opts.check && opts.command !== 'render') fail('--check is only valid with render');
  return opts;
}

const HELP = `create-loop - install the create-loop skill and slash commands.

Usage: create-loop [install|render|uninstall|list] [options]

  -g, --global          install into user-level host directories
  -p, --project <dir>   install into a project (default: current directory)
  -H, --host <a,b>      target opencode and/or claude
      --commands-only   operate only on slash commands
      --skill-root <dir> Skill root embedded by commands-only install
      --skill-only      operate only on the skill
  -f, --force           overwrite user-edited owned files
  -n, --dry-run         report without writing
      --check           with render, fail if committed files differ
      --json            append a machine-readable summary
  -q, --quiet           suppress informational output
  -h, --help            show help
  -v, --version         show version
`;

function main() {
  const opts = parseArgs(process.argv.slice(2));
  switch (opts.command) {
    case 'install': case 'add': case 'i': return process.exit(cmdInstall(opts));
    case 'uninstall': case 'remove': case 'rm': return process.exit(cmdUninstall(opts));
    case 'render': return process.exit(cmdRender(opts));
    case 'list': case 'ls': return process.exit(cmdList(opts));
    case 'version': process.stdout.write(PKG_VERSION + '\n'); return process.exit(0);
    case 'help': process.stdout.write(HELP); return process.exit(0);
    default: fail(`unknown command: ${opts.command}`);
  }
}

main();
