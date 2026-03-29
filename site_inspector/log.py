from __future__ import annotations

import logging
import os
import sys

_configured = False


def setup_logging() -> None:
    """Configure site_inspector logging from environment variables.

    SITE_INSPECTOR_DEBUG=1  → DEBUG level (superset of previous behavior)
    SITE_INSPECTOR_LOG_LEVEL=INFO|WARNING|ERROR  → explicit level (default WARNING)

    Output goes to stderr so it never pollutes JSON stdout.
    """
    global _configured
    if _configured:
        return
    _configured = True

    if os.environ.get("SITE_INSPECTOR_DEBUG"):
        level = logging.DEBUG
    else:
        level_name = os.environ.get("SITE_INSPECTOR_LOG_LEVEL", "WARNING").upper()
        level = getattr(logging, level_name, logging.WARNING)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    root = logging.getLogger("site_inspector")
    root.setLevel(level)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"site_inspector.{name}")
