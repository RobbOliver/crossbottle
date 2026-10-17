"""Build the environment and command used to run a Windows program in a bottle."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .bottle import Bottle, BottleError


def find_wine(explicit: Optional[str] = None, bottle: Optional[Bottle] = None) -> str:
    """Resolve Wine: explicit argument, then the bottle's setting, then env/PATH."""
    if not explicit and bottle is not None and bottle.meta.wine:
        explicit = bottle.meta.wine
    if explicit:
        found = shutil.which(explicit)
        if not found:
            raise BottleError("Wine not found at %s" % explicit)
        return found
    for c in (os.environ.get("OPENBOTTLE_WINE"), "wine64", "wine"):
        if not c:
            continue
        found = shutil.which(c)
        if found:
            return found
    raise BottleError("Wine not found; install it or set OPENBOTTLE_WINE / --wine")


def build_env(bottle: Bottle, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = dict(os.environ if base is None else base)
    env["WINEPREFIX"] = str(bottle.prefix)
    env["WINEARCH"] = bottle.meta.arch
    env.setdefault("WINEDEBUG", "-all")
    if bottle.meta.dll_overrides:
        env["WINEDLLOVERRIDES"] = bottle.meta.dll_overrides
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        # Lets x86_64 Wine under Rosetta advertise AVX to guests.
        env.setdefault("ROSETTA_ADVERTISE_AVX", "1")
    env["OPENBOTTLE_BOTTLE"] = bottle.name
    env["OPENBOTTLE_UUID"] = bottle.meta.uuid
    for key, value in (bottle.meta.env or {}).items():
        env[str(key)] = str(value)
    return env


def program_key(program: str) -> str:
    """Lowercase executable basename, for both Windows and native paths."""
    return program.replace("\\", "/").rsplit("/", 1)[-1].lower()


def default_args(bottle: Bottle, program: str) -> List[str]:
    return list((bottle.meta.program_args or {}).get(program_key(program), []))


def build_command(wine: str, program: str, args: List[str], workdir: Optional[str]) -> List[str]:
    prog = Path(program)
    if prog.suffix.lower() in (".msi",):
        cmd = [wine, "msiexec", "/i", str(prog)]
    elif prog.suffix.lower() == ".bat":
        cmd = [wine, "cmd", "/c", str(prog)]
    else:
        cmd = [wine, program]
    return cmd + list(args)


def initialize_prefix(bottle: Bottle, wine: str) -> None:
    """Create the Wine prefix on first use."""
    if (bottle.prefix / "system.reg").exists():
        return
    subprocess.run([wine, "wineboot", "--init"], env=build_env(bottle), check=True)


def run(bottle: Bottle, program: str, args: Optional[List[str]] = None,
        wine: Optional[str] = None, workdir: Optional[str] = None,
        wait: bool = True, replace_process: bool = False) -> int:
    wine_bin = find_wine(wine, bottle)
    initialize_prefix(bottle, wine_bin)
    cmd = build_command(wine_bin, program, default_args(bottle, program) + list(args or []), workdir)
    if replace_process:
        # Used by .app shortcuts: Wine becomes the bundle's main process.
        if workdir:
            os.chdir(workdir)
        os.execve(cmd[0], cmd, build_env(bottle))
    proc = subprocess.Popen(cmd, env=build_env(bottle), cwd=workdir or None)
    return proc.wait() if wait else 0
