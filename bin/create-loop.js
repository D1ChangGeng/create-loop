#!/usr/bin/env node
/*
 * create-loop — standalone installer CLI.
 *
 * Installs the create-loop skill AND its slash commands into a host agent's
 * directories in one command, tracks every written file in a hash-stamped
 * manifest, and treats a re-run as an idempotent upgrade that preserves files
 * the user has hand-edited. Zero runtime dependencies (Node >= 18).
 *
 * This mirrors the standalone-installer pattern used by BMAD-METHOD
 * (`npx bmad-method install`) and GitHub spec-kit (`specify`): a per-host
 * adapter table declares skill + command destinations, a bundled manifest is
 * the source of truth, and re-running the installer refreshes managed files
 * while leaving user customizations alone.
 *
 * Usage:
 *   npx github:D1ChangGeng/create-loop [command] [options]
 *
 * Commands:
 *   install            Install / upgrade the skill and commands (default)
 *   render             Regenerate the committed host command files from command/manifest.json
 *   uninstall          Remove files this installer previously wrote (per the manifest)
 *   list               Show detected hosts and resolved destinations
 *   help               Show help
 *
 * Options:
 *   -g, --global               Install into the user-level (global) host dirs
 *   -p, --project <dir>        Install into a project dir (default: cwd)
 *   -H, --host <h,h>           Comma-separated hosts (default: auto-detect, else all)
 *       --commands-only        Install only the slash commands (skip the skill)
 *       --skill-only           Install only the skill (skip the commands)
 *   -f, --force                Overwrite even user-modified files
 *   -y, --yes                  Non-interactive; assume yes (reserved; installer is already non-interactive)
 *   -n, --dry-run              Print what would happen; write nothing
 *       --json                 Machine-readable summary on stdout
 *   -q, --quiet                Only warnings and errors
 *   -h, --help                 Show help
 *   -v, --version              Show installer version
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

/* ------------------------------------------------------------------ *
 * Package roots. When run via `npx github:...`, __dirname is bin/, so
 * the package root is one level up; skill + command sources live there.
 * ------------------------------------------------------------------ */
const PKG_ROOT = path.resolve(__dirname, '..');
const SKILL_SRC = path.join(PKG_ROOT, 'skills', 'create-loop');
const COMMAND_SRC = path.join(PKG_ROOT, 'command');
const COMMAND_MANIFEST = path.join(COMMAND_SRC, 'manifest.json');
const SKILL_NAME = 'create-loop';
const STATE_BASENAME = 'install-state.json';
const MANIFEST_VERSION = 1;

let PKG_VERSION = '0.0.0';
try {
  PKG_VERSION = require(path.join(PKG_ROOT, 'package.json')).version || PKG_VERSION;
} catch (_) { /* ignore */ }

/* ------------------------------------------------------------------ *
 * Host adapter registry.
 *
 * Each host declares how to resolve its skill dir and command dir for both
 * project and global scope, plus a `renderCommand` that turns a canonical
 * command entry into that host's on-disk file. Paths are verified against the
 * vercel-labs/skills agent table and each host's own command-dir convention.
 * ------------------------------------------------------------------ */
const HOSTS = {
  opencode: {
    label: 'OpenCode',
    // Skill target matches `npx skills add`: the shared .agents/skills canonical
    // (project .agents/skills, global ~/.agents/skills) that OpenCode scans —
    // so installing here never duplicates a `skills add` install.
    skillDir: (scope, project) =>
      scope === 'global'
        ? path.join(os.homedir(), '.agents', 'skills', SKILL_NAME)
        : path.join(project, '.agents', 'skills', SKILL_NAME),
    commandDir: (scope, project) =>
      scope === 'global'
        ? path.join(configHome(), 'opencode', 'command')
        : path.join(project, '.opencode', 'command'),
    // Detected when the host's config dir already exists.
    detect: (scope, project) =>
      scope === 'global'
        ? dirExists(path.join(configHome(), 'opencode'))
        : dirExists(path.join(project, '.opencode')),
    renderCommand: (cmd, body) =>
      frontmatter([
        ['description', cmd.description],
        ['agent', 'build'],
      ]) + body,
  },

  claude: {
    label: 'Claude Code',
    skillDir: (scope, project) =>
      scope === 'global'
        ? path.join(claudeHome(), 'skills', SKILL_NAME)
        : path.join(project, '.claude', 'skills', SKILL_NAME),
    commandDir: (scope, project) =>
      scope === 'global'
        ? path.join(claudeHome(), 'commands')
        : path.join(project, '.claude', 'commands'),
    detect: (scope, project) =>
      scope === 'global'
        ? dirExists(claudeHome())
        : dirExists(path.join(project, '.claude')),
    renderCommand: (cmd, body) =>
      frontmatter(
        [
          ['description', cmd.description],
          cmd.argumentHint ? ['argument-hint', quote(cmd.argumentHint)] : null,
        ].filter(Boolean)
      ) + body,
  },
};

