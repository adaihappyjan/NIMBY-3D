"""A mod folder as the nimby3d add-on sees it.

read_units(): the [TrainUnit]s of a mod.txt, read as src/rollingstock.h reads them (a unit counts
only with an id and a length above 0; keys and values trimmed; ; and # start comment lines).

check_manifest(): nimby3d/manifest.json judged by the rules of src/vehicle_models.h
(VehicleLibrary::add_mod), with the same outcome for every model: used, or "not used" and why. The
add-on's own JSON reader is stricter than Python's in places (no byte order mark, no NaN); those
differences are reported as the add-on would see them.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .export import plain_name
from .gov import decode, bake_stats, GovError

MAX_MODEL_FILE = 64 << 20
MAX_MODTXT = 4 << 20


# ---------------------------------------------------------------- mod.txt

def _trim(s: str) -> str:
    return s.strip(" \t\r\n\v\f")


def parse_mod_txt(text: str) -> dict:
    """{"meta": {...ModMeta...}, "units": [{id, length, width, tags, name}], "sections": n}"""
    sections = []
    cur = None
    for raw in text.split("\n"):
        line = _trim(raw)
        if not line or line[0] in ";#":
            continue
        if line[0] == "[":
            e = line.find("]")
            cur = {"name": line[1:e if e >= 0 else None], "kv": []}
            sections.append(cur)
            continue
        if cur is None:
            cur = {"name": "", "kv": []}
            sections.append(cur)
        eq = line.find("=")
        if eq >= 0:
            cur["kv"].append((_trim(line[:eq]), _trim(line[eq + 1:])))
    meta = {}
    units = []
    for sec in sections:
        if sec["name"].lstrip("﻿") == "ModMeta":
            for k, v in sec["kv"]:
                meta[k] = v
        if sec["name"] != "TrainUnit":
            continue
        u = {"id": "", "length": 0.0, "width": 0.0, "tags": [], "name": "",
             "tex_base": [], "tex_top": [], "tex_decors": [], "tex_m_width": 30.0, "tex_m_height": 3.75}
        for k, v in sec["kv"]:
            if k == "id":
                u["id"] = v
            elif k == "tags":
                u["tags"] = [t for t in re.split(r"[\s,]+", v) if t]
            elif k in ("length", "width"):
                u[k] = _number(v)
            elif k == "name_en" or (k == "name" and not u["name"]):
                u["name"] = v
            elif k == "max_pax":
                u["max_pax"] = _number(v)
            elif k in ("tex_base", "tex_top", "tex_decors"):
                # the sprite's pictures, paths inside the mod folder (comma separated; the key may repeat)
                u[k] += [p.strip() for p in v.split(",") if p.strip()]
            elif k in ("tex_m_width", "tex_m_height"):
                n = _number(v)
                if n > 0:
                    u[k] = n
        if u["id"] and u["length"] > 0:
            units.append(u)
    return {"meta": meta, "units": units}


def _number(s: str) -> float:
    m = re.match(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", s)
    try:
        v = float(m.group(0)) if m else 0.0
    except ValueError:
        v = 0.0
    return v if v == v and abs(v) < 3.4e38 else 0.0


def read_mod_txt(path: Path) -> dict:
    data = path.read_bytes()[:MAX_MODTXT]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return parse_mod_txt(text)


# ---------------------------------------------------------------- the add-on's JSON

def _strict_json(raw: bytes):
    """Parse as the add-on's little JSON reader does: UTF-8, no byte order mark, no NaN/Infinity, the
    first of duplicate keys wins. Raises ValueError with the reason."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("it starts with a UTF-8 byte order mark (BOM), which the add-on's reader does not accept")

    def first_wins(pairs):
        out = {}
        for k, v in pairs:
            if k not in out:
                out[k] = v
        return out

    def no_constants(name):
        raise ValueError(f"{name} is not a number the add-on reads")
    text = raw.decode("utf-8", errors="replace")
    return json.loads(text, object_pairs_hook=first_wins, parse_constant=no_constants)


def _num(d, key, fallback):
    v = d.get(key) if isinstance(d, dict) else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else fallback


def _text(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, str) else ""


# ---------------------------------------------------------------- nimby3d/manifest.json

