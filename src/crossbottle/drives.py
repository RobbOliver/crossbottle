"""Map Windows drive letters in a bottle to Mac folders or external disks.

Wine drives are symlinks in <prefix>/dosdevices. A drive pointing at an
external disk (/Volumes/...) is also recorded as a fixed hard disk in
HKLM\\Software\\Wine\\Drives; otherwise Wine may report it as having no root
directory, and programs like Steam refuse it ("not mounted"). Wine reads that
key when its services start, so restart the bottle's programs afterwards.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Dict, Optional

from .bottle import Bottle, BottleError

DRIVE_RE = re.compile(r"^([D-Yd-y]):?$")
RESERVED = ("c", "z")


def _letter(drive: str) -> str:
    m = DRIVE_RE.match(drive)
    if not m:
        raise BottleError("drive must be a letter from D: to Y:, got %r" % drive)
    return m.group(1).lower()


def list_drives(bottle: Bottle) -> Dict[str, str]:
    dev = bottle.prefix / "dosdevices"
    out = {}
    if dev.is_dir():
        for link in sorted(dev.iterdir()):
            if link.is_symlink() and re.match(r"^[a-z]:$", link.name):
                out[link.name.upper()] = os.readlink(link)
    return out


def add(bottle: Bottle, drive: str, target: Path,
        set_registry: Optional[Callable[[str, str], None]] = None) -> str:
    letter = _letter(drive)
    target = Path(target).expanduser()
    if not target.is_dir():
        raise BottleError("folder not found: %s" % target)
    dev = bottle.prefix / "dosdevices"
    if not dev.is_dir():
        raise BottleError("bottle %s has no Wine prefix yet; run something in it first" % bottle.name)
    link = dev / (letter + ":")
    if link.exists() or link.is_symlink():
        raise BottleError("%s: is already mapped to %s" % (letter.upper(), os.readlink(link)))
    link.symlink_to(target)
    if set_registry:
        set_registry(letter + ":", "hd")
    return "%s: -> %s" % (letter.upper(), target)


def remove(bottle: Bottle, drive: str) -> str:
    letter = _letter(drive)
    link = bottle.prefix / "dosdevices" / (letter + ":")
    if not link.is_symlink():
        raise BottleError("%s: is not mapped" % letter.upper())
    link.unlink()
    return "%s: removed" % letter.upper()
