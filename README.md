# UPWISE Chat for QGIS

A chat dock plugin for QGIS, powered by a Claude Code backend.

> **Status: pre-MVP (work in progress).** Nothing here is released yet.

## What it is

A thin chat UI as a QGIS dock widget. The reasoning runs in a long-lived
[Claude Code](https://claude.com/claude-code) CLI subprocess (stream-json
in/out), so the plugin inherits the Claude Code ecosystem as-is, including
whatever authentication that installation already uses (no separate API key
is asked for by this plugin).

Map control runs **inside this distribution**. The plugin starts its own
socket server in the QGIS process and the CLI talks to it through
`qgis_bridge.py`, a single standard-library file launched with the QGIS
bundled Python. There is nothing to install alongside it and nothing is
fetched at run time:

- No second QGIS plugin, and no port 9876. The embedded server binds an
  ephemeral port so it cannot collide with another plugin holding 9876.
- No `uvx`, no network fetch and no `mcp`/`pydantic` requirement at run time.
- A session token is required, and the six arbitrary-execution tool names are
  refused by the server itself, not only filtered out of what the model is
  offered.

Public data collection has its own server in the plugin, so API keys stay out
of the model context. Skill preset buttons cover collection (bundled with the
plugin) and preprocessing, verification and styling (supplied by the
[UPWISE QGIS MCP Toolkit](https://github.com/upwise-edu/upwise-qgis-mcp-toolkit));
behaviour instructions come from the plugin itself.

## Planned MVP scope

- Chat with streamed responses
- Tool execution with an approval guard (no silent code execution)
- Preset buttons for the skills listed above
- UPWISE branding: logo, link to [upwise.co.kr](https://upwise.co.kr), brand palette

## Design constraints (measured, not assumed)

- No LLM calls or tool execution on the UI thread (dedicated reader/writer worker threads)
- The embedded QGIS socket server answers from the GUI thread timer and is
  single-socket serial, so there are no concurrent requests, and the plugin
  never blocks on its own socket (the self check calls the handler directly)
- One backend process per dock, multi-turn over the same stdin
  (`system/init` is re-emitted every turn with the same session id - the UI must not
  treat it as a new session)
- A tool result is capped at 256 KB with a structured truncation note; the
  socket would pass 10 MB, which no context can hold

## License

**GPL-2.0-or-later.** The full text is in [LICENSE](LICENSE), and
[NOTICE](NOTICE) carries the third-party attributions.

`upwise_chat_for_qgis/mcpserver/` is vendored third-party code: 19 files from
`qgis_mcp_plugin` 0.15.1, Copyright (c) Nicolas Karasiak, GPL-2.0-or-later.
Its own license text ships as `mcpserver/LICENSE.upstream` and every change
UPWISE made to it is listed in `mcpserver/VENDOR.md`. The tool schema asset
`upwise_chat_for_qgis/qgis_tools.json` is derived from the MIT-licensed
`qgis-mcp` 0.15.0 bridge; the MIT text is in `NOTICE`. UPWISE is a licensee of
that code, not its copyright holder, and claims none of it.
