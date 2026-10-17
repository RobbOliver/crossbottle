"""Extract the main icon of a Windows PE executable as an .ico file."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

RT_ICON = 3
RT_GROUP_ICON = 14


class IconError(Exception):
    pass


def _sections(data: bytes) -> Tuple[List[Tuple[int, int, int]], int]:
    """Return [(virtual_address, size, raw_offset)] and the resource directory RVA."""
    if data[:2] != b"MZ":
        raise IconError("not a PE file")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise IconError("not a PE file")
    nsect, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (96 if magic == 0x10B else 112)
    res_rva = struct.unpack_from("<I", data, dirs + 2 * 8)[0]
    table = opt + opt_size
    secs = []
    for i in range(nsect):
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, table + i * 40 + 8)
        secs.append((va, max(vsize, rawsize), raw))
    return secs, res_rva


def _rva_to_offset(secs, rva: int) -> int:
    for va, size, raw in secs:
        if va <= rva < va + size:
            return rva - va + raw
    raise IconError("RVA 0x%x outside sections" % rva)


def _resources(data: bytes) -> Dict[int, Dict[int, bytes]]:
    """{type_id: {name_id: first-language data}} for integer-ID resources."""
    secs, res_rva = _sections(data)
    if not res_rva:
        return {}
    base = _rva_to_offset(secs, res_rva)

    def entries(off: int):
        named, ids = struct.unpack_from("<HH", data, base + off + 12)
        for i in range(named + ids):
            name, target = struct.unpack_from("<II", data, base + off + 16 + i * 8)
            yield name, target

    def leaf(target: int) -> bytes:
        while target & 0x80000000:  # descend into the first subdirectory entry
            target = next(entries(target & 0x7FFFFFFF))[1]
        rva, size = struct.unpack_from("<II", data, base + target)
        start = _rva_to_offset(secs, rva)
        return data[start:start + size]

    out: Dict[int, Dict[int, bytes]] = {}
    for type_id, type_target in entries(0):
        if type_id & 0x80000000 or not type_target & 0x80000000:
            continue
        names: Dict[int, bytes] = {}
        for name_id, target in entries(type_target & 0x7FFFFFFF):
            key = name_id if not name_id & 0x80000000 else -len(names) - 1
            names[key] = leaf(target)
        out[type_id] = names
    return out


def extract_ico(exe: Path) -> Optional[bytes]:
    """Return the first icon group of `exe` as .ico bytes, or None if it has none."""
    res = _resources(Path(exe).read_bytes())
    groups, icons = res.get(RT_GROUP_ICON), res.get(RT_ICON, {})
    if not groups:
        return None
    group = groups[sorted(groups)[0]] if all(k >= 0 for k in groups) else next(iter(groups.values()))
    count = struct.unpack_from("<H", group, 4)[0]
    images = []
    for i in range(count):
        w, h, colors, _, planes, bpp, _, icon_id = struct.unpack_from("<BBBBHHIH", group, 6 + i * 14)
        blob = icons.get(icon_id)
        if blob:
            images.append((w, h, colors, planes, bpp, blob))
    if not images:
        return None
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    table, body = b"", b""
    for w, h, colors, planes, bpp, blob in images:
        table += struct.pack("<BBBBHHII", w, h, colors, 0, planes, bpp, len(blob), offset + len(body))
        body += blob
    return header + table + body


def best_png(ico: bytes) -> Optional[bytes]:
    """Largest PNG-compressed image inside an .ico, if any (Vista+ 256px icons)."""
    count = struct.unpack_from("<H", ico, 4)[0]
    best = None
    for i in range(count):
        w, h, _, _, _, _, size, off = struct.unpack_from("<BBBBHHII", ico, 6 + i * 16)
        blob = ico[off:off + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            dim = w or 256
            if best is None or dim > best[0]:
                best = (dim, blob)
    return best[1] if best else None
