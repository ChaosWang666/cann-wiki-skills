#!/usr/bin/env python3
"""Upload a transcript Markdown to CANN Wiki via the HTTP MCP endpoint.

Bypasses the model output-token cap. Calling `wiki_submit_trajectory` as a
regular `tool_use` forces the entire `content` string through the model's
response budget; on long sessions (>~13KB rendered) the call gets silently
truncated mid-string. This script is invoked from Bash, so the payload travels
over a local HTTP socket — verified byte-identical at 250KB.

Usage:
    python3 mcp_upload.py --file /tmp/session_output.md --session-id <id>

URL resolution order:
    --url flag  >  $CANN_WIKI_MCP_URL  >  agent MCP config (cann-wiki entry's
    `url` in `.mcp.json` / `.opencode/opencode.json` walking up from cwd, or
    `~/.claude.json`)  >  http://localhost:3000/mcp

This means setting a non-default port via `/setup-cann-wiki` is enough: the
agent config that setup wrote is what this script reads when uploading.
"""
import argparse
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError


def _post(url, headers, body):
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.headers, resp.read().decode("utf-8")


def _parse_sse(body):
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue


def _scan_config(path):
    """Return the cann-wiki entry's `url` from one MCP config file, or None."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    # `mcpServers` is the Claude Code / Desktop shape; `mcp` is OpenCode's.
    for top_key in ("mcpServers", "mcp"):
        servers = data.get(top_key)
        if isinstance(servers, dict):
            entry = servers.get("cann-wiki")
            if isinstance(entry, dict):
                url = entry.get("url")
                if isinstance(url, str) and url:
                    return url
    return None


def _find_url_in_agent_configs():
    cur = os.path.abspath(os.getcwd())
    while True:
        for rel in (".mcp.json", os.path.join(".opencode", "opencode.json")):
            url = _scan_config(os.path.join(cur, rel))
            if url:
                return url
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return _scan_config(os.path.expanduser("~/.claude.json"))


def _resolve_url(cli_url):
    if cli_url:
        return cli_url
    env_url = os.environ.get("CANN_WIKI_MCP_URL")
    if env_url:
        return env_url
    found = _find_url_in_agent_configs()
    if found:
        return found
    return "http://localhost:3000/mcp"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Path to rendered Markdown transcript")
    p.add_argument("--session-id", required=True, help="Session id used as <session_id>.md filename")
    p.add_argument(
        "--url",
        default=None,
        help="MCP HTTP endpoint (default: $CANN_WIKI_MCP_URL > agent MCP config > http://localhost:3000/mcp)",
    )
    args = p.parse_args()
    args.url = _resolve_url(args.url)

    with open(args.file, encoding="utf-8") as f:
        content = f.read()

    common = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "session-upload", "version": "1.0"},
        },
    }
    try:
        headers, _ = _post(args.url, common, json.dumps(init_req))
    except (URLError, HTTPError) as e:
        sys.exit(f"MCP init failed against {args.url}: {e}")

    sid = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
    if not sid:
        sys.exit("MCP init: server did not return mcp-session-id header")

    sess = dict(common, **{"mcp-session-id": sid})

    # Required handshake step before tools/call.
    _post(args.url, sess, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    call_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "wiki_submit_trajectory",
            "arguments": {"session_id": args.session_id, "content": content},
        },
    }
    try:
        _, body = _post(args.url, sess, json.dumps(call_req, ensure_ascii=False))
    except (URLError, HTTPError) as e:
        sys.exit(f"wiki_submit_trajectory call failed: {e}")

    response = next((o for o in _parse_sse(body) if o.get("id") == 2), None)
    if response is None:
        sys.exit(f"No JSON-RPC response in MCP body:\n{body[:500]}")
    if "error" in response:
        sys.exit(f"MCP error: {json.dumps(response['error'], ensure_ascii=False)}")

    inner = response.get("result", {})
    structured = inner.get("structuredContent") or {}
    if structured.get("status") == "ok":
        print(f"OK {structured.get('path', '')}")
        return 0

    # Surface server's own error/status verbatim — don't paraphrase.
    print(json.dumps(inner, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