/* --------------------------- path helpers --------------------------- */
function configHome() {
  return process.env.XDG_CONFIG_HOME && process.env.XDG_CONFIG_HOME.trim()
    ? process.env.XDG_CONFIG_HOME
    : path.join(os.homedir(), '.config');
}
function claudeHome() {
  return process.env.CLAUDE_CONFIG_DIR && process.env.CLAUDE_CONFIG_DIR.trim()
    ? process.env.CLAUDE_CONFIG_DIR
    : path.join(os.homedir(), '.claude');
}
function dirExists(p) {
  try { return fs.statSync(p).isDirectory(); } catch (_) { return false; }
}
function fileExists(p) {
  try { return fs.statSync(p).isFile(); } catch (_) { return false; }
}

/* --------------------------- render helpers ------------------------- */
function quote(s) {
  return '"' + String(s).replace(/"/g, '\\"') + '"';
}
function frontmatter(pairs) {
  const lines = pairs.map(([k, v]) => `${k}: ${v}`);
  return `---\n${lines.join('\n')}\n---\n\n`;
}

/* --------------------------- fs primitives -------------------------- */
function sha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}
function readFile(p) {
  return fs.readFileSync(p);
}
function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}
function listFilesRecursive(root) {
  const out = [];
  const EXCLUDE_DIRS = new Set(['.git', '__pycache__', '__pypackages__', 'node_modules']);
  const EXCLUDE_FILES = new Set(['metadata.json', '.DS_Store']);
  (function walk(dir) {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return; }
    for (const e of entries) {
      if (e.isDirectory()) {
        if (EXCLUDE_DIRS.has(e.name)) continue;
        walk(path.join(dir, e.name));
      } else if (e.isFile()) {
        if (EXCLUDE_FILES.has(e.name)) continue;
        out.push(path.join(dir, e.name));
      }
    }
  })(root);
  return out;
}

/* --------------------------- logging -------------------------------- */
let QUIET = false;
const C = process.stdout.isTTY
  ? { dim: (s) => `\x1b[2m${s}\x1b[0m`, grn: (s) => `\x1b[32m${s}\x1b[0m`, ylw: (s) => `\x1b[33m${s}\x1b[0m`, red: (s) => `\x1b[31m${s}\x1b[0m`, bold: (s) => `\x1b[1m${s}\x1b[0m`, cyan: (s) => `\x1b[36m${s}\x1b[0m` }
  : { dim: (s) => s, grn: (s) => s, ylw: (s) => s, red: (s) => s, bold: (s) => s, cyan: (s) => s };
function info(msg) { if (!QUIET) process.stdout.write(msg + '\n'); }
function warn(msg) { process.stderr.write(C.ylw('warning: ') + msg + '\n'); }
function fail(msg) { process.stderr.write(C.red('error: ') + msg + '\n'); process.exit(1); }

/* --------------------------- install state ------------------------- *
 * One state file per (scope, root), holding a section per host. Stored
 * OUTSIDE any host skill/command dir so it survives commands-only and
 * skill-only runs and never pollutes a host directory. Records the sha256
 * of each file AS WRITTEN, so a later run tells "unchanged since we wrote
 * it" (safe to overwrite) from "user edited it" (preserve unless --force).
 * Global: ~/.config/create-loop/install-state.json
 * Project: <project>/.create-loop/install-state.json
 * ------------------------------------------------------------------- */
