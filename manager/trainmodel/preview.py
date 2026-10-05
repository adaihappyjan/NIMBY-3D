"""A built model as a compact mesh for the editor's WebGL viewer.

Positions are quantised to 16 bits over the model's extent, normals to 8 bits; per vertex a material
index, a door index (0: not a door leaf; k: the k-th entry of "doors", whose slide vector says where
it goes when its side opens) and a group (0 body, 1 interior, 2 door leaf, 3 running gear, 4 the
interior wall lining). Each
array is base64 of little-endian bytes. Indices: opaque triangles first, then glass.
"""
from __future__ import annotations

import base64
import sys
from array import array

from . import materials as mats

GROUPS = {"interior": 1, "door_leaf": 2, "bogie": 3, "wheelset": 3, "coupler": 3}


def _b64(arr: array) -> str:
    if sys.byteorder != "little":
        arr = array(arr.typecode, arr)
        arr.byteswap()
    return base64.b64encode(arr.tobytes()).decode("ascii")


def encode(c) -> dict:
    m = c.m
    parts = m.parts
    at = []
    door_of = []
    doors = []
    group_of = []
    for i, p in enumerate(parts):
        t = list(p["translation"])
        if p["parent"] is not None:
            t = [t[k] + at[p["parent"]][k] for k in range(3)]
        at.append(t)
        # the nearest door leaf up the tree moves this part
        dd = 0
        g = 4 if p["extras"].get("detail") == "lining" else GROUPS.get(p["extras"]["role"], 0)
        qq = i
        while qq is not None:
            ex = parts[qq]["extras"]
            if ex["role"] == "door_leaf":
                if qq == i:
                    doors.append({"side": {"left": 1, "right": 2}.get(ex.get("side"), 0),
                                  "slide": [ex["slide_axis"][k] * ex["travel_m"] for k in range(3)], "part": p["name"]})
                    dd = len(doors)
                else:
                    dd = door_of[qq]
                g = 2
                break
            qq = parts[qq]["parent"]
        door_of.append(dd)
        group_of.append(g)
    pos, nrm = [], []
    mat_ids = array("B")
    door_ids = array("B")
    groups = array("B")
    opaque, glass = [], []
    blend = [mt["blend"] for mt in c.materials]
    for i, p in enumerate(parts):
        ox, oy, oz = at[i]
        for mat, prim in sorted(p["primitives"].items()):
            base = len(pos)
            for v in prim["vertices"]:
                pos.append((v[0] + ox, v[1] + oy, v[2] + oz))
                nrm.append((v[3], v[4], v[5]))
            n = len(prim["vertices"])
            mat_ids.extend([mat] * n)
            door_ids.extend([min(door_of[i], 255)] * n)
            groups.extend([group_of[i]] * n)
            (glass if blend[mat] else opaque).extend(base + k for k in prim["indices"])
    count = len(pos)
    if count == 0:
        lo = [0.0, 0.0, 0.0]
        hi = [1.0, 1.0, 1.0]
    else:
        lo = [min(pv[k] for pv in pos) for k in range(3)]
        hi = [max(pv[k] for pv in pos) for k in range(3)]
    span = [max(hi[k] - lo[k], 1e-6) for k in range(3)]
    qpos = array("H")
    for pv in pos:
        qpos.extend(int(round((pv[k] - lo[k]) / span[k] * 65535)) for k in range(3))
    qn = array("b")
    for nv in nrm:
        qn.extend(max(-127, min(127, int(round(x * 127)))) for x in nv)
    idx = opaque + glass
    index_type = "u16" if count <= 65535 else "u32"
    ia = array("H" if index_type == "u16" else "I", idx)
    if ia.itemsize != (2 if index_type == "u16" else 4):
        ia = array("L", idx)
    materials = []
    for mt in c.materials:
        materials.append({"key": mt["key"], "name": mt["name"], "color": mats.hex_of(mt["rgba"][:3]), "alpha": mt["rgba"][3],
                          "emissive": mats.hex_of(mt["emissive"]) if any(mt["emissive"]) else None,
                          "metallic": mt["metallic"], "roughness": mt["roughness"], "blend": mt["blend"]})
    return {
        "lod": m.lod,
        "count": count,
        "min": lo, "max": hi,
        "positions": _b64(qpos),
        "normals": _b64(qn),
        "material": _b64(mat_ids),
        "door": _b64(door_ids),
        "group": _b64(groups),
        "indices": _b64(ia),
        "index_type": index_type,
        "opaque": len(opaque),
        "triangles": len(idx) // 3,
        "materials": materials,
        "doors": doors,
        "parts": [{"name": p["name"], "role": p["extras"]["role"]} for p in parts],
    }
