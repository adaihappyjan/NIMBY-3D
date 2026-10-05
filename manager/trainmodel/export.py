"""From a spec to files: the GOV2 model of each level of detail, its .rig.json (the parts and their
bindings, for people and other engines), optionally a GLB (glTF 2.0 binary, for Blender and other
viewers; the add-on does not read it), and the manifest entry that names them with their SHA-256.

GLB and rig output follow go_train.py exactly (the GO example specs reproduce the published files).
"""
from __future__ import annotations

import hashlib
import json
import re
import struct

from .gov import encode
from .parts import Ctx
from . import carbody, hood

GENERATOR = "nimby3d-trainmodel"
GENERATOR_VERSION = 1


def build_model(spec: dict, lod: int) -> Ctx:
    """Build one level of detail of a (validated) spec; returns the Ctx (its .m is the Model)."""
    if lod not in (0, 1, 2):
        raise ValueError("LOD must be 0, 1 or 2")
    style = spec["body"]["style"]
    if style == "import":
        from . import glbimport
        return glbimport.build(spec, lod)
    c = Ctx(spec, lod)
    if style == "carbody":
        carbody.build(c)
    elif style == "hood":
        hood.build(c)
    else:
        raise ValueError(f"unknown body style {style}")
    return c


def gov_bytes(c: Ctx) -> bytes:
    return encode(c.m, c.materials)


def rig_bytes(c: Ctx) -> bytes:
    m = c.m
    rig = {"schema": 1, "unit_id": m.unit_id, "lod": m.lod,
           "parts": [{"name": p["name"], "parent": p["parent"], "translation": p["translation"], **p["extras"]} for p in m.parts]}
    # (as the GO pack was written: text mode on Windows, CRLF line ends)
    return json.dumps(rig, indent=2).replace("\n", "\r\n").encode("utf-8")


def glb_bytes(c: Ctx) -> bytes:
    m = c.m
    spec = c.spec
    meta = spec.get("meta") or {}
    asset_version = meta.get("asset_version", "1.0.0")
    generator = meta.get("generator", "Nimby3D train editor")
    doors = spec.get("doors") or {}
    open_s, close_s = doors.get("open_seconds", 1.6), doors.get("close_seconds", .7)
    blob = bytearray()
    views = []
    accessors = []

    def add(values, fmt, type_, components, target):
        while len(blob) % 4:
            blob.append(0)
        start = len(blob)
        flat = [x for row in values for x in row] if components > 1 else values
        blob.extend(struct.pack('<' + fmt * len(flat), *flat))
        views.append({"buffer": 0, "byteOffset": start, "byteLength": len(blob) - start})
        if target:
            views[-1]['target'] = target
        ac = {"bufferView": len(views) - 1, "componentType": 5126 if fmt == 'f' else 5125, "count": len(values), "type": type_}
        if type_ == 'VEC3':
            ac['min'] = [min(v[i] for v in values) for i in range(3)]
            ac['max'] = [max(v[i] for v in values) for i in range(3)]
        accessors.append(ac)
        return len(accessors) - 1
    nodes = []
    meshes = []
    for i, p in enumerate(m.parts):
        node = {k: p[k] for k in ('name', 'translation', 'extras')}
        children = [j for j, n in enumerate(m.parts) if n['parent'] == i]
        if children:
            node['children'] = children
        prims = []
        for mat, prim in sorted(p['primitives'].items()):
            vs = prim['vertices']
            attrs = {'POSITION': add([v[:3] for v in vs], 'f', 'VEC3', 3, 34962),
                     'NORMAL': add([v[3:6] for v in vs], 'f', 'VEC3', 3, 34962),
                     'TEXCOORD_0': add([v[6:] for v in vs], 'f', 'VEC2', 2, 34962)}
            prims.append({'attributes': attrs, 'indices': add(prim['indices'], 'I', 'SCALAR', 1, 34963), 'material': mat})
        if prims:
            node['mesh'] = len(meshes)
            meshes.append({'name': p['name'], 'primitives': prims})
        nodes.append(node)
    animations = []
    for side in ('left', 'right'):
        leaves = [i for i, p in enumerate(m.parts) if p['extras'].get('side') == side and p['extras']['role'] == 'door_leaf']
        for opening, duration in ((True, open_s), (False, close_s)):
            if not leaves:
                continue
            times = [duration * i / 8 for i in range(9)]
            ac = add(times, 'f', 'SCALAR', 1, None)
            accessors[ac].update(min=[0], max=[duration])
            animation = {'name': f'doors_{side}_{"open" if opening else "close"}', 'samplers': [], 'channels': []}
            for i in leaves:
                p = m.parts[i]
                ex = p['extras']
                values = []
                for j in range(9):
                    t = j / 8
                    amount = t * t * (3 - 2 * t)
                    amount = amount if opening else 1 - amount
                    values.append([p['translation'][k] + ex['slide_axis'][k] * ex['travel_m'] * amount for k in range(3)])
                aout = add(values, 'f', 'VEC3', 3, None)
                animation['channels'].append({'sampler': len(animation['samplers']), 'target': {'node': i, 'path': 'translation'}})
                animation['samplers'].append({'input': ac, 'output': aout, 'interpolation': 'LINEAR'})
            animations.append(animation)
    mats = []
    for mt in c.materials:
        mats.append({'name': mt["name"], 'pbrMetallicRoughness': {'baseColorFactor': mt["rgba"], 'metallicFactor': mt["metallic"], 'roughnessFactor': mt["roughness"]},
                     'emissiveFactor': mt["emissive"], 'alphaMode': 'BLEND' if mt["blend"] else 'OPAQUE', 'doubleSided': mt["double_sided"]})
    data = {'asset': {'version': '2.0', 'generator': generator + ' ' + asset_version}, 'scene': 0,
            'scenes': [{'nodes': [m.root]}], 'nodes': nodes, 'meshes': meshes, 'materials': mats,
            'buffers': [{'byteLength': len(blob)}], 'bufferViews': views, 'accessors': accessors,
            'extras': {'unit_id': m.unit_id, 'lod': m.lod, 'units': 'metres', 'forward': '+X', 'up': '+Y', 'asset_version': asset_version}}
    if animations:
        data['animations'] = animations
    js = json.dumps(data, separators=(',', ':')).encode()
    js += b' ' * ((-len(js)) % 4)
    blob += b'\0' * ((-len(blob)) % 4)
    return (struct.pack('<III', 0x46546c67, 2, 12 + 8 + len(js) + 8 + len(blob)) + struct.pack('<II', len(js), 0x4e4f534a) + js +
            struct.pack('<II', len(blob), 0x004e4942) + bytes(blob))


