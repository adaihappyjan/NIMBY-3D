"""GOV2: the binary model format the nimby3d add-on reads (src/vehicle_models.h, gov_decode).

Little-endian; a string is a u32 byte length and UTF-8 bytes.

  magic "GOV2"; u32 material_count, part_count
  material: string name; f32 rgba[4], metallic, roughness, emissive[3]; u32 blend (0/1), double_sided (0/1)
  part:     string name; i32 parent (-1, else an earlier part); f32 translation[3]
            string role; u32 door_side (0 none, 1 left -Z, 2 right +Z)
            f32 slide_axis[3], travel_m, open_seconds, close_seconds, rotation_axis[3], wheel_radius_m
            u32 primitive_count; per primitive: u32 material, vertex_count, index_count,
            vertices (f32 position[3], normal[3], uv[2]), indices (u32)

encode() writes a Model (geometry.py) exactly as the GO reference generator did; decode() is a port of
the add-on's reader with every rule it enforces, so a file it accepts here is one the add-on accepts.
"""
from __future__ import annotations

import math
import struct
from array import array

MAGIC_V1 = 0x31564F47
MAGIC_V2 = 0x32564F47
MAX_BYTES = 64 << 20


class GovError(ValueError):
    pass


def encode(m, materials) -> bytes:
    out = bytearray(b"GOV2")

    def u(n):
        out.extend(struct.pack("<I", n))

    def f(values):
        out.extend(struct.pack("<" + "f" * len(values), *values))

    def s(text):
        b = text.encode()
        u(len(b))
        out.extend(b)
    u(len(materials))
    u(len(m.parts))
    for mat in materials:
        s(mat["name"])
        f((*mat["rgba"], mat["metallic"], mat["roughness"], *mat["emissive"]))
        u(int(mat["blend"]))
        u(int(mat["double_sided"]))
    for p in m.parts:
        s(p["name"])
        out.extend(struct.pack("<i", p["parent"] if p["parent"] is not None else -1))
        f(p["translation"])
        ex = p["extras"]
        s(ex["role"])
        u({"left": 1, "right": 2}.get(ex.get("side"), 0))
        f(ex.get("slide_axis", [0, 0, 0]))
        f([ex.get("travel_m", 0), ex.get("open_seconds", 0), ex.get("close_seconds", 0)])
        f(ex.get("rotation_axis", [0, 0, 0]))
        f([ex.get("radius_m", 0)])
        u(len(p["primitives"]))
        for mat, prim in sorted(p["primitives"].items()):
            u(mat)
            u(len(prim["vertices"]))
            u(len(prim["indices"]))
            for v in prim["vertices"]:
                f(v)
            for idx in prim["indices"]:
                u(idx)
    return bytes(out)


