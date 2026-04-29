---
name: session-upload
description: "Upload session trajectory to wiki knowledge base. Use when user explicitly requests to save conversation, mentions 'upload trajectory', 'save session', or triggers '/session-upload' command."
---

# Session Upload

Upload current session transcript to AscendC Wiki knowledge base for experience extraction and feedback loop.

## Prerequisites

**MCP Server must be running** with `wiki_submit_trajectory` tool available.

Upload destination: `raw/sessions/uploaded/{session_id}.jsonl`

If MCP Server not running, prompt user to start it first.

## Activation

When user:
- Explicitly requests to upload/save current session
- Mentions "upload trajectory", "save conversation"
- Triggers `/session-upload` command
- After completing a wiki-query session (skill may prompt user)

## Input

$ARGUMENTS (optional: can include feedback or notes)

## Workflow

### Phase A: Collect Transcript

Gather complete conversation history in JSONL format (one JSON object per line).

**Format**:

```jsonl
{"role":"user","content":"..."}
{"role":"assistant","content":"...","tool_calls":["wiki_search","wiki_get_page"]}
{"role":"tool","name":"wiki_search","args":{"query":"...","limit":3}}
{"role":"tool","name":"wiki_get_page","args":{"path":"..."}}
```

**Rules**:
- Include all user messages
- Include all assistant messages with `tool_calls` array
- Include tool invocation metadata (name, args)
- **Do NOT include tool return results** (keep transcript concise)
- Keep each message's content summarized if too long

### Phase B: Generate Session ID

Generate UUID v4 for session_id:

```
session_id = generate_uuid_v4()
```

Example: `550e8400-e29b-41d4-a716-446655440000`

### Phase C: Call MCP Tool

Call `wiki_submit_trajectory`:

```
wiki_submit_trajectory(
  session_id: "<UUID>",
  transcript: "<JSONL string>",
  source: "<agent name, e.g., 'claude-code', 'opencode', 'cursor'>"
)
```

### Phase D: Report Result

Report upload status:

```markdown
## Upload Complete

- Session ID: {session_id}
- Status: ok
- Path: raw/sessions/uploaded/{session_id}.jsonl
- Size: {N} messages logged
```

If upload failed:
```markdown
## Upload Failed

- Error: {error message}
- Action: Check MCP Server status, retry later
```

## Output Format

```markdown
## Session Upload

### Transcript Summary
- Messages: {N}
- Tool calls: {M}
- Duration: approximately {time}

### Upload Result
- Session ID: {uuid}
- Status: ok/error
- Path: raw/sessions/uploaded/{session_id}.jsonl

### Next Steps
- Trajectory will be processed by extraction service
- Knowledge gaps extracted → wiki pages created
```

## Notes

- **MCP Server required** — Cannot upload without MCP connection
- **Transcript excludes tool returns** — Keep file size manageable
- **One upload per session** — Don't upload partial conversations
- **Source identifier important** — Helps downstream processing filter by agent
- **Graceful error handling** — If upload fails, offer retry or manual save

## Error Handling

| Scenario | Handling |
|----------|----------|
| MCP not running | Prompt: "Start MCP Server first" |
| Empty transcript | "No messages to upload" |
| Upload API error | "Network error, retry later" |
| Invalid session_id | Generate new UUID and retry |

## Example Transcript

```jsonl
{"role":"user","content":"What is AscendC programming model?"}
{"role":"assistant","content":"I'll search the wiki for AscendC programming model...","tool_calls":["wiki_search"]}
{"role":"tool","name":"wiki_search","args":{"query":"AscendC programming model","limit":3}}
{"role":"assistant","content":"Found 3 relevant pages. Let me fetch them...","tool_calls":["wiki_get_page","wiki_get_page","wiki_get_page"]}
{"role":"tool","name":"wiki_get_page","args":{"path":"guide/concepts/programming-model.md"}}
{"role":"tool","name":"wiki_get_page","args":{"path":"guide/concepts/memory-hierarchy.md"}}
{"role":"tool","name":"wiki_get_page","args":{"path":"guide/concepts/pipeline-sync.md"}}
{"role":"assistant","content":"Based on wiki pages, AscendC uses SIMD/SIMT programming model with..."}
{"role":"user","content":"Thanks! Upload this session."}
{"role":"assistant","content":"Uploading trajectory...","tool_calls":["wiki_submit_trajectory"]}
```

## Integration with wiki-query

This skill is often triggered after wiki-query completes. The wiki-query skill should prompt:

```
## Trajectory Upload
Use `/session-upload` to upload this session transcript
```

Users can then trigger this skill to complete the feedback loop.