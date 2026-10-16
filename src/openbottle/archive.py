"""Bottle export/import as a gzip-compressed tar (.obarchive)."""
from __future__ import annotations

import tarfile
import uuid
from pathlib import Path, PurePosixPath

from .bottle import BottleError, META_NAME, Store

EXTENSION = ".obarchive"


def export_bottle(store: Store, name: str, dest: Path) -> Path:
    bottle = store.get(name)
    dest = Path(dest)
    if dest.suffix != EXTENSION:
        dest = dest.with_name(dest.name + EXTENSION)
    with tarfile.open(dest, "w:gz", compresslevel=9) as tar:
        tar.add(bottle.path, arcname=bottle.name)
    return dest


def _check_member(member: tarfile.TarInfo, top: str, symlinks: set) -> None:
    p = PurePosixPath(member.name)
    if p.is_absolute() or ".." in p.parts or p.parts[0] != top:
        raise BottleError("unsafe path in archive: %s" % member.name)
    if member.islnk() or member.isdev():
        raise BottleError("unsupported member in archive: %s" % member.name)
    # Wine prefixes legitimately contain symlinks (dosdevices/c: -> ../drive_c,
    # z: -> /). They are inert unless a later member is written *through* one,
    # so reject any member whose parent path is, or sits under, a symlink.
    for parent in p.parents:
        if str(parent) in symlinks:
            raise BottleError("member written through symlink: %s" % member.name)
    if member.issym():
        symlinks.add(str(p))


def import_bottle(store: Store, archive: Path, rename: str = "") -> str:
    archive = Path(archive)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise BottleError("empty archive")
        top = PurePosixPath(members[0].name).parts[0]
        symlinks: set = set()
        for m in members:
            _check_member(m, top, symlinks)
        if "%s/%s" % (top, META_NAME) not in {m.name for m in members}:
            raise BottleError("archive has no %s" % META_NAME)
        name = rename or top
        target = store._path(name)
        if target.exists():
            raise BottleError("bottle already exists: %s" % name)
        store.root.mkdir(parents=True, exist_ok=True)
        tar.extractall(store.root, members=members)
        if name != top:
            (store.root / top).rename(target)
    bottle = store.get(name)
    bottle.meta.name = name
    # A restored bottle gets a fresh identity so it never collides with its source.
    bottle.meta.uuid = str(uuid.uuid4())
    bottle.save()
    return name
