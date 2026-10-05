"""Export what the in-game add-on needs from a save and from the game's own elevation file.

Usage: python export_data.py <save.nimbyrails5> <out data.bin> [<out dem.bin>]
Read-only on the save and on the game files.

data.bin: "N3D1", u32 stations, u32 nodes, then (x, y) doubles in Web-Mercator metres (y north-up).
dem.bin:  "N3DE", u32 zoom, u32 tile_px, u32 count, then per tile: u32 x, u32 y, tile_px*tile_px u16
          (elevation in metres). Only tiles on or next to the network are included.
"""
import math
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))  # the save reader (tools/vendor/README.txt)
sys.path.insert(0, str(HERE))
import toolkit_savereader as sr  # noqa: E402
from toolkit_coordedit import lonlat_to_mercator  # noqa: E402

WORLD = 2 * math.pi * 6378137.0


def read_save(save: Path):
    raw = sr.Zstd().decompress(sr.split_save(save)[1])
    stations = [lonlat_to_mercator(s.lon, s.lat) for s in sr.read_stations_from_raw(raw)]
    nodes = [lonlat_to_mercator(n.lon, n.lat) for n in sr.read_track_nodes(raw, include_planned=False).values()]
    return stations, nodes


def replaced(out: Path):
    """Open a scratch file next to `out`; the caller writes it and then calls os.replace(scratch, out).
    The add-on reads these files again when they change, and must never see one half written."""
    return out.with_name(out.name + ".new")


def export(save: Path, out: Path) -> tuple[int, int]:
    stations, nodes = read_save(save)
    final, out = out, replaced(out)
    with open(out, "wb") as f:
        f.write(b"N3D1")
        f.write(struct.pack("<II", len(stations), len(nodes)))
        for x, y in stations:
            f.write(struct.pack("<dd", x, y))
        for x, y in nodes:
            f.write(struct.pack("<dd", x, y))
    os.replace(out, final)
    return len(stations), len(nodes)


def read_platforms(raw: bytes, nodes: dict) -> list[tuple[int, int, int]]:
    """Platform edges as (track id, track id, station number).

    A station record lists its platform tracks after its name: `<flag> <b1> <b2> <count>` and
    then `count` track ids. They come as the two ends of each platform: two listed tracks that
    name each other as neighbours are one platform."""
    from toolkit_coordedit import _try_uvarint

    out = []
    for number, st in enumerate(sr.read_stations_from_raw(raw)):
        r = _try_uvarint(raw, st.coord_off + 16)
        if not r:
            continue
        p = r[1] + r[0]  # past the name
        if p + 4 > len(raw) or raw[p] not in (0, 1):
            continue
        r = _try_uvarint(raw, p + 3)
        if not r or r[0] > 4096:
            continue
        count, q = r
        listed = []
        for _ in range(count):
            rr = sr._is_id(raw, q, {sr.TYPE_TRACK})
            if not rr:
                break
            listed.append(rr[0])
            q = rr[1]
        members = set(listed)
        for t in listed:
            n = nodes.get(t)
            if n is None:
                continue
            for c in n.connections:
                if c is not None and c in members and c > t and c in nodes and t in nodes[c].connections:
                    out.append((t, c, number))
    return out


def read_signal_posts(raw: bytes) -> list[tuple[float, float, float, float, int]]:
    """Signals as (x, y, dx, dy, kind): Web-Mercator position, the direction of travel they are
    taken to speak to, and a kind (0 is the plain signal).

    A signal record is `<id of type 3> 3a 00 00 00 <code> 00 <..> <f64 x> <f64 y> <f32 nx> <f32 ny> ...`.
    (nx, ny) is a unit vector across the track, always to the left of the track's own direction,
    so it says how the track runs there but not which way the signal faces. `code` is 0..4 in
    the reference save: 0 (1236 signals) and 1 (816) are taken to be the plain signal facing
    with and against the track's direction, which is a guess; 2..4 are exported as other kinds.
    Type-3 records with another length byte (1a, 36) sit beside platforms, off the track; they
    are not signals and are left out."""
    out = {}
    n = len(raw)
    i = 0
    while i < n - 40:
        if raw[i + 7] != sr.TYPE_SIGNAL:
            i += 1
            continue
        r = sr._is_id(raw, i, {sr.TYPE_SIGNAL})
        if not r:
            i += 1
            continue
        ident, end = r
        i = end
        if raw[end] != 0x3A or raw[end + 1:end + 4] != b"\x00\x00\x00" or ident in out:
            continue
        x, y = struct.unpack_from("<dd", raw, end + 7)
        nx, ny = struct.unpack_from("<ff", raw, end + 23)
        if not (all(math.isfinite(v) for v in (x, y, nx, ny)) and abs(x) < 2.1e7 and abs(y) < 2.1e7 and abs(x) > 1e3):
            continue
        if abs(math.hypot(nx, ny) - 1.0) > 0.05:
            continue
        code = raw[end + 4]
        way = -1.0 if code == 1 else 1.0
        out[ident] = (x, y, ny * way, -nx * way, 0 if code in (0, 1) else code)
    return list(out.values())


