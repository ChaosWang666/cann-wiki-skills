---
name: session-upload
description: "Auto-upload current session transcript. One command: /skills → session-upload."
---

# Session Upload

Auto-upload current session transcript to AscendC Wiki knowledge base.

## Prerequisites

1. OpenCode CLI available (`opencode` command)
2. MCP Server running with `wiki_submit_trajectory` tool
3. Session contains "Ascend C" / "AscendC" keywords (for automatic processing)

## Workflow (Fully Automated)

### Step 1: Get Current Session ID

```bash
SESSION_ID=$(opencode session list -n 1 --format json | jq -r '.[0].id')
```

### Step 2: Export Session JSON

```bash
opencode export $SESSION_ID
```

Returns complete JSON with all messages and parts.

### Step 3: Convert JSON to Markdown

Use embedded Python script (matches TUI `/export` format):

```python
#!/usr/bin/env python3
"""
OpenCode session JSON to Markdown converter.
Matches the exact format of TUI /export command.
"""
import json
import sys
from datetime import datetime

def format_timestamp(ms):
    if ms == 0: return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%x, %X")

def format_assistant_header(msg_info, include_metadata=True):
    if not include_metadata: return "## Assistant\n\n"
    agent = msg_info.get("agent", "build")
    model_id = msg_info.get("model", {}).get("modelID", "unknown")
    duration = ""
    tc = msg_info.get("time", {}).get("created")
    tf = msg_info.get("time", {}).get("completed")
    if tc and tf: duration = f"{(tf - tc) / 1000:.1f}s"
    parts = [agent.capitalize(), model_id]
    if duration: parts.append(duration)
    return f"## Assistant ({' · '.join(parts)})\n\n"

def format_part(part, thinking=True, tools=True):
    t = part.get("type", "")
    if t == "text" and not part.get("synthetic"):
        return f"{part.get('text', '')}\n\n"
    if t == "reasoning" and thinking:
        return f"_Thinking:_\n\n{part.get('text', '')}\n\n"
    if t == "tool" and tools:
        name = part.get("tool", "")
        r = f"**Tool: {name}**\n"
        s = part.get("state", {})
        if s.get("input"): r += f"\n**Input:**\n```json\n{json.dumps(s['input'], indent=2)}\n```\n"
        if s.get("status") == "completed" and s.get("output"):
            r += f"\n**Output:**\n```\n{s['output'][:500]}\n```\n"
        r += "\n"
        return r
    return ""

def format_transcript(json_str, thinking=True, tools=False, metadata=True):
    data = json.loads(json_str)
    info = data.get("info", {})
    msgs = data.get("messages", [])
    lines = [
        f"# {info.get('title', 'Untitled')}\n\n",
        f"**Session ID:** {info.get('id', '')}\n",
        f"**Created:** {format_timestamp(info.get('time', {}).get('created', 0))}\n",
        f"**Updated:** {format_timestamp(info.get('time', {}).get('updated', 0))}\n\n",
        "---\n\n",
    ]
    for m in msgs:
        mi = m.get("info", {})
        ps = m.get("parts", [])
        lines.append("## User\n\n" if mi.get("role") == "user" else format_assistant_header(mi, metadata))
        for p in ps:
            lines.append(format_part(p, thinking, tools))
        lines.append("---\n\n")
    return "".join(lines)

if __name__ == "__main__":
    content = sys.stdin.read() if len(sys.argv) == 1 else open(sys.argv[1]).read()
    print(format_transcript(content))
```

Run conversion:
```bash
opencode export $SESSION_ID | python3 -c "$(cat <<'SCRIPT'
... embedded script ...
SCRIPT
)"
```

### Step 4: Upload via MCP

```
wiki_submit_trajectory(
  session_id="$SESSION_ID",
  transcript="<converted Markdown>",
  source="opencode"
)
```

### Step 5: Report Result

```
✓ 上传成功
- Session: {session_id}
- Path: raw/sessions/uploaded/{session_id}.md
- Processing: knowledge_engine auto-sanitize + knowledge extraction
```

## Output Format

The transcript matches TUI `/export` format:

```markdown
# {title}

**Session ID:** {id}
**Created:** {timestamp}
**Updated:** {timestamp}

---

## User

{user text}

---

## Assistant (Build · GLM-5 · 12.5s)

_Thinking:_

{reasoning}

**Tool: read**

**Input:**
```json
{"filePath": "..."}
```

**Output:**
```
{tool output}
```

---

...
```

## Domain Requirement

Transcript must contain "Ascend C" or "AscendC" keywords.

Without keywords → goes to `raw/sessions/to_review/` for manual review.

## Error Handling

| Scenario | Handling |
|----------|----------|
| OpenCode CLI unavailable | "Install opencode first" |
| MCP not running | "Start MCP Server first" |
| Empty transcript | "No messages to upload" |
| JSON parse error | "Invalid session data" |
| Upload API error | "Network error, retry later" |

## Notes

- **Zero user interaction** — Agent handles all steps automatically
- **Format matches `/export`** — Same Markdown structure as TUI export
- **JSON to MD conversion** — Deterministic, no LLM involved
- **Tool details excluded by default** — Keep output compact (can enable if needed)
- **Thinking included** — Preserves reasoning blocks