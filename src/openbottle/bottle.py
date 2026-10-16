"""Bottle storage: a bottle is a directory holding a Wine prefix plus metadata."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

DEFAULT_ROOT = Path.home() / "Library" / "Application Support" / "OpenBottle" / "Bottles"
META_NAME = "bottle.json"
PREFIX_DIR = "prefix"
SCHEMA_VERSION = 1
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")

WINDOWS_VERSIONS = ("win7", "win10", "win11")


class BottleError(Exception):
    pass


@dataclass
class Meta:
    name: str
    uuid: str
    windows_version: str = "win10"
    arch: str = "win64"
    description: str = ""
    dll_overrides: str = ""
    env: Optional[dict] = None
    # Wine binary used for this bottle; empty means auto-detect.
    wine: str = ""
    # Default arguments per program, keyed by lowercase executable basename.
    program_args: Optional[dict] = None
    # Keep the CEF helper wrapper applied (re-applied before each run).
    cefwrap: bool = False
    # Direct3D 10/11 backend: "" / "wined3d" or "dxvk", and the runtime directory used.
    graphics: str = ""
    graphics_runtime: str = ""
    schema: int = SCHEMA_VERSION


class Bottle:
    def __init__(self, path: Path, meta: Meta):
        self.path = path
        self.meta = meta

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def prefix(self) -> Path:
        return self.path / PREFIX_DIR

    def save(self) -> None:
        tmp = self.path / (META_NAME + ".tmp")
        tmp.write_text(json.dumps(asdict(self.meta), indent=2, sort_keys=True))
        os.replace(tmp, self.path / META_NAME)


class Store:
    """A directory containing bottles."""

    def __init__(self, root: Optional[Path] = None):
        env = os.environ.get("OPENBOTTLE_ROOT")
        self.root = Path(root or env or DEFAULT_ROOT)

    def _path(self, name: str) -> Path:
        if not NAME_RE.match(name) or ".." in name:
            raise BottleError("invalid bottle name: %r" % name)
        return self.root / name

    def exists(self, name: str) -> bool:
        return (self._path(name) / META_NAME).is_file()

    def get(self, name: str) -> Bottle:
        path = self._path(name)
        try:
            data = json.loads((path / META_NAME).read_text())
        except FileNotFoundError:
            raise BottleError("no such bottle: %s" % name)
        except json.JSONDecodeError as exc:
            raise BottleError("corrupt metadata for %s: %s" % (name, exc))
        known = Meta.__dataclass_fields__
        meta = Meta(**{k: v for k, v in data.items() if k in known})
        return Bottle(path, meta)

    def list(self) -> List[Bottle]:
        if not self.root.is_dir():
            return []
        out = []
        for child in sorted(self.root.iterdir()):
            if (child / META_NAME).is_file():
                try:
                    out.append(self.get(child.name))
                except BottleError:
                    continue
        return out

    def create(self, name: str, windows_version: str = "win10", arch: str = "win64",
               description: str = "") -> Bottle:
        if windows_version not in WINDOWS_VERSIONS:
            raise BottleError("unsupported windows version: %s" % windows_version)
        if arch not in ("win32", "win64"):
            raise BottleError("unsupported arch: %s" % arch)
        path = self._path(name)
        if path.exists():
            raise BottleError("bottle already exists: %s" % name)
        (path / PREFIX_DIR).mkdir(parents=True)
        bottle = Bottle(path, Meta(name=name, uuid=str(uuid.uuid4()),
                                   windows_version=windows_version, arch=arch,
                                   description=description))
        bottle.save()
        return bottle

    def copy(self, source: str, target: str) -> Bottle:
        src = self.get(source)
        dst = self._path(target)
        if dst.exists():
            raise BottleError("bottle already exists: %s" % target)
        shutil.copytree(src.path, dst, symlinks=True)
        new = self.get(target)
        new.meta.name = target
        new.meta.uuid = str(uuid.uuid4())
        new.save()
        return new

    def delete(self, name: str) -> None:
        bottle = self.get(name)
        shutil.rmtree(bottle.path)

    def set_uuid(self, name: str, value: Optional[str] = None) -> str:
        bottle = self.get(name)
        bottle.meta.uuid = str(uuid.UUID(value)) if value else str(uuid.uuid4())
        bottle.save()
        return bottle.meta.uuid