def export_tracks(save: Path, out: Path) -> dict:
    """tracks.bin: "N3DT", u32 nodes, then per node: f64 x, f64 y (Web-Mercator metres), i32 a, i32 b
    (indices of the two neighbours, -1 for none), u8 level, u8 variant, 2 unused bytes.
    Level 0 is ground, odd levels are tunnels (1 the shallowest), even levels viaducts (2 the lowest).
    Then "PLAT", u32 count, per platform: i32 node, i32 node, i32 station number;
    "SIGN", u32 count, per signal: f64 x, f64 y, f32 dx, f32 dy, u32 kind;
    and "STAT", u32 count, per station (in the order the platforms number them): f64 x, f64 y,
    u16 length of its name in bytes, the name in UTF-8 (for the name boards on its platforms);
    and "NIDS", u32 count, per node: u32 its number in the game (the index in its id)."""
    raw = sr.Zstd().decompress(sr.split_save(save)[1])
    nodes = sr.read_track_nodes(raw, include_planned=False)
    index = {ident: i for i, ident in enumerate(nodes)}
    special = 0
    platforms = [(index[a], index[b], st) for a, b, st in read_platforms(raw, nodes)]
    signals = read_signal_posts(raw)
    stations = sr.read_stations_from_raw(raw)
    final, out = out, replaced(out)
    with open(out, "wb") as f:
        f.write(b"N3DT")
        f.write(struct.pack("<I", len(nodes)))
        for ident, n in nodes.items():
            x, y = lonlat_to_mercator(n.lon, n.lat)
            # an edge exists only where both nodes name each other
            nb = [index[c] if c is not None and c in nodes and ident in nodes[c].connections else -1 for c in n.connections]
            f.write(struct.pack("<ddiiBBBB", x, y, nb[0], nb[1], n.level_code, n.variant, 0, 0))
            special += 1 if n.level_code else 0
        f.write(b"PLAT")
        f.write(struct.pack("<I", len(platforms)))
        for a, b, st in platforms:
            f.write(struct.pack("<iii", a, b, st))
        f.write(b"SIGN")
        f.write(struct.pack("<I", len(signals)))
        for x, y, dx, dy, kind in signals:
            f.write(struct.pack("<ddffI", x, y, dx, dy, kind))
        f.write(b"STAT")
        f.write(struct.pack("<I", len(stations)))
        for st in stations:
            x, y = lonlat_to_mercator(st.lon, st.lat)
            name = (st.name or "").encode("utf-8")[:480]
            # not through the middle of a character
            name = name.decode("utf-8", errors="ignore").encode("utf-8")
            f.write(struct.pack("<ddH", x, y, len(name)))
            f.write(name)
        # each node's number in the game (its id's index: id >> 16 & 0xffffffff), as the game's
        # memory names the track a train is on
        f.write(b"NIDS")
        f.write(struct.pack("<I", len(nodes)))
        f.write(b"".join(struct.pack("<I", (ident >> 16) & 0xFFFFFFFF) for ident in nodes))
    os.replace(out, final)
    return {"nodes": len(nodes), "special": special, "platforms": len(platforms), "signals": len(signals), "stations": len(stations)}


