#!/usr/bin/env node
/* Reproducible Node 18.20.8 / 24.13.0 renderer and installer matrix. */
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const VERSIONS = ['18.20.8', '24.13.0'];
const OFFICIAL_SHA256 = {
  win32: {
    '18.20.8': '1a1e40260a6facba83636e4cd0ba01eb5bd1386896824b36645afba44857384a',
    '24.13.0': 'ca2742695be8de44027d71b3f53a4bdb36009b95575fe1ae6f7f0b5ce091cb88',
  },
  linux: {
    '18.20.8': '5467ee62d6af1411d46b6a10e3fb5cacc92734dbcef465fea14e7b90993001c9',
    '24.13.0': 'e798599612f4bb71333a3397ab0d095fd62214e115aea45aa858a145fc72d67e',
  },
};

function fail(message) { throw new Error(message); }
function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}
function run(file, args, options = {}) {
  const result = spawnSync(file, args, {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: options.capture ? 'pipe' : 'inherit',
    env: process.env,
  });
  if (result.error) fail(`${file} could not start: ${result.error.message}`);
  if (result.status !== 0) {
    fail(`${file} ${args.join(' ')} exited ${result.status}${result.stderr ? `: ${result.stderr.trim()}` : ''}`);
  }
  return result;
}
function archiveName(version) {
  if (process.platform === 'win32') return `node-v${version}-win-x64.zip`;
  if (process.platform === 'linux') return `node-v${version}-linux-x64.tar.xz`;
  fail(`unsupported platform for the frozen Node matrix: ${process.platform}`);
}
function executableName() { return process.platform === 'win32' ? 'node.exe' : 'bin/node'; }
function download(url, destination) {
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  const temporary = `${destination}.${process.pid}.tmp`;
  try {
    if (process.platform === 'win32') {
      run('powershell.exe', [
        '-NoProfile', '-NonInteractive', '-Command',
        `Invoke-WebRequest -UseBasicParsing -Uri '${url}' -OutFile '${temporary.replace(/'/g, "''")}'`,
      ]);
    } else {
      run('curl', ['--fail', '--location', '--proto', '=https', '--tlsv1.2', '--output', temporary, url]);
    }
    fs.renameSync(temporary, destination);
  } finally {
    try { fs.unlinkSync(temporary); } catch (_) {}
  }
}
function extract(archive, destination) {
  const parent = path.dirname(destination);
  fs.mkdirSync(parent, { recursive: true });
  const temporary = fs.mkdtempSync(path.join(parent, '.node-extract-'));
  try {
    if (process.platform === 'win32') {
      run('powershell.exe', [
        '-NoProfile', '-NonInteractive', '-Command',
        `Expand-Archive -LiteralPath '${archive.replace(/'/g, "''")}' -DestinationPath '${temporary.replace(/'/g, "''")}' -Force`,
      ]);
    } else {
      run('tar', ['-xJf', archive, '-C', temporary]);
    }
    const entries = fs.readdirSync(temporary);
    if (entries.length !== 1) fail(`unexpected Node archive root: ${entries.join(', ')}`);
    fs.renameSync(path.join(temporary, entries[0]), destination);
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}
function provision(version, cacheRoot, allowDownload) {
  const destination = path.join(cacheRoot, `node-v${version}-${process.platform}-x64`);
  const executable = path.join(destination, executableName());
  if (!fs.existsSync(executable)) {
    if (!allowDownload) fail(`Node ${version} is absent from ${cacheRoot}; rerun with --download`);
    const name = archiveName(version);
    const archive = path.join(cacheRoot, 'downloads', name);
    if (!fs.existsSync(archive)) download(`https://nodejs.org/dist/v${version}/${name}`, archive);
    const expected = OFFICIAL_SHA256[process.platform][version];
    const actual = sha256(archive);
    if (actual !== expected) fail(`official Node ${version} archive hash mismatch: ${actual}`);
    extract(archive, destination);
  }
  const reported = run(executable, ['--version'], { capture: true }).stdout.trim();
  if (reported !== `v${version}`) fail(`expected Node v${version}, got ${reported}`);
  return executable;
}
function main() {
  const args = new Set(process.argv.slice(2));
  for (const arg of args) {
    if (!['--download', '--full'].includes(arg)) fail(`unknown option: ${arg}`);
  }
  const cacheRoot = path.resolve(
    process.env.CREATE_LOOP_NODE_MATRIX_CACHE
      || path.join(os.homedir(), '.cache', 'create-loop', 'node-matrix')
  );
  for (const version of VERSIONS) {
    const node = provision(version, cacheRoot, args.has('--download'));
    console.log(`\nNode v${version}: render --check`);
    run(node, ['bin/create-loop.js', 'render', '--check']);
    if (args.has('--full')) {
      console.log(`Node v${version}: installer/package regression`);
      run(node, ['test/installer.test.js']);
    }
  }
  console.log(`\nNODE MATRIX OK: ${VERSIONS.join(', ')}; cache=${cacheRoot}`);
}

try { main(); } catch (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
}
