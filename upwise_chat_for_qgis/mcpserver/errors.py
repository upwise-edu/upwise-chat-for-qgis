# --- UPWISE vendor header -------------------------------------------------
# Source: qgis_mcp_plugin 0.15.0 - Copyright (c) Nicolas Karasiak
# Upstream: https://github.com/nkarasiak/qgis-mcp, tag v0.15.0, taken 2026-10-11
# License: GPL-2.0-or-later (see LICENSE.upstream). UPWISE is a licensee here,
#   not the copyright holder, and redistributes under the same terms.
# Not changed by UPWISE: strip this block and the file is upstream byte for
#   byte. VENDOR.md records both digests.
# --- end UPWISE vendor header ---------------------------------------------
"""Exception types raised by command handlers.

Stdlib-only and free of ``qgis`` imports, like :mod:`wire`, so the tests can
import it without QGIS. Must stay Python 3.9-compatible (see
``tests/test_py39_compat.py``).

Why this exists: every handler used to ``raise Exception(...)``, and the
dispatcher caught bare ``Exception``. A plugin bug (``TypeError`` from a
signature change, ``AttributeError`` from a renamed PyQGIS method) therefore
came back to the client looking exactly like "Layer not found" - no traceback
anywhere, and nothing in the response to tell the two apart. Handlers raise
:class:`CommandError` for a condition the caller can act on; anything else
reaching the dispatcher is a defect, gets its traceback logged, and is flagged
``internal`` in the response.
"""


class CommandError(Exception):
    """A command failed for a reason the caller can act on and understand.

    Bad parameters, a missing layer, an unsupported option, a QGIS operation
    that legitimately refused. The message is user-facing.
    """


class LayerNotFound(CommandError):
    """No layer with the requested id exists in the current project."""

    def __init__(self, layer_id):
        super().__init__(f"Layer not found: {layer_id}")
        self.layer_id = layer_id


class WrongLayerType(CommandError):
    """The layer exists but is not the kind the command needs."""
