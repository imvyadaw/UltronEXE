# Ultron as an MCP Server

`mcp_server.py` exposes Ultron over the Model Context Protocol (MCP), so
Claude Desktop, Claude Code, or any other MCP client can send it commands
and get back real answers — same brain, same tools, same memory as typed
text mode, just reachable from outside Ultron's own process.

It does not rebuild Ultron. It boots the same `Assistant` (client +
command processor) `main.py` boots, and forwards each MCP call straight
into `Assistant.handle_command()` — the one entry point `run_text()`,
`run_voice_typed()`, and `run_listen()` all already share.

## 1. Install

```
pip install "mcp>=1.2.0,<2"
```

(Everything else Ultron needs is already in `requirements.txt`. This
server never imports voice/STT — no mic, no speaker, no
faster_whisper/torch, so the Windows DLL crash noted in
`ULTRON_VOICE_MODE_FIX_GUIDE.md` can't affect it.)

## 2. Try it standalone

```
python mcp_server.py
```

This starts a stdio MCP server and waits for a client to attach — it
won't print a banner or prompt, since stdout is reserved for the MCP
protocol itself.

## 3. Connect Claude Desktop

Edit `claude_desktop_config.json` (Claude menu → Settings → Developer →
Edit Config) and add:

```json
{
  "mcpServers": {
    "ultron": {
      "command": "python",
      "args": ["C:\\full\\path\\to\\ultron_project\\mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop. Ultron's tools (`ultron_command`, `ultron_reset`,
`ultron_status`) show up under the 🔌 connector icon.

## 4. Connect Claude Code

```
claude mcp add ultron python C:\full\path\to\ultron_project\mcp_server.py
```

## Tools exposed

- **ultron_command(text)** — send anything you'd normally type/say to
  Ultron. Runs the full pipeline: control commands, slash-commands,
  local router, intent router, tool-calling, memory, intelligence
  layer. Returns whatever Ultron would have said back.
- **ultron_reset()** — clears conversation history (same as `/reset`).
- **ultron_status()** — reports whether the intelligence layer and
  Phase 18 observer layer connected for this process.

## Notes / limitations

- **Headless by design.** No mic, no TTS. `ultron_command` is text in,
  text out — this is what makes it work in an MCP client at all.
- **"exit"/"quit"/"bye" are blocked** inside `ultron_command` — in
  Ultron's normal loop those call `sys.exit(0)`, which would kill this
  server process instead of just ending a turn. They return a message
  explaining that instead of running.
- **One Assistant per server process**, built on the first tool call
  (not at startup) so an MCP client that never sends a command never
  pays Ultron's boot cost. Conversation history persists across calls
  within that process, same as a normal Ultron session — restart the
  server (or call `ultron_reset`) to start clean.
- **Autonomy stays exactly as configured.** If `ULTRON_AUTONOMY_ENABLED`
  or `ULTRON_ORCHESTRATOR_ENABLED` are set in `.env`, goal-shaped
  commands sent through `ultron_command` can trigger the same
  autonomous multi-step execution they would from voice/text mode.
