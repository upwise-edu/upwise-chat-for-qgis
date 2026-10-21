# Changelog

## 0.6.0

A seam under the CLI session for a second backend, a portal search link where
the data.go.kr catalogue runs out, and two charts under a bottom navigation in
the dock. The repository this release ships from was restarted in public.

- **A backend adapter layer, with the behaviour held equal.** The session the
  dock drives now sits behind an interface: `backend/adapter.py` declares it,
  `backend/adapter_claude.py` delegates to the Claude Code CLI path that was
  already there, and `backend/adapter_registry.py` chooses one. The Claude
  adapter forwards rather than reimplements, and the claim that nothing moved
  is carried by an equality check rather than by this description: 48 argv
  combinations, the environment block, 10 startup gates and a replay of the
  wire protocol and the state machine return the same digests as the code
  before the layer existed (42 checks, 0 failures). The slot for a second
  backend, the Codex CLI, is empty in this release.
- **The vendored code execution handler refuses instead of calling exec().**
  `execute_code` has not been exposed since 0.3.0: the blocked command list
  holds it and the dispatcher refuses it by name before a handler runs, so
  the vendored body was unreachable. That body is now a structured refusal
  carrying the dispatcher's own wording, because the upload scan at
  plugins.qgis.org treats an `exec()` call as a blocking finding whether or
  not a request can reach it. The signature, the decorator and the file
  around it are left alone so the diff against upstream stays mechanical.
  This is the eleventh recorded change to the vendored copy, and the 19
  recorded upstream digests in `VENDOR.md` do not move; the consistency gate
  over the vendored tree reports 111 checks and 0 failures, and it fails on a
  copy with this change reverted.
- **Registration metadata.** `metadata.txt` drops `category`, whose value was
  outside the allowed list, and gains `tags` and a short `changelog` block.
  The `about` text now says where this was measured: development and testing
  ran on Windows 10 and 11 with QGIS 3.44, Linux and macOS are untested, and
  one path, killing a stuck CLI process tree, is written for Windows only.
- **data.go.kr: a portal search link where the catalogue ends.** A dataset
  list that comes back with no rows now carries a `portal_search` block with
  one link into the portal's own search page. The three parts of that
  address, the base URL, the fixed parameters and the name of the query
  parameter, come from the shipped catalogue declaration; the server builds
  the link and does not fetch it, and the portal list pages that its
  `robots.txt` disallows stay unvisited. The link rides on an empty result
  only, since an empty result is what "not in the shipped catalogue" looks
  like, and a call with candidates spends no bytes on the notice. The query
  parameter name is declared rather than measured: opening the link once in a
  browser is what settles it, and the catalogue note says so. The collection
  checks around this come to 157 with 0 failures.
- **Two charts in the dock.** A usage card draws the 5 hour and 7 day
  utilization that the stream's rate limit event carries, next to the session
  cost summed from the result events. A collection card counts collection
  runs per provider from the sidecar files under the profile workspace.
  Neither card adds a dependency: the bars are QPainter fills and the text is
  QLabel, and neither card file carries a hardcoded color value, so the cards
  draw from theme tokens that were already there. The 14 contrast pairs for
  this round come out at 6.256 or better for text and 3.266 for decoration
  (29 checks, 0 failures).
- **A bottom navigation.** One row under the input picks what the dock shows:
  the chat, the key panel, or the statistics panel that holds the two charts.
  The statistics panel is closed by default, and it rereads the collection
  sidecars when it opens rather than while it is closed (27 checks, 0
  failures). The floating treatment of that row is an approximation of the
  design reference, not a match to it.
- **Section titles wrap instead of clipping.** A folded section title wider
  than the body viewport used to lose its tail. The titles now break across
  lines, and at the narrowest dock width the children measured wider than the
  viewport go from 2 to 0.
- **Recorded test fixtures no longer carry a local account name.** The four
  recorded stream fixtures held 26 occurrences of a developer account name
  across 4 spellings. They are replaced, and the two generators that write
  these fixtures now apply the same substitution, so a regeneration applies
  it as well.
- **The repository history was restarted.** This release ships from a public
  repository whose history begins at a single root commit; the earlier
  history is kept in a private archive repository and in a local bundle.

## 0.5.4

One UI fix, reported from the same live session on 2026-10-19: putting words
on the icons is good, but they run into each other and it looks bad
(translated from the report).

- **The header words sat flush against each other, and two of them fused.**
  They did not
  overlap. No two captions shared a pixel: each word sits in its own cell and
  each cell clips its own label. What was missing was the space between them.
  The four cells shared their edges (0-24, 24-57, 57-94 and 94-144 across the
  action box), so between the last stroke of one word and the first stroke of
  the next there could be no background pixel at all. In the dark theme the
  measured horizontal run of ink from x=44 to x=72 crossed the cell boundary
  at x=57, which is to say that `new` and `save` were drawn as one shape;
  the other two gaps held a single background pixel each, so the row read
  as barely separated words around one fused pair.

  Three places could have opened the gap: the spacing of the layout that holds
  the four cells, a left and right margin inside each cell, or left and right
  padding on the caption label itself. All three were measured against one
  quantity, the gap between the text boxes of two adjacent captions. Each of
  the three sets that gap in fixed pixels, so it does not move with the font,
  and both font lineages returned the same numbers.

  Padding of 3 px gives a 6 px gap and leaves the minimum dock width
  unchanged. Layout spacing of 6 px gives the same 6 px gap for 18 px of
  minimum dock width, and a 3 px margin inside each cell costs 24 px. Only
  padding is free, and the reason is that each caption label carries a minimum
  width of 1 px: that pins what the layout has to grant it, so padding lands
  on the preferred width alone and never on the minimum. The gate on minimum
  dock width is 480 px and the dock asks for 341 px of it in the harness
  lineage that the gate itself measures; this fix spends none of that margin.

  The cost is not width but clipping. Padding raises each caption's preferred
  width by 6 px, so the dock width at which a caption starts to lose its last
  column of glyph moves up as well. On the measured width grid in the clean
  lineage, 0.5.3 was clean at 480 px and first clipped at 460; 0.5.4 is clean
  at 520 px and first clips at 480, where all four words come up 2 to 3 px
  short of their preferred width. The grid steps around those widths are
  20 and 40 px wide, so those are brackets, not exact onsets. The onset moved up one step; the
  behaviour did not change. Layout spacing is the one option that would not
  have moved it, and it costs 18 px of the width margin instead.

  The words themselves, their order, their color token and their place under
  the icons are unchanged, and no new color was added. The buttons stay
  icon-only. A check was added that reads the laid-out geometry and fails if
  two adjacent captions come closer than 6 px, so the state this release fixes
  cannot come back unnoticed.