def decode(data: bytes) -> dict:
    """The model a GOV1/GOV2 file holds, or GovError with the reason the add-on would give."""
    n = len(data)
    if n > MAX_BYTES:
        raise GovError("larger than 64 MB")
    at = 0

    def u32():
        nonlocal at
        if n - at < 4:
            raise GovError("truncated")
        v = struct.unpack_from("<I", data, at)[0]
        at += 4
        return v

    def f32():
        nonlocal at
        if n - at < 4:
            raise GovError("truncated")
        v = struct.unpack_from("<f", data, at)[0]
        at += 4
        if not math.isfinite(v):
            raise GovError("a number that is not finite")
        return v

    def text():
        nonlocal at
        k = u32()
        if k > 4096 or k > n - at:
            raise GovError("a name too long")
        s = data[at:at + k].decode("utf-8", errors="replace")
        at += k
        return s
    magic = u32()
    if magic not in (MAGIC_V1, MAGIC_V2):
        raise GovError("not GOV1 or GOV2")
    version = 2 if magic == MAGIC_V2 else 1
    nm, np_ = u32(), u32()
    if nm == 0 or nm > 256 or np_ == 0 or np_ > 4096:
        raise GovError("material or part count out of range")
    materials = []
    for _ in range(nm):
        mat = {"name": text(), "rgba": [f32() for _ in range(4)]}
        mat["metallic"], mat["roughness"] = f32(), f32()
        if any(c < 0 or c > 1 for c in mat["rgba"]):
            raise GovError("a colour out of range")
        if not (0 <= mat["metallic"] <= 1 and 0 <= mat["roughness"] <= 1):
            raise GovError("metallic or roughness out of range")
        mat["emissive"], mat["blend"], mat["double_sided"] = [0.0, 0.0, 0.0], False, False
        if version == 2:
            em = [f32() for _ in range(3)]
            if any(c < 0 or c > 1 for c in em):
                raise GovError("emission out of range")
            blend, two = u32(), u32()
            if blend > 1 or two > 1:
                raise GovError("material flags out of range")
            mat["emissive"], mat["blend"], mat["double_sided"] = em, bool(blend), bool(two)
        materials.append(mat)
    parts = []
    total_v = total_i = 0
    for i in range(np_):
        p = {"name": text()}
        parent = u32()
        if parent != 0xFFFFFFFF and parent >= i:
            raise GovError("a parent after its child")
        p["parent"] = -1 if parent == 0xFFFFFFFF else parent
        p["translation"] = [f32() for _ in range(3)]
        p.update(role="", door_side=0, slide=[0.0] * 3, travel=0.0, open_s=0.0, close_s=0.0, axis=[0.0] * 3, radius=0.0)
        if version == 2:
            p["role"] = text()
            p["door_side"] = u32()
            p["slide"] = [f32() for _ in range(3)]
            p["travel"], p["open_s"], p["close_s"] = f32(), f32(), f32()
            p["axis"] = [f32() for _ in range(3)]
            p["radius"] = f32()
            sn = sum(c * c for c in p["slide"])
            rn = sum(c * c for c in p["axis"])
            if p["door_side"] > 2 or p["travel"] < 0 or p["travel"] > 2 or p["radius"] < 0 or p["radius"] > 3:
                raise GovError("rig values out of range")
            if p["role"] == "door_leaf" and (p["door_side"] == 0 or abs(sn - 1) > 0.002 or p["travel"] <= 0 or p["open_s"] <= 0 or p["close_s"] <= 0):
                raise GovError("a door leaf without a valid binding")
            if p["role"] != "door_leaf" and p["door_side"] != 0:
                raise GovError("a door side on a part that is not a door")
            if p["role"] in ("bogie", "wheelset") and abs(rn - 1) > 0.002:
                raise GovError("a bogie or wheelset without a valid axis")
            if p["role"] == "wheelset" and p["radius"] <= 0:
                raise GovError("a wheelset without a radius")
        count = u32()
        if count > 256:
            raise GovError("too many primitives in a part")
        prims = []
        for _ in range(count):
            mat, nv, ni = u32(), u32(), u32()
            if mat >= nm or nv == 0 or ni == 0 or ni % 3 != 0 or nv > 1000000 or ni > 3000000:
                raise GovError("a primitive out of range")
            total_v += nv
            total_i += ni
            if total_v > 1000000 or total_i > 3000000 or nv * 32 + ni * 4 > n - at:
                raise GovError("buffer sizes out of range")
            verts = array("f")
            verts.frombytes(data[at:at + nv * 32])
            at += nv * 32
            if verts.itemsize != 4:
                raise GovError("this Python has no 32-bit floats")
            for v in range(nv):
                b = v * 8
                for k in range(8):
                    if not math.isfinite(verts[b + k]):
                        raise GovError("a number that is not finite")
                nn = verts[b + 3] * verts[b + 3] + verts[b + 4] * verts[b + 4] + verts[b + 5] * verts[b + 5]
                if abs(nn - 1) > 0.002:
                    raise GovError("a normal that is not of unit length")
            idx = array("I")
            if idx.itemsize != 4:
                idx = array("L")
            idx.frombytes(data[at:at + ni * 4])
            at += ni * 4
            if max(idx) >= nv:
                raise GovError("an index past its vertices")
            prims.append({"material": mat, "verts": verts, "idx": idx})
        p["prims"] = prims
        parts.append(p)
    if at != n:
        raise GovError("bytes left over at the end")
    return {"version": version, "materials": materials, "parts": parts}


def bake_stats(model: dict) -> dict:
    """What the add-on's bake_model keeps of a decoded model: triangle and vertex counts (opaque and
    glass), the extent in the rest pose, and how many vertices belong to door leaves."""
    parts = model["parts"]
    at = []
    tris = opaque = verts = door_vertices = 0
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for i, p in enumerate(parts):
        t = list(p["translation"])
        if p["parent"] >= 0:
            t = [t[k] + at[p["parent"]][k] for k in range(3)]
        at.append(t)
        door = False
        qq = i
        while qq >= 0:
            if parts[qq]["role"] == "door_leaf":
                door = True
                break
            qq = parts[qq]["parent"]
        for pr in p["prims"]:
            nv = len(pr["verts"]) // 8
            verts += nv
            k3 = len(pr["idx"]) // 3
            tris += k3
            if not model["materials"][pr["material"]]["blend"]:
                opaque += k3
            if door:
                door_vertices += nv
            vv = pr["verts"]
            for k in range(3):
                col = vv[k::8]
                lo[k] = min(lo[k], min(col) + t[k])
                hi[k] = max(hi[k], max(col) + t[k])
    return {"triangles": tris, "opaque_triangles": opaque, "vertices": verts, "door_vertices": door_vertices,
            "extent": {"x": [lo[0], hi[0]], "y": [lo[1], hi[1]], "z": [lo[2], hi[2]]} if verts else None}
