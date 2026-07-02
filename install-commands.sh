#!/usr/bin/env bash
# install-commands.sh — copy create-loop slash commands into an agent runtime.
#
# npx skills add installs only the skill directory; it does NOT populate a
# runtime's command directory. This script copies the repo-root command files
# into the OpenCode and/or Claude Code command directories (project or global).
set -euo pipefail

RUNTIME="both"
SCOPE="project"
PROJECT_DIR="."
FORCE=0

# Directory this script lives in = repo root (source of the command files).
SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage: install-commands.sh [options]

  --runtime opencode|claude|both   Which runtime(s) to install for (default: both)
  --global                         Install to the global (user) command dir
  --project <dir>                  Install to a project command dir (default: .)
  --force                          Overwrite existing command files
  -h, --help                       Show this help

Examples:
  ./install-commands.sh
  ./install-commands.sh --runtime opencode --global
  ./install-commands.sh --runtime both --project /path/to/proj --force
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --runtime)
      RUNTIME="${2:-}"
      shift 2
      ;;
    --global)
      SCOPE="global"
      shift
      ;;
    --project)
      SCOPE="project"
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "$RUNTIME" in
  opencode|claude|both) ;;
  *)
    echo "error: --runtime must be opencode, claude, or both (got: $RUNTIME)" >&2
    exit 1
    ;;
esac

# Resolve the destination command directory for a given runtime.
dest_dir() {
  runtime="$1"
  if [ "$runtime" = "opencode" ]; then
    if [ "$SCOPE" = "global" ]; then
      echo "$HOME/.config/opencode/command"
    else
      echo "$PROJECT_DIR/.opencode/command"
    fi
  else
    if [ "$SCOPE" = "global" ]; then
      echo "$HOME/.claude/commands"
    else
      echo "$PROJECT_DIR/.claude/commands"
    fi
  fi
}

# Source command directory (at repo root) for a given runtime.
src_dir() {
  runtime="$1"
  if [ "$runtime" = "opencode" ]; then
    echo "$SRC_ROOT/.opencode/command"
  else
    echo "$SRC_ROOT/.claude/commands"
  fi
}

install_runtime() {
  runtime="$1"
  src="$(src_dir "$runtime")"
  dst="$(dest_dir "$runtime")"

  if [ ! -d "$src" ]; then
    echo "skip: no source command dir for $runtime ($src)"
    return 0
  fi

  mkdir -p "$dst"
  echo "installing $runtime commands -> $dst"

  for f in "$src"/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    target="$dst/$name"
    if [ -e "$target" ] && [ "$FORCE" -ne 1 ]; then
      echo "  skip (exists): $target"
      continue
    fi
    cp "$f" "$target"
    echo "  copied: $f -> $target"
  done
}

case "$RUNTIME" in
  opencode) install_runtime opencode ;;
  claude)   install_runtime claude ;;
  both)     install_runtime opencode; install_runtime claude ;;
esac

echo "done."
exit 0
