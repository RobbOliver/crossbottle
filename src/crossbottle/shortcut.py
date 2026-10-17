"""Create a macOS .app per Windows program, so the Dock shows its own name and icon.

macOS names a process after the bundle whose *main executable* it is running;
any other executable falls back to its embedded Info.plist, which for Wine's
loader says "Wine". Wine runs every program through its unix loader
(`lib/wine/x86_64-unix/wine`) and computes all paths from the real location of
ntdll.so. So the shortcut contains an inner bundle whose main executable is a
hard link of the loader, next to hard links of the unix libraries; Wine and
every child process then run as that inner app:

    <Name>.app/                              what the user opens
      Contents/Info.plist                    CFBundleExecutable = crossbottle-launch
      Contents/MacOS/crossbottle-launch       runs `crossbottle run --exec --wine <inner>/wine`
      Contents/Resources/app.icns            icon extracted from the .exe
      Contents/Resources/python/crossbottle  copy of this package (Finder apps cannot read ~/Documents)
      Contents/crossbottle.json              marker: bottle, program, wine root
      Contents/Resources/<Name>.app/         inner bundle shown in the Dock
        Contents/Info.plist                  CFBundleName = <Name>, CFBundleExecutable = wine
        Contents/MacOS/wine, *.so            hard links of lib/wine/x86_64-unix/*
        Contents/MacOS/x86_64-unix -> .      so <dll_dir>/x86_64-unix resolves
        Contents/MacOS/*-windows             symlinks to lib/wine/*-windows
        Contents/MacOS/<lib>.dylib           symlinks to lib/* (found via @loader_path)
        Contents/MacOS/vulkan/icd.d/*.json   ICD files rewritten with absolute paths
        bin, share                           symlinks; Wine looks for ../../bin, ../../share
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import shlex
import shutil
from struct import error as struct_error
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from . import icons, launcher, paths
from .bottle import Bottle, BottleError, Store

MARKER = "crossbottle.json"
LEGACY_MARKERS = ("openbottle.json",)
LAUNCHER = "crossbottle-launch"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")


def wine_root(wine: str) -> Path:
    """Wine install root (containing bin/ and lib/wine/) for a bin/wine path."""
    root = Path(wine).resolve().parent.parent
    if not (root / "lib" / "wine" / "x86_64-unix" / "wine").is_file():
        raise BottleError("not a Wine install with lib/wine/x86_64-unix: %s" % root)
    return root


def windows_to_unix(bottle: Bottle, program: str) -> Optional[Path]:
    """Map 'C:\\dir\\app.exe' to its file in the prefix; native paths pass through."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", program)
    if not m:
        p = Path(program)
        return p if p.is_absolute() else None
    drive = bottle.prefix / "dosdevices" / (m.group(1).lower() + ":")
    if not drive.exists():
        drive = bottle.prefix / "drive_c" if m.group(1).lower() == "c" else drive
    return drive.joinpath(*[part for part in re.split(r"[\\/]", m.group(2)) if part])


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:  # different volume
        shutil.copy2(src, dst)


def _copy_vulkan_icds(src: Path, dst: Path) -> None:
    """Copy Vulkan ICD manifests, making relative library paths absolute."""
    for manifest in src.rglob("*.json"):
        out = dst / manifest.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(manifest.read_text())
        icd = data.get("ICD", {})
        lib = icd.get("library_path", "")
        if lib and not os.path.isabs(lib) and "/" in lib:
            icd["library_path"] = os.path.normpath(str(manifest.parent / lib))
        out.write_text(json.dumps(data, indent=4))


def _vulkan_exports(inner: Path, name: str) -> list:
    """Shell lines pointing the Vulkan loader at the bundle's ICD manifests.

    Run from inside the bundle, the loader does not find Wine's relative
    vulkan/icd.d, so MoltenVK (and DXVK on top of it) would be unavailable.
    """
    macos = inner / "Contents" / "MacOS"
    rel = ["$here/../Resources/%s.app/Contents/MacOS/%s" % (name, m.relative_to(macos))
           for m in sorted((macos / "vulkan").rglob("*.json"))] if (macos / "vulkan").is_dir() else []
    if not rel:
        return []
    joined = ":".join(rel)
    return ['export VK_ICD_FILENAMES="%s"' % joined, 'export VK_DRIVER_FILES="%s"' % joined]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "app"