function stateDir(opts) {
  return opts.scope === 'global'
    ? path.join(configHome(), 'create-loop')
    : path.join(opts.project, '.create-loop');
}
function statePath(opts) {
  return path.join(stateDir(opts), STATE_BASENAME);
}
function readState(opts) {
  const p = statePath(opts);
  if (!fileExists(p)) return { manifestVersion: MANIFEST_VERSION, tool: 'create-loop', scope: opts.scope, hosts: {} };
  try {
    const s = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (!s.hosts) s.hosts = {};
    return s;
  } catch (_) {
    return { manifestVersion: MANIFEST_VERSION, tool: 'create-loop', scope: opts.scope, hosts: {} };
  }
}
function writeState(opts, state) {
  const dir = stateDir(opts);
  ensureDir(dir);
  fs.writeFileSync(statePath(opts), JSON.stringify(state, null, 2) + '\n');
}
function emptyHostRecord(host, scope) {
  return {
    host,
    scope,
    installerVersion: PKG_VERSION,
    installedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    files: {}, // absPath -> { hash, kind }
  };
}

/* ------------------------------------------------------------------- *
 * Core: write one managed file with three-way reconciliation.
 * Returns one of: 'created' | 'updated' | 'unchanged' | 'skipped-user' | 'dry'
 * ------------------------------------------------------------------- */
function writeManaged(absPath, content, kind, prev, next, opts) {
  const newHash = sha256(content);
  const record = { hash: newHash, kind };

  if (fileExists(absPath)) {
    const curHash = sha256(readFile(absPath));
    if (curHash === newHash) {
      next.files[absPath] = record;
      return 'unchanged';
    }
    const prevHash = prev && prev.files[absPath] && prev.files[absPath].hash;
    const userEdited = !prevHash || prevHash !== curHash;
    if (userEdited && !opts.force) {
      // We did not write the current on-disk content (or never tracked it):
      // treat as a user customization and preserve it.
      next.files[absPath] = prev && prev.files[absPath] ? prev.files[absPath] : record;
      return 'skipped-user';
    }
  }

  if (opts.dryRun) { next.files[absPath] = record; return 'dry'; }

  ensureDir(path.dirname(absPath));
  const existed = fileExists(absPath);
  fs.writeFileSync(absPath, content);
  next.files[absPath] = record;
  return existed ? 'updated' : 'created';
}

/* --------------------------- command loading ------------------------ */
function loadCommandManifest() {
  if (!fileExists(COMMAND_MANIFEST)) {
    fail(`command manifest not found at ${COMMAND_MANIFEST}`);
  }
  let m;
  try { m = JSON.parse(fs.readFileSync(COMMAND_MANIFEST, 'utf8')); }
  catch (e) { fail(`command manifest is not valid JSON: ${e.message}`); }
  if (!m || !Array.isArray(m.commands)) fail('command manifest has no "commands" array');
  return m.commands.map((c) => {
    const bodyPath = path.join(COMMAND_SRC, c.body);
    if (!fileExists(bodyPath)) fail(`command body missing: ${bodyPath}`);
    return { ...c, _body: fs.readFileSync(bodyPath, 'utf8').replace(/^\s+/, '') };
  });
}

/* ============================ commands ============================= */

function resolveHosts(opts) {
  if (opts.hosts && opts.hosts.length) {
    for (const h of opts.hosts) if (!HOSTS[h]) fail(`unknown host: ${h} (known: ${Object.keys(HOSTS).join(', ')})`);
    return opts.hosts;
  }
  const detected = Object.keys(HOSTS).filter((h) => HOSTS[h].detect(opts.scope, opts.project));
  return detected.length ? detected : Object.keys(HOSTS);
}