class PlainDemReader:
    """The game's dem400.pmtiles read with the standard library only (no numpy, no Pillow), for the released
    package. Same tiles as tools/pmtiles_dem.py gives: PMTiles v3, uncompressed directories and tiles,
    zoom 0-8, 434x434 16-bit greyscale PNG (zlib, filters 0-4), elevation in metres; returned as
    little-endian u16 bytes. Slower (about 0.1 s a tile) but byte for byte the same."""

    MAX_ZOOM = 8
    TILE_PX = 434

    def __init__(self, path: Path):
        self.f = open(path, "rb")
        h = self.f.read(127)
        if h[:7] != b"PMTiles" or h[7] != 3:
            raise ValueError("not a PMTiles v3 file")
        (self.root_off, root_len, _, _, self.leaf_off, _, self.data_off, _) = struct.unpack("<8Q", h[8:72])
        if h[97] != 1 or h[98] != 1:
            raise ValueError("compressed PMTiles are not supported here")
        self.f.seek(self.root_off)
        self.root = self._dir(self.f.read(root_len))
        self.leaves = {}

    def close(self):
        self.f.close()

    @staticmethod
    def _varint(b, i):
        r = s = 0
        while True:
            c = b[i]
            i += 1
            r |= (c & 0x7F) << s
            s += 7
            if not c & 0x80:
                return r, i

    def _dir(self, d):
        n, i = self._varint(d, 0)
        ids, runs, lens, offs, last = [], [], [], [], 0
        for _ in range(n):
            v, i = self._varint(d, i)
            last += v
            ids.append(last)
        for target in (runs, lens):
            for _ in range(n):
                v, i = self._varint(d, i)
                target.append(v)
        for k in range(n):
            v, i = self._varint(d, i)
            offs.append(offs[-1] + lens[k - 1] if (v == 0 and k > 0) else v - 1)
        return list(zip(ids, runs, lens, offs))

    @staticmethod
    def _tile_id(z, x, y):
        acc = sum(4 ** i for i in range(z))
        d, s = 0, (1 << z) >> 1
        while s > 0:
            rx = 1 if (x & s) else 0
            ry = 1 if (y & s) else 0
            d += s * s * ((3 * rx) ^ ry)
            if ry == 0:
                if rx == 1:
                    x, y = s - 1 - x, s - 1 - y
                x, y = y, x
            s >>= 1
        return acc + d

    def tile(self, z, x, y):
        tid = self._tile_id(z, x, y)
        d = self.root
        for _ in range(4):
            cand = None
            for e in d:
                if e[0] <= tid:
                    cand = e
                else:
                    break
            if cand is None:
                return None
            if cand[1] == 0:
                if cand[3] not in self.leaves:
                    self.f.seek(self.leaf_off + cand[3])
                    self.leaves[cand[3]] = self._dir(self.f.read(cand[2]))
                d = self.leaves[cand[3]]
                continue
            if tid < cand[0] + cand[1]:
                self.f.seek(self.data_off + cand[3])
                return self._png(self.f.read(cand[2]))
            return None
        return None

    def _png(self, png):
        import zlib
        if png[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG tile")
        p, idat, head = 8, [], None
        while p + 8 <= len(png):
            n, typ = struct.unpack(">I4s", png[p:p + 8])
            if typ == b"IHDR":
                head = struct.unpack(">IIBBBBB", png[p + 8:p + 21])
            elif typ == b"IDAT":
                idat.append(png[p + 8:p + 8 + n])
            elif typ == b"IEND":
                break
            p += 12 + n
        if head is None or head[2:] != (16, 0, 0, 0, 0) or head[:2] != (self.TILE_PX, self.TILE_PX):
            raise ValueError(f"unexpected tile format {head}")
        w, h = head[:2]
        raw = zlib.decompress(b"".join(idat))
        stride, bpp = w * 2, 2
        out = bytearray(stride * h)
        prev = bytearray(stride)
        for r in range(h):
            at = r * (stride + 1)
            ft, row = raw[at], bytearray(raw[at + 1:at + 1 + stride])
            if ft == 1:
                for i in range(bpp, stride):
                    row[i] = (row[i] + row[i - bpp]) & 255
            elif ft == 2:
                row = bytearray((a + b) & 255 for a, b in zip(row, prev))
            elif ft == 3:
                for i in range(stride):
                    row[i] = (row[i] + (((row[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
            elif ft == 4:
                for i in range(stride):
                    a = row[i - bpp] if i >= bpp else 0
                    b = prev[i]
                    c = prev[i - bpp] if i >= bpp else 0
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - c - c)
                    row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            elif ft != 0:
                raise ValueError(f"bad PNG filter {ft}")
            out[r * stride:(r + 1) * stride] = row
            prev = row
        out[0::2], out[1::2] = out[1::2], out[0::2]  # PNG is big-endian; the add-on reads little-endian
        return bytes(out)


def _dem_reader(dem: Path | None):
    """tools/pmtiles_dem.py (numpy, Pillow) when it is there, else the plain reader above."""
    try:
        from pmtiles_dem import MAX_ZOOM, TILE_PX, DemReader
        return MAX_ZOOM, TILE_PX, (DemReader(dem) if dem else DemReader())
    except ImportError:
        if dem is None:
            raise FileNotFoundError("the game's dem400.pmtiles is needed (give its path)")
        r = PlainDemReader(dem)
        return r.MAX_ZOOM, r.TILE_PX, r


def export_dem(save: Path, out: Path, ring: int = 1, dem: Path | None = None) -> int:
    """`dem`: the game's dem400.pmtiles (default: the one in the developer's game folder, pmtiles_dem.DEM_PATH)."""
    MAX_ZOOM, TILE_PX, reader = _dem_reader(dem)

    _, nodes = read_save(save)
    T = WORLD / (1 << MAX_ZOOM)
    wanted = set()
    for x, y in nodes:
        tx, ty = int((x + WORLD / 2) // T), int((WORLD / 2 - y) // T)
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if 0 <= tx + dx < (1 << MAX_ZOOM) and 0 <= ty + dy < (1 << MAX_ZOOM):
                    wanted.add((tx + dx, ty + dy))
    tiles = []
    try:
        for tx, ty in sorted(wanted):
            arr = reader.tile(MAX_ZOOM, tx, ty)
            if arr is not None:
                tiles.append((tx, ty, arr))
    finally:
        if hasattr(reader, "close"):
            reader.close()
    with open(out, "wb") as f:
        f.write(b"N3DE")
        f.write(struct.pack("<III", MAX_ZOOM, TILE_PX, len(tiles)))
        for tx, ty, arr in tiles:
            f.write(struct.pack("<II", tx, ty))
            f.write(arr if isinstance(arr, (bytes, bytearray)) else arr.tobytes())
    return len(tiles)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    ns, nn = export(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"stations {ns}, track nodes {nn} -> {sys.argv[2]}")
    if len(sys.argv) == 4:
        print(f"elevation tiles {export_dem(Path(sys.argv[1]), Path(sys.argv[3]))} -> {sys.argv[3]}")
