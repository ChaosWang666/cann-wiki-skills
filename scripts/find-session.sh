#!/usr/bin/env bash
# Search Claude Code session JSONL files for a keyword (case-insensitive),
# print a summary table, then render each matching session to Markdown via
# cc_convert.py and drop the .md files into ./sessions-<keyword>/ under $PWD.
#
# Default dir is derived from $PWD: Claude Code stores sessions under
# ~/.claude/projects/<encoded>/, where <encoded> is the absolute path with
# every '/' replaced by '-'. Override by passing a second arg.
#
# Usage:
#   find-session.sh <keyword> [dir]
#   find-session.sh "multi-head self-attention"
#   find-session.sh "kernel fusion" /path/to/session/dir

set -euo pipefail

# Resolve cc_convert.py relative to this script so the repo can move freely.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CC_CONVERT="$SCRIPT_DIR/../skills/wiki/session-upload/scripts/cc_convert.py"

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

keyword="$1"

# Derive default search dir from pwd: ~/.claude/projects/<pwd with / -> ->
cwd="$(pwd)"
encoded="${cwd//\//-}"
default_dir="$HOME/.claude/projects/$encoded"

dir="${2:-$default_dir}"

if [[ ! -d "$dir" ]]; then
  if [[ -z "${2:-}" ]]; then
    echo "error: no session directory for current pwd." >&2
    echo "  pwd:      $cwd" >&2
    echo "  expected: $default_dir" >&2
    echo "Either cd into a project that has Claude Code sessions, or pass a dir explicitly:" >&2
    echo "  $(basename "$0") \"$keyword\" /path/to/session/dir" >&2
  else
    echo "error: directory not found: $dir" >&2
  fi
  exit 1
fi

# Only search .jsonl files. Use nullglob so a no-match glob expands to empty
# rather than the literal pattern (otherwise grep would try to open a file
# named "*.jsonl" and we'd give the wrong error).
shopt -s nullglob
jsonl_files=("$dir"/*.jsonl)
shopt -u nullglob

if [[ ${#jsonl_files[@]} -eq 0 ]]; then
  echo "warn: no .jsonl files in $dir" >&2
  echo "(this script only searches *.jsonl session transcripts)" >&2
  exit 0
fi

# -l: list matching files, -i: case-insensitive, -F: fixed string (so the
# keyword is treated literally, not as a regex — safer for arbitrary input).
mapfile -t hits < <(grep -l -i -F -- "$keyword" "${jsonl_files[@]}" 2>/dev/null || true)

if [[ ${#hits[@]} -eq 0 ]]; then
  echo "No session files matched: $keyword"
  echo "Searched: $dir (${#jsonl_files[@]} .jsonl file(s))"
  exit 0
fi

printf '%-40s | %-8s | %-10s | %s\n' "session" "matches" "size" "mtime"
printf '%-40s-+-%-8s-+-%-10s-+-%s\n' "----------------------------------------" "--------" "----------" "-------------------"
for f in "${hits[@]}"; do
  count=$(grep -c -i -F -- "$keyword" "$f")
  size=$(stat -c %s "$f")
  mtime=$(stat -c %y "$f" | cut -d. -f1)
  printf '%-40s | %-8s | %-10s | %s\n' "$(basename "$f")" "$count" "${size}B" "$mtime"
done

echo
echo "Found ${#hits[@]} file(s) in $dir"

# Render hits to Markdown via cc_convert.py.
if [[ ! -f "$CC_CONVERT" ]]; then
  echo "warn: cc_convert.py not found at $CC_CONVERT — skipping md render" >&2
  exit 0
fi

# Sanitize keyword for use as a directory name: lowercase, non-alnum -> '-',
# collapse runs, trim leading/trailing dashes. Fall back if it sanitizes empty.
slug="$(printf '%s' "$keyword" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | tr -s '-' | sed 's/^-//; s/-$//')"
[[ -z "$slug" ]] && slug="query"
out_dir="$cwd/sessions-$slug"
mkdir -p "$out_dir"

echo
echo "Rendering to: $out_dir"
rendered=0
for f in "${hits[@]}"; do
  base="$(basename "$f" .jsonl)"
  target="$out_dir/$base.md"
  if python3 "$CC_CONVERT" "$f" > "$target"; then
    rendered=$((rendered + 1))
    echo "  [ok]   $base.md"
  else
    echo "  [fail] $base.md (cc_convert.py failed)" >&2
    rm -f "$target"
  fi
done
echo "Rendered $rendered/${#hits[@]} session(s)."
