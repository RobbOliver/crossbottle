"""Install the CEF helper wrapper (tools/cefwrap) over Steam's steamwebhelper.exe.

Layout after applying, per CEF directory:
    steamwebhelper.exe       the wrapper
    steamwebhelper_real.exe  Valve's original
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .bottle import Bottle, BottleError

HELPER = "steamwebhelper.exe"
REAL = "steamwebhelper_real.exe"
WRAPPER = Path(__file__).with_name("data") / "cefwrap.exe"
SEARCH = ("Program Files (x86)/Steam/bin/cef/*/" + HELPER,
          "Program Files/Steam/bin/cef/*/" + HELPER)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_helpers(bottle: Bottle) -> List[Path]:
    drive_c = bottle.prefix / "drive_c"
    found = []
    for pattern in SEARCH:
        found.extend(sorted(drive_c.glob(pattern)))
    return found


def status(helper: Path, wrapper: Path = WRAPPER) -> str:
    """wrapped | original | replaced (Steam restored its helper over our wrapper)."""
    real = helper.with_name(REAL)
    if _sha256(helper) == _sha256(wrapper):
        return "wrapped" if real.is_file() else "broken"
    return "replaced" if real.is_file() else "original"


def apply(bottle: Bottle, wrapper: Optional[Path] = None) -> List[Tuple[Path, str]]:
    wrapper = Path(wrapper or WRAPPER)
    if not wrapper.is_file():
        raise BottleError("wrapper binary not found: %s" % wrapper)
    helpers = find_helpers(bottle)
    if not helpers:
        raise BottleError("no %s found in bottle %s; install Steam first" % (HELPER, bottle.name))
    results = []
    for helper in helpers:
        state = status(helper, wrapper)
        if state == "wrapped":
            results.append((helper, "already wrapped"))
            continue
        if state == "broken":
            raise BottleError("%s is the wrapper but %s is missing" % (helper, REAL))
        # 'original' and 'replaced': the current helper is Valve's; it becomes the real one.
        os.replace(helper, helper.with_name(REAL))
        shutil.copy2(wrapper, helper)
        results.append((helper, "wrapped" if state == "original" else "re-wrapped after update"))
    return results


def remove(bottle: Bottle, wrapper: Optional[Path] = None) -> List[Tuple[Path, str]]:
    wrapper = Path(wrapper or WRAPPER)
    results = []
    for helper in find_helpers(bottle):
        real = helper.with_name(REAL)
        if status(helper, wrapper) == "wrapped":
            os.replace(real, helper)
            results.append((helper, "restored"))
        else:
            results.append((helper, "not wrapped"))
    return results
