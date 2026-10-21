# --- UPWISE vendor header -------------------------------------------------
# Source: qgis_mcp_plugin 0.15.0 - Copyright (c) Nicolas Karasiak
# Upstream: https://github.com/nkarasiak/qgis-mcp, tag v0.15.0, taken 2026-10-11
# License: GPL-2.0-or-later (see LICENSE.upstream). UPWISE is a licensee here,
#   not the copyright holder, and redistributes under the same terms.
# Not changed by UPWISE: strip this block and the file is upstream byte for
#   byte. VENDOR.md records both digests.
# --- end UPWISE vendor header ---------------------------------------------
"""Command handler mixins that make up ``QgisMCPServer``.

One module per domain. ``base`` comes last in the MRO: it holds the
lookups and conversions the other mixins call.
"""

from .base import HandlerBase
from .canvas import CanvasHandlers
from .connections import ConnectionHandlers
from .features import FeatureHandlers
from .layers import LayerHandlers
from .layout import LayoutHandlers
from .processing import ProcessingHandlers
from .project import ProjectHandlers
from .session import SessionHandlers
from .style import StyleHandlers
from .system import SystemHandlers

__all__ = [
    "CanvasHandlers",
    "ConnectionHandlers",
    "FeatureHandlers",
    "HandlerBase",
    "LayerHandlers",
    "LayoutHandlers",
    "ProcessingHandlers",
    "ProjectHandlers",
    "SessionHandlers",
    "StyleHandlers",
    "SystemHandlers",
]
