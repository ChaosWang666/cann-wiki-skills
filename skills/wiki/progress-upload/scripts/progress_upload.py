#!/usr/bin/env python3
"""Upload an operator-development progress.md to CANN Wiki via the HTTP MCP endpoint.

Targets the `wiki_submit_progress(op, content, run_id?)` MCP tool. The server
archives the body at `<progress.uploaded_dir>/<op>/<run_id or op>.progress.md`
(path from the server's `config.yaml`); it is write-only, downstream
consumption (progress-to-wiki / offline engine) is out of scope.

Why a Bash helper instead of a plain `tool_use` call: invoking
`wiki_submit_progress` as a regular tool_use forces the whole `content` string
through the model's output-token budget, which silently truncates large files
(a real progress.md is ~18KB > the ~13KB cutoff). This script POSTs from a Bash
subprocess over a local HTTP socket, fully bypassing the cap.

Usage:
    python3 progress_upload.py --file <op>.progress.md [--op NAME] [--run-id RUN]

`--op` / `--run-id` are auto-derived from the path when omitted:
    .../claude/run0/gemm_add_relu.progress.md  ->  op=gemm_add_relu, run_id=run0

URL resolution order:
    --url flag  >  $CANN_WIKI_MCP_URL  >  agent MCP config (cann-wiki entry's
    `url` in `.mcp.json` / `.opencode/opencode.json` walking up from cwd, or
    `~/.claude.json`)  >  http://localhost:3000/mcp
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from urllib.error import HTTPError, URLError

_RUN_RE = re.compile(r"run\d+", re.IGNORECASE)


def derive_op(file_path, explicit_op=None):
    """Operator name = explicit value, else basename minus `.progress.md`/`.md`.

    `gemm_add_relu.progress.md` -> `gemm_add_relu`. The server re-sanitizes with
    Path().name, so traversal-bearing inputs can't escape uploaded_dir; this is
    only about picking a sensible archive key.
    """
    if explicit_op:
        return explicit_op
    base = os.path.basename(file_path)
    for suffix in (".progress.md", ".md"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def derive_run_id(file_path, explicit_run=None):
    """Run id = explicit value, else the parent dir name if it looks like `run<N>`.

    `.../claude/run0/x.progress.md` -> `run0`. No match -> None (server then
    names the file `<op>.progress.md`).
    """
    if explicit_run:
        return explicit_run
    parent = os.path.basename(os.path.dirname(os.path.abspath(file_path)))
    if _RUN_RE.fullmatch(parent):
        return parent.lower()
    return None


def short_display_path(path):
    """Reduce the server's absolute path to `<op-dir>/<filename>` (no machine path)."""
    if not path:
        return ""
    base = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    return f"{parent}/{base}" if parent else base


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
    p.add_argument("--file", required=True, help="Path to the progress.md to upload")
    p.add_argument("--op", default=None,
                   help="Operator name (archive key). Default: basename minus .progress.md")
    p.add_argument("--run-id", default=None,
                   help="Run id distinguishing multiple runs. Default: parent dir if it matches run<N>")
    p.add_argument("--url", default=None,
                   help="MCP HTTP endpoint (default: $CANN_WIKI_MCP_URL > agent MCP config > http://localhost:3000/mcp)")
    args = p.parse_args()

    op = derive_op(args.file, args.op)
    run_id = derive_run_id(args.file, args.run_id)
    url = _resolve_url(args.url)

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
            "clientInfo": {"name": "progress-upload", "version": "1.0"},
        },
    }
    try:
        headers, _ = _post(url, common, json.dumps(init_req))
    except (URLError, HTTPError) as e:
        sys.exit(f"MCP init failed against {url}: {e}")

    # Stateful servers return an mcp-session-id header that must echo on every
    # later request; stateless servers (stateless_http=True) return none and
    # accept tools/call directly. Support both: use the header when present,
    # otherwise fall through to a sessionless call.
    sid = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
    sess = dict(common)
    if sid:
        sess["mcp-session-id"] = sid
        _post(url, sess, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    arguments = {"op": op, "content": content}
    if run_id:
        arguments["run_id"] = run_id
    call_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "wiki_submit_progress", "arguments": arguments},
    }
    try:
        _, body = _post(url, sess, json.dumps(call_req, ensure_ascii=False))
    except (URLError, HTTPError) as e:
        sys.exit(f"wiki_submit_progress call failed: {e}")

    response = next((o for o in _parse_sse(body) if o.get("id") == 2), None)
    if response is None:
        sys.exit(f"No JSON-RPC response in MCP body:\n{body[:500]}")
    if "error" in response:
        sys.exit(f"MCP error: {json.dumps(response['error'], ensure_ascii=False)}")

    inner = response.get("result", {})
    structured = inner.get("structuredContent") or {}
    if structured.get("status") == "ok":
        print(f"OK {short_display_path(structured.get('path', ''))}")
        return 0

    # Surface server's own error/status verbatim — don't paraphrase.
    print(json.dumps(inner, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