def _populate_wine(app: Path, root: Path) -> None:
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    unix = root / "lib" / "wine" / "x86_64-unix"
    for entry in sorted(unix.iterdir()):
        target = macos / entry.name
        if entry.name == "vulkan" and entry.is_dir():
            _copy_vulkan_icds(entry, target)
        elif entry.is_file() and not entry.is_symlink():
            _link_or_copy(entry, target)
        else:
            target.symlink_to(entry)
    (macos / "x86_64-unix").symlink_to(".")
    for entry in sorted((root / "lib" / "wine").iterdir()):
        if entry.name.endswith("-windows"):
            (macos / entry.name).symlink_to(entry)
    for entry in sorted((root / "lib").iterdir()):
        if entry.name != "wine" and not (macos / entry.name).exists():
            (macos / entry.name).symlink_to(entry)
    (app / "bin").symlink_to(root / "bin")
    (app / "share").symlink_to(root / "share")


def _write_icon(res: Path, exe: Optional[Path]) -> bool:
    if not exe or not exe.is_file():
        return False
    try:
        ico = icons.extract_ico(exe)
    except (icons.IconError, OSError, ValueError, IndexError, struct_error):
        return False
    if not ico:
        return False
    res.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "app.ico"
        src.write_bytes(ico)
        r = subprocess.run(["sips", "-s", "format", "icns", str(src), "--out", str(res / "app.icns")],
                           capture_output=True)
    return r.returncode == 0 and (res / "app.icns").is_file()


def create(store: Store, bottle: Bottle, program: str, name: str,
           dest: Optional[Path] = None, wine: Optional[str] = None,
           replace: bool = False) -> Path:
    if not name.strip() or "/" in name or name.startswith("."):
        raise BottleError("invalid app name: %r" % name)
    root = wine_root(launcher.find_wine(wine, bottle))
    dest = Path(dest or paths.apps_dir())
    app = dest / (name + ".app")
    if app.exists():
        if not any((app / "Contents" / m).is_file() for m in (MARKER,) + LEGACY_MARKERS):
            raise BottleError("%s exists and was not created by CrossBottle" % app)
        if not replace:
            raise BottleError("%s already exists; use --replace to rebuild it" % app)
        shutil.rmtree(app)
    outer_macos = app / "Contents" / "MacOS"
    resources = app / "Contents" / "Resources"
    inner = resources / (name + ".app")
    outer_macos.mkdir(parents=True)
    try:
        _populate_wine(inner, root)
        has_icon = _write_icon(resources, windows_to_unix(bottle, program))
        if has_icon:
            (inner / "Contents" / "Resources").mkdir(parents=True, exist_ok=True)
            shutil.copy2(resources / "app.icns", inner / "Contents" / "Resources" / "app.icns")

        # Ship a copy of crossbottle inside the app: apps opened from Finder cannot read
        # privacy-protected folders such as ~/Documents, where the source may live.
        shutil.copytree(Path(__file__).resolve().parent, resources / "python" / "crossbottle",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        script = "\n".join([
            "#!/bin/sh",
            "# Generated by CrossBottle; rebuild with `crossbottle shortcut --replace`.",
            'here="$(cd "$(dirname "$0")" && pwd)"',
            'mkdir -p "$HOME/Library/Logs/CrossBottle"',
            'exec >>"$HOME/Library/Logs/CrossBottle/%s.log" 2>&1' % _slug(name),
            'echo "--- $(date) launching %s"' % _slug(name),
            'export PYTHONPATH="$here/../Resources/python"',
        ] + _vulkan_exports(inner, name) + [
            "exec %s -m crossbottle --root %s run --exec --wine \"$here/../Resources/%s/Contents/MacOS/wine\" %s %s \"$@\"" % (
                shlex.quote(sys.executable), shlex.quote(str(store.root)), name + ".app",
                shlex.quote(bottle.name), shlex.quote(program)),
            "",
        ])
        (outer_macos / LAUNCHER).write_text(script)
        (outer_macos / LAUNCHER).chmod(0o755)

        ident = "io.crossbottle.%s.%s" % (_slug(bottle.name), _slug(name))
        base = {
            "CFBundleName": name[:15],
            "CFBundleDisplayName": name,
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "1.0",
            "CFBundleVersion": "1",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        }
        if has_icon:
            base["CFBundleIconFile"] = "app"
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump(dict(base, CFBundleIdentifier=ident, CFBundleExecutable=LAUNCHER), f)
        with open(inner / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump(dict(base, CFBundleIdentifier=ident + ".wine", CFBundleExecutable="wine"), f)
        (app / "Contents" / MARKER).write_text(json.dumps(
            {"bottle": bottle.name, "bottle_uuid": bottle.meta.uuid, "program": program,
             "wine_root": str(root)}, indent=2))
    except Exception:
        shutil.rmtree(app, ignore_errors=True)
        raise
    if os.path.exists(LSREGISTER):
        for bundle in (inner, app):
            subprocess.run([LSREGISTER, "-f", str(bundle)], capture_output=True)
    return app
