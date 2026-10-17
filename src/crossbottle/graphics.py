"""Select the Direct3D 10/11 backend of a bottle.

wined3d  Wine's built-in D3D over OpenGL (default; limited to feature level 9_3 on macOS)
dxvk     DXVK-macOS over MoltenVK/Vulkan: native d3d11/d3d10core/dxgi DLLs in the prefix
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from . import paths
from .bottle import Bottle, BottleError

BACKENDS = ("wined3d", "dxvk")
DXVK_DLLS = ("d3d11", "d3d10core", "dxgi")
DEFAULT_DXVK = "dxvk-macos-1.10.3"
BACKUP_DIR = "crossbottle-backup"
LEGACY_BACKUP_DIR = "openbottle-backup"
# runtime subdirectory -> prefix directory
ARCH_DIRS = (("x64", "system32"), ("x32", "syswow64"))


def parse_overrides(value: str) -> Dict[str, str]:
    """'a,b=n,b;c=d' -> {'a': 'n,b', 'b': 'n,b', 'c': 'd'}"""
    out: Dict[str, str] = {}
    for entry in filter(None, (e.strip() for e in (value or "").split(";"))):
        names, sep, mode = entry.partition("=")
        if not sep:
            raise BottleError("invalid DLL override entry: %r" % entry)
        for name in filter(None, (n.strip().lower() for n in names.split(","))):
            out[name] = mode.strip()
    return out


def format_overrides(table: Dict[str, str]) -> str:
    return ";".join("%s=%s" % (name, table[name]) for name in sorted(table))


def default_runtime() -> Path:
    env = paths.env("DXVK")
    return Path(env) if env else paths.data_dir() / "Runtimes" / DEFAULT_DXVK


def _windows_dir(bottle: Bottle) -> Path:
    return bottle.prefix / "drive_c" / "windows"


def _backup_dir(bottle: Bottle) -> Path:
    legacy = bottle.path / LEGACY_BACKUP_DIR / "graphics"
    return legacy if legacy.is_dir() else bottle.path / BACKUP_DIR / "graphics"


def current(bottle: Bottle) -> str:
    return bottle.meta.graphics or "wined3d"


def apply(bottle: Bottle, backend: str, runtime: Optional[Path] = None) -> List[str]:
    if backend not in BACKENDS:
        raise BottleError("unknown backend %r (choose from %s)" % (backend, ", ".join(BACKENDS)))
    windows = _windows_dir(bottle)
    if not (windows / "system32").is_dir():
        raise BottleError("bottle %s has no Wine prefix yet; run something in it first" % bottle.name)
    backup = _backup_dir(bottle)
    overrides = parse_overrides(bottle.meta.dll_overrides)
    log: List[str] = []

    if backend == "dxvk":
        runtime = Path(runtime or default_runtime())
        if not (runtime / "x64" / "d3d11.dll").is_file():
            raise BottleError("DXVK runtime not found at %s" % runtime)
        for arch, sysdir in ARCH_DIRS:
            src_dir, dst_dir = runtime / arch, windows / sysdir
            if not dst_dir.is_dir() or not src_dir.is_dir():
                continue
            for name in DXVK_DLLS:
                src, dst = src_dir / (name + ".dll"), dst_dir / (name + ".dll")
                if not src.is_file():
                    continue
                saved = backup / sysdir / dst.name
                # Keep Wine's own file the first time only; later runs would back up DXVK.
                if dst.is_file() and not saved.exists() and current(bottle) != "dxvk":
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, saved)
                shutil.copy2(src, dst)
                log.append("%s/%s <- %s" % (sysdir, dst.name, src))
        for name in DXVK_DLLS:
            overrides[name] = "n,b"
        bottle.meta.graphics_runtime = str(runtime)
    else:
        for _, sysdir in ARCH_DIRS:
            for name in DXVK_DLLS:
                saved = backup / sysdir / (name + ".dll")
                if saved.is_file():
                    os.replace(saved, windows / sysdir / saved.name)
                    log.append("%s/%s restored" % (sysdir, saved.name))
        for name in DXVK_DLLS:
            overrides.pop(name, None)
        bottle.meta.graphics_runtime = ""

    bottle.meta.dll_overrides = format_overrides(overrides)
    bottle.meta.graphics = backend
    bottle.save()
    return log
