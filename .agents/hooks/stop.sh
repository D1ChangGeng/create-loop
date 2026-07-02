#!/bin/sh

script_dir=$(CDPATH= cd -- "$(dirname "$0")" 2>/dev/null && pwd)
if [ -z "$script_dir" ]; then
  exit 0
fi

project_root=$(CDPATH= cd -- "$script_dir/../.." 2>/dev/null && pwd)
if [ -z "$project_root" ]; then
  exit 0
fi

manifest=$project_root/.agents/knowledge/manifest.json
if [ ! -f "$manifest" ]; then
  exit 0
fi

inbox_count=$(grep -E '"inbox_count"[[:space:]]*:' "$manifest" 2>/dev/null \
  | sed -n 's/.*"inbox_count"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
  | sed -n '1p')

days_since_evolution=$(grep -E '"days_since_evolution"[[:space:]]*:' "$manifest" 2>/dev/null \
  | sed -n 's/.*"days_since_evolution"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
  | sed -n '1p')

case "$inbox_count" in
  ''|*[!0-9]*) exit 0 ;;
esac

case "$days_since_evolution" in
  ''|*[!0-9]*) exit 0 ;;
esac

if [ "$inbox_count" -gt 10 ] || [ "$days_since_evolution" -gt 14 ]; then
  printf "%s\n" "[knowledge] inbox_count=$inbox_count, days_since_evolution=$days_since_evolution. Consider running 'evolve'." \
    >&2
fi

exit 0
