"""Per-user locations.

New installs use the CrossBottle folders. The project used to be called
openbottle; existing OpenBottle folders and OPENBOTTLE_* variables keep working.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

HOME = Path.home()


def _pick(parent: Path) -> Path:
    new, old = parent / "CrossBottle", parent / "OpenBottle"
    return old if old.is_dir() and not new.exists() else new


def data_dir() -> Path:
    """~/Library/Application Support/CrossBottle (Bottles/, Wine/, Runtimes/)."""
    return _pick(HOME / "Library" / "Application Support")


def apps_dir() -> Path:
    """~/Applications/CrossBottle, where shortcuts go by default."""
    return _pick(HOME / "Applications")


def env(name: str) -> Optional[str]:
    """CROSSBOTTLE_<name>, falling back to the legacy OPENBOTTLE_<name>."""
    return os.environ.get("CROSSBOTTLE_" + name) or os.environ.get("OPENBOTTLE_" + name)
