#!/usr/bin/env bash
# Compatibility wrapper: command installation is owned by the Node installer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_HOSTS="opencode,claude"
ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --runtime)
      case "${2:-}" in
        opencode|claude) RUNTIME_HOSTS="$2" ;;
        both) RUNTIME_HOSTS="opencode,claude" ;;
        *) echo "error: --runtime must be opencode, claude, or both" >&2; exit 1 ;;
      esac
      shift 2
      ;;
    --global) ARGS+=(--global); shift ;;
    --project) [ "$#" -ge 2 ] || { echo "error: --project requires a directory" >&2; exit 1; }; ARGS+=(--project "$2"); shift 2 ;;
    --skill-root) [ "$#" -ge 2 ] || { echo "error: --skill-root requires a directory" >&2; exit 1; }; ARGS+=(--skill-root "$2"); shift 2 ;;
    --force) ARGS+=(--force); shift ;;
    -h|--help)
      cat <<'EOF'
install-commands.sh - install create-loop slash commands through the Node installer.

Usage: ./install-commands.sh [options]

      --runtime <host>   opencode, claude, or both (default: both)
      --global           install into user-level host directories
      --project <dir>    install into a project (default: current directory)
      --skill-root <dir> use this installed create-loop Skill root
      --force            overwrite user-edited owned files
  -h, --help             show this help
EOF
      exit 0
      ;;
    *) echo "error: unknown argument: $1" >&2; exit 1 ;;
  esac
done

exec node "$ROOT/bin/create-loop.js" install --commands-only --host "$RUNTIME_HOSTS" "${ARGS[@]}"