# ---------------------------------------------------------------- file names

_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(10)}


def plain_name(f: str) -> bool:
    """The add-on's rule for a file a manifest names (vehicle_models.h, plain_name + device_name)."""
    if not isinstance(f, str) or not f or len(f.encode("utf-8")) > 128 or f[0] == ".":
        return False
    if any(ch in '/\\:*?"<>|' or ord(ch) < 32 for ch in f):
        return False
    if f[-1] in ". ":
        return False
    if ".." in f:
        return False
    base = f.split(".", 1)[0].rstrip(" ").upper()
    if base in _RESERVED or (len(base) >= 4 and base[:3] in ("COM", "LPT") and base[3:] in ("¹", "²", "³")):
        return False
    return True


def file_stem(unit_id: str) -> str:
    """A unit id as the start of a file name the add-on accepts (unsafe characters become _)."""
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", unit_id).strip(". ") or "unit"
    stem = re.sub(r"\.{2,}", ".", stem)
    if stem != unit_id:
        stem += "_" + hashlib.sha256(unit_id.encode("utf-8")).hexdigest()[:6]
    if not plain_name(stem + "_lod0.gov") or not plain_name(stem + ".train.json"):
        stem = "unit_" + stem
    return stem[:100]


def generate(spec: dict, glb: bool = False, stem: str | None = None) -> dict:
    """Every file of one spec: {"files": {name: bytes}, "entry": manifest model entry, "stats": [...]}."""
    stem = stem or file_stem(spec["unit_id"])
    meta = spec.get("meta") or {}
    files = {}
    variants = []
    stats = []
    for lod in range(3):
        c = build_model(spec, lod)
        name = f"{stem}_lod{lod}"
        gov = gov_bytes(c)
        rig = rig_bytes(c)
        variant = {"lod": lod}
        if glb:
            g = glb_bytes(c)
            files[name + ".glb"] = g
            variant["glb"] = name + ".glb"
        files[name + ".gov"] = gov
        files[name + ".rig.json"] = rig
        variant.update({"native_mesh": name + ".gov", "rig": name + ".rig.json", **c.m.stats()})
        if glb:
            variant["sha256"] = hashlib.sha256(files[name + ".glb"]).hexdigest()
        variant["native_sha256"] = hashlib.sha256(gov).hexdigest()
        variant["rig_sha256"] = hashlib.sha256(rig).hexdigest()
        variants.append(variant)
        st = c.m.stats()
        st.update(lod=lod, bytes=len(gov))
        stats.append(st)
    entry = {"unit_id": spec["unit_id"], "length_m": spec["length"], "width_m": spec["width"],
             "dimension_source": meta.get("dimension_source", "mod.txt length and width; height and details from the spec"),
             "variants": variants}
    return {"files": files, "entry": entry, "stats": stats, "stem": stem}
