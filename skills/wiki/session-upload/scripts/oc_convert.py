#!/usr/bin/env python3
"""OpenCode session JSON -> Markdown converter (matches TUI /export layout).

Reads `opencode export <session-id>` output (stdin or file) and emits a
Markdown rendering suitable for upload via wiki_submit_trajectory.

Usage:
    opencode export "$SESSION_ID" | python3 oc_convert.py > session_output.md
    # or
    python3 oc_convert.py exported_session.json > session_output.md
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def fmt_ts(ms):
    if not ms:
        return ""
    dt = datetime.fromtimestamp(ms / 1000, tz=BEIJING_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_assistant(mi, meta=True):
    if not meta:
        return "## Assistant\n\n"
    agent = mi.get("agent", "build")
    # OpenCode message.info model field is inconsistent across roles:
    #   user message:      info.model.modelID
    #   assistant message: info.modelID (top-level)
    model = mi.get("model", {}).get("modelID") or mi.get("modelID") or "unknown"
    dur = ""
    tc = mi.get("time", {}).get("created")
    tf = mi.get("time", {}).get("completed")
    if tc and tf:
        dur = f"{(tf - tc) / 1000:.1f}s"
    parts = [agent.capitalize(), model] + ([dur] if dur else [])
    return f"## Assistant ({' · '.join(parts)})\n\n"


def extract_skill_input(text):
    """Pull the `## Input` section body out of an embedded SKILL.md text block."""
    match = re.search(r"## Input\s*\n+(.+?)(?:\n##|\Z)", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def get_skill_name(text):
    """Recover skill name from an embedded SKILL.md text block.

    Frontmatter `name:` is the canonical source. A title-fallback is kept for
    legacy transcripts whose skills predate frontmatter conventions.
    """
    fm = re.search(r"^---\s*\nname:\s*(.+?)\s*\n", text, re.MULTILINE)
    if fm:
        return fm.group(1).strip()
    h1 = re.match(r"#\s+(.+?)\n", text.strip())
    if h1:
        return h1.group(1).strip().lower().replace(" ", "-")
    return None


def fmt_part(p, thinking=True, tools=True):
    t = p.get("type", "")
    if t == "text" and not p.get("synthetic"):
        text = p.get("text", "")
        # Inline SKILL.md text -> render as `/skill-name <input>` placeholder
        skill_name = get_skill_name(text)
        if skill_name:
            input_text = extract_skill_input(text)
            if input_text:
                return f"/{skill_name} {input_text}\n\n"
            return ""
        return text + "\n\n"
    if t == "reasoning" and thinking:
        return f"_Thinking:_\n\n{p.get('text','')}\n\n"
    if t == "tool" and tools:
        s = p.get("state", {})
        tool_name = p.get("tool", "")
        out = f"**Tool: {tool_name}**\n"
        # `skill` tool output carries the full SKILL.md body — keep just the name.
        if tool_name == "skill" and s.get("status") == "completed" and s.get("output"):
            output = s.get("output", "")
            if "<skill_content" in output:
                match = re.search(r'name="([^"]+)"', output)
                if match:
                    out += f"\n**Output:** Loaded skill: {match.group(1)}\n"
                return out + "\n"
        # Drop noisy converter-script writes — runtime plumbing.
        if tool_name == "write" and s.get("input"):
            input_data = s.get("input", {})
            file_path = input_data.get("filePath", "")
            if file_path in ("/tmp/oc_convert.py", "/tmp/mcp_upload.py"):
                out += f"\n**Input:** filePath: {file_path}\n"
                return out + "\n"
        if s.get("input"):
            out += "\n**Input:**\n```json\n" + json.dumps(s["input"], indent=2) + "\n```\n"
        if s.get("status") == "completed" and s.get("output"):
            output = s["output"]
            out += "\n**Output:**\n```\n" + output + "\n```\n"
        return out + "\n"
    return ""


def convert(s):
    # `opencode export` may print a leading "Exporting session: ..." line before
    # the JSON body. Skip lines until the first one starting with `{`.
    lines = s.strip().split("\n")
    json_content = None
    for i, line in enumerate(lines):
        if line.startswith("{"):
            json_content = "\n".join(lines[i:])
            break
    if json_content is None:
        raise ValueError("No valid JSON found in input")

    d = json.loads(json_content)
    info = d.get("info", {})
    msgs = d.get("messages", [])
    head = [
        f"# {info.get('title','Untitled')}\n\n",
        f"**Session ID:** {info.get('id','')}\n",
        f"**Directory:** {info.get('directory','')}\n",
        f"**Created:** {fmt_ts(info.get('time',{}).get('created',0))}\n",
        f"**Updated:** {fmt_ts(info.get('time',{}).get('updated',0))}\n\n",
        "---\n\n",
    ]
    body = []
    for m in msgs:
        mi = m.get("info", {})
        ps = m.get("parts", [])
        body.append("## User\n\n" if mi.get("role") == "user" else fmt_assistant(mi))
        for p in ps:
            body.append(fmt_part(p))
        body.append("---\n\n")
    return "".join(head + body)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        content = sys.stdin.read()
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            content = f.read()
    print(convert(content))
