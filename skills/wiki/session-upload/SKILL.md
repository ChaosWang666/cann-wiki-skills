---
name: session-upload
description: "Auto-upload current session transcript (Claude Code or OpenCode) to the AscendC Wiki via MCP. Trigger: `/session-upload`."
---

# Session Upload

Auto-upload the current session transcript to the AscendC Wiki knowledge base. Works for both **Claude Code** and **OpenCode** — the skill detects which agent is running and dispatches to the matching converter under `scripts/`.

## Layout

```
session-upload/
├── SKILL.md              # this file — detect + dispatch + upload
└── scripts/
    ├── cc_convert.py     # Claude Code JSONL → Markdown (used by 2A)
    ├── oc_convert.py     # OpenCode JSON → Markdown   (used by 2B)
    └── mcp_upload.py     # HTTP MCP uploader (used by 3, both platforms)
```

The two converters are independent. Adding a new platform = drop a new converter into `scripts/` and add a branch in Step 2; you should never need to touch the existing converter when working on the other platform. `mcp_upload.py` is platform-agnostic — both paths converge on it for Step 3.

## Prerequisites

1. MCP Server is running and `wiki_submit_trajectory` is available — run `/setup-cann-wiki` first.
2. **Claude Code path**: session is being run inside Claude Code (transcripts under `~/.claude/projects/`).
   **OpenCode path**: OpenCode CLI (`opencode`) is installed and has at least one session.
3. The transcript should mention "Ascend C" / "AscendC" — otherwise the downstream `knowledge_engine` ingest pipeline routes it to the configured to-review directory for manual triage (expected, not an error). The MCP server itself only persists; routing is decided downstream.

## Step 1: Detect Agent

Pick the platform branch. **Priority: project config > active session > historical files**.

```bash
if [ -f ".opencode/opencode.json" ] || [ -f ".agents/skills" ]; then
  AGENT=opencode
elif [ -f ".mcp.json" ] || [ -f ".claude/settings.json" ] || [ -d ".claude" ]; then
  AGENT=claude-code
elif command -v opencode >/dev/null 2>&1 \
     && opencode session list -n 1 --format json 2>/dev/null | jq -e '.[0].id' >/dev/null 2>&1; then
  AGENT=opencode
else
  ENC_CWD="$(pwd | sed 's|/|-|g')"
  CC_DIR="$HOME/.claude/projects/$ENC_CWD"
  if [ -d "$CC_DIR" ] && ls "$CC_DIR"/*.jsonl >/dev/null 2>&1; then
    AGENT=claude-code
  else
    echo "No supported agent transcript found"; exit 1
  fi
fi
echo "Agent: $AGENT"
```

Then proceed to **2A** if `AGENT=claude-code`, or **2B** if `AGENT=opencode`.

## Resolving the skill base directory

All scripts under `scripts/` are run **in place** from this skill's base directory — do **not** Read+Write them to `/tmp` (that wasted ~4K output tokens per invocation). Set `SKILL_DIR` once at the top of the Bash session, then reference it in every step:

```bash
SKILL_DIR="<absolute path shown at 'Base directory for this skill:' in your context>"
```

Substitute the literal path the agent has in its skill-load header. Claude Code emits it as a one-line prefix; OpenCode wraps skill content in `<skill_content name=...>` and may not surface an absolute path — in that case fall back to `find ~ /usr/local /opt -maxdepth 6 -type d -name session-upload 2>/dev/null | head -1`.

## Step 2A: Claude Code Path

```bash
ENC_CWD="$(pwd | sed 's|/|-|g')"
CC_DIR="$HOME/.claude/projects/$ENC_CWD"
LATEST=$(ls -t "$CC_DIR"/*.jsonl 2>/dev/null | head -1)
SESSION_ID=$(basename "$LATEST" .jsonl)

python3 "$SKILL_DIR/scripts/cc_convert.py" "$LATEST" > /tmp/session_output.md
```

Output: `/tmp/session_output.md`. Continue to **Step 3 (Upload)**.

