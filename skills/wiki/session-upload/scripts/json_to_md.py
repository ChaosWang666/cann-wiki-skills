#!/usr/bin/env python3
"""
OpenCode session JSON to Markdown converter.
Matches the exact format of TUI /export command.

Based on OpenCode source: packages/opencode/src/cli/cmd/tui/util/transcript.ts
"""

import json
import sys
from datetime import datetime


def format_timestamp(ms):
    """Convert Unix timestamp (ms) to locale-style string."""
    if ms == 0:
        return ""
    dt = datetime.fromtimestamp(ms / 1000)
    return dt.strftime("%x, %X")


def format_assistant_header(msg_info, include_metadata=True):
    """Format assistant message header."""
    if not include_metadata:
        return "## Assistant\n\n"
    
    agent = msg_info.get("agent", "build")
    model_id = msg_info.get("model", {}).get("modelID", "unknown")
    
    duration = ""
    time_created = msg_info.get("time", {}).get("created")
    time_completed = msg_info.get("time", {}).get("completed")
    if time_created and time_completed:
        duration = f"{(time_completed - time_created) / 1000:.1f}s"
    
    parts = [agent.capitalize(), model_id]
    if duration:
        parts.append(duration)
    
    return f"## Assistant ({' · '.join(parts)})\n\n"


def format_part(part, include_thinking=True, include_tool_details=True):
    """Format a message part to Markdown."""
    p_type = part.get("type", "")
    
    if p_type == "text" and not part.get("synthetic"):
        return f"{part.get('text', '')}\n\n"
    
    if p_type == "reasoning":
        if include_thinking:
            return f"_Thinking:_\n\n{part.get('text', '')}\n\n"
        return ""
    
    if p_type == "tool":
        tool_name = part.get("tool", "")
        result = f"**Tool: {tool_name}**\n"
        
        state = part.get("state", {})
        
        if include_tool_details and state.get("input"):
            result += f"\n**Input:**\n```json\n{json.dumps(state['input'], indent=2)}\n```\n"
        
        if include_tool_details and state.get("status") == "completed" and state.get("output"):
            output = state["output"]
            if len(output) > 500:
                output = output[:500] + "..."
            result += f"\n**Output:**\n```\n{output}\n```\n"
        
        if include_tool_details and state.get("status") == "error" and state.get("error"):
            result += f"\n**Error:**\n```\n{state['error']}\n```\n"
        
        result += "\n"
        return result
    
    return ""


def format_transcript(session_json_str, include_thinking=True, include_tool_details=True, include_assistant_metadata=True):
    """
    Convert OpenCode session JSON to Markdown.
    
    Args:
        session_json_str: JSON string from `opencode export <session_id>`
        include_thinking: Include reasoning blocks (default: True)
        include_tool_details: Include tool input/output (default: True)
        include_assistant_metadata: Include agent/model/duration in assistant headers (default: True)
    
    Returns:
        Markdown string matching TUI /export format
    """
    data = json.loads(session_json_str)
    
    info = data.get("info", {})
    messages = data.get("messages", [])
    
    lines = [
        f"# {info.get('title', 'Untitled')}\n",
        "\n",
        f"**Session ID:** {info.get('id', '')}\n",
        f"**Created:** {format_timestamp(info.get('time', {}).get('created', 0))}\n",
        f"**Updated:** {format_timestamp(info.get('time', {}).get('updated', 0))}\n",
        "\n",
        "---\n",
        "\n",
    ]
    
    for msg in messages:
        msg_info = msg.get("info", {})
        parts = msg.get("parts", [])
        role = msg_info.get("role", "unknown")
        
        if role == "user":
            lines.append("## User\n\n")
        else:
            lines.append(format_assistant_header(msg_info, include_assistant_metadata))
        
        for part in parts:
            formatted = format_part(part, include_thinking, include_tool_details)
            if formatted:
                lines.append(formatted)
        
        lines.append("---\n\n")
    
    return "".join(lines)


def main():
    """CLI entry point."""
    include_thinking = True
    include_tool_details = False  # Default: compact output
    include_assistant_metadata = True
    
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = sys.stdin.read()
    
    md = format_transcript(content, include_thinking, include_tool_details, include_assistant_metadata)
    print(md)


if __name__ == "__main__":
    main()