#!/usr/bin/env python3
"""Claude Code JSONL transcript -> Markdown converter.

Reads a single Claude Code session JSONL file and emits a Markdown rendering
suitable for upload to the AscendC Wiki via wiki_submit_trajectory.

Usage:
    python3 cc_convert.py <session.jsonl> > session_output.md
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def ts(s):
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return s


def get_skill_name(text):
    """Detect a Claude Code skill-load text block and recover its skill name.

    Claude Code prefixes loaded skill content with
    "Base directory for this skill: /.../skills/<skill-name>" and strips the
    SKILL.md YAML frontmatter, so we recover the name from the directory's
    final path segment (which by convention matches frontmatter `name:`).
    Frontmatter and H1 slug remain as fallbacks for transcripts produced by
    older or non-stripping clients.
    """
    stripped = text.strip()
    if not stripped.startswith("Base directory for this skill:"):
        return None
    first_line = stripped.split("\n", 1)[0]
    base_dir = first_line[len("Base directory for this skill:"):].strip()
    if base_dir:
        last_segment = base_dir.rstrip("/").rsplit("/", 1)[-1]
        if last_segment:
            return last_segment
    fm = re.search(r"^---\s*\nname:\s*(.+?)\s*\n", text, re.MULTILINE)
    if fm:
        return fm.group(1).strip()
    h1 = re.search(r"\n#\s+(.+?)\n", text)
    if h1:
        return h1.group(1).strip().lower().replace(" ", "-")
    return None


_PLUMBING_BASENAMES = ("cc_convert.py", "oc_convert.py", "mcp_upload.py", "session_output.md")


def _is_plumbing_path(path):
    """True if path targets a file that this upload skill itself produces or consumes.

    Matches by basename so it catches both source locations
    (.../cann-wiki-skills/skills/wiki/session-upload/scripts/*.py) and the
    runtime artifacts (/tmp/cc_convert.py, /tmp/session_output.md). These bodies
    are upload plumbing, not knowledge — we strip their content but keep the
    call signature.
    """
    if not path:
        return False
    base = path.rsplit("/", 1)[-1]
    return base in _PLUMBING_BASENAMES


def render_block(blk, thinking=True, tools=True, suppressed_read_ids=None):
    suppressed_read_ids = suppressed_read_ids or set()
    t = blk.get("type")
    if t == "text":
        text = blk.get("text", "")
        skill = get_skill_name(text)
        if skill:
            return f"/{skill}\n\n"
        return text + "\n\n"
    if t == "thinking" and thinking:
        text = blk.get("thinking", "").strip()
        return f"_Thinking:_\n\n{text}\n\n" if text else ""
    if t == "tool_use" and tools:
        tool_name = blk.get("name", "")
        inp = blk.get("input") or {}
        out = f"**Tool: {tool_name}**\n\n"
        # Strip plumbing bodies from Write/Edit but keep the call signature.
        if tool_name == "Write" and _is_plumbing_path(inp.get("file_path", "")):
            stub = {"file_path": inp.get("file_path", ""), "content": "<plumbing body, omitted>"}
            out += "**Input:**\n```json\n" + json.dumps(stub, indent=2, ensure_ascii=False) + "\n```\n\n"
            return out
        if tool_name == "Edit" and _is_plumbing_path(inp.get("file_path", "")):
            stub = {
                "file_path": inp.get("file_path", ""),
                "old_string": "<omitted>",
                "new_string": "<omitted>",
            }
            out += "**Input:**\n```json\n" + json.dumps(stub, indent=2, ensure_ascii=False) + "\n```\n\n"
            return out
        # The trajectory upload re-embeds the entire rendered transcript inside
        # itself — keep session_id visible but stub the content.
        if tool_name.endswith("wiki_submit_trajectory"):
            stub = {"session_id": inp.get("session_id", ""), "content": "<rendered transcript, omitted>"}
            out += "**Input:**\n```json\n" + json.dumps(stub, indent=2, ensure_ascii=False) + "\n```\n\n"
            return out
        if blk.get("input") is not None:
            out += "**Input:**\n```json\n" + json.dumps(blk["input"], indent=2, ensure_ascii=False) + "\n```\n\n"
        return out
    if t == "tool_result" and tools:
        if blk.get("tool_use_id", "") in suppressed_read_ids:
            return "**Tool Result:**\n```\n<plumbing body, omitted>\n```\n\n"
        c = blk.get("content", "")
        if isinstance(c, list):
            c = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
        return "**Tool Result:**\n```\n" + str(c) + "\n```\n\n"
    return ""


def convert(path, thinking=True, tools=True):
    title, sid, cwd, created, updated = "Untitled", "", "", "", ""
    version, git_branch = "", ""
    body = []

    # First pass: collect Read tool_use IDs whose target is a converter script,
    # so the matching tool_result body (file content) can be stubbed out.
    suppressed_read_ids = set()
    with open(path, encoding="utf-8") as f:
        for raw in f:
            try:
                o = json.loads(raw)
            except Exception:
                continue
            if o.get("type") != "assistant":
                continue
            for blk in (o.get("message", {}) or {}).get("content", []) or []:
                if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                    continue
                if blk.get("name") != "Read":
                    continue
                inp = blk.get("input") or {}
                if _is_plumbing_path(inp.get("file_path", "")):
                    suppressed_read_ids.add(blk.get("id", ""))

    # Second pass: render
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            tp = o.get("type")
            if tp == "ai-title":
                title = o.get("aiTitle", title)
            if not sid:
                sid = o.get("sessionId", "")
            if not cwd:
                cwd = o.get("cwd", "")
            if not version:
                version = o.get("version", "")
            if not git_branch:
                git_branch = o.get("gitBranch", "")
            if tp in ("user", "assistant"):
                t_iso = o.get("timestamp", "")
                created = created or t_iso
                updated = t_iso or updated
                msg = o.get("message", {})
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    if isinstance(content, str):
                        body.append("## User\n\n" + content + "\n\n---\n\n")
                    elif isinstance(content, list):
                        rendered = "".join(
                            render_block(b, thinking, tools, suppressed_read_ids)
                            for b in content
                            if isinstance(b, dict)
                        )
                        if rendered.strip():
                            body.append("## User\n\n" + rendered + "---\n\n")
                else:
                    model = msg.get("model", "unknown")
                    skill_attr = o.get("attributionSkill") or ""
                    header_parts = [model] + ([f"/{skill_attr}"] if skill_attr else [])
                    header = " · ".join(header_parts)
                    parts = msg.get("content", [])
                    rendered = "".join(
                        render_block(b, thinking, tools, suppressed_read_ids)
                        for b in parts
                        if isinstance(b, dict)
                    )
                    if rendered.strip():
                        body.append(f"## Assistant ({header})\n\n" + rendered + "---\n\n")

    header_lines = [
        f"# {title}\n\n",
        f"**Session ID:** {sid}\n",
        f"**Directory:** {cwd}\n",
    ]
    if version:
        header_lines.append(f"**Claude Code Version:** {version}\n")
    if git_branch:
        header_lines.append(f"**Git Branch:** {git_branch}\n")
    header_lines += [
        f"**Created:** {ts(created)}\n",
        f"**Updated:** {ts(updated)}\n\n",
        "---\n\n",
    ]
    return "".join(header_lines + ["".join(body)])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: cc_convert.py <session.jsonl>")
    print(convert(sys.argv[1]))