## Step 2B: OpenCode Path

```bash
SESSION_ID=$(opencode session list -n 1 --format json | jq -r '.[0].id')
opencode export "$SESSION_ID" 2>/dev/null | python3 "$SKILL_DIR/scripts/oc_convert.py" > /tmp/session_output.md
```

Output: `/tmp/session_output.md`. Continue to **Step 3 (Upload)**.

## Step 3: Upload via MCP

The MCP tool signature is exactly:

```
wiki_submit_trajectory(session_id: str, content: str) -> dict
```

The server lands the bytes verbatim at `<trajectory.uploaded_dir>/{session_id}.md` (path comes from server's `config.yaml`); downstream sanitization and extraction are owned by the knowledge engine's monitor process.

**Do NOT call `wiki_submit_trajectory` directly as a `tool_use`.** Long `content` bodies (>~13KB) get silently truncated mid-string because the entire JSON tool_use payload — including `content` — has to fit inside the model's max-output-tokens budget. Observed truncation: 13.4KB of a 38KB rendered transcript reached the server. Use the helper `scripts/mcp_upload.py` instead — it POSTs to the MCP HTTP endpoint from a Bash subprocess, so the payload travels over a local socket and bypasses the output-token cap entirely (verified byte-identical at 250KB).

Run it directly from `$SKILL_DIR` (set in the section above) — no need to copy:

```bash
python3 "$SKILL_DIR/scripts/mcp_upload.py" --file /tmp/session_output.md --session-id "$SESSION_ID"
```

Output is one line: `OK <uploaded path>` on success. On server error or unexpected response the script prints the server payload verbatim and exits non-zero — surface that to the user without paraphrasing.

The script reads the MCP URL from `$CANN_WIKI_MCP_URL` (default `http://localhost:3000/mcp`); pass `--url` to override.

**DO NOT**:
- Call `wiki_submit_trajectory` directly as a tool_use (truncates per above)
- Replace content with summaries like "[Full session uploaded]"
- Hand-truncate the file before upload
- Pass `file_path=` or `source=` to the MCP tool — those parameters do not exist on the server

## Step 4: Report Result

```
✓ Uploaded
- Agent:   claude-code | opencode
- Session: {session_id}
- Path:    <trajectory.uploaded_dir>/{session_id}.md  (resolved from server config.yaml — do NOT hard-code)
- Pipeline: knowledge_engine auto-sanitize + extraction
```

## Error Handling

| Scenario | Handling |
|---|---|
| No `~/.claude/projects/<cwd>/*.jsonl` and no `opencode` CLI | "No agent transcript source found — run from inside Claude Code or install opencode" |
| MCP not configured | "Run `/setup-cann-wiki` first" |
| `wiki_submit_trajectory` not registered | "MCP tool missing — restart agent after setup" |
| Empty transcript | "No messages to upload" |
| JSON/JSONL parse error | "Skipping malformed line, continuing" |
| Server returns `{status: "error", message: "..."}` | Surface the `message` payload to the user verbatim — don't paraphrase or swallow |
| Network/API error | "Network error, retry later" |

## Notes

- **Platform-isolated converters** — `cc_convert.py` and `oc_convert.py` know nothing about each other. Modifying one cannot break the other.
- **Adding a new platform** — Drop `scripts/<name>_convert.py` (signature: read transcript source, print Markdown to stdout) and add a `Step 2X` section. SKILL.md stays small.
- **Format parity** — Both converters target the same Markdown layout so downstream extraction is uniform.
- **Thinking included** — preserves `thinking` blocks (Claude Code) and `reasoning` parts (OpenCode).
- **Tool details preserved verbatim** — all tool inputs and outputs are kept whole. The converters' `_PLUMBING_BASENAMES` filter strips any rare model-side Read/Write of converter / uploader scripts (in case of debugging) by basename — works regardless of source path. Normal flow no longer copies scripts to `/tmp`, so the filter is a safety net rather than load-bearing.
