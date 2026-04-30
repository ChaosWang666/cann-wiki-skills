---
name: session-upload
description: "Auto-upload current session transcript (OpenCode or Claude Code) to the AscendC Wiki via MCP. Claude Code: /session-upload. OpenCode: /skills → select session-upload."
---

# Session Upload

Auto-upload the current session transcript to the AscendC Wiki knowledge base. Works for both **OpenCode** and **Claude Code** — the skill detects which agent is running and picks the right transcript source.

## Prerequisites

1. MCP Server is running and `wiki_submit_trajectory` is available (run `/setup-ascendc-wiki` first).
2. Either OpenCode CLI (`opencode`) is installed, OR the session is being run inside Claude Code (transcripts under `~/.claude/projects/`).
3. Session contains "Ascend C" / "AscendC" keywords (otherwise it lands in `raw/sessions/to_review/` for manual review).

## Step 1: Detect Agent

Run a shell check to decide which path to take:

```bash
# Claude Code transcript directory for the current cwd
ENC_CWD="$(pwd | sed 's|/|-|g')"
CC_DIR="$HOME/.claude/projects/$ENC_CWD"

if [ -d "$CC_DIR" ] && ls "$CC_DIR"/*.jsonl >/dev/null 2>&1; then
  AGENT=claude-code
elif command -v opencode >/dev/null 2>&1; then
  AGENT=opencode
else
  echo "No supported agent transcript found"; exit 1
fi
echo "Agent: $AGENT"
```

Prefer `claude-code` when running inside Claude Code, otherwise fall back to `opencode`.

## Step 2A: Claude Code Path

### 2A.1 Find Latest Session JSONL

Claude Code stores JSONL transcripts at `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`, where `<encoded-cwd>` is the absolute working dir with `/` replaced by `-`.

```bash
ENC_CWD="$(pwd | sed 's|/|-|g')"
CC_DIR="$HOME/.claude/projects/$ENC_CWD"
LATEST=$(ls -t "$CC_DIR"/*.jsonl 2>/dev/null | head -1)
SESSION_ID=$(basename "$LATEST" .jsonl)
echo "Session: $SESSION_ID"
echo "File: $LATEST"
```

### 2A.2 Convert JSONL to Markdown

Each line in the JSONL is one row. Relevant rows:

| Top-level `type` | Meaning |
|---|---|
| `user` | `message.role=user`, `message.content` is a string OR a list of `tool_result` blocks |
| `assistant` | `message.role=assistant`, `message.content` is a list of `text` / `thinking` / `tool_use` blocks; `message.model` carries the model id |
| `attachment` / `last-prompt` / `permission-mode` / `file-history-snapshot` / `ai-title` | metadata — skip |

Use this embedded Python converter (run it from the same shell):

```python
#!/usr/bin/env python3
"""Claude Code JSONL → Markdown converter (matches the OpenCode export layout)."""
import json, sys
from datetime import datetime, timezone, timedelta

# Beijing time: UTC+8
BEIJING_TZ = timezone(timedelta(hours=8))

def ts(s):
    """Convert ISO timestamp to Beijing time format."""
    if not s: return ""
    try:
        # Parse as UTC (Z suffix)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        # Convert to Beijing time
        dt_beijing = dt.astimezone(BEIJING_TZ)
        return dt_beijing.strftime("%Y-%m-%d %H:%M:%S")
    except Exception: return s

def render_block(blk, thinking=True, tools=True):
    t = blk.get("type")
    if t == "text":
        return blk.get("text","") + "\n\n"
    if t == "thinking" and thinking:
        text = blk.get("thinking","").strip()
        return f"_Thinking:_\n\n{text}\n\n" if text else ""
    if t == "tool_use" and tools:
        out = f"**Tool: {blk.get('name','')}**\n\n"
        if blk.get("input") is not None:
            out += "**Input:**\n```json\n" + json.dumps(blk["input"], indent=2, ensure_ascii=False) + "\n```\n\n"
        return out
    if t == "tool_result" and tools:
        c = blk.get("content","")
        if isinstance(c, list):
            c = "".join(p.get("text","") if isinstance(p, dict) else str(p) for p in c)
        return "**Tool Result:**\n```\n" + str(c)[:500] + "\n```\n\n"
    return ""

def convert(path, thinking=True, tools=False):
    title, sid, created, updated = "Untitled", "", "", ""
    body = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try: o = json.loads(line)
            except Exception: continue
            tp = o.get("type")
            if tp == "ai-title":
                title = o.get("title", title) or title
            if not sid: sid = o.get("sessionId","")
            if tp in ("user","assistant"):
                t_iso = o.get("timestamp","")
                created = created or t_iso
                updated = t_iso or updated
                msg = o.get("message", {})
                if msg.get("role") == "user":
                    c = msg.get("content","")
                    if isinstance(c, str):
                        body.append("## User\n\n" + c + "\n\n---\n\n")
                    elif isinstance(c, list):
                        # tool_result blocks under user role
                        rendered = "".join(render_block(b, thinking, tools) for b in c if isinstance(b, dict))
                        if rendered.strip():
                            body.append("## User\n\n" + rendered + "---\n\n")
                else:
                    model = msg.get("model","unknown")
                    parts = msg.get("content", [])
                    rendered = "".join(render_block(b, thinking, tools) for b in parts if isinstance(b, dict))
                    if rendered.strip():
                        body.append(f"## Assistant ({model})\n\n" + rendered + "---\n\n")
    head = [
        f"# {title}\n\n",
        f"**Session ID:** {sid}\n",
        f"**Created:** {ts(created)}\n",
        f"**Updated:** {ts(updated)}\n\n",
        "---\n\n",
    ]
    return "".join(head + body)

if __name__ == "__main__":
    print(convert(sys.argv[1]))
```

