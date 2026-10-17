"""One-command setups for well-known programs."""
from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from . import cefwrap, graphics, launcher, paths, shortcut
from .bottle import BottleError, Store

STEAM_INSTALLER_URL = "https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe"
STEAM_EXE = r"C:\Program Files (x86)\Steam\Steam.exe"
STEAM_ARGS = ["-noverifyfiles", "-no-cef-sandbox"]


def _download(url: str, dest: Path, say: Callable[[str], None]) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    say("Downloading %s" % url)
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    if tmp.read_bytes()[:2] != b"MZ":
        tmp.unlink()
        raise BottleError("download from %s is not a Windows executable" % url)
    tmp.replace(dest)
    return dest


def _first_update(bottle, wine_bin: str, say: Callable[[str], None], timeout: int = 900) -> None:
    """Start Steam once so it downloads its client (incl. steamwebhelper), then close it."""
    say("First Steam start: downloading the Steam client (a few minutes)")
    log = shortcut.windows_to_unix(bottle, STEAM_EXE).parent / "logs" / "bootstrap_log.txt"
    start = time.time()
    # No flags here: -noverifyfiles would also skip downloading the client.
    proc = subprocess.Popen(launcher.build_command(wine_bin, STEAM_EXE, [], None),
                            env=launcher.build_env(bottle), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    exited_at = None
    try:
        while time.time() - start < timeout:
            text = log.read_text(errors="replace") if log.is_file() else ""
            if cefwrap.find_helpers(bottle) and "Update complete" in text:
                break
            if proc.poll() is not None and "Downloading update" not in text:
                exited_at = exited_at or time.time()
                if time.time() - exited_at > 45:
                    raise BottleError("Steam exited without updating; see %s" % log)
            time.sleep(3)
        else:
            raise BottleError("Steam did not finish its first update in %d s" % timeout)
        time.sleep(10)  # let the updated client start before asking it to quit
    finally:
        subprocess.run(launcher.build_command(wine_bin, STEAM_EXE, ["-shutdown"], None),
                       env=launcher.build_env(bottle), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=120)
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
        server = Path(wine_bin).resolve().parent / "wineserver"
        if server.is_file():  # stop leftover Wine services before files are swapped
            subprocess.run([str(server), "-k"], env=launcher.build_env(bottle), timeout=60)
            time.sleep(3)


def install_steam(store: Store, name: str = "Steam", installer: Optional[Path] = None,
                  wine: Optional[str] = None, make_app: bool = True,
                  say: Callable[[str], None] = print) -> Optional[Path]:
    """Create a bottle with Steam, the CEF fix, DXVK (if installed) and a Dock app."""
    if store.exists(name):
        bottle = store.get(name)
        say("Using existing bottle %s" % name)
    else:
        bottle = store.create(name, "win10", description="Steam")
        say("Created bottle %s" % name)
    wine_bin = launcher.find_wine(wine, bottle)
    if not bottle.meta.wine:
        bottle.meta.wine = wine_bin
        bottle.save()
    say("Wine: %s" % wine_bin)

    if not shortcut.windows_to_unix(bottle, STEAM_EXE).is_file():
        setup = Path(installer) if installer else _download(
            STEAM_INSTALLER_URL, paths.data_dir() / "Cache" / "SteamSetup.exe", say)
        say("Installing Steam (first run also creates the Windows prefix, ~1 min)")
        rc = launcher.run(bottle, str(setup), ["/S"])
        if rc != 0 or not shortcut.windows_to_unix(bottle, STEAM_EXE).is_file():
            raise BottleError("Steam installer failed (exit code %s)" % rc)
    else:
        say("Steam already installed")

    if not cefwrap.find_helpers(bottle):
        _first_update(bottle, wine_bin, say)

    table = dict(bottle.meta.program_args or {})
    table[launcher.program_key(STEAM_EXE)] = list(STEAM_ARGS)
    bottle.meta.program_args = table
    bottle.save()

    for helper, what in cefwrap.apply(bottle):
        say("Steam web helper: %s" % what)
    bottle.meta.cefwrap = True
    bottle.save()

    if (graphics.default_runtime() / "x64" / "d3d11.dll").is_file():
        graphics.apply(bottle, "dxvk")
        say("Graphics: DXVK (Direct3D 10/11 games)")
    else:
        say("Graphics: Wine default (run install.sh to add DXVK for Direct3D 11 games)")

    if not make_app:
        return None
    app = shortcut.create(store, bottle, STEAM_EXE, name, replace=True)
    say("App: %s" % app)
    return app
