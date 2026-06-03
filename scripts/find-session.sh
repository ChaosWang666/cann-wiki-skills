#!/usr/bin/env bash
# Search Claude Code session JSONL files for a keyword (case-insensitive),
# print a summary table, then render each matching session to Markdown via
# cc_convert.py and drop the .md files into ./sessions-<keyword>/ under $PWD.
#
# Default dir is derived from $PWD: Claude Code stores sessions under
# ~/.claude/projects/<encoded>/, where <encoded> is the absolute path with
# every '/' replaced by '-'. Override by passing a second arg.
#
# Options:
#   -H, --hours N   only consider sessions whose file mtime is within the last
#                   N hours (N = positive integer). Use it to narrow "recently
#                   touched" transcripts when a bare keyword matches too many.
#
# Usage:
#   find-session.sh [-H N] <keyword> [dir]
#   find-session.sh "multi-head self-attention"
#   find-session.sh --hours 3 "kernel fusion"
#   find-session.sh -H 6 "sparse_flash_attention" /path/to/session/dir

set -euo pipefail

# Resolve cc_convert.py relative to this script so the repo can move freely.
# Follow symlinks (readlink -f) so installs via `ln -s` to PATH still work.
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
CC_CONVERT="$SCRIPT_DIR/../skills/wiki/session-upload/scripts/cc_convert.py"

# Print the leading comment block (line 2 onward, up to the first non-comment).
print_help() {
  awk 'NR>=2 && /^#/ {sub(/^# ?/, ""); print; next} NR>=2 {exit}' "$0"
}

# Parse options first; -H/--hours <N> is a time filter, the rest are positionals
# (<keyword> [dir]). Keeping it option-based preserves the old positional API.
hours=""
positional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)  print_help; exit 0 ;;
    -H|--hours) hours="${2:-}"; shift 2 ;;
    --hours=*)  hours="${1#*=}"; shift ;;
    -H*)        hours="${1#-H}"; shift ;;          # allow -H6 (no space)
    --)         shift; positional+=("$@"); break ;;
    -*)         echo "error: unknown option: $1" >&2; print_help; exit 1 ;;
    *)          positional+=("$1"); shift ;;
  esac
done
set -- "${positional[@]}"

if [[ $# -lt 1 ]]; then
  print_help
  exit 0
fi

if [[ -n "$hours" && ! "$hours" =~ ^[0-9]+$ ]]; then
  echo "error: --hours expects a positive integer (got: '$hours')" >&2
  exit 1
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

# Collect candidate .jsonl files. With --hours, use `find -mmin` to keep only
# transcripts touched in the last N hours (N*60 minutes); the keyword grep then
# runs over just the recent set. Without it, fall back to a nullglob expansion
# (so a no-match glob is empty rather than the literal "*.jsonl" pattern).
if [[ -n "$hours" ]]; then
  mapfile -t jsonl_files < <(
    find "$dir" -maxdepth 1 -type f -name '*.jsonl' -mmin "-$((hours * 60))" 2>/dev/null
  )
else
  shopt -s nullglob
  jsonl_files=("$dir"/*.jsonl)
  shopt -u nullglob
fi

if [[ ${#jsonl_files[@]} -eq 0 ]]; then
  if [[ -n "$hours" ]]; then
    echo "warn: no .jsonl files in $dir modified within the last ${hours}h" >&2
  else
    echo "warn: no .jsonl files in $dir" >&2
    echo "(this script only searches *.jsonl session transcripts)" >&2
  fi
  exit 0
fi

# -l: list matching files, -i: case-insensitive, -F: fixed string (so the
# keyword is treated literally, not as a regex — safer for arbitrary input).
mapfile -t hits < <(grep -l -i -F -- "$keyword" "${jsonl_files[@]}" 2>/dev/null || true)

window_note=""
[[ -n "$hours" ]] && window_note=" within last ${hours}h"

if [[ ${#hits[@]} -eq 0 ]]; then
  echo "No session files matched: $keyword"
  echo "Searched: $dir (${#jsonl_files[@]} .jsonl file(s)${window_note})"
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
echo "Found ${#hits[@]} file(s) in $dir${window_note}"

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