## 0.5.3

Two UI fixes from a live QGIS session on 2026-10-19.

- **The theme and model dropdown lists were unreadable.** In the popup list
  that opens from either dropdown, the text of every item except the
  current one was drawn in #cbd5e1 on #f0f0f0, a contrast ratio of 1.30
  against the 4.5 that WCAG 2.x asks for body text. This was not specific
  to the dark theme: the light and the system theme rendered the same two
  colors (pixel count for pixel count on the model dropdown, the one
  measured in both modes), and the dark theme did not reach the popup at
  all, so a dark dock opened a light grey list. Only the current
  item was legible, because it is drawn with the accent fill and navy text
  (9.22).

  The cause has two halves. The dock stylesheet carries no rule that can
  name the popup: the list is not part of the dock's widget tree but a
  separate window owned by the combo box, and this project's stylesheet
  only uses object-name and property selectors, never descendant ones. So
  the list took its surface from whatever Qt style the user runs. Its text,
  meanwhile, came from the combo box's own `color` declaration, which Qt
  inherits down into child widgets and which beats the widget palette when
  the item is painted.

  The text color turns out not to be ours to choose. A condition grid over
  every override point - the list's palette, the list's own stylesheet with
  object-name, type and universal selectors including the `::item`
  pseudo-element, the popup frame's own stylesheet, and a descendant
  selector on the combo box itself - changed the rendered text in exactly
  none of those cases. The only lever is the combo box's own `color`, and
  that one has to stay light because the combo box sits on the navy header.

  That fixes the surface by arithmetic. Text at #cbd5e1 has a relative
  luminance of 0.6572, so any surface that clears 4.5 has to sit at or
  below 0.1072 - it has to be dark. No single text color can clear 4.5 on
  both white and navy (the first wants luminance at or below 0.1833, the
  second wants 0.2164 or more), so the list surface is now the header navy
  in both themes, set through the palette and the list's own stylesheet.
  The list that drops out of a navy control is now the same navy. Measured
  contrast is 11.946 for the other items and 9.218 for the current one. In
  the dark theme that navy is the same value the dark body surface already
  uses; it is the light theme where the list no longer matches the body.
  No new color was added: the surface is the header token, the text is the
  status-chip token, and the current item keeps the accent-and-navy pair
  the open combo box already used.
- **The four header icons now carry a word each: api, new, save, delete.**
  The icons had been left to speak for themselves since 0.4.2, and in use
  they did not. Replacing an icon was already ruled out in 0.5.1, where a
  shield glyph resolved to a null icon and pushed the minimum dock width to
  495 px.

  Each word is a separate label under its icon, not the button's own text.
  The text on the new-conversation and clear buttons changes to a
  confirmation sentence while the two-press confirmation is armed, so
  showing that text would let a transient state set the width of the
  header. A label that never changes cannot. The buttons stay icon-only and
  keep their full Korean names for the accessibility name and the tooltip.

  The captions are allowed to compress, the same treatment the connection
  and status labels already get, so they add nothing to the minimum dock
  width: it stays at the measured 341 px against a 480 px ceiling, in all
  four header and badge states. At a real dock width each caption is laid
  out at its full text width in the registered-font lineage that can
  measure Latin glyphs; the offscreen default-font lineage pads every
  glyph to 17 px and clips, so it cannot judge captions. The header grows
  8 px taller when collapsed. Placing the words beside the icons was
  measured and dropped: with compressing captions it still costs 4 px
  over the adopted layout (345 vs 341), and with non-compressing captions
  it leaves 4 px of headroom under the ceiling in the registered-font
  lineage, while a 7 px margin was already judged too tight in 0.5.1.

## 0.5.2

Tracks upstream `qgis_mcp_plugin` 0.15.1 in the vendored QGIS-side server.

