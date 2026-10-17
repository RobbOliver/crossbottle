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
MARKER = b"CROSSBOTTLE_CEFWRAP_V"
# Wrapper builds released before MARKER existed.
LEGACY_WRAPPERS = {"8dd52ecf368c860fa64e299033fdb01dbf31584368e77ed51e9650b41dddd7a6"}
# Only cef.win64 is used on Windows 10/11 bottles; the cef.win7* builds are legacy.
SEARCH = ("Program Files (x86)/Steam/bin/cef/cef.win64/" + HELPER,
          "Program Files/Steam/bin/cef/cef.win64/" + HELPER)


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


def is_wrapper(path: Path) -> bool:
    """True for any version of our wrapper (never for Valve's helper)."""
    data = path.read_bytes()
    return MARKER in data or hashlib.sha256(data).hexdigest() in LEGACY_WRAPPERS


def status(helper: Path, wrapper: Path = WRAPPER) -> str:
    """wrapped | outdated (older wrapper) | original | replaced (Steam restored its
    helper over our wrapper) | broken (wrapper without the real helper)."""
    real = helper.with_name(REAL)
    if real.is_file() and is_wrapper(real):
        # The "real" helper is one of our wrappers (an older crossbottle swapped
        # them): Valve's file is gone or sits in helper's place.
        return "broken"
    if is_wrapper(helper):
        if not real.is_file():
            return "broken"
        return "wrapped" if _sha256(helper) == _sha256(wrapper) else "outdated"
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
            real = helper.with_name(REAL)
            if real.is_file() and is_wrapper(real) and not is_wrapper(helper):
                real.unlink()  # helper is Valve's again: drop the misplaced wrapper, wrap anew
                state = "original"
            else:
                raise BottleError("%s: Steam's web helper is missing; let Steam repair its files "
                                  "(or reinstall Steam), then run `crossbottle cefwrap` again" % helper.parent)
        if state == "outdated":
            shutil.copy2(wrapper, helper)
            results.append((helper, "wrapper updated"))
            continue
        # 'original' and 'replaced': the current helper is Valve's; it becomes the real one.
        if is_wrapper(helper):
            raise BottleError("refusing to treat a wrapper as Steam's helper: %s" % helper)
        os.replace(helper, helper.with_name(REAL))
        shutil.copy2(wrapper, helper)
        results.append((helper, "wrapped" if state == "original" else "re-wrapped after update"))
    return results


def remove(bottle: Bottle, wrapper: Optional[Path] = None) -> List[Tuple[Path, str]]:
    wrapper = Path(wrapper or WRAPPER)
    results = []
    for helper in find_helpers(bottle):
        real = helper.with_name(REAL)
        if status(helper, wrapper) in ("wrapped", "outdated"):
            os.replace(real, helper)
            results.append((helper, "restored"))
        else:
            results.append((helper, "not wrapped"))
    return results