Save as `/tmp/cc_convert.py`, then:

```bash
MD=$(python3 /tmp/cc_convert.py "$LATEST")
```

### 2A.3 Upload via MCP

Call the MCP tool from the agent (not shell):

```
wiki_submit_trajectory(
  session_id="$SESSION_ID",
  transcript=<MD>,
  source="claude-code"
)
```

## Step 2B: OpenCode Path

### 2B.1 Get Current Session ID

```bash
SESSION_ID=$(opencode session list -n 1 --format json | jq -r '.[0].id')
```

### 2B.2 Export Session JSON and Convert

```bash
opencode export "$SESSION_ID"
```

Use the embedded Python below (matches the TUI `/export` format) to convert the JSON to Markdown:

```python
#!/usr/bin/env python3
"""OpenCode session JSON → Markdown converter (matches TUI /export)."""
import json, sys
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

def fmt_ts(ms):
    """Convert milliseconds timestamp to Beijing time format."""
    if not ms: return ""
    dt = datetime.fromtimestamp(ms/1000, tz=BEIJING_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def fmt_assistant(mi, meta=True):
    if not meta: return "## Assistant\n\n"
    agent = mi.get("agent","build")
    model = mi.get("model",{}).get("modelID","unknown")
    dur = ""
    tc = mi.get("time",{}).get("created"); tf = mi.get("time",{}).get("completed")
    if tc and tf: dur = f"{(tf-tc)/1000:.1f}s"
    parts = [agent.capitalize(), model] + ([dur] if dur else [])
    return f"## Assistant ({' · '.join(parts)})\n\n"

def fmt_part(p, thinking=True, tools=True):
    t = p.get("type","")
    if t == "text" and not p.get("synthetic"): return p.get("text","") + "\n\n"
    if t == "reasoning" and thinking: return f"_Thinking:_\n\n{p.get('text','')}\n\n"
    if t == "tool" and tools:
        s = p.get("state",{})
        out = f"**Tool: {p.get('tool','')}**\n"
        if s.get("input"): out += "\n**Input:**\n```json\n" + json.dumps(s["input"], indent=2) + "\n```\n"
        if s.get("status") == "completed" and s.get("output"):
            out += "\n**Output:**\n```\n" + s["output"][:500] + "\n```\n"
        return out + "\n"
    return ""

def convert(s):
    d = json.loads(s); info = d.get("info",{}); msgs = d.get("messages",[])
    head = [
        f"# {info.get('title','Untitled')}\n\n",
        f"**Session ID:** {info.get('id','')}\n",
        f"**Created:** {fmt_ts(info.get('time',{}).get('created',0))}\n",
        f"**Updated:** {fmt_ts(info.get('time',{}).get('updated',0))}\n\n",
        "---\n\n",
    ]
    body = []
    for m in msgs:
        mi = m.get("info",{}); ps = m.get("parts",[])
        body.append("## User\n\n" if mi.get("role")=="user" else fmt_assistant(mi))
        for p in ps: body.append(fmt_part(p))
        body.append("---\n\n")
    return "".join(head + body)

if __name__ == "__main__":
    print(convert(sys.stdin.read() if len(sys.argv)==1 else open(sys.argv[1]).read()))
```

```bash
MD=$(opencode export "$SESSION_ID" | python3 /tmp/oc_convert.py)
```

### 2B.3 Upload via MCP

```
wiki_submit_trajectory(
  session_id="$SESSION_ID",
  transcript=<MD>,
  source="opencode"
)
```

## Step 3: Report Result

```
✓ Uploaded
- Agent:   claude-code | opencode
- Session: {session_id}
- Path:    raw/sessions/uploaded/{session_id}.md
- Pipeline: knowledge_engine auto-sanitize + extraction
```

## Domain Requirement

The transcript must mention "Ascend C" or "AscendC". Otherwise the server routes it to `raw/sessions/to_review/` for manual triage — that is expected, not an error.

## Error Handling

| Scenario | Handling |
|---|---|
| No `~/.claude/projects/<cwd>/*.jsonl` and no `opencode` CLI | "No agent transcript source found — run from inside Claude Code or install opencode" |
| MCP not configured | "Run `/setup-ascendc-wiki` first" |
| `wiki_submit_trajectory` not registered | "MCP tool missing — restart agent after setup" |
| Empty transcript | "No messages to upload" |
| JSON/JSONL parse error | "Skipping malformed line, continuing" |
| Network/API error | "Network error, retry later" |

## Notes

- **Zero user interaction** — the agent runs all steps itself.
- **Format parity** — Claude Code and OpenCode transcripts both render to the same Markdown layout.
- **Tool details excluded by default** — keeps the upload compact; flip the `tools` flag in the converter to include them.
- **Thinking included** — preserves `thinking` blocks (Claude Code) and `reasoning` parts (OpenCode).
- **Agent detection is path-based** — the Claude Code branch fires whenever a transcript exists for the current cwd, regardless of which CLI invoked the skill.
