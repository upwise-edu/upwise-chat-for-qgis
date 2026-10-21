# VENDOR - qgis_mcp_plugin 0.15.1

This directory is third-party code. UPWISE is a licensee of it, not the
copyright holder, and does not claim it.

| | |
|---|---|
| Project | qgis-mcp (QGIS-side plugin half) |
| Copyright | Copyright (c) Nicolas Karasiak |
| License | GPL-2.0-or-later - full text in `LICENSE.upstream` |
| Upstream | https://github.com/nkarasiak/qgis-mcp |
| Tag | `v0.15.1` |
| Taken from | the installed QGIS plugin. 18 files on 2026-10-11 from `v0.15.0`, whose bytes are identical in `v0.15.1`; `handlers/connections.py` re-taken on 2026-10-18 from `v0.15.1` (16839 -> 17504 bytes, upstream's only change between the two releases - see `scripts/65_revendor_connections.py`). Each file's own header states which release it came from. |
| Tracking | **pinned. Manual merges only** - there is no automatic update path for vendored code (design decision D-B10). |

`LICENSE.upstream` is upstream's GPLv2 text, byte for byte: 18092 bytes, sha256 `8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643`. It is not reformatted or recompressed.

## Why it is here

UPWISE Chat for QGIS 0.3.0 runs the QGIS-side tool execution inside its
own distribution instead of asking the user to install a second plugin
and letting `uvx` fetch a bridge at run time. Both halves of that older
arrangement were run-time external dependencies, and every connection
defect the product has had came from them. Vendoring closes that class.

Redistributing GPLv2+ code inside a GPLv2+ distribution is ordinary
compliance - no permission and no relicensing is involved. The plugin's
`LICENSE` is GPLv2 and the source ships inside the distribution, so the
source-availability obligation is met by the artifact itself.

## What was changed

`git diff` against the commit that added these files unmodified is the
record. This table is its summary.

| # | File | Where | Change | Why |
|---|---|---|---|---|
| 1 | `constants.py` | `SETTINGS_PREFIX` | "qgis_mcp" -> "upwise_chat/embedded_server" | Upstream's prefix is the key the user's own installed qgis_mcp_plugin reads on load. Sharing it means our embedded server rewrites the port of a plugin we do not own. |
| 2 | `constants.py` | `plugin_version()` | reads HOST_PLUGIN_DIR/metadata.txt instead of PLUGIN_DIR/metadata.txt | Vendored one level down, so there is no metadata.txt beside this package. Upstream would quietly return "unknown" and `diagnose` would report a wrong version. |
| 3 | `constants.py` | `DEFAULT_PORT` | 9876 -> 0 (ephemeral) | SO_EXCLUSIVEADDRUSE means only one socket can hold 9876. An embedded server that took it would make the user's own Run MCP fail. |
| 4 | `server.py` | `start()` | self.port = self.socket.getsockname()[1] after bind | With an ephemeral port the kernel chooses, so the bound port has to be read back - it is what the bridge needs in its env and what diagnose reports. |
| 5 | `server.py` | `start()` | refuses to start when no token is set (open mode removed) | Upstream treats "no token" as the backward-compatible default: an open socket with execute_code reachable over it. We do not inherit that as a default. |
| 6 | `server.py` | `_dispatch()` | adds an is_exposed(cmd_type) check after the COMMANDS membership test | A CLI --disallowedTools flag filters what the model is offered and does nothing to a direct socket peer. The server has to refuse by name. See exposure.py. |
| 7 | `server.py` | `_in_dispatch` | instance attribute -> module-level _IN_DISPATCH behind a property | Two server objects in one QGIS process could not see each other's dispatch, so a long handler pumping the event loop let the other server's timer interleave a second command. |
| 8 | `__init__.py` | `classFactory re-export` | removed; replaced by a package docstring | A nested QGIS plugin entry point inside another plugin is confusing, and upstream plugin.py is not vendored, so there is nothing to import. |
| 9 | `all vendored files` | `file headers` | provenance header block added to every file; changed files also carry a GPLv2 section 2(a) change notice | Upstream ships no copyright headers at all (0 of 21 files), so without this a reader cannot tell our code from theirs. |
| 10 | `server.py` | `TOKEN_ENV` | reads UPWISE_QGIS_TOKEN instead of QGIS_MCP_TOKEN | os.environ is process-wide and the user's installed qgis_mcp_plugin runs in the same QGIS process, re-reading QGIS_MCP_TOKEN on every command. Setting it would switch auth on for a server we do not own, whose uvx peer has never seen our token: five rejected commands and it drops the connection. The user's Run MCP would break and it would look like our plugin did it. Point 5 (token required) cannot be built without this. |
| 11 | `handlers/system.py` | `execute_code()` | handler body no longer compiles or exec()s the caller's string; it raises CommandError with the dispatcher's own refusal wording | exposure.py BLOCKED_COMMANDS holds execute_code and server._dispatch refuses it by name before any handler runs, so the body was unreachable code. Bandit B102 (Exec used) is a blocking finding in the plugins.qgis.org upload scan (docs/9 B-3), and a blocked version cannot be re-uploaded under the same version number. Removing the body costs no feature because no caller can reach it. |

Point 10 was found during implementation, not at design time: point 5
(refusing to start without a token) cannot be built without it. It was
reviewed and folded into the design's own list, which now specifies ten
points rather than nine. Nothing here is provisional.

Point 11 came later still, from the plugins.qgis.org registration review
(`docs/9.public_release_and_qgis_registration_v1.md` B-3): the upload
security scan treats Bandit B102 (Exec used) as a blocking finding, and
the package's only `exec(` sat in a handler this build already refuses by
name. The list now specifies eleven points.

### Left alone on purpose

`_record_client_version`, `_FIX_COMMANDS` and `client_fixes` in
`server.py` only do anything when a peer announces `client_install`.
Our bridge does not send it, so `_fix_command()` returns `""` and there
is no path by which upstream's `uv cache clean` advice can reach a user.
They are not deleted: that would only make the diff larger.

`_CodeDeadline`, `_deadline_tracer`, `_CODE_TIMEOUT` and `_CODE_FILENAME`
in `handlers/system.py` served only the `execute_code` body that point 11
removed. They hold no `exec`, `eval` or `compile` call, so they are left
in place for the same reason: a smaller diff against upstream.

## Integrity

Two digests per file. `upstream_sha256` is the byte-exact upstream file,
which is what a future upstream release is diffed against.
`our_sha256` is the file as shipped here. For every file that carries no
change beyond its header, stripping the header block reproduces the
upstream bytes exactly, and the harness asserts it.

| File | Changed | Upstream bytes | upstream_sha256 | Our bytes | our_sha256 | Header strip restores upstream |
|---|---|---|---|---|---|---|
| `__init__.py` | yes | 148 | `8960ec44d6a85e2cacb6d26c5c0ade800e3582580ecf12f2dab187225dda75ae` | 1868 | `68d686b3fc8e39209109a3b71d082f79069450f3fda2ce4f9242f736ce1d29dd` | n/a (changed) |
| `compat.py` | no | 13510 | `90b8cc095d2c7815116138a35231ac7d3fb6a1da1e862c1b3e72015d10da3907` | 14078 | `f6298f6937f053d65ef8af8eec1ec89a4cb18053af8a474aff0c1772de94176f` | yes |
| `constants.py` | yes | 2096 | `9e5ab3180604db05b78406eddbc73b1535769def81061595a32337ac636ab102` | 3937 | `73dec08df1c774e8f7cbf85c6500cf13702823291708201493d57c92e1c78dd4` | n/a (changed) |
| `errors.py` | no | 1375 | `71099e8cac8411bc3427f9c8e762a209e5a4ff4a121e69037b76118348b014e3` | 1943 | `6732b85147b3ab607461fd7cd34be0b9b34420de590c12d02efc78d30abb00b7` | yes |
| `handlers/__init__.py` | no | 843 | `44fba1675724b205795aa92c34efae772cc539644ce2ee855192c7cf33d3eef2` | 1411 | `75473923e9ccaca65d6e8eaabe3e67cfed49644f90c4fcbbfc363a95a463fbc3` | yes |
| `handlers/base.py` | no | 7147 | `d66edda38f8b3e2619c26ff0e750d7f865e217fa7f7aa93888273f647ee31f56` | 7715 | `743c0abded709fe9fe7bc06605f8af807243d754961f951b101fffee76cf2f2c` | yes |
| `handlers/canvas.py` | no | 14172 | `f445c2282a6220cef96f64c8a94ca310bb14ee93500e96904dee0de4292ca242` | 14740 | `0dd68234e56e7467a2e3d71881ae58fd17e6c87283ba9c77ef026de5c67359d1` | yes |
| `handlers/connections.py` | no | 17504 | `9b1544cb921f39471b3cc56d01caeb668d119a482f8c9e8fa7667ddd9fa35d5e` | 18072 | `a3940076a264995d042ae836dd5182b70e0a608dab5291896e5381a8bd9de69d` | yes |
| `handlers/features.py` | no | 37050 | `ef804e9540b29b8c0892c204a3523c085a7bdd049b4b75dcd7704f402e26fdc7` | 37618 | `90b133af9cb7887b4a55cbfbc57418a95843935b11414f58ac923a60fde5277c` | yes |
| `handlers/layers.py` | no | 31922 | `f5500ced9fe836da18e89922b80d12e4a44b4faa2becf9174b734ad2c253fa33` | 32490 | `9cd5d7c7e2c316e9bacff547507986608292ff053421f51e228e6e83bd361514` | yes |
| `handlers/layout.py` | no | 12723 | `01c25ef7d9a38c20a06f3e63e8dde67c8db3eec92a162f0450deb3685a11ffa6` | 13291 | `a02acabd4e513d53d76f68788cde6a83be254d227f05f9aaceff925467bd7745` | yes |
| `handlers/processing.py` | no | 60557 | `7557e8962da5219f6f6c7ff930c79284d8024ceb8b015404809968850397b4b4` | 61125 | `cff2dba693c1435d3555e7e095cfedab297920ffdbbdf1f895e57cf1ef02cd42` | yes |
| `handlers/project.py` | no | 9384 | `e256ed90c1f870cd3756535125c300c156e411a4e022115a57f13106843864e6` | 9952 | `4f71a4b0c08c25b250a97821afd1428bb41bd39ac8cf9624b09a348fba84f4d8` | yes |
| `handlers/session.py` | no | 9280 | `68c18a652c63f8984904ffdbfb96da3a34d74c97a0145b54bfb3170bc5223cf2` | 9848 | `5dc947593541a60218e6a82107e54c9e98c433b0b0a469d516ece62c912d0f8b` | yes |
| `handlers/style.py` | no | 11735 | `e9b7ccfb57ddce6066d79de9a97f7a525ecd816566c94bedde02addb9dcc65be` | 12303 | `aa080ebe0f92add7472c4a0e69ebeaeb1d2d36d99ab3aceae8b2032fb50ca243` | yes |
| `handlers/system.py` | yes | 12136 | `5a9a357808cb1f708a34d587077ef4718bc2fc819acea4fb6322cf09da11ff6d` | 11728 | `1e9eb2b02c17542baae8fc6fd22be953806b549ad71bd5cb776cab8805abcee4` | n/a (changed) |
| `registry.py` | no | 1078 | `4dde8d472e4bc5a3f2d41f7ffa652469174353adfaec3a06e22e0832dae04b54` | 1646 | `195f9715266f50b7ab3ab4cfd762e5979d620ffa7106d6eda321ea6e508c6174` | yes |
| `server.py` | yes | 33121 | `c251833991c6ddc13f3c0fa85f5f8cc8038a2eea4fed948fba8101d58d05b7bd` | 39584 | `ff5fcb54a65d1c9d8c516f809608f1fe0c1c2dd4d3438f9efeb8c6e4941b1f49` | n/a (changed) |
| `wire.py` | no | 7371 | `2a18ccf3ecaaf6948ad368df2834372ae3444ccb514879491fa39d3454ba8d84` | 7939 | `6293b6c81dc9a5b25c58dd485adca08e524bfc0d9924aa1c100139263862a203` | yes |

Totals: 19 vendored .py files, 283152 upstream bytes, 301288 bytes as shipped.

## Not vendored

| Upstream file | Why not |
|---|---|
| `plugin.py` | QGIS toolbar action, the "Run MCP" button, a port spin box, an icon badge. Our dock is that surface. |
| `configurator.py` | A `QDialog` that writes config files for Claude Desktop and Cursor. Modal dialogs are forbidden in this product and external clients are out of scope. |
| `icons/`, `mcp_logo.svg`, `metadata.txt` | Branding conflict. |
| the `qgis_mcp` stdio bridge (6,054 lines, MIT) | Needs `mcp[cli]>=1.20`, `pydantic>=2.11` and Python >= 3.12. QGIS 3.44 bundles pydantic but not mcp, and QGIS 3.34 bundles neither; this plugin's minimum is 3.28. `qgis_bridge.py` replaces it. |

Its tool schemas are a separate matter: `../qgis_tools.json` is derived
from that MIT bridge's generated schemas, with the MIT notice carried in
the asset's own provenance block and the full MIT text in `NOTICE`.

## Our own files in this directory

`exposure.py` is UPWISE's, GPL-2.0-or-later. It carries no vendor header.

---

Generated by `scripts/35_write_vendor_md.py` on 2026-10-21. Do not hand-edit the
digest table - regenerate it.