def check_manifest(folder: Path, mod: str) -> dict:
    """Judge <folder>/nimby3d/manifest.json for the mod named `mod` (its Workshop item: the folder's
    name; "" for the game's own trains, whose source must be "builtin"), as the add-on would.

    {"found": bool, "used": bool, "notes": [add-on log lines], "problems": [str], "models": [
       {"unit_id", "used", "why", "lods": [{lod, file, triangles, ok, why}], "length_m", "width_m"}],
     "source_workshop_id": str}"""
    nd = Path(folder) / "nimby3d"
    out = {"found": False, "used": False, "notes": [], "problems": [], "models": [], "source_workshop_id": None}
    man = nd / "manifest.json"
    if not man.is_file():
        return out
    out["found"] = True
    label = mod or "the game's own trains"
    try:
        raw = man.read_bytes()
        root = _strict_json(raw)
    except (OSError, ValueError) as ex:
        out["notes"].append(f"{label}: manifest.json is not JSON; not used")
        out["problems"].append(f"manifest.json cannot be read as the add-on reads it: {ex}")
        return out
    if not isinstance(root, dict):
        out["notes"].append(f"{label}: manifest.json is not JSON; not used")
        out["problems"].append("manifest.json must hold a JSON object { ... }")
        return out
    if _num(root, "schema", 0) != 2 or _text(root, "native_format") != "GOV2":
        out["notes"].append(f"{label}: a manifest of another schema or format; not used")
        out["problems"].append('the manifest must have "schema": 2 (a number) and "native_format": "GOV2"')
        return out
    source = _text(root, "source_workshop_id")
    out["source_workshop_id"] = source
    if (source != "builtin") if not mod else (source != mod):
        out["notes"].append(f"{label}: the manifest is for {source or 'nothing named'}, not this; not used")
        out["problems"].append(f'"source_workshop_id" is {source!r} but must be {"builtin" if not mod else mod!r}'
                               + ("" if not mod else " (the mod folder's name: its Workshop item number)"))
        return out
    models = root.get("models")
    if not isinstance(models, list):
        out["problems"].append('the manifest has no "models" list')
        return out
    seen = set()
    for i, mv in enumerate(models):
        unit = _text(mv, "unit_id")
        length = _num(mv, "length_m", 0)
        vars_ = mv.get("variants") if isinstance(mv, dict) else None
        rec = {"unit_id": unit, "used": False, "why": "", "lods": [], "length_m": length, "width_m": _num(mv, "width_m", 0)}
        out["models"].append(rec)
        if not unit or length <= 0 or not isinstance(vars_, list):
            rec["why"] = "skipped without a word in the log: it needs unit_id, length_m above 0 and a variants list"
            out["problems"].append(f"models[{i}] ({unit or 'no unit_id'}): {rec['why']}")
            continue
        good = True
        why = ""
        lods = {}
        for var in vars_:
            lod = int(_num(var, "lod", -1))
            file = _text(var, "native_mesh")
            digest = _text(var, "native_sha256")
            entry = {"lod": lod, "file": file, "ok": False, "why": "", "triangles": None}
            rec["lods"].append(entry)
            if lod < 0 or lod > 2 or not plain_name(file) or len(digest) != 64:
                good, why = False, "a variant without a level, a plain file name or a hash"
                entry["why"] = why
                break
            path = nd / file
            try:
                if path.stat().st_size > MAX_MODEL_FILE:
                    raise OSError("larger than 64 MB")
                data = path.read_bytes()
            except OSError:
                good, why = False, f"{file} cannot be read"
                entry["why"] = why
                break
            if hashlib.sha256(data).hexdigest() != digest.lower():
                good, why = False, f"{file} is not the file the manifest names (its hash differs)"
                entry["why"] = why
                break
            try:
                gm = decode(data)
                if gm["version"] != 2:
                    raise GovError("not GOV2")
            except GovError as ex:
                good, why = False, f"{file}: {ex}"
                entry["why"] = why
                break
            st = bake_stats(gm)
            entry.update(ok=True, triangles=st["triangles"], vertices=st["vertices"], door_vertices=st["door_vertices"], extent=st["extent"])
            lods[lod] = st
        count = (max(lods) + 1) if lods else 0
        if good:
            for lv in range(count):
                if lv not in lods or lods[lv]["vertices"] == 0:
                    good, why = False, "a level of detail is missing"
        if not good or count == 0:
            rec["why"] = why or "no level of detail"
            out["notes"].append(f"{mod or 'game'}/{unit}: not used ({why})")  # (the add-on's words, empty when no variant)
            continue
        if unit in seen:
            rec["why"] = "another model for this unit comes first in the manifest; this one is never drawn"
            out["problems"].append(f"{unit}: {rec['why']}")
        seen.add(unit)
        rec["used"] = unit not in [m["unit_id"] for m in out["models"][:-1] if m["used"]]
        tri = [lods[lv]["triangles"] if lv in lods else 0 for lv in range(3)]
        out["notes"].append(f"{mod or 'game'}/{unit}: {count} levels, {tri[0]} / {tri[1] if count > 1 else 0} / {tri[2] if count > 2 else 0} triangles")
        out["used"] = True
    return out