function cmdInstall(opts) {
  const commands = opts.skillOnly ? [] : loadCommandManifest();
  const hosts = resolveHosts(opts);
  const summary = [];

  info(C.bold(`create-loop v${PKG_VERSION}`) + C.dim(`  (${opts.scope}${opts.scope === 'project' ? ' @ ' + opts.project : ''}${opts.dryRun ? ', dry-run' : ''})`));
  info(C.dim(`hosts: ${hosts.join(', ')}`));

  const state = readState(opts);

  for (const hostKey of hosts) {
    const host = HOSTS[hostKey];
    const skillDir = host.skillDir(opts.scope, opts.project);
    const prev = state.hosts[hostKey] || null;
    const next = emptyHostRecord(hostKey, opts.scope);
    if (prev && prev.installedAt) next.installedAt = prev.installedAt;

    const stats = { created: 0, updated: 0, unchanged: 0, 'skipped-user': 0, dry: 0 };

    info('\n' + C.cyan(host.label));

    // 1. Skill files (verbatim copy of skills/create-loop/**).
    if (!opts.commandsOnly) {
      if (!dirExists(SKILL_SRC)) fail(`skill source not found: ${SKILL_SRC}`);
      for (const src of listFilesRecursive(SKILL_SRC)) {
        const rel = path.relative(SKILL_SRC, src);
        const dst = path.join(skillDir, rel);
        const res = writeManaged(dst, readFile(src), 'skill', prev, next, opts);
        stats[res]++;
      }
      info(`  skill  -> ${C.dim(skillDir)}`);
    }

    // 2. Command files (rendered per host).
    if (!opts.skillOnly && commands.length) {
      const cmdDir = host.commandDir(opts.scope, opts.project);
      for (const cmd of commands) {
        const content = Buffer.from(host.renderCommand(cmd, cmd._body), 'utf8');
        const dst = path.join(cmdDir, `${cmd.id}.md`);
        const res = writeManaged(dst, content, 'command', prev, next, opts);
        stats[res]++;
      }
      info(`  commands -> ${C.dim(cmdDir)}  ${C.dim('(' + commands.map((c) => '/' + c.id).join('  ') + ')')}`);
    }

    // 3. Persist the per-host record into the shared state file (unless dry-run).
    next.updatedAt = new Date().toISOString();
    state.hosts[hostKey] = next;

    const parts = [];
    if (stats.created) parts.push(C.grn(`${stats.created} created`));
    if (stats.updated) parts.push(C.grn(`${stats.updated} updated`));
    if (stats.unchanged) parts.push(C.dim(`${stats.unchanged} unchanged`));
    if (stats['skipped-user']) parts.push(C.ylw(`${stats['skipped-user']} preserved (user-edited; use --force to overwrite)`));
    if (stats.dry) parts.push(C.dim(`${stats.dry} would write`));
    info('  ' + (parts.length ? parts.join(C.dim(', ')) : C.dim('nothing to do')));

    summary.push({ host: hostKey, label: host.label, skillDir, stats });
  }

  if (!opts.dryRun) {
    state.updatedAt = new Date().toISOString();
    writeState(opts, state);
    info('\n' + C.grn('✓') + ' done. ' + C.dim('Re-run this command any time to upgrade in place.'));
    if (!opts.skillOnly) info(C.dim('  Type /loop- in a supported host to see the commands. Natural language ("create a loop") also works.'));
  } else {
    info('\n' + C.dim('dry-run: no files written.'));
  }

  if (opts.json) process.stdout.write(JSON.stringify({ ok: true, version: PKG_VERSION, scope: opts.scope, project: opts.project, dryRun: opts.dryRun, results: summary }, null, 2) + '\n');
  return 0;
}