- **Vendored upstream moves from 0.15.0 to 0.15.1.** One of the 19 vendored
  files changed between those releases: `mcpserver/handlers/connections.py`
  (16,839 to 17,504 bytes). Upstream's fix is in
  `add_layer_from_connection`: for a non-OGR provider it now reads the
  table's geometry column and sets it, with the primary key, on the data
  source URI, because `tableUri()` names no geometry column and the
  postgres provider read that as a geometryless table (upstream #53).
  No tool signature, no import and no tool schema changed, so the 78 tool
  schemas in `qgis_tools.json` are untouched. The other 18 vendored files
  are byte-identical in both releases. UPWISE's ten modification points are
  unaffected: none of them is in this file, which carries only the
  provenance header that every vendored file carries. `mcpserver/VENDOR.md`
  is regenerated against the new upstream digests.
  The changed handler, `add_layer_from_connection`, is not one of the
  78 exposed tools, and the embedded server refuses it by name, so no
  behavior reachable through this plugin changes: the vendored copy
  simply stays current with upstream.
- **Correction to the 0.5.1 notes below.** The 0.5.1 entry says the key
  icon becomes a shield. That change was applied and then reverted before
  0.5.1 shipped: the shield (`SP_VistaShield`) resolves to a null icon in
  every widget style on the reference machine, an icon-only button with a
  null icon falls back to its full text label, and the minimum dock width
  rose to 495 px, past the 480 px ceiling. 0.5.1 shipped with the same
  borrowed network-drive glyph as 0.5.0, and the key icon's readability
  remains open. The 0.5.1 text below is preserved as released.

## 0.5.1

Two ways the dataset list misled the model, both found in the field, and
two rows of chrome given back.

- **The list now says what cannot be collected.** Each row carries
  `supported`, and an unsupported row also carries one sentence of reason
  taken from the catalogue. A model reading the 0.5.0 list saw an
  unsupported dataset as an ordinary candidate and offered it; the skill,
  the tool descriptions and the server hint now all say not to offer such
  a row and not to collect it. Those rows still appear, on purpose:
  showing one is not offering it.
- **A provider with no datasets yet stops disappearing.** The provider
  inventory comes from the shipped declarations instead of the rows a
  query happened to match, so data.go.kr shows up with its key state and a
  dataset count of zero until you register something. A configured
  provider with zero datasets now points at the registration section
  rather than reading as a missing key.
- **The preset row and the fold-out area are one row each**; the fold-out
  area goes from 225 to 133 px tall. The theme and model segments become
  drop-downs, which keeps their labels, tooltips, values and persistence
  inside a width the segments could not fit.
- **A clearer key icon.** The header icons keep no text label: measured
  against a 480 px ceiling, a one-letter label beside each icon costs 561
  px of minimum dock width and a caption under it 481, because those four
  buttons sit on the row that decides how narrow the dock can be. The key
  icon becomes a shield, which reads better than the network-drive glyph
  it had borrowed for want of a key in the standard set.

## 0.5.0

Public data collection grows from eight V-World layers to three providers,
and the dock gives the chat area its width back.

- **V-World: 158 datasets.** The official 2D data list is transcribed into
  a shipped snapshot (150 names read from the WFS capabilities document, 4
  that answer under an alias name confirmed by a real GetFeature call, and
  4 that no WFS layer serves, kept in the list and marked unsupported with
  the reason). Every entry carries a verified flag; only the six that have
  returned at least one feature are true. Three more complete a collection
  without error but return nothing for the box they were tried in, and a
  single empty answer cannot tell an empty area from a layer that does not
  work, so they stay false. The dataset list takes a provider,
  a query, a limit and an offset, so a long catalog no longer arrives in
  one block.
- **SGIS.** Token authentication (one exchange per collection, one retry,
  then a structured error), administrative boundaries and population. The
  two measured traps are in the dataset notes and in the key panel
  tooltip: low_search means different things per endpoint, and the SGIS
  adm_cd is not the national administrative code, so joining it straight
  to a V-World sig_cd is wrong.
- **data.go.kr by registration.** That portal publishes no machine-readable
  catalogue of its APIs, and it approves each one separately, so the dock
  registers them one at a time: a name, an endpoint, a
  preset (JSON or XML standard shape) and the call parameters. The record
  is written atomically to the profile, never into QGIS settings, and the
  server picks it up without a restart. Saving is checked but never calls
  out: https only, no query string in the URL, no path template, no id
  collision, and a Decoding key rather than an Encoding one.
- **Results without geometry now load.** A record response with no
  coordinates is written as a CSV table and loaded as a table layer. Every
  field arrives as text, so code columns keep their leading zeros and
  number columns need converting before statistics or graduated styling -
  the dock says so when it hands the table over.
- **A declared response envelope, and a loud failure.** Each dataset
  declares where its records live and which field carries the error code.
  A response that does not contain the declared path ends as an error that
  names the top-level keys it did find, instead of a successful empty
  collection.
- **One provider key is enough.** The collect button used to need a key
  for every provider; now one is enough and the datasets of an
  unconfigured provider say so in one line.
- **Key handling.** Each provider declares the character set its key
  accepts, so a portal key with +, / or = saves while a typo still does
  not. An Encoding key (percent escapes) is refused at the input box,
  where the two forms can still be told apart. Masking now covers the
  url-encoded forms of a key as well as the key itself.
- **The header folds into one row of icons.** The keys, new chat, export
  and clear actions sit next to the menu as icon buttons, the fold-out
  area loses a row, and the permission badge keeps its mode name in the
  tooltip. The badge no longer decides how narrow the dock can be: with a
  long badge the minimum width goes from 1085 to 341 px. The preset row
  shrinks with it (card 300 -> 168 px).
- **/login says the right thing.** It is still intercepted, because the
  dock runs the CLI non-interactively, but the message now depends on
  whether credentials are present instead of always claiming you are
  logged out.
- The export notice gets a close button in its top right corner.

## 0.4.1

One fix for the first field complaint about 0.4.0: the header rows the
release added crowded the chat area out.

- **The header folds to a single row.** Only the brand, the status dot,
  the permission badge and a menu toggle stay visible; the four action
  buttons, the theme and model segments and the connection line move
  into a fold-out area (header height 272 -> 71 px). The folded or
  expanded state is remembered across sessions.
- **Notices fold too.** Standing notices collapse to one "N notices"
  line and expand on click; a notice that just fired (such as the login
  guard) opens expanded until the user folds it, and the whole group
  disappears when there is nothing to announce.

## 0.4.0

One field-reported dead end closed and four usability improvements, all
driven by real use on a second machine.

- **Not being logged in no longer dead-ends the dock.** On a machine where
  the Claude Code CLI had never run `/login`, every turn came back "Not
  logged in - Please run /login", and typing `/login` in the dock hit
  "/login isn't available in this environment" (it is interactive-only).
  Three guards now cover this: the dock warns at startup when neither a
  credentials file nor an API key is found (advisory only - other auth
  paths exist), a notice with the terminal fix is appended whenever a
  "Not logged in" reply arrives (the CLI text itself is kept), and
  `/login`/`/logout` typed into the dock are intercepted with the same
  guidance instead of being sent to a CLI that cannot serve them.
- **Up/Down arrows recall sent messages.** With the cursor on the first
  line, Up walks back through what was sent (consecutive duplicates
  folded); on the last line, Down walks forward and finally restores the
  draft that was being typed. Recalled text is editable before sending.
- **A model picker.** A new header segment chooses between the user's own
  Claude Code default and the opus/sonnet/haiku aliases. The choice is
  stored in QgsSettings and applies from the next spawn; changing it while
  a session is running posts a notice saying exactly that.
- **The export confirmation dismisses itself.** The "saved" bar leaves
  after 8 seconds; failure notices still stay until dismissed.
- **Clearer button labels for first-time users.** The export button now
  names the conversation, and the key button is named after the public
  data API keys it manages, with a tooltip stating these keys are
  unrelated to the Claude login. The dock minimum width grows 316 -> 393
  px, still under the 480 px gate.

## 0.3.1

Three defects found while watching 0.3.0 do real work, and one usability
gap, are fixed. Nothing else changes.

- **Writing files in posture W no longer trips a permission bar every
  time.** 0.3.0 exposed the built-in Write and Edit tools in posture W but
  did not pre-approve them, and under `--permission-mode dontAsk` an
  exposed but unapproved tool is denied on every call. In real use that
  meant three denials for one preprocessing log, and the model inventing a
  workaround to create a folder (an empty memory layer fed to a split
  algorithm). Write and Edit are now in the W allow list; postures R and C
  are unchanged.

- **The startup gate now catches that class of defect.** A new hard gate
  item fails the spawn when a built-in tool is exposed but absent from the
  allow list. ToolSearch and Skill are the two deliberate exceptions:
  measured against the real session log, both pass without an allow-list
  entry (9 calls, 0 denials). A planted orphan name makes the gate fail,
  so the check cannot rot silently.

- **`execute_processing` honors its `timeout` argument.** The bridge used
  a fixed 60-second socket timeout for every long command, so a call
  asking for `timeout: 300` was cut at 60 seconds while QGIS kept running
  the job to completion in the background. The socket now waits for the
  server's own budget (the `timeout` argument, or 55 seconds when absent)
  plus a 10-second margin, so the server's structured cancellation message
  arrives instead of a bare socket timeout. Commands with no `timeout`
  parameter behave exactly as before.

- **The dock toggle lives on its own toolbar.** "UPWISE Chat" now appears
  in View > Toolbars (and the toolbar right-click list) as a dedicated
  toolbar with one toggle button, instead of an icon on the shared Plugins
  toolbar that could not be managed from that list. Unloading the plugin
  removes the toolbar completely.

## 0.3.0

Map control no longer depends on anything outside this distribution. Until
0.2.4 it needed two things the user had to supply: a second QGIS plugin
(`qgis_mcp_plugin`) listening on port 9876, and `uvx` fetching a bridge from
GitHub at run time. Every connection defect this product has had came from one
of those two. 0.3.0 ships both halves itself.

- **The QGIS side of tool execution runs inside this plugin.** The socket
  server is vendored into `upwise_chat_for_qgis/mcpserver/` and started when
  the dock loads. It binds an ephemeral port, not 9876, because only one
  socket can hold 9876 and taking it would break the other plugin's own
  Run MCP button for anyone who has both installed. The port it actually got
  is read back after bind and passed to the bridge.

- **The bridge is ours and needs nothing installed.** `qgis_bridge.py` is one
  standard-library file that the Claude Code CLI starts with the QGIS bundled
  Python. It replaces `uvx --from <github zip> qgis-mcp-server`, so there is
  no network fetch, no cache, and no `mcp`/`pydantic` requirement at run time.
  It connects and pings on startup and exits non-zero if it cannot reach the
  server, which means the startup check "map control is connected" now states
  that QGIS answered rather than that a process started.

- **78 tools are offered instead of 120.** The bridge owns `tools/list`, so
  only the tools a posture can actually run are advertised. Before, 42 of the
  advertised names were in no posture's allow list, and picking one spent a
  turn to produce a refusal bar.

- **A token is required and the blocked names are refused by the server.**
  Upstream's default was an open socket with arbitrary code execution
  reachable over it; that default is not inherited here. A fresh token is
  issued on every load. `execute_code`, `execute_sql`,
  `execute_connection_sql`, `import_layer_to_connection`, `add_web_layer` and
  `reload_plugin` are now rejected by name inside the server, not only
  filtered out of what the model is offered, because a command-line flag does
  nothing to a direct socket peer.

- **The connection check costs no model turn.** It used to be a skill that
  asked the model to query another plugin's version, and it reported
  "cannot tell" wherever that plugin was absent. The dock now calls the
  embedded server's own diagnostics and prints the port, the plugin version,
  the QGIS version and the layer count.

- **A tool result larger than 256 KB is cut at that limit** and the cut
  result carries `truncated`, `dropped`, `original_bytes` and a hint to narrow
  the request. The socket itself will pass 10 MB, which no context can hold.

- **The right-click copy path now goes through the redaction gate too.** 0.2.4
  said every clipboard write passes one redactor. That was true of the three
  copy paths this product builds, and not of the context menu Qt puts on a
  transcript row by itself: selecting characters in a row and picking Copy
  there wrote to the clipboard directly, so a key stored after that row was
  drawn went out in full, because redaction is not retroactive. The transcript
  now takes the right-click itself and offers its own copy action, so that
  menu never appears and the write passes the same redactor as the export.
  Selecting characters inside a row and copying them still works.

### Third-party code in this release

The code in `upwise_chat_for_qgis/mcpserver/` is **upstream's, not UPWISE's**.
It is 19 Python files and 7,222 lines as shipped, of which **6,932 lines are
the ones taken from** `qgis_mcp_plugin` 0.15.0 (upstream tag `v0.15.0`,
<https://github.com/nkarasiak/qgis-mcp>), Copyright (c) Nicolas Karasiak,
licensed **GPL-2.0-or-later**. The remaining 290 lines are UPWISE's own
additions to those files and are not part of that attribution: a provenance
header on every file, and in the three files that were changed, a GPLv2
section 2(a) change notice alongside the changes themselves. Strip the header
block from an unchanged file and it is upstream byte for byte. Upstream's
GPLv2 text is included byte for byte as `mcpserver/LICENSE.upstream` (18,092
bytes). Ten change points are recorded in `mcpserver/VENDOR.md`, which lists
each change, each file and two SHA-256 digests per file (upstream and as
shipped) so a future upstream release can be diffed mechanically.

`upwise_chat_for_qgis/qgis_tools.json` (78 tool schemas) is derived from the
`qgis-mcp` 0.15.0 stdio bridge, Copyright (c) 2025 Nicolas Karasiak, **MIT**;
the MIT text is in `NOTICE` and the asset carries its own provenance block.
`mcpserver/exposure.py`, `qgis_bridge.py` and `backend/embedded.py` are
UPWISE's, GPL-2.0-or-later.

This plugin is distributed under GPLv2 or later, which the vendored code
already permits: no relicensing is involved and UPWISE claims none. Because a
QGIS plugin ships as Python source, the source of everything above is inside
the distribution you installed, which is how the GPL's source-availability
obligation is met here.

## 0.2.4

A hotfix for one thing 0.2.3 claimed and did not do. No new behaviour, no new
colours, and no change to the backend, the permission gate, the posture ladder,
key storage or the redaction rules themselves.

- **Copying goes through redaction now, which is what 0.2.3 said already
  happened.** It did not. The 0.2.3 entry below says a cell copy "copies what
  you see, which is the text redaction has already been through", and the
  0.2.3 commit message said the same thing. Redaction is not retroactive, by
  design: a row drawn *before* you saved a key keeps that key in place, so the
  only thing protecting such a row is a pass taken immediately before the text
  leaves the dock. The export had that pass. The two copy paths had none, so
  copying such a row put the key on the clipboard. Measured on 0.2.3 with a
  stored test key: the cell copy button, the range copy and the system
  clipboard each carried one hit of the key, while exporting the same row
  carried none. Every clipboard write now goes through the same redactor
  immediately before the clipboard is touched, in one place, so a copy path
  added later is covered without being remembered.

- **A copy that cannot be redacted is not copied.** This is the rule the
  export already followed. If the redaction pass raises, nothing reaches the
  clipboard, the cell button does not claim `복사됨`, and the notice bar in the
  dock says the copy was stopped. Failing quietly would leave you pasting text
  you believe was cleaned.

The 0.2.3 section below is left as it was written. Its claim about copying was
wrong on the day it shipped, and rewriting it would hide that rather than fix
it.

## 0.2.3

Four things people asked for after using 0.2.2: three ways to get text out of
the transcript, and one wrong guess the model kept making. No change to the
backend, the permission gate, the posture ladder, key storage or the
redaction rules.

- **Copy one cell.** Every row in the transcript (your message, a model
  reply, a thinking block, a tool card) carries a small `복사` button in its
  top-right corner. It copies that row only, and it copies what you see,
  which is the text redaction has already been through. A tool card copies
  its title, the full arguments and the result, whether or not it is folded
  open.

- **Select a range by dragging.** Drag across the transcript and the rows you
  cross are picked up as a range; `Ctrl+C` or the right-click menu copies
  them. A drag that stays inside one row still selects characters the way it
  always did. Qt's character selection cannot cross widget boundaries, and
  the transcript is one widget per row on purpose (folding tool cards, the
  200-row cap, incremental streaming inserts, the stick-to-bottom fix), so
  the selection unit across rows is the row.

- **Export the whole conversation.** A `내보내기` button in the header writes
  the transcript to
  `<QGIS profile>/upwise_chat/workspace/exports/transcript_<session>_<time>.md`
  as Markdown: a header with the session, time, working folder and posture,
  then one section per message, with tool cards as folded `<details>` blocks
  holding the full arguments and result. No file dialog is involved - the
  path is fixed and a bar in the dock tells you where it went, with a button
  to open the folder. The assembled file is passed through the redactor once
  more immediately before it is written, because rows drawn *before* a key
  was saved were never redacted in place, and the export would otherwise copy
  them to disk. If that pass fails, nothing is written.

- **The model no longer guesses the MCP plugin's name.** It kept calling
  `get_plugin_info` with `plugin_name="qgis_mcp"` and getting
  `Plugin not found`. The server looks the name up in QGIS's list of
  installed plugin *folders*, so the identifier is `qgis_mcp_plugin`;
  `QGIS MCP` is only the display name in the metadata. The dock's system
  prompt now says so.

No new colours. The copy button and the export button reuse tokens whose
contrast was already measured in 0.2.2 (`muted_fg`/`caption_fg` on the window
surface, `header_accent`/`chip_fg` on the header navy), and the range
indicator is the platform rubber band rather than a colour of ours.

## 0.2.2

A visual and usability pass over the dock. No new behaviour: the backend, the
permission gate, the posture ladder, key storage and redaction are untouched.
What changed is what the dock looks like and how much room it needs.

- **The dock fits a narrow panel again.** Its minimum width was 694 px, which
  is wider than most people keep a side dock. Three things were forcing that
  number: the full working-folder path sat in a button that never shrank, the
  status chip shared a row with the brand, the toggle and the badge, and the
  key panel put each provider's status label in a fourth grid column. The path
  button now elides from the left and keeps the full path in its tooltip, the
  chip moved to its own line, and the key panel gives each provider three
  rows (name / field + buttons / status). Measured minimum width is now
  347 px.

- **User messages and model replies look different.** A user message is drawn
  as a tinted band with its own text colour; a model reply keeps the QGIS
  background and gets a left rail. Line height in text blocks went to 125 %,
  row spacing from 6 to 9 px, and the turn separator is a 1 px line instead of
  a sunken double rule.

- **Bars say how serious they are.** The prerequisite, exclusion, stale,
  skill-marker, posture-confirm and silence-watchdog bars share one amber
  surface with a 3 px left accent; the denial bar is the only red one. Each
  bar now puts its sentence on its own line above the buttons, because in a
  435 px dock the buttons took the row and the sentence broke into one word
  per line.

- **The prerequisite bar separates "missing" from "checking".** Each item is
  its own row with a `미충족` or `확인 중` tag, read from the detection status
  that was already there. Past three items the rest fold into one line with
  the full list in a tooltip.

- **The permission badge has three colours**, matching the three states it
  already reported in words, and the header's terminal warning is visible
  again: a blanket `#UpwiseChatHeader QLabel` rule had been painting it the
  same white as the body text, so its accent colour never showed.

- **Preset buttons sit in a 3-column grid** instead of one row, and bar and
  panel buttons share a minimum width.

- **An inline "응답 받는 중" indicator** appears next to the send button while
  a turn is running, driven by the one-second watchdog tick that already runs.
  It is separate from the silence watchdog, which still only appears when a
  turn goes quiet for too long.

- **Corrected text.** Switching to collection mode said the data is saved to
  "the working folder". It is saved to the plugin's workspace, which is
  `upwise_chat/workspace/collected` under the QGIS profile, not the project
  folder the backend runs in.

Every colour introduced here was checked against WCAG 2.x before use, in both
light and dark themes:

| group | threshold | pairs | worst measured |
|---|---|---|---|
| text on fill | 4.5:1 | 24 | 6.649 (`#475569` on `#f0f0f0`) |
| informational boundary | 3:1 | 6 | 3.503 (`#64748b` on `#1e1e1e`) |

Container borders that carry no information are not held to 3:1 and were not
changed: the card border is 1.178:1 against the card fill, as it was before.

The design token table itself is unchanged; the new colours live in a
separate layer, so the existing contrast checks kept their expected values.

## 0.2.1

The key settings panel 0.2.0 left out, plus value-based redaction. Until now a
user had to edit `QGIS3.ini` by hand with QGIS closed, and the dock gave no
sign that no key was configured: the first evidence was `key_configured: false`
inside a tool result, after paying for a turn.

- **A non-modal key panel inside the dock.** The header carries a `키 설정`
  toggle. Each provider in the bundled registry gets a masked field
  (`QLineEdit.Password`), save and delete buttons, and a status line that shows
  the stored length but none of its characters. A successful save clears the
  field, because a value left in a widget is a copy with no owner. No modal
  dialog and no `QFileDialog` is used, so QGIS stays usable while the panel is
  open. One line states where the key is stored and that it is stored in clear
  text; another states that pasting a key into the chat box puts it where we
  cannot delete it. A collapsed advanced section holds the endpoint base URL
  override the collection server already reads.

- **`sync()` is called on every write.** `QgsSettings` caches in memory, so
  without it the collection server reads an empty value and reports that no key
  is set. Saving and deleting both go through `backend/keystore.py`, which is
  the only module that touches key values.

- **Missing keys are now a stated precondition.** The prerequisite bar says
  `키가 설정되지 않았습니다` and the collect button is disabled, before the
  first turn is sent, because the key state is readable without an `init`
  event. Chat and the read-only tools are unaffected.

- **Value-based redaction at three points.** Anything written to
  `session_<uuid>.jsonl`, drawn in the transcript (bubbles, text blocks, tool
  card arguments and results, the "full view" temporary file) or appended to
  the diagnostic log is first passed through a redactor that replaces exact
  matches of the stored key values with `***REDACTED***`. It does not look for
  things that resemble keys - a false positive would corrupt the transcript -
  and it skips values shorter than 12 characters. The substitution is
  irreversible; the only audit trail is a `레다크션 n건` counter line, which
  never carries a value. The redactor lives on the dock and is handed to the
  backend, so it survives the respawns used by cancel, posture elevation and
  working-folder changes.

- A respawned backend now writes a `logfiles` line naming its recording and
  diagnostic paths and whether it resumed, so a new diagnostic file after a
  posture change is not mistaken for a backend that stopped logging.

## 0.2.0

General-purpose public data collection. The collect preset used to call a
course skill that depended on a local practice package and on a shell to run
its collector, and the dock exposes no shell, so collection never actually ran
(the skill reported the missing shell itself and only checked key names). This
release moves collection into the plugin.

This is a specification change decided by the product owner on 2026-10-10, not
a relaxation. The design record is `docs/2.collect_feature_design_v1.md` in the
monorepo; the measurements it rests on are ledger rows V28-37, V28-38,
V28-A51, V28-A52, V28-P17 and V28-P18.

- **The plugin owns the network access, not the model.** A second MCP server,
  `upwise_collect`, ships with the plugin (`collect_server.py`, standard
  library only, single file, started with `-I`). It calls the public API,
  writes the raw response to disk, merges it, computes the summary and returns
  the saved path. The model picks a dataset id and an extent from a bundled
  registry and passes the returned path to `add_vector_layer`. `WebFetch` is
  not exposed in any posture, and the model cannot pass a URL or an output
  path. One measurement made this possible: a hand-written standard-library
  MCP stdio server does connect to this CLI version, two servers in one
  `--mcp-config` both come back `connected`, and the allowlist is enforced per
  server.

- **API keys never enter the model context.** This is a design constraint, not
  a mitigation. A key that enters the context is simultaneously stored on the
  model provider's side, in the CLI's own session store, in our session
  recording and in the transcript, and the first two are out of our reach - all
  three surfaces were measured to retain a dummy key. So keys live in
  `QGIS3.ini` under `upwise_chat/keys/<provider>` and the collection server
  reads that file directly with `configparser`. Keys are not written to
  `--mcp-config`, not passed in argv, and not placed in the environment; the
  per-server `env` block carries only the settings path and the key prefix. The
  server masks the key in every log line, in the metadata sidecar and in every
  tool result. A stored value that cannot be decoded is reported as "the key
  format could not be read" rather than guessed at.

- **A third posture, C (collect), sits between R and W.** Its built-in
  exposure is identical to R - no `Write`, no `Edit` - and only its allowlist
  is wider: the three collection tools plus three loading tools
  (`add_vector_layer`, `add_raster_layer`, `create_layer_group`). The file
  writing is done by the server, so the model needs no built-in write tool for
  collection. The allowlists form a total order, R within C within W, so the
  elevation ladder and the gate expectations stay monotonic. The permission
  badge now has three values. Pressing the collect button while read-only asks
  first in a non-modal bar and then restarts the backend with `--resume`; it
  does not resend anything, because a collection needs a region and a dataset
  that the user has to state.

- **`add_web_layer` moved to the exclusion list.** It let the model attach a
  remote WFS or WMS layer whose URL is then stored in the QGIS project file in
  clear text, so a shared `.qgz` carried the key with it. The key invariant
  closes that path on its own, but a guard has to be an exposure removal. The
  exclusion list is now five names and is identical in all three postures.

- **The collect preset points at a bundled skill.** `qgis-data-collect` ships
  with the plugin and is supplied through `--plugin-dir`, so it is registered
  as `upwise-chat-for-qgis:qgis-data-collect`. The marker
  `[qgis-data-collect 0.2.0]` matches the existing marker regex unchanged. The
  skill is a convenience, not a requirement: most of the procedure lives in the
  tool schemas, so collection works even where the skill is not registered. The
  course `qgis-collect` keeps its typed slash-command path and its marker
  verdict; it just no longer has a button.

- **A preset-state defect was fixed before it could ship.** The enablement
  check required the pressed preset to appear in the detected skill list, and
  that list only ever holds toolkit skills. Adding our own skill to the button
  row would therefore have disabled the collect button permanently, and most
  reliably in environments where the toolkit is correctly detected. The check
  now applies to toolkit presets only.

- **Gate changes, three of them.** Gate 4 takes a server list with a severity:
  a disconnected `qgis` is still a hard failure that blocks input, while a
  disconnected `upwise_collect` is soft - it disables the collect button and
  adds one line to the prerequisite bar, and the input box stays open, because
  chat and reading are unaffected. Gate 5 counted all tools in one number, so a
  collection server that died mid-session shrank the count and blocked input
  although permissions had not changed; the drift verdict now uses the
  session id, the permission mode and the **built-in** tool count, and a change
  in the MCP tool count is a warning line. Gate wording is separated so a log
  reader can tell a blocking failure from a warning.

- **Interpreter resolution for the collection server.** The command is the
  absolute path to `<QGIS root>/apps/Python312/python.exe` or a sibling
  version, confirmed by actually starting it with `-I` before use. QGIS's
  launcher `bin/python3.exe` is not a candidate: under `-I` it cannot find the
  standard library and exits immediately, and that same path is what QGIS puts
  in the inherited `PYTHONEXECUTABLE`, so inheritance is not trusted either.
  If no candidate passes the probe, the collection server is left out of the
  MCP configuration entirely and the prerequisite bar says so - writing a
  configuration that cannot start would report as "the server died".

- **Removed scaffolding.** `PRESET_NEEDS_PACKAGE`, the practice package
  default path, `package_present()` and the two `package_*` fields of the
  detection summary are gone. No preset used them once the course collect
  preset was replaced.

- Collected files land under `<QGIS profile>/upwise_chat/workspace/collected/`
  as raw pages plus a derived `merged.geojson` and a `collect_meta.json`
  sidecar. Raw responses are kept byte for byte and are never overwritten by
  the merge. Writes go to a `.part` file and are renamed on completion, so a
  backend kill cannot leave a half file that looks finished. A partial result is
  kept and flagged `incomplete` rather than discarded. The server does not
  reproject; it records the CRS the data arrived in. Limits are 50 pages,
  50 MB, 120 s and 20 collect calls per session; they are conservative design
  choices, not measurements.

## 0.1.4

Two bug fixes. The first of them is a deliberate specification change, decided
by the product owner on 2026-10-10, not a quiet relaxation of a guard.

- **The three read-only built-in file tools are pre-approved in both
  postures (specification change).** `Read`, `Glob` and `Grep` were exposed
  through `--tools` but were absent from the `--allowedTools` list of posture R
  and posture W alike. `--allowedTools` does not block anything; it
  pre-approves. A tool that is merely exposed still raises a permission prompt,
  and under `--permission-mode dontAsk` that prompt comes back as a denial with
  `decision_reason_type="mode"`. In real use the collect skill tried to read
  the course package files and every `Read`, `Glob` and `Grep` call was denied,
  so the skill failed over and over (13 denied `Glob` calls in a single
  session). Both postures now carry the three exact names in
  `--allowedTools`. No wildcards: this project has never measured whether a
  wildcard actually grants execution. `ToolSearch` and `Skill` are untouched,
  the `--disallowedTools` list is unchanged, and the approval path for `Write`,
  `Edit` and the dangerous MCP tools is unchanged. The S5 harness records the
  old and the new expected value side by side, so the revision is visible in
  the log rather than hidden in a diff.

- **The skill marker is searched for in the whole reply, not just its first
  line.** The judge read only the first line of the first assistant text block
  of a preset turn. A model that answers a slash command by first saying what
  it is about to do prints the marker on a later line, and the dock then told
  the user "the skill was not called" although it had been: in the 18:20
  session, turn 1 was judged `ok=False` while that same turn carried two
  markers, ten tool calls and a successful result. The marker regex itself is
  unchanged; it now carries `re.MULTILINE`, so the `^` anchor applies to the
  start of every line, and the input is the turn's full assistant text
  (`Turn.assistant_text()`, all text blocks joined by a newline, because tool
  calls split a reply into several blocks). A marker quoted in the middle of a
  line, as in `결과: [qgis-style 2.1.0]`, is still rejected. The judged scope
  is unchanged: only turns closed by a `result` event are judged. The
  `preset_marker` diagnostic row now records the matched marker and its line
  number within the reply, so a future false negative can be told apart from a
  reply that really had no marker.

## 0.1.3

Bug fix.

- **The transcript stays pinned to the latest output while a reply streams in.**
  `ChatView.sync()` read the scroll position before updating the widgets and
  then called `setValue(maximum())` at the end of the same call. At that point
  the scroll range was still the old one: `QScrollArea` recomputes it only after
  the inner widget's `LayoutRequest`, which Qt defers to the next event loop
  pass. The view therefore scrolled to the *previous* bottom and fell further
  behind with every tick, so the user had to drag the scrollbar down by hand
  after each new block. `ChatView` now keeps a `_pinned` flag and follows the
  content from `verticalScrollBar().rangeChanged`, which fires once the range
  has actually been recomputed. Scrolling up releases the pin (detected on
  `valueChanged`), so new output no longer drags the view away from what is
  being read, and scrolling back to the bottom restores it. The programmatic
  `setValue` is wrapped in a re-entrancy guard so that the plugin's own scroll
  is never mistaken for a user scroll. The "at the bottom" tolerance is now the
  named constant `BOTTOM_EPSILON_PX` (4 px, the value the previous code used
  inline).

## 0.1.2

Bug fix.

- **Inherited Python environment variables are stripped from the CLI child
  environment.** QGIS ships its own Python and exports
  `PYTHONEXECUTABLE`, `PYTHONHOME`, `PYTHONPATH` and `PYTHONSTARTUP` into its
  own process environment. The Claude Code CLI is a Node process and does not
  care, but the MCP bridge that the CLI launches is a Python entry point inside
  a `uv` cache virtual environment, and it inherited the same values. With
  `PYTHONEXECUTABLE` pointing at the QGIS interpreter, that virtual environment
  computed its paths from the QGIS interpreter instead of its own
  `pyvenv.cfg` and never added its own `site-packages`, so the bridge died at
  import time with `ModuleNotFoundError: No module named 'qgis_mcp'` even
  though 0.1.1 resolved `uvx` correctly and the cache entry was intact. An A/B
  measurement isolated `PYTHONEXECUTABLE` as the single cause: injecting all
  132 variables of the QGIS environment killed the bridge, removing the seven
  `PYTHON*` variables started it, removing `PYTHONEXECUTABLE` alone started it,
  removing `PYTHONHOME` alone or `PYTHONPATH` alone did not, and injecting
  `PYTHONEXECUTABLE` alone into an otherwise clean environment killed it.
  `backend/process.py` now removes the four variables in `child_env()` through
  the `INHERITED_PYTHON_KEYS` constant. `PYTHONUTF8` and `PYTHONIOENCODING` are
  deliberately kept, because the pipe runs in UTF-8 text mode. The keys that
  were actually removed are listed on the existing `env_stripped` line of the
  session diagnostic log, which used to read `(none)`.

## 0.1.1

Bug fix.

- **uvx is resolved to an absolute path for the MCP bridge.** The generated
  `<profile>/upwise_chat/qgis_mcp.json` carried `"command": "uvx"` as a bare
  name. Where `uvx` is not on the PATH of the QGIS process (for example an
  install that only has `uvx.exe` under an Anaconda `Scripts` folder that is not
  on the registry PATH), the Claude Code CLI could not launch the bridge, the
  `system/init` event reported `{"name": "qgis", "status": "failed"}`, the
  startup gate `mcp_server_connected` failed and the dock blocked input.
  `backend/detect.py` now resolves the launcher in a fixed candidate order
  (`QgsSettings` key `upwise_chat/uvx_path`, `shutil.which("uvx")`,
  `%USERPROFILE%\.local\bin\uvx.exe`, `%USERPROFILE%\anaconda3\Scripts\uvx.exe`,
  `%USERPROFILE%\miniconda3\Scripts\uvx.exe`) and writes the first existing file
  as an absolute path. Detection only tests for the file; it never runs `uvx`.
  When no candidate exists the config keeps the bare name and the prerequisite
  bar reports that `uvx` was not found. The resolved path is recorded in the
  session diagnostic log (`prereq_detect`).

## 0.1.0 - unreleased

First MVP build. Marked `experimental=True` in `metadata.txt`. Not published yet:
`metadata.txt` still carries `email=TODO_SET_BEFORE_RELEASE`, which the QGIS plugin
repository requires before a public release.

Built in eight stages (S1 - S8), each closed by a verification harness kept in the
UPWISE monorepo (`scripts/06` .. `scripts/17`):

- **S1 - plugin skeleton.** Dock widget with a checkable toolbar/menu toggle,
  `metadata.txt`, placeholder icon. Plugin body import deferred to `classFactory`.
- **S2 - backend process layer.** Long-lived Claude Code CLI subprocess
  (stream-json in/out), reader/writer worker threads, session recording to JSONL.
- **S3 - protocol.** stream-json parser and the turn state machine, replayed from
  recorded fixtures (no paid CLI calls in the harness).
- **S4 - chat UI.** Dock wiring, streaming transcript, collapsible tool cards,
  denial bar.
- **S5 - posture enforcement.** Startup gates (CLI, toolkit, MCP, cwd), posture
  mismatch handling, approval guard.
- **S6 - skill presets.** Preset buttons for the five toolkit skills, prerequisite
  bar, detection wiring.
- **S7 - branding.** UPWISE logo tile and wordmark link, brand palette theme
  (light/dark), plugin icon.
- **S8 - packaging.** `packaging/build_zip.py` (QGIS-installable ZIP with a single
  top-level package folder), `packaging/plugins.xml.tmpl` for a custom plugin
  repository feed, `LICENSE` (GPL v2 or later), `NOTICE` (trademark notice),
  this changelog.

Known limits of this build:

- Qt5 only. `supportsQt6` is deliberately not declared: the plugin has only been
  loaded on Qt 5.15 builds.
- `plugins.xml` carries `<icon>` as the package-relative path from `metadata.txt`.
  The QGIS plugin manager expects a URL there, so the icon may not render in the
  repository listing until an absolute URL is hosted.
- Installation from a real QGIS plugin manager (custom repository entry) has not
  been exercised; the S8 harness only checks the headless equivalent (unzip,
  import, `classFactory`).
