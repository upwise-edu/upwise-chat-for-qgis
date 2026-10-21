# --- UPWISE vendor header -------------------------------------------------
# Source: qgis_mcp_plugin 0.15.0 - Copyright (c) Nicolas Karasiak
# Upstream: https://github.com/nkarasiak/qgis-mcp, tag v0.15.0, taken 2026-10-11
# License: GPL-2.0-or-later (see LICENSE.upstream). UPWISE is a licensee here,
#   not the copyright holder, and redistributes under the same terms.
# Changed by UPWISE 2026-10-11 (GPLv2 section 2(a) notice): SETTINGS_PREFIX,
#   DEFAULT_PORT and plugin_version() - design 3-3 points 1, 2 and 3.
# Below this block the file is upstream bytes except where marked "UPWISE".
# --- end UPWISE vendor header ---------------------------------------------
"""Values shared by the server, the plugin entry point and the configurator.

Stdlib-only and free of ``qgis`` imports, like :mod:`wire`, :mod:`errors` and
:mod:`registry`. Keeping them here is what lets ``configurator`` read the
settings prefix without importing ``plugin``, which imports it back.
"""

import errno
import os

DEFAULT_HOST = "localhost"

# UPWISE change (design 3-3 point 3, rationale 5-3): upstream defaults to 9876.
# We bind 0 and let the OS pick, then recover the real port in start(). 9876 is
# not available to us as a default: SO_EXCLUSIVEADDRUSE means only one socket
# can hold it, so an embedded server that grabbed it would make the user's own
# installed qgis_mcp_plugin fail to start - our plugin breaking someone else's
# feature, from the user's point of view.
DEFAULT_PORT = 0

# The plugin package directory - where metadata.txt and icons/ live. Anchored
# here rather than on each module's own ``__file__`` so a module inside a
# subpackage (``handlers/``) still resolves them correctly.
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# UPWISE change (design 3-3 point 2): vendored one level down, so metadata.txt
# is in the parent package, not here. Upstream read it from PLUGIN_DIR, which
# would quietly resolve to "unknown" and put a wrong version in `diagnose`.
HOST_PLUGIN_DIR = os.path.dirname(PLUGIN_DIR)

# QgsSettings key prefix for every setting the plugin persists.
#
# UPWISE change (design 3-3 point 1): upstream uses "qgis_mcp". Keeping that
# would make us write the user's installed qgis_mcp_plugin settings - the same
# `qgis_mcp/port` key it reads on load - so our embedded server would silently
# rewrite the port of a plugin we do not own.
SETTINGS_PREFIX = "upwise_chat/embedded_server"

# Cap what is accepted as a peer's version string: it arrives over the socket
# and ends up in front of the user. Mirrors MAX_VERSION_LENGTH in
# src/qgis_mcp/protocol.py, which the client applies before sending.
MAX_VERSION_LENGTH = 32

# Same treatment for the checkout path a peer announces. Mirrors
# MAX_PATH_LENGTH in src/qgis_mcp/protocol.py.
MAX_PATH_LENGTH = 160

_plugin_version = None


def plugin_version():
    """This plugin's version, from metadata.txt - the file QGIS itself reads.

    Cached: both ``diagnose`` and the version-drift warning ask for it, and it
    cannot change without a plugin reload.

    UPWISE change (design 3-3 point 2): reads the host plugin's metadata.txt,
    one directory up, because this package is vendored inside it.
    """
    global _plugin_version
    if _plugin_version is None:
        import configparser

        config = configparser.ConfigParser()
        config.read(os.path.join(HOST_PLUGIN_DIR, "metadata.txt"))
        _plugin_version = config.get("general", "version", fallback="unknown")
    return _plugin_version


# "someone else already holds this port". EADDRINUSE is the usual answer, and is
# what a second QGIS window gets since both sides set SO_EXCLUSIVEADDRUSE. Windows
# answers WSAEACCES instead when the other holder used plain SO_REUSEADDR, which
# means the same thing here - the spin box floor is 1024, so EACCES cannot be the
# "privileged port" case.
ADDR_IN_USE = frozenset({errno.EADDRINUSE, errno.EACCES, 10048, 10013})