function cmdUninstall(opts) {
  const hosts = resolveHosts(opts);
  const summary = [];
  info(C.bold(`create-loop uninstall`) + C.dim(`  (${opts.scope}${opts.scope === 'project' ? ' @ ' + opts.project : ''}${opts.dryRun ? ', dry-run' : ''})`));

  const state = readState(opts);

  for (const hostKey of hosts) {
    const host = HOSTS[hostKey];
    const rec = state.hosts[hostKey];
    info('\n' + C.cyan(host.label));
    if (!rec || !Object.keys(rec.files).length) { info('  ' + C.dim('nothing tracked here.')); summary.push({ host: hostKey, removed: 0, skipped: 0 }); continue; }

    let removed = 0, skipped = 0;
    const keptFiles = {};
    const touchedDirs = new Set();
    for (const [abs, meta] of Object.entries(rec.files)) {
      if (!fileExists(abs)) continue;
      const curHash = sha256(readFile(abs));
      if (curHash !== meta.hash && !opts.force) { skipped++; keptFiles[abs] = meta; warn(`preserved (user-edited): ${abs}`); continue; }
      if (opts.dryRun) { removed++; continue; }
      try { fs.unlinkSync(abs); removed++; touchedDirs.add(path.dirname(abs)); } catch (e) { warn(`could not remove ${abs}: ${e.message}`); keptFiles[abs] = meta; }
    }
    if (!opts.dryRun) {
      // Keep the per-host record if we preserved user-edited files, so a later
      // `uninstall --force` can still find and remove them. Drop it only once
      // everything tracked is gone.
      if (skipped === 0 && !Object.keys(keptFiles).length) delete state.hosts[hostKey];
      else { rec.files = keptFiles; state.hosts[hostKey] = rec; }
      const boundary = opts.scope === 'global' ? os.homedir() : opts.project;
      for (const d of touchedDirs) pruneUpwards(d, boundary);
    }
    info(`  ${C.grn(removed + ' removed')}${skipped ? C.dim(', ') + C.ylw(skipped + ' preserved') : ''}`);
    summary.push({ host: hostKey, removed, skipped });
  }
  if (!opts.dryRun) {
    if (Object.keys(state.hosts).length) writeState(opts, state);
    else { try { fs.unlinkSync(statePath(opts)); } catch (_) {} pruneEmptyDirs(stateDir(opts)); }
  }
  if (opts.json) process.stdout.write(JSON.stringify({ ok: true, action: 'uninstall', results: summary }, null, 2) + '\n');
  return 0;
}

function pruneEmptyDirs(dir) {
  let entries;
  try { entries = fs.readdirSync(dir); } catch (_) { return; }
  for (const e of entries) {
    const p = path.join(dir, e);
    let st; try { st = fs.statSync(p); } catch (_) { continue; }
    if (st.isDirectory()) pruneEmptyDirs(p);
  }
  try { if (fs.readdirSync(dir).length === 0) fs.rmdirSync(dir); } catch (_) {}
}

function pruneUpwards(dir, stopAt) {
  let cur = dir;
  while (cur && cur.startsWith(stopAt) && cur !== stopAt) {
    try { if (fs.readdirSync(cur).length === 0) fs.rmdirSync(cur); else break; } catch (_) { break; }
    cur = path.dirname(cur);
  }
}

/* render: regenerate the committed host command files at the repo root. */
function cmdRender(opts) {
  const commands = loadCommandManifest();
  const targets = [
    { host: 'opencode', dir: path.join(PKG_ROOT, '.opencode', 'command') },
    { host: 'claude', dir: path.join(PKG_ROOT, '.claude', 'commands') },
  ];
  info(C.bold('create-loop render') + C.dim('  (regenerating committed host command files from command/manifest.json)'));
  for (const t of targets) {
    const host = HOSTS[t.host];
    if (!opts.dryRun) ensureDir(t.dir);
    for (const cmd of commands) {
      const content = host.renderCommand(cmd, cmd._body);
      const dst = path.join(t.dir, `${cmd.id}.md`);
      if (opts.dryRun) { info('  would write ' + C.dim(dst)); continue; }
      fs.writeFileSync(dst, content);
      info('  ' + C.grn('wrote') + ' ' + C.dim(dst));
    }
  }
  info('\n' + C.grn('✓') + ' rendered ' + commands.length + ' commands for ' + targets.length + ' hosts.');
  return 0;
}

function cmdList(opts) {
  const commands = fileExists(COMMAND_MANIFEST) ? loadCommandManifest() : [];
  info(C.bold(`create-loop v${PKG_VERSION}`) + C.dim(`  scope=${opts.scope}${opts.scope === 'project' ? ' project=' + opts.project : ''}`));
  info(C.dim('commands: ') + commands.map((c) => '/' + c.id).join('  '));
  for (const hostKey of Object.keys(HOSTS)) {
    const host = HOSTS[hostKey];
    const detected = host.detect(opts.scope, opts.project);
    info('\n' + C.cyan(host.label) + (detected ? C.grn('  [detected]') : C.dim('  [not detected]')));
    info('  skill    ' + C.dim(host.skillDir(opts.scope, opts.project)));
    info('  commands ' + C.dim(host.commandDir(opts.scope, opts.project)));
  }
  return 0;
}

