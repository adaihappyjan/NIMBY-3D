"""Your own model: a GLB (glTF 2.0 binary, as Blender exports it) turned into GOV2 parts.

Standard library only. What is read: the scene's nodes (their hierarchy, translation, rotation, scale
or matrix), meshes (triangles: POSITION, NORMAL, TEXCOORD_0, indices) and materials (base colour
factor, metallic, roughness, emissive, alpha mode, double sided). Textures, skins, morph targets,
animations, cameras and lights are not used (the add-on draws plain coloured materials).

GOV2 parts have no rotation of their own, so every node's rotation and scale are baked into its
vertices; a part keeps only its origin (where wheelsets and bogies turn, from where doors slide).

A node's role comes from its custom properties (glTF "extras", Blender: Object Properties ->
Custom Properties, exported with Include -> Custom Properties), else from its name:

  door_left_*, door_right_*   a door leaf on the left (-Z) / right (+Z) side; it slides along
                              slide_axis (property; or _fwd / _back at the end of the name: +X / -X;
                              else away from the nearest leaf beside it) by travel_m (property; else
                              its own length), open_seconds / close_seconds (1.6 / 0.7)
  bogie_*                     turns about its origin around +Y
  wheelset_*, wheels_*, axle_*  turns about its origin around +Z; radius_m (property; else half its height)
  interior_*                  left out at LOD2 (and kept at LOD0/1)
  coupler_*                   a coupler
  detail_*                    left out at LOD1 and LOD2 when they are made from LOD0
  anything else               a static part of the body

A material is glass (blended, both sides) when its alpha mode is BLEND, or its name says glass or
window and its alpha is below 1.

The model must be in metres, +X the front, +Y up, +Z right, the origin at the middle of the vehicle on
the rail head (Blender: front along +X, top along +Z, the right side towards -Y; export glTF 2.0 with
+Y Up). check() says where an import breaks these rules.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import struct
import sys
import threading
from array import array
from pathlib import Path

from .geometry import Model
from . import materials as mats

MAX_GLB = 300 << 20
GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
NORM_DIV = {"b": 127.0, "B": 255.0, "h": 32767.0, "H": 65535.0}
RIG_KEYS = ("role", "detail", "slide_axis", "travel_m", "side", "animation_ready", "open_seconds", "close_seconds", "rotation_axis", "radius_m")
RIG_ROLES = ("door_leaf", "bogie", "wheelset", "coupler", "vehicle_root")


class GlbError(ValueError):
    pass


def _msg(en, zh, **kw):
    return {"en": en.format(**kw), "zh": zh.format(**kw)}


# ---------------------------------------------------------------- reading the file

def parse(data: bytes):
    """(the glTF JSON, [buffers as bytes])"""
    if len(data) > MAX_GLB:
        raise GlbError("the file is larger than 300 MB")
    if data[:1] == b"{" or data[:3] == b"\xef\xbb\xbf":
        raise GlbError("this is a .gltf text file: export as glTF Binary (.glb) instead")
    if len(data) < 20:
        raise GlbError("not a GLB file (too short)")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise GlbError("not a GLB file (it does not start with glTF)")
    if version != 2:
        raise GlbError(f"a GLB of version {version}: only glTF 2.0 is read")
    off, end = 12, min(length, len(data))
    doc, binary = None, None
    while off + 8 <= end:
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == JSON_CHUNK and doc is None:
            try:
                doc = json.loads(chunk.decode("utf-8").rstrip(" \0"))
            except (UnicodeDecodeError, ValueError) as ex:
                raise GlbError(f"the GLB's JSON cannot be read: {ex}") from None
        elif ctype == BIN_CHUNK and binary is None:
            binary = chunk
    if not isinstance(doc, dict):
        raise GlbError("the GLB has no JSON chunk")
    buffers = []
    for i, b in enumerate(doc.get("buffers") or []):
        uri = b.get("uri")
        if uri is None:
            if binary is None:
                raise GlbError("the GLB names a binary buffer but has none")
            buffers.append(binary)
        elif isinstance(uri, str) and uri.startswith("data:"):
            try:
                buffers.append(base64.b64decode(uri.split(",", 1)[1]))
            except (IndexError, ValueError):
                raise GlbError(f"buffer {i} has a data URI that cannot be read") from None
        else:
            raise GlbError(f"buffer {i} is in another file ({uri}): export as glTF Binary (.glb), which keeps everything in one file")
    return doc, buffers


def accessor(doc, buffers, index):
    """An accessor as a flat list of numbers and its number of components."""
    try:
        a = doc["accessors"][index]
    except (KeyError, IndexError, TypeError):
        raise GlbError(f"accessor {index} does not exist") from None
    if "sparse" in a:
        raise GlbError("sparse accessors are not supported (Blender does not write them for meshes)")
    fmt, size = COMP.get(a.get("componentType"), (None, 0))
    n = NCOMP.get(a.get("type"))
    if fmt is None or n is None:
        raise GlbError(f"accessor {index} has a type this importer does not read")
    count = int(a.get("count", 0))
    if "bufferView" not in a:
        return [0.0] * (count * n), n
    bv = doc["bufferViews"][a["bufferView"]]
    buf = buffers[bv.get("buffer", 0)]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    elem = size * n
    stride = bv.get("byteStride") or elem
    if count and start + stride * (count - 1) + elem > len(buf):
        raise GlbError(f"accessor {index} reaches past the end of its buffer")
    arr = array(fmt)
    if stride == elem:
        arr.frombytes(buf[start:start + count * elem])
    else:
        arr.frombytes(b"".join(buf[start + k * stride:start + k * stride + elem] for k in range(count)))
    if sys.byteorder != "little":
        arr.byteswap()
    if a.get("normalized") and fmt in NORM_DIV:
        d = NORM_DIV[fmt]
        return [max(v / d, -1.0) for v in arr], n
    return arr, n


# ---------------------------------------------------------------- transforms (3x3 row-major + translation)

IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _is_identity(L):
    return all(L[r][c] == (1.0 if r == c else 0.0) for r in range(3) for c in range(3))


def _mul(A, B):
    return tuple(tuple(sum(A[r][k] * B[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def _apply(L, v):
    return (L[0][0] * v[0] + L[0][1] * v[1] + L[0][2] * v[2],
            L[1][0] * v[0] + L[1][1] * v[1] + L[1][2] * v[2],
            L[2][0] * v[0] + L[2][1] * v[1] + L[2][2] * v[2])


def _local(node):
    """(L, t, translation as given or None) of a node."""
    if "matrix" in node:
        m = node["matrix"]
        L = tuple(tuple(float(m[c * 4 + r]) for c in range(3)) for r in range(3))
        return L, (m[12], m[13], m[14]), None
    t = node.get("translation") or [0, 0, 0]
    x, y, z, w = node.get("rotation") or [0, 0, 0, 1]
    s = node.get("scale") or [1, 1, 1]
    if (x, y, z, w) == (0, 0, 0, 1):
        R = IDENTITY
    else:
        R = ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
             (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
             (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))
    if list(s) == [1, 1, 1]:
        L = R
    else:
        L = tuple(tuple(R[r][c] * s[c] for c in range(3)) for r in range(3))
    return L, tuple(t), (list(t) if "translation" in node else [0, 0, 0])


def _inverse_transpose(L):
    a, b, c = L
    det = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if abs(det) < 1e-12:
        return None
    inv = [[(b[1] * c[2] - b[2] * c[1]) / det, (a[2] * c[1] - a[1] * c[2]) / det, (a[1] * b[2] - a[2] * b[1]) / det],
           [(b[2] * c[0] - b[0] * c[2]) / det, (a[0] * c[2] - a[2] * c[0]) / det, (a[2] * b[0] - a[0] * b[2]) / det],
           [(b[0] * c[1] - b[1] * c[0]) / det, (a[1] * c[0] - a[0] * c[1]) / det, (a[0] * b[1] - a[1] * b[0]) / det]]
    return tuple(tuple(inv[c][r] for c in range(3)) for r in range(3))


# ---------------------------------------------------------------- names and roles

def _clean_name(name: str) -> str:
    """Blender adds .001, .002 to duplicate names."""
    return re.sub(r"\.\d{3,}$", "", name or "")


def material_key(name: str, used: set) -> str:
    k = re.sub(r"[^a-z0-9_]", "_", (name or "").lower()).strip("_")
    k = re.sub(r"_+", "_", k)
    if not k or not k[0].isalpha():
        k = "m_" + k if k else "material"
    k = k[:40]
    base, n = k, 2
    while k in used:
        k = f"{base[:36]}_{n}"
        n += 1
    used.add(k)
    return k


def role_of(name: str, extras: dict):
    """(role, side, extras for the part) from custom properties, else the name."""
    ex = {k: v for k, v in extras.items() if k in RIG_KEYS} if isinstance(extras, dict) else {}
    nm = _clean_name(name).lower()
    role = ex.get("role")
    side = ex.get("side")
    if not isinstance(role, str):
        if nm.startswith("door_left"):
            role, side = "door_leaf", "left"
        elif nm.startswith("door_right"):
            role, side = "door_leaf", "right"
        elif nm.startswith("bogie"):
            role = "bogie"
        elif nm.startswith(("wheelset", "wheels", "axle")):
            role = "wheelset"
        elif nm.startswith("interior"):
            role = "interior"
        elif nm.startswith("coupler"):
            role = "coupler"
        else:
            role = "static"
    if role == "door_leaf" and side not in ("left", "right"):
        side = "left" if "left" in nm else "right" if "right" in nm else None
    return role, side, ex


# ---------------------------------------------------------------- the conversion

class Imported:
    """A GLB converted: parts (as Model parts, origins and bindings), materials (GLB order), and what
    was noticed (warnings), before LOD reduction and material overrides."""

    def __init__(self):
        self.parts = []          # {"name","translation","parent","extras","primitives":{mat:{"vertices","indices"}}, "node": i, "size": diag}
        self.materials = []      # {"key","name","rgba","metallic","roughness","emissive","blend","double_sided"}
        self.warnings = []
        self.textures = 0


def convert(data: bytes, unit_id: str, scale=1.0, turn=False, offset=(0, 0, 0)) -> Imported:
    doc, buffers = parse(data)
    out = Imported()
    # materials
    used = set()
    for i, m in enumerate(doc.get("materials") or []):
        pbr = m.get("pbrMetallicRoughness") or {}
        rgba = list(pbr.get("baseColorFactor", [1, 1, 1, 1]))
        if len(rgba) != 4:
            rgba = [1, 1, 1, 1]
        rgba = [min(1, max(0, v)) if isinstance(v, (int, float)) else 1 for v in rgba]
        if pbr.get("baseColorTexture") is not None:
            out.textures += 1
        em = list(m.get("emissiveFactor", [0, 0, 0]))
        strength = ((m.get("extensions") or {}).get("KHR_materials_emissive_strength") or {}).get("emissiveStrength")
        if isinstance(strength, (int, float)) and strength != 1:
            em = [v * strength for v in em]
        em = tuple(min(1, max(0, v)) for v in em) if any(em) else tuple(em)
        name = str(m.get("name") or f"material_{i}")
        alpha_mode = m.get("alphaMode", "OPAQUE")
        glassy = re.search(r"glass|window|glas|玻璃", name, re.I) is not None
        blend = alpha_mode == "BLEND" or (glassy and rgba[3] < 1)
        out.materials.append({"key": material_key(name, used), "name": name, "rgba": rgba,
                              "metallic": min(1, max(0, pbr.get("metallicFactor", 1))), "roughness": min(1, max(0, pbr.get("roughnessFactor", 1))),
                              "emissive": em, "blend": blend, "double_sided": bool(m.get("doubleSided", False)) or blend})
    default_mat = None
    # the scene's nodes
    nodes = doc.get("nodes") or []
    scenes = doc.get("scenes") or []
    if scenes:
        roots = list((scenes[doc.get("scene", 0)] if doc.get("scene", 0) < len(scenes) else scenes[0]).get("nodes") or [])
    else:
        children = {c for n in nodes for c in n.get("children") or []}
        roots = [i for i in range(len(nodes)) if i not in children]
    meshes = doc.get("meshes") or []

    def wanted(i, seen=()):
        if i in seen or i >= len(nodes):
            return False
        n = nodes[i]
        if "mesh" in n or (isinstance(n.get("extras"), dict) and isinstance(n["extras"].get("role"), str)):
            return True
        return any(wanted(c, seen + (i,)) for c in n.get("children") or [])
    s = float(scale)
    A = IDENTITY if s == 1 and not turn else tuple(tuple((-s if (turn and r != 1 and r == c) else s if r == c else 0.0) for c in range(3)) for r in range(3))
    A_t = tuple(float(v) for v in offset)
    adjust = not (_is_identity(A) and A_t == (0.0, 0.0, 0.0))
    # one root part: the scene's own when it is a single vehicle_root node, else one made here
    root_given = len(roots) == 1 and isinstance(nodes[roots[0]].get("extras"), dict) and nodes[roots[0]]["extras"].get("role") == "vehicle_root"
    if not root_given:
        out.parts.append({"name": unit_id, "translation": [0, 0, 0], "parent": None, "extras": {"role": "vehicle_root"}, "primitives": {}, "node": None,
                          "size": 0, "_world": (0.0, 0.0, 0.0), "_name": ""})
    names = {unit_id} if not root_given else set()

    def visit(i, parent_part, parent_L, parent_t, parent_is_part_node, depth):
        nonlocal default_mat
        if depth > 64 or not wanted(i):
            return
        n = nodes[i]
        L_l, t_l, t_given = _local(n)
        L_w = _mul(parent_L, L_l)
        t_w = tuple(a + b for a, b in zip(_apply(parent_L, t_l), parent_t)) if not (_is_identity(parent_L) and parent_t == (0.0, 0.0, 0.0)) else tuple(float(v) for v in t_l)
        role, side, ex = role_of(n.get("name", ""), n.get("extras") or {})
        name = n.get("name") or f"node_{i}"
        base, k = name, 2
        while name in names:
            name = f"{base}_{k}"
            k += 1
        names.add(name)
        # the part's origin relative to its parent part (no rotation in GOV2: a world-space difference;
        # as the file gives it when nothing above it turns or scales, so nothing is rounded on the way)
        if not adjust and _is_identity(parent_L) and t_given is not None:
            translation = list(t_given)
        else:
            pt = out.parts[parent_part]["_world"] if parent_part is not None else (0.0, 0.0, 0.0)
            translation = [t_w[k2] - pt[k2] for k2 in range(3)]
        extras = {"role": role}
        for key, v in ex.items():
            if key != "role":
                extras[key] = v
        if role == "door_leaf":
            extras["side"] = side
        else:
            extras.pop("side", None)
        part = {"name": name, "translation": translation, "parent": parent_part, "extras": extras, "primitives": {}, "node": i,
                "_world": t_w, "_name": _clean_name(n.get("name", "")).lower()}
        out.parts.append(part)
        me = len(out.parts) - 1
        if "mesh" in n:
            ident = _is_identity(L_w)
            NL = None if ident else _inverse_transpose(L_w)
            a_, b_, c_ = L_w
            mirrored = (a_[0] * (b_[1] * c_[2] - b_[2] * c_[1]) - a_[1] * (b_[0] * c_[2] - b_[2] * c_[0]) + a_[2] * (b_[0] * c_[1] - b_[1] * c_[0])) < 0
            for prim in (meshes[n["mesh"]].get("primitives") or []) if n["mesh"] < len(meshes) else []:
                mode = prim.get("mode", 4)
                if mode != 4:
                    out.warnings.append(_msg("{name}: a primitive that is not triangles (mode {mode}) was left out",
                                             "{name}：一个不是三角形的图元（mode {mode}）被略过了", name=name, mode=mode))
                    continue
                attrs = prim.get("attributes") or {}
                if "POSITION" not in attrs:
                    continue
                pos, _ = accessor(doc, buffers, attrs["POSITION"])
                nv = len(pos) // 3
                nrm = accessor(doc, buffers, attrs["NORMAL"])[0] if "NORMAL" in attrs else None
                uv = accessor(doc, buffers, attrs["TEXCOORD_0"])[0] if "TEXCOORD_0" in attrs else None
                idx = list(accessor(doc, buffers, prim["indices"])[0]) if "indices" in prim else list(range(nv))
                if len(idx) % 3:
                    idx = idx[:len(idx) - len(idx) % 3]
                if idx and max(idx) >= nv:
                    raise GlbError(f"{name}: an index past its vertices")
                mi = prim.get("material")
                if mi is None or mi >= len(out.materials):
                    if default_mat is None:
                        out.materials.append({"key": material_key("default", used), "name": "default", "rgba": [0.6, 0.6, 0.6, 1], "metallic": 0,
                                              "roughness": 0.6, "emissive": (0, 0, 0), "blend": False, "double_sided": False})
                        default_mat = len(out.materials) - 1
                    mi = default_mat
                verts = []
                need_flat = nrm is None
                for v in range(nv):
                    p = (pos[3 * v], pos[3 * v + 1], pos[3 * v + 2])
                    if not ident:
                        p = _apply(L_w, p)
                    if nrm is not None:
                        q = (nrm[3 * v], nrm[3 * v + 1], nrm[3 * v + 2])
                        if NL is not None:
                            q = _apply(NL, q)
                        ll = q[0] * q[0] + q[1] * q[1] + q[2] * q[2]
                        if abs(ll - 1) > 1e-5:
                            if ll < 1e-12:
                                need_flat = True
                                q = (0.0, 1.0, 0.0)
                            else:
                                d = math.sqrt(ll)
                                q = (q[0] / d, q[1] / d, q[2] / d)
                    else:
                        q = (0.0, 1.0, 0.0)
                    t = (uv[2 * v], uv[2 * v + 1]) if uv is not None else (0.0, 0.0)
                    verts.append((*p, *q, *t))
                if mirrored:
                    # a mirroring transform turns faces inside out: keep them facing out
                    for k2 in range(0, len(idx), 3):
                        idx[k2 + 1], idx[k2 + 2] = idx[k2 + 2], idx[k2 + 1]
                if need_flat:
                    verts, idx = _flat(verts, idx)
                if not idx:
                    continue
                bucket = part["primitives"].setdefault(mi, {"vertices": [], "indices": []})
                at = len(bucket["vertices"])
                bucket["vertices"].extend(verts)
                bucket["indices"].extend(k2 + at for k2 in idx)
        for c in n.get("children") or []:
            visit(c, me, L_w, t_w, True, depth + 1)

    for r in roots:
        visit(r, 0 if not root_given else None, A, A_t, False, 0)
    for p in out.parts:
        vs = [v for pr in p["primitives"].values() for v in pr["vertices"]]
        if vs:
            lo = [min(v[k] for v in vs) for k in range(3)]
            hi = [max(v[k] for v in vs) for k in range(3)]
            p["size"] = math.sqrt(sum((hi[k] - lo[k]) ** 2 for k in range(3)))
            p["_box"] = (lo, hi)
        else:
            p["size"] = 0
            p["_box"] = None
    _bind(out)
    if out.textures:
        out.warnings.append(_msg("{n} material(s) use a texture: the add-on draws plain colours, so each takes its base colour factor (set the colours in the editor)",
                                 "{n} 个材质用了贴图：附加组件只画纯色，所以取材质的基础颜色（可在编辑器里改颜色）", n=out.textures))
    if doc.get("skins"):
        out.warnings.append(_msg("skins (armatures) are ignored: apply them before exporting", "骨骼蒙皮被忽略：导出前先应用", ))
    return out


def _flat(verts, idx):
    """Per-face normals (vertices split), for meshes without normals."""
    out, oi = [], []
    for k in range(0, len(idx), 3):
        a, b, c = verts[idx[k]], verts[idx[k + 1]], verts[idx[k + 2]]
        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        d = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if d < 1e-12:
            continue
        n = (n[0] / d, n[1] / d, n[2] / d)
        base = len(out)
        for v in (a, b, c):
            out.append((v[0], v[1], v[2], *n, v[6], v[7]))
        oi.extend((base, base + 1, base + 2))
    return out, oi


def _bind(out: Imported):
    """Fill in the bindings a role needs that the file did not give."""
    leaves = [p for p in out.parts if p["extras"]["role"] == "door_leaf"]
    for p in out.parts:
        ex = p["extras"]
        role = ex["role"]
        box = p.get("_box")
        if role == "door_leaf":
            if ex.get("side") not in ("left", "right"):
                ex["side"] = "right" if p["_world"][2] >= 0 else "left"
            if "slide_axis" not in ex:
                nm = p.get("_name", "")
                if re.search(r"(_fwd|_front|_px|_\+x)$", nm):
                    ex["slide_axis"] = [1, 0, 0]
                elif re.search(r"(_back|_rear|_nx|_-x)$", nm):
                    ex["slide_axis"] = [-1, 0, 0]
                else:
                    # away from the nearest leaf of the same side
                    others = [q for q in leaves if q is not p and q["extras"].get("side") == ex["side"]]
                    near = min(others, key=lambda q: abs(q["_world"][0] - p["_world"][0]), default=None)
                    if near is not None and abs(near["_world"][0] - p["_world"][0]) < 2.0:
                        ex["slide_axis"] = [1, 0, 0] if p["_world"][0] > near["_world"][0] else [-1, 0, 0]
                    else:
                        ex["slide_axis"] = [1, 0, 0]
                        out.warnings.append(_msg("{name}: no slide direction (custom property slide_axis, or _fwd / _back in the name): it slides to +X",
                                                 "{name}：没有滑动方向（自定义属性 slide_axis，或名字结尾 _fwd / _back）：按 +X 滑动", name=p["name"]))
            if "travel_m" not in ex:
                ex["travel_m"] = round(min(2.0, max(0.2, (box[1][0] - box[0][0]) if box else 0.6)), 3)
            ex.setdefault("animation_ready", True)
            ex.setdefault("open_seconds", 1.6)
            ex.setdefault("close_seconds", 0.7)
            tv = ex["travel_m"]
            if not isinstance(tv, (int, float)) or not 0 < tv <= 2:
                ex["travel_m"] = min(2.0, max(0.01, float(tv) if isinstance(tv, (int, float)) else 0.6))
            for key in ("open_seconds", "close_seconds"):
                if not isinstance(ex[key], (int, float)) or ex[key] <= 0:
                    ex[key] = 1.6 if key == "open_seconds" else 0.7
            sa = ex["slide_axis"]
            ll = math.sqrt(sum(float(v) ** 2 for v in sa)) or 1
            if abs(ll - 1) > 1e-6:
                ex["slide_axis"] = [float(v) / ll for v in sa]
        elif role == "bogie":
            ex.setdefault("rotation_axis", [0, 1, 0])
        elif role == "wheelset":
            ex.setdefault("rotation_axis", [0, 0, 1])
            if "radius_m" not in ex:
                r = (box[1][1] - box[0][1]) / 2 if box else 0.45
                ex["radius_m"] = round(min(3.0, max(0.05, r)), 4)
                if not box:
                    out.warnings.append(_msg("{name}: a wheelset without a mesh: radius 0.45 m assumed", "{name}：轮对没有网格，按半径 0.45 米", name=p["name"]))


def check(out: Imported, length=None, width=None) -> list:
    """Where the model breaks the conventions (metres, +X front, +Y up, origin on the rail head in the middle)."""
    w = []
    vs_lo = [math.inf] * 3
    vs_hi = [-math.inf] * 3
    world = {}
    for i, p in enumerate(out.parts):
        t = p["translation"] if p["parent"] is None else [a + b for a, b in zip(p["translation"], world[p["parent"]])]
        world[i] = t
        if p.get("_box"):
            lo, hi = p["_box"]
            for k in range(3):
                vs_lo[k] = min(vs_lo[k], lo[k] + t[k])
                vs_hi[k] = max(vs_hi[k], hi[k] + t[k])
    if vs_lo[0] == math.inf:
        return [_msg("the model has no triangles", "模型里没有三角形")]
    ext = [vs_hi[k] - vs_lo[k] for k in range(3)]
    cx, cz = (vs_hi[0] + vs_lo[0]) / 2, (vs_hi[2] + vs_lo[2]) / 2
    if ext[0] > 150:
        w.append(_msg("it is {l:.0f} units long: probably centimetres or millimetres (set the scale, e.g. 0.01)",
                      "长 {l:.0f} 个单位：大概是厘米或毫米（设缩放，比如 0.01）", l=ext[0]))
    if ext[2] > ext[0] * 1.2 or ext[1] > ext[0] * 1.2:
        w.append(_msg("its long side is not along X: in Blender point the train along +X (top +Z) and export with +Y Up",
                      "长边不在 X 方向：在 Blender 里让列车朝 +X（上为 +Z），导出时选 +Y Up"))
    if length and abs(ext[0] - length) > max(0.6, length * 0.04) and ext[0] <= 150:
        w.append(_msg("it is {l:.2f} m long, the unit {u:.2f} m (the add-on stretches it to the unit's length; model it to size)",
                      "模型长 {l:.2f} 米，车辆是 {u:.2f} 米（附加组件会按车辆长度拉伸；最好按尺寸建模）", l=ext[0], u=length))
    if width and ext[2] > width + 0.6 and ext[0] <= 150:
        w.append(_msg("it is {w:.2f} m wide, the unit {u:.2f} m", "模型宽 {w:.2f} 米，车辆是 {u:.2f} 米", w=ext[2], u=width))
    if abs(cx) > 0.25:
        w.append(_msg("its middle is at x = {c:.2f} m, not 0: the origin must be the middle of the vehicle", "中心在 x = {c:.2f} 米而不是 0：原点必须在车辆中间", c=cx))
    if abs(cz) > 0.15:
        w.append(_msg("its middle is at z = {c:.2f} m, not 0", "中心在 z = {c:.2f} 米而不是 0", c=cz))
    if vs_lo[1] < -0.05:
        w.append(_msg("it reaches {d:.2f} m below the rail head (y = 0 is the top of the rail)", "低于轨面 {d:.2f} 米（y = 0 是轨面）", d=-vs_lo[1]))
    elif vs_lo[1] > 0.25:
        w.append(_msg("its lowest point is {d:.2f} m above the rail head: the wheels should stand on y = 0", "最低点高出轨面 {d:.2f} 米：车轮应该站在 y = 0 上", d=vs_lo[1]))
    return w


def report(out: Imported, triangles=None) -> dict:
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    world = {}
    roles = {}
    for i, p in enumerate(out.parts):
        t = p["translation"] if p["parent"] is None else [a + b for a, b in zip(p["translation"], world[p["parent"]])]
        world[i] = t
        roles[p["extras"]["role"]] = roles.get(p["extras"]["role"], 0) + 1
        if p.get("_box"):
            for k in range(3):
                lo[k] = min(lo[k], p["_box"][0][k] + t[k])
                hi[k] = max(hi[k], p["_box"][1][k] + t[k])
    box = {"min": lo, "max": hi} if lo[0] != math.inf else None
    return {"parts": len(out.parts), "roles": roles, "materials": len(out.materials), "box": box, "triangles": triangles}


# ---------------------------------------------------------------- per level of detail

_CACHE = {}
_CACHE_LOCK = threading.Lock()


def load(path: str, unit_id: str, scale, turn, offset) -> Imported:
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        raise GlbError(f"{path} cannot be found") from None
    key = (os.path.normcase(str(p.resolve())), st.st_size, st.st_mtime_ns, unit_id, float(scale), bool(turn), tuple(offset))
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit
    if st.st_size > MAX_GLB:
        raise GlbError(f"{p.name} is larger than 300 MB")
    out = convert(p.read_bytes(), unit_id, scale, turn, offset)
    with _CACHE_LOCK:
        if len(_CACHE) > 12:
            _CACHE.clear()
        _CACHE[key] = out
    return out


class ImportCtx:
    """What the exporters and the preview use of a built model (as parts.Ctx): spec, lod, m, materials."""

    def __init__(self, spec, lod, m, materials, report_, warnings):
        self.spec, self.lod, self.m, self.materials = spec, lod, m, materials
        self.report = report_
        self.warnings = warnings


def build(spec: dict, lod: int) -> ImportCtx:
    imp = spec["import"]
    lods = list(imp.get("lods") or [])
    lods += [None] * (3 - len(lods))
    scale, turn, offset = imp.get("scale", 1), bool(imp.get("turn", False)), tuple(imp.get("offset") or (0, 0, 0))
    own = lods[lod]
    src = own or lods[0]
    if not src:
        raise GlbError("no GLB file for LOD0")
    out = load(src, spec["unit_id"], scale, turn, offset)
    reduce_ = own is None and lod > 0
    m = Model(spec["unit_id"], spec["length"], spec["width"], lod)
    m.parts = []
    cell = float(imp.get("lod1_cell", 0.03) if lod == 1 else imp.get("lod2_cell", 0.10))
    for p in out.parts:
        prims = p["primitives"]
        if reduce_:
            if not _keep(p, lod, imp):
                prims = {}
            elif cell > 0:
                prims = {mat: _cluster(pr, cell) for mat, pr in prims.items()}
                prims = {mat: pr for mat, pr in prims.items() if pr["indices"]}
        m.parts.append({"name": p["name"], "translation": list(p["translation"]), "parent": p["parent"], "extras": dict(p["extras"]), "primitives": prims})
    m.root = 0
    # materials: the file's, with the spec's changes (by key); glass opaque at LOD2
    overrides = spec.get("materials") or {}
    table = []
    for mt in out.materials:
        o = overrides.get(mt["key"]) or {}
        rgba = list(mats.parse_color(o["color"])) if o.get("color") is not None and mats.parse_color(o["color"]) else list(mt["rgba"][:3])
        rgba.append(o.get("alpha", mt["rgba"][3]))
        em = mats.parse_color(o["emissive"]) if o.get("emissive") is not None else None
        blend = bool(o.get("blend", mt["blend"]))
        entry = {"key": mt["key"], "name": str(o.get("name") or mt["name"]), "rgba": rgba, "metallic": o.get("metallic", mt["metallic"]),
                 "roughness": o.get("roughness", mt["roughness"]), "emissive": tuple(em) if em else (tuple(mt["emissive"]) if "emissive" not in o else (0, 0, 0)),
                 "blend": blend, "double_sided": bool(o.get("double_sided", mt["double_sided"]))}
        if entry["blend"] and lod == 2:
            entry["rgba"][3] = 1
            entry["blend"] = False
        table.append(entry)
    m.materials = table
    warnings = list(out.warnings) if lod == 0 else []
    if lod == 0:
        warnings += check(out, spec.get("length"), spec.get("width"))
    st = m.stats()
    return ImportCtx(spec, lod, m, table, report(out, st["triangles"]), warnings)


def _cluster(prim, cell):
    """A lighter mesh for a lower level of detail: vertices closer than `cell` metres merged (each to
    the middle of its grid cell's vertices), triangles that collapse dropped, flat normals. Kept as it
    was when that saves nothing."""
    verts, idx = prim["vertices"], prim["indices"]
    if len(idx) < 30:
        return prim
    inv = 1.0 / cell
    cells = {}
    of = []
    for v in verts:
        key = (math.floor(v[0] * inv), math.floor(v[1] * inv), math.floor(v[2] * inv))
        c = cells.get(key)
        if c is None:
            c = cells[key] = [len(cells), 0.0, 0.0, 0.0, 0]
        c[1] += v[0]
        c[2] += v[1]
        c[3] += v[2]
        c[4] += 1
        of.append(c[0])
    pos = [None] * len(cells)
    for c in cells.values():
        pos[c[0]] = (c[1] / c[4], c[2] / c[4], c[3] / c[4])
    seen = set()
    out_v, out_i = [], []
    for k in range(0, len(idx), 3):
        a, b, c = of[idx[k]], of[idx[k + 1]], of[idx[k + 2]]
        if a == b or b == c or a == c:
            continue
        r = min((a, b, c), (b, c, a), (c, a, b))
        if r in seen:
            continue
        seen.add(r)
        pa, pb, pc = pos[a], pos[b], pos[c]
        e1 = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        e2 = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        d = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if d < 1e-10:
            continue
        n = (n[0] / d, n[1] / d, n[2] / d)
        base = len(out_v)
        for pp in (pa, pb, pc):
            out_v.append((pp[0], pp[1], pp[2], n[0], n[1], n[2], 0.0, 0.0))
        out_i.extend((base, base + 1, base + 2))
    if len(out_i) >= len(idx) * 0.9:
        return prim
    return {"vertices": out_v, "indices": out_i}


def _keep(p, lod, imp):
    role = p["extras"]["role"]
    if role in RIG_ROLES:
        return True
    name = p.get("_name", "")
    if name.startswith("detail"):
        return False
    if lod == 2 and role == "interior" and imp.get("lod2_drop_interior", True):
        return False
    limit = imp.get("lod1_drop_below", 0.10) if lod == 1 else imp.get("lod2_drop_below", 0.35)
    return p.get("size", 0) >= limit


def materials_of(path: str, unit_id="unit") -> dict:
    """The materials of a GLB as a spec's materials (key -> values), for the editor to change."""
    out = load(path, unit_id, 1, False, (0, 0, 0))
    res = {}
    for mt in out.materials:
        d = {"name": mt["name"], "color": list(mt["rgba"][:3]), "alpha": mt["rgba"][3], "metallic": mt["metallic"], "roughness": mt["roughness"]}
        if any(mt["emissive"]):
            d["emissive"] = list(mt["emissive"])
        if mt["blend"]:
            d["blend"] = True
        if mt["double_sided"]:
            d["double_sided"] = True
        res[mt["key"]] = d
    return res
