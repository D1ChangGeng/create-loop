#!/bin/sh

script_dir=$(CDPATH= cd -- "$(dirname "$0")" 2>/dev/null && pwd)
if [ -z "$script_dir" ]; then
  exit 0
fi

project_root=$(CDPATH= cd -- "$script_dir/../.." 2>/dev/null && pwd)
if [ -z "$project_root" ]; then
  exit 0
fi

inbox_dir=$project_root/.agents/knowledge/inbox
if [ ! -d "$inbox_dir" ]; then
  exit 0
fi

payload=$(cat 2>/dev/null)
session_id=$(printf '%s\n' "$payload" \
  | grep -E '"session_id"[[:space:]]*:' 2>/dev/null \
  | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
  | sed -n '1p')

month=$(date +%Y-%m 2>/dev/null)
stamp=$(date '+%Y-%m-%d %H:%M' 2>/dev/null)

if [ -z "$month" ] || [ -z "$stamp" ]; then
  exit 0
fi

inbox_file=$inbox_dir/$month.md

{
  printf '## %s — Session ended\n' "$stamp"
  printf '%s\n' '- Session completed. Review POST-TASK CHECKLIST for any uncaptured knowledge.'
  if [ -n "$session_id" ]; then
    : "$session_id"
  fi
  printf '%s\n' '- [source: hooks/session-end.sh]'
  printf '\n'
} >> "$inbox_file" 2>/dev/null

exit 0