/* --------------------------- arg parsing ---------------------------- */
function parseArgs(argv) {
  const opts = {
    command: null,
    scope: 'project',
    project: process.cwd(),
    hosts: null,
    force: false,
    dryRun: false,
    json: false,
    yes: false,
    commandsOnly: false,
    skillOnly: false,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '-g': case '--global': opts.scope = 'global'; break;
      case '-p': case '--project': opts.scope = 'project'; opts.project = path.resolve(argv[++i] || '.'); break;
      case '-H': case '--host': opts.hosts = (argv[++i] || '').split(',').map((s) => s.trim()).filter(Boolean); break;
      case '--commands-only': opts.commandsOnly = true; break;
      case '--skill-only': opts.skillOnly = true; break;
      case '-f': case '--force': opts.force = true; break;
      case '-y': case '--yes': opts.yes = true; break;
      case '-n': case '--dry-run': opts.dryRun = true; break;
      case '--json': opts.json = true; break;
      case '-q': case '--quiet': QUIET = true; break;
      case '-h': case '--help': opts.command = 'help'; break;
      case '-v': case '--version': opts.command = 'version'; break;
      default:
        if (a.startsWith('-')) fail(`unknown option: ${a}`);
        rest.push(a);
    }
  }
  if (!opts.command) opts.command = rest.shift() || 'install';
  if (opts.commandsOnly && opts.skillOnly) fail('--commands-only and --skill-only are mutually exclusive');
  return opts;
}

const HELP = `${C.bold('create-loop')} — install the create-loop skill and slash commands into your agent.

${C.bold('Usage')}
  npx github:D1ChangGeng/create-loop [command] [options]

${C.bold('Commands')}
  install            Install / upgrade the skill and commands (default)
  render             Regenerate the committed host command files from command/manifest.json
  uninstall          Remove files this installer previously wrote (per its manifest)
  list               Show detected hosts and resolved destinations
  version            Print the installer version
  help               Show this help

${C.bold('Options')}
  -g, --global               Install into user-level (global) host dirs
  -p, --project <dir>        Install into a project dir (default: current dir)
  -H, --host <a,b>           Comma-separated hosts (${Object.keys(HOSTS).join(', ')}); default auto-detect
      --commands-only        Install only the slash commands
      --skill-only           Install only the skill
  -f, --force                Overwrite even user-modified files
  -n, --dry-run              Show what would happen; write nothing
      --json                 Machine-readable summary
  -q, --quiet                Only warnings and errors
  -h, --help                 Show this help
  -v, --version              Show version

${C.bold('Examples')}
  npx github:D1ChangGeng/create-loop                       ${C.dim('# auto-detect hosts, install into ./')}
  npx github:D1ChangGeng/create-loop -g                    ${C.dim('# global install for all projects')}
  npx github:D1ChangGeng/create-loop --host claude -g      ${C.dim('# Claude Code, global')}
  npx github:D1ChangGeng/create-loop --dry-run             ${C.dim('# preview')}
  npx github:D1ChangGeng/create-loop uninstall             ${C.dim('# clean removal')}

Re-running ${C.bold('install')} upgrades in place. Files you hand-edit are preserved
unless you pass --force. ${C.dim('npx skills add installs only the skill; this installer')}
${C.dim('adds the slash commands too.')}
`;

function main() {
  const opts = parseArgs(process.argv.slice(2));
  switch (opts.command) {
    case 'install': case 'add': case 'i': return process.exit(cmdInstall(opts));
    case 'uninstall': case 'remove': case 'rm': return process.exit(cmdUninstall(opts));
    case 'render': return process.exit(cmdRender(opts));
    case 'list': case 'ls': return process.exit(cmdList(opts));
    case 'version': process.stdout.write(PKG_VERSION + '\n'); return process.exit(0);
    case 'help': process.stdout.write(HELP + '\n'); return process.exit(0);
    default: fail(`unknown command: ${opts.command} (try: install, render, uninstall, list, help)`);
  }
}

main();
