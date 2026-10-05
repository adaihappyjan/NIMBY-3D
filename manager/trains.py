r"""The train editor's API (the page calls it as trains.<method> with keyword arguments).

  api = TrainsApi(ctx)   ctx: game_dir() -> Path|None, state_dir -> Path, log(line),
                              workshop_dirs() -> [Path] (steamapps/workshop/content/1134710),
                              local_mods_dir() -> Path|None (%USERPROFILE%\Saved Games\Weird and Wry\NIMBY Rails\mods,
                              beside the saves; %APPDATA%\Weird and Wry\NIMBY Rails only holds the game's settings)

Every method returns JSON-able data or raises an Exception whose message says what went wrong.
Writing (export) only ever touches <mod folder>/nimby3d/: the files it generates, the manifest it
merges, and (when a unit's model is replaced) that model's old files. Every file it replaces or
removes is first copied to <state_dir>/train_backups/<time>_<mod>/. Workshop items and the game's
own folder are refused unless the caller passes allow_protected=True (the page asks the player first:
Steam may replace or delete files added to a Workshop item's folder when the item updates).

The model generator is manager/trainmodel (standard library only).
"""
from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import json
import os
import re
import shutil
import struct
import threading
import time
from pathlib import Path

from trainmodel import spec as S
from trainmodel import modcheck, preview as P
from trainmodel.export import build_model, generate, gov_bytes, file_stem, plain_name, GENERATOR, GENERATOR_VERSION

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"

# Whether the nimby3d add-on reads nimby3d/ folders of local mods (%USERPROFILE%\Saved Games\Weird and
# Wry\NIMBY Rails\mods\<mod>). src/addon.cpp read_rolling_stock() does: the game's own trains
# (resources\trains, source "builtin"), Workshop items (steamapps\workshop\content\1134710\<id>) and
# local mods (the folder's name is the mod's id and its manifest's source_workshop_id; folders that
# are junctions or links are skipped); it logs "trains: N local mods read (M with models of their own)".
ADDON_SCANS_LOCAL_MODS = True
MAX_SPRITE = 8 << 20

MAX_SPEC_FILE = 2 << 20
SPEC_SUFFIX = ".train.json"


class TrainsError(Exception):
    pass


def _canon(p: Path) -> str:
    try:
        return os.path.normcase(str(Path(p).resolve()))
    except OSError:
        return os.path.normcase(os.path.abspath(str(p)))


def _inside(p: Path, root: Path) -> bool:
    a, b = _canon(p), _canon(root)
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.n3d-{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1)
    finally:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _spec_key(spec) -> str:
    return _sha(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _messages(problems, limit=6):
    out = [f"{p['path']}: {p['en']}" if p["path"] else p["en"] for p in problems[:limit]]
    if len(problems) > limit:
        out.append(f"... and {len(problems) - limit} more")
    return "; ".join(out)


class TrainsApi:
    def __init__(self, ctx):
        self.ctx = ctx
        self._lock = threading.Lock()
        self._cache: dict = {}   # (spec key, lod) -> preview payload; spec key -> stats
        self._export_lock = threading.Lock()

    # ------------------------------------------------------------ helpers
    def _log(self, line: str) -> None:
        with contextlib.suppress(Exception):
            self.ctx.log(line)

    def _workshop_dirs(self) -> list:
        with contextlib.suppress(Exception):
            return [Path(p) for p in (self.ctx.workshop_dirs() or [])]
        return []

    def _local_dir(self):
        with contextlib.suppress(Exception):
            d = self.ctx.local_mods_dir()
            return Path(d) if d else None
        return None

    def _game_dir(self):
        with contextlib.suppress(Exception):
            d = self.ctx.game_dir()
            return Path(d) if d else None
        return None

    def _state_dir(self) -> Path:
        d = self.ctx.state_dir
        return Path(d() if callable(d) else d)

    def _classify(self, folder: Path) -> dict:
        """Where a mod folder is, and so: its id as the add-on sees it, whether the add-on reads it,
        whether writing there is fragile."""
        folder = Path(folder)
        for w in self._workshop_dirs():
            if _inside(folder, w) and _canon(folder.parent) == _canon(w):
                return {"location": "workshop", "mod_id": folder.name, "expected_source": folder.name, "scanned": True, "protected": True}
        g = self._game_dir()
        if g and _canon(folder) == _canon(g / "resources" / "trains"):
            return {"location": "game", "mod_id": "", "expected_source": "builtin", "scanned": True, "protected": True}
        if g and _inside(folder, g):
            return {"location": "game_other", "mod_id": folder.name, "expected_source": folder.name, "scanned": False, "protected": True}
        loc = self._local_dir()
        if loc and _inside(folder, loc) and _canon(folder.parent) == _canon(loc):
            return {"location": "local", "mod_id": folder.name, "expected_source": folder.name, "scanned": ADDON_SCANS_LOCAL_MODS, "protected": False}
        return {"location": "other", "mod_id": folder.name, "expected_source": folder.name, "scanned": False, "protected": False}

    def _mod_info(self, folder: Path, source_hint=None) -> dict | None:
        mt = folder / "mod.txt"
        if not mt.is_file():
            return None
        try:
            parsed = modcheck.read_mod_txt(mt)
        except OSError:
            return None
        where = self._classify(folder)
        models, man_source = [], None
        man = folder / "nimby3d" / "manifest.json"
        if man.is_file():
            with contextlib.suppress(OSError, ValueError):
                doc = json.loads(man.read_text("utf-8-sig"))
                man_source = doc.get("source_workshop_id") if isinstance(doc, dict) else None
                models = [m.get("unit_id") for m in (doc.get("models") or []) if isinstance(m, dict) and m.get("unit_id")]
        units = [{"id": u["id"], "name": u.get("name") or u["id"], "length": u["length"], "width": u["width"], "tags": u["tags"],
                  "has_model": u["id"] in models, "sprite": bool(u.get("tex_base") or u.get("tex_top"))} for u in parsed["units"]]
        meta = parsed["meta"]
        return {"id": where["mod_id"] or "builtin", "name": meta.get("name") or folder.name, "author": meta.get("author", ""),
                "version": meta.get("version", ""), "folder": str(folder), "source": where["location"],
                "units": units, "nimby3d": (folder / "nimby3d").is_dir(), "models": models, "manifest_source": man_source,
                "expected_source": where["expected_source"], "scanned_by_addon": where["scanned"], "protected": where["protected"]}

    def _cached_build(self, spec: dict, lod: int):
        stamps = ()
        if spec.get("body", {}).get("style") == "import":
            # an imported model follows its files: a new export from Blender is a new model
            for f in (spec.get("import") or {}).get("lods") or []:
                with contextlib.suppress(OSError, TypeError):
                    st_ = os.stat(f)
                    stamps += ((f, st_.st_size, st_.st_mtime_ns),)
        key = (_spec_key(spec), lod, stamps)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit
        c = build_model(spec, lod)
        payload = P.encode(c)
        st = c.m.stats()
        st["bytes"] = len(gov_bytes(c))
        extra = {"report": getattr(c, "report", None), "warnings": getattr(c, "warnings", None)}
        with self._lock:
            if len(self._cache) > 48:
                self._cache.clear()
            self._cache[key] = (payload, st, extra)
        return payload, st, extra

    # ------------------------------------------------------------ examples and specs
    def examples(self) -> dict:
        out = []
        for d in sorted(EXAMPLES.iterdir()) if EXAMPLES.is_dir() else []:
            idx = d / "example.json"
            if not idx.is_file():
                continue
            try:
                info = json.loads(idx.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            info["name"] = d.name
            out.append(info)
        return {"examples": out, "addon_scans_local_mods": ADDON_SCANS_LOCAL_MODS, "kinds": list(S.KINDS),
                "generator": f"{GENERATOR} {GENERATOR_VERSION}"}

    def load_example(self, name) -> dict:
        name = str(name)
        d = EXAMPLES / name
        if not name or "/" in name or "\\" in name or name.startswith(".") or not (d / "example.json").is_file():
            raise TrainsError(f"there is no example named {name!r}")
        info = json.loads((d / "example.json").read_text("utf-8"))
        specs = []
        for u in info.get("units", []):
            specs.append(json.loads((d / u["file"]).read_text("utf-8")))
        mod_txt = manifest = None
        me = d / "mod_example"
        with contextlib.suppress(OSError):
            mod_txt = (me / "mod.txt").read_text("utf-8")
        with contextlib.suppress(OSError, ValueError):
            manifest = json.loads((me / "nimby3d" / "manifest.json").read_text("utf-8"))
        info["name"] = name
        return {"name": name, "info": info, "specs": specs, "mod_txt": mod_txt, "manifest": manifest}

    def new_spec(self, kind="emu", style=None) -> dict:
        try:
            return S.new_spec(str(kind), style or None)
        except ValueError as ex:
            raise TrainsError(str(ex)) from None

    def validate(self, spec) -> dict:
        pr = S.validate(spec)
        return {"valid": not pr["errors"], "errors": pr["errors"], "warnings": pr["warnings"]}

    def fit(self, spec, length=None, width=None, height=None) -> dict:
        try:
            return S.fit(spec, length, width, height)
        except (ValueError, KeyError, TypeError) as ex:
            raise TrainsError(f"the spec could not be resized: {ex}") from None

    def arrange(self, spec, doors_per_side=None, window_width=None, pillar=None) -> dict:
        s = copy.deepcopy(spec)
        try:
            return S.arrange(s, doors_per_side, window_width, pillar)
        except (ValueError, KeyError, TypeError) as ex:
            raise TrainsError(f"doors and windows could not be arranged: {ex}") from None

    def preview(self, spec, lod=0) -> dict:
        """The mesh of one level of detail for the viewer, and the counts of all three."""
        lod = int(lod)
        if lod not in (0, 1, 2):
            raise TrainsError("lod must be 0, 1 or 2")
        pr = S.validate(spec)
        if pr["errors"]:
            raise TrainsError("the spec has errors: " + _messages(pr["errors"]))
        s = S.normalized(spec)
        try:
            payload, _, _ = self._cached_build(s, lod)
            stats = []
            report = None
            warnings = list(pr["warnings"])
            for lv in range(3):
                _, st, extra = self._cached_build(s, lv)
                stats.append({"lod": lv, **st})
                if lv == 0 and extra.get("report") is not None:
                    report = extra["report"]
                    warnings += [{"path": "import", **w} for w in extra.get("warnings") or []]
        except (ValueError, ZeroDivisionError, KeyError, TypeError, IndexError, OSError) as ex:
            raise TrainsError(f"the model could not be built: {ex}") from None
        limits = []
        for st in stats:
            if st["vertices"] > 1000000 or st["triangles"] * 3 > 3000000:
                limits.append(f"LOD{st['lod']} is over the add-on's limit of 1,000,000 vertices / 3,000,000 indices per model")
            if st["parts"] > 4096:
                limits.append(f"LOD{st['lod']} has more than 4096 parts")
        if report is not None:
            lods = list((s.get("import") or {}).get("lods") or []) + [None, None]
            if not lods[1] and stats[1]["triangles"] >= stats[0]["triangles"] * 0.9:
                warnings.append({"path": "import.lods", "en": "LOD1 made from LOD0 is hardly lighter: export a simpler LOD1 from Blender (a Decimate modifier), name small parts detail_*, or merge vertices further apart",
                                 "zh": "由 LOD0 自动生成的 LOD1 几乎没有变轻：从 Blender 导出一个简化的 LOD1（减面修改器），把小零件命名为 detail_*，或加大顶点合并间距"})
        budget = (15000, 8000, 2500)
        for st in stats:
            if st["triangles"] > budget[st["lod"]] * 2:
                warnings.append({"path": "", "en": f"LOD{st['lod']} has {st['triangles']:,} triangles; about {budget[st['lod']]:,} or fewer keeps hundreds of cars smooth",
                                 "zh": f"LOD{st['lod']} 有 {st['triangles']:,} 个三角形；控制在约 {budget[st['lod']]:,} 以内，几百节车同屏才流畅"})
        return {"mesh": payload, "stats": stats, "warnings": warnings, "limits": limits, "report": report,
                "length": s["length"], "width": s["width"], "height": s.get("height")}

    # ------------------------------------------------------------ the mod's sprite, and imports
    def unit_sprite(self, folder, unit_id) -> dict:
        """The pictures the game draws a unit with (mod.txt tex_base, tex_top, tex_decors): top views,
        the car's front at the left, tex_m_width metres across the whole picture (the car spans
        length / tex_m_width of it from the left), tex_m_height metres down it."""
        f = Path(str(folder))
        mt = f / "mod.txt"
        if not mt.is_file():
            raise TrainsError(f"{f} is not a mod folder (there is no mod.txt in it)")
        units = modcheck.read_mod_txt(mt)["units"]
        u = next((x for x in units if x["id"] == str(unit_id)), None)
        if u is None:
            raise TrainsError(f"mod.txt has no [TrainUnit] with id={unit_id}")
        layers, missing = [], []
        for kind, names in (("base", u["tex_base"]), ("top", u["tex_top"]), ("decor", u["tex_decors"])):
            for name in names:
                path = _find_inside(f, name)
                if path is None:
                    missing.append(name)
                    continue
                data = path.read_bytes() if path.stat().st_size <= MAX_SPRITE else b""
                mime, w, h = _image_info(data)
                if not mime:
                    missing.append(name)
                    continue
                layers.append({"kind": kind, "name": name, "mime": mime, "w": w, "h": h, "data": base64.b64encode(data).decode("ascii")})
        return {"unit_id": u["id"], "length": u["length"], "width": u["width"], "tex_m_width": u["tex_m_width"], "tex_m_height": u["tex_m_height"],
                "layers": layers, "missing": missing}

    def import_glb(self, path, unit_id=None, label=None, kind=None, length=None, width=None) -> dict:
        """A new spec whose model is the GLB at `path` (its materials ready to change), and what the
        importer noticed. Lower LODs are made from it until GLBs of their own are chosen."""
        from trainmodel import glbimport
        p = Path(str(path))
        if not p.is_file():
            raise TrainsError(f"{p} cannot be found")
        uid = str(unit_id or re.sub(r"[^A-Za-z0-9_]", "_", p.stem.replace("_lod0", "")) or "my_model")
        try:
            out = glbimport.load(str(p), uid, 1, False, (0, 0, 0))
            mats_ = glbimport.materials_of(str(p), uid)
        except glbimport.GlbError as ex:
            raise TrainsError(f"{p.name}: {ex}") from None
        rep = glbimport.report(out)
        box = rep["box"] or {"min": [0, 0, 0], "max": [1, 1, 1]}
        L = float(length) if length else round(max(1.0, box["max"][0] - box["min"][0]), 3)
        W = float(width) if width else round(max(1.0, box["max"][2] - box["min"][2]), 3)
        spec = {"format": "nimby3d-train", "version": 1, "unit_id": uid, "label": label or p.stem,
                "kind": kind if kind in S.KINDS else "coach", "length": L, "width": W, "height": round(max(0.5, box["max"][1]), 3),
                "body": {"style": "import"},
                "import": {"lods": [str(p), None, None], "scale": 1, "turn": False, "offset": [0, 0, 0],
                           "lod1_drop_below": 0.10, "lod2_drop_below": 0.35, "lod2_drop_interior": True},
                "interior": {"level": "detailed", "layout": "none"},
                "materials": mats_,
                "meta": {"generator": "Nimby3D train editor (imported)", "asset_version": "1.0.0", "dimension_source": "mod.txt length and width; geometry from " + p.name}}
        warnings = out.warnings + glbimport.check(out, L if length else None, W if width else None)
        return {"spec": spec, "report": rep, "warnings": warnings}

    def save_spec(self, spec, path) -> dict:
        if not isinstance(spec, dict):
            raise TrainsError("a spec must be a JSON object")
        p = Path(str(path))
        if p.suffix.lower() != ".json":
            p = p.with_name(p.name + SPEC_SUFFIX)
        if not p.parent.is_dir():
            raise TrainsError(f"the folder {p.parent} does not exist")
        data = (json.dumps(_relative_imports(spec, p.parent), indent=1, ensure_ascii=False) + "\n").encode("utf-8")
        _write_atomic(p, data)
        self._log(f"train editor: saved the spec of {spec.get('unit_id')} to {p}")
        return {"path": str(p), "bytes": len(data)}

    def load_spec(self, path) -> dict:
        p = Path(str(path))
        try:
            if p.stat().st_size > MAX_SPEC_FILE:
                raise TrainsError(f"{p.name} is larger than 2 MB: not a train spec")
            spec = json.loads(p.read_text("utf-8-sig"))
        except OSError as ex:
            raise TrainsError(f"{p} cannot be read: {ex.strerror or ex}") from None
        except ValueError as ex:
            raise TrainsError(f"{p.name} is not JSON: {ex}") from None
        if not isinstance(spec, dict) or spec.get("format", "nimby3d-train") != "nimby3d-train" or "unit_id" not in spec:
            raise TrainsError(f"{p.name} is not a train spec (it needs \"format\": \"nimby3d-train\" and a unit_id)")
        spec = _absolute_imports(spec, p.parent)
        return {"path": str(p), "spec": spec, **self.validate(spec)}

    # ------------------------------------------------------------ mods
    def list_mods(self) -> dict:
        mods = []
        seen = set()

        def add(folder: Path):
            key = _canon(folder)
            if key in seen:
                return
            seen.add(key)
            info = self._mod_info(folder)
            if info and (info["units"] or info["nimby3d"]):
                mods.append(info)
        local = self._local_dir()
        if local and local.is_dir():
            for d in sorted(local.iterdir()):
                if d.is_dir():
                    add(d)
        for w in self._workshop_dirs():
            if w.is_dir():
                for d in sorted(w.iterdir()):
                    if d.is_dir():
                        add(d)
        g = self._game_dir()
        if g and (g / "resources" / "trains" / "mod.txt").is_file():
            add(g / "resources" / "trains")
        order = {"local": 0, "other": 1, "workshop": 2, "game": 3, "game_other": 4}
        mods.sort(key=lambda m: (order.get(m["source"], 9), m["name"].lower()))
        return {"mods": mods, "local_dir": str(local) if local else None, "workshop_dirs": [str(w) for w in self._workshop_dirs()],
                "game_dir": str(g) if g else None, "addon_scans_local_mods": ADDON_SCANS_LOCAL_MODS}

    def mod_info(self, folder) -> dict:
        f = Path(str(folder))
        info = self._mod_info(f) if f.is_dir() else None
        if info is None:
            raise TrainsError(f"{f} is not a mod folder (there is no mod.txt in it)")
        return info

    def read_mod_models(self, folder) -> dict:
        f = Path(str(folder))
        info = self.mod_info(f)
        v = self.validate_mod(f)
        specs = []
        nd = f / "nimby3d"
        if nd.is_dir():
            for sp in sorted(nd.glob("*" + SPEC_SUFFIX)):
                with contextlib.suppress(OSError, ValueError):
                    if sp.stat().st_size <= MAX_SPEC_FILE:
                        doc = json.loads(sp.read_text("utf-8"))
                        if isinstance(doc, dict) and doc.get("format") == "nimby3d-train":
                            specs.append({"file": sp.name, "unit_id": doc.get("unit_id"), "spec": _absolute_imports(doc, nd)})
        manifest = None
        with contextlib.suppress(OSError, ValueError):
            manifest = json.loads((nd / "manifest.json").read_text("utf-8-sig"))
        return {"mod": info, "manifest": manifest, "check": v, "specs": specs}

    def validate_mod(self, folder) -> dict:
        """The mod folder checked as the add-on would read it, and what else stands in the way."""
        f = Path(str(folder))
        if not f.is_dir():
            raise TrainsError(f"{f} is not a folder")
        where = self._classify(f)
        problems, warnings = [], []
        units = []
        if (f / "mod.txt").is_file():
            units = modcheck.read_mod_txt(f / "mod.txt")["units"]
        else:
            problems.append({"en": "there is no mod.txt in this folder: it is not a mod", "zh": "此文件夹里没有 mod.txt：不是模组"})
        check = modcheck.check_manifest(f, where["mod_id"])
        if not check["found"]:
            problems.append({"en": "there is no nimby3d\\manifest.json in this mod", "zh": "此模组没有 nimby3d\\manifest.json"})
        for p in check["problems"]:
            problems.append({"en": p, "zh": _zh_problem(p)})
        ids = {u["id"] for u in units}
        for mdl in check["models"]:
            if mdl["unit_id"] and mdl["unit_id"] not in ids and units:
                warnings.append({"en": f"{mdl['unit_id']}: mod.txt has no [TrainUnit] with this id, so no vehicle uses this model "
                                       "(ids must match exactly, upper and lower case too)",
                                 "zh": f"{mdl['unit_id']}：mod.txt 里没有这个 id 的 [TrainUnit]，没有车辆会用这个模型（id 须完全一致，包括大小写）"})
            if mdl["used"] and mdl["unit_id"] in ids:
                u = next(u for u in units if u["id"] == mdl["unit_id"])
                if mdl["length_m"] and u["length"] and abs(mdl["length_m"] - u["length"]) > .05:
                    warnings.append({"en": f"{mdl['unit_id']}: the model is {mdl['length_m']} m long but mod.txt says {u['length']} m",
                                     "zh": f"{mdl['unit_id']}：模型长 {mdl['length_m']} 米，但 mod.txt 写的是 {u['length']} 米"})
        if _is_reparse(f):
            warnings.append({"en": "this mod folder is a junction or link: the add-on skips such local mod folders; make it a real folder",
                             "zh": "这个本地模组文件夹是链接（junction）：附加组件会跳过这种文件夹；请改成真正的文件夹"})
        if not where["scanned"]:
            if where["location"] == "local":
                warnings.append({"en": "this is a local mod: the current nimby3d add-on reads models only from Workshop items and the game's "
                                       "own trains, so it does not load these yet",
                                 "zh": "这是本地模组：当前的 nimby3d 附加组件只从创意工坊物品和游戏自带列车读取模型，暂时不会加载这些"})
            else:
                warnings.append({"en": "this folder is neither a Workshop item nor in the local mods folder: the add-on does not look here",
                                 "zh": "此文件夹既不是创意工坊物品，也不在本地模组文件夹里：附加组件不会在这里找模型"})
        used = [m for m in check["models"] if m["used"]]
        valid = bool(used) and not problems and check["used"]
        return {"folder": str(f), "location": where["location"], "mod_id": where["mod_id"], "expected_source": where["expected_source"],
                "scanned_by_addon": where["scanned"], "valid": valid, "loads": valid and where["scanned"],
                "problems": problems, "warnings": warnings, "log_lines": check["notes"], "models": check["models"],
                "source_workshop_id": check["source_workshop_id"], "units": [u["id"] for u in units]}

    # ------------------------------------------------------------ export
    def export(self, spec_or_specs, mod_folder, source_workshop_id=None, glb=False, allow_protected=False, include_spec=True,
               include_sources=False) -> dict:
        """Write the models of one spec (or a list) into <mod_folder>/nimby3d/ and merge the manifest.
        include_sources: an imported model's GLB files go along (as <unit>_source_lod<n>.glb)."""
        specs = spec_or_specs if isinstance(spec_or_specs, list) else [spec_or_specs]
        if not specs:
            raise TrainsError("nothing to export: no spec given")
        if not mod_folder:
            raise TrainsError("choose the mod folder to export into")
        try:
            mod = Path(str(mod_folder)).resolve(strict=True)
        except OSError:
            raise TrainsError(f"the mod folder {mod_folder} does not exist") from None
        if not mod.is_dir() or not (mod / "mod.txt").is_file():
            raise TrainsError(f"{mod} is not a mod folder: there is no mod.txt in it")
        where = self._classify(mod)
        if where["protected"] and not allow_protected:
            what = {"workshop": "a Steam Workshop item's folder", "game": "the game's own folder", "game_other": "the game's own folder"}[where["location"]]
            raise TrainsError(f"{mod} is {what}: files added there can be deleted or replaced by Steam when it updates. "
                              "Export into your own mod instead, or confirm that you want to write here.")
        target = mod / "nimby3d"
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_dir() or _canon(target) != _canon(mod / "nimby3d") or _is_reparse(target):
                raise TrainsError(f"{target} is not a plain folder (a link or a file): nothing was written")
        checked = []
        unit_ids = set()
        for sp in specs:
            pr = S.validate(sp)
            if pr["errors"]:
                raise TrainsError(f"the spec of {sp.get('unit_id') if isinstance(sp, dict) else '?'} has errors: " + _messages(pr["errors"]))
            if sp["unit_id"] in unit_ids:
                raise TrainsError(f"two specs are for the same unit {sp['unit_id']}")
            unit_ids.add(sp["unit_id"])
            checked.append((sp, S.normalized(sp)))
        source = str(source_workshop_id).strip() if source_workshop_id not in (None, "") else where["expected_source"]
        warnings = []
        if source != where["expected_source"]:
            warnings.append(f"source_workshop_id is {source!r} but the add-on expects {where['expected_source']!r} for this folder: "
                            "it will not use these models")
        mod_units = {u["id"] for u in modcheck.read_mod_txt(mod / "mod.txt")["units"]}
        for sp, _ in checked:
            if sp["unit_id"] not in mod_units:
                warnings.append(f"{sp['unit_id']}: mod.txt has no [TrainUnit] with this id: no vehicle will use this model")
        # what to write
        stems = set()
        files: dict[str, bytes] = {}
        entries = []
        for sp, norm in checked:
            stem = file_stem(sp["unit_id"])
            while stem.lower() in stems:
                stem += "_"
            stems.add(stem.lower())
            try:
                out = generate(norm, glb=bool(glb), stem=stem)
            except (ValueError, ZeroDivisionError, KeyError, TypeError, IndexError, OSError) as ex:
                raise TrainsError(f"the model of {sp['unit_id']} could not be built: {ex}") from None
            for st in out["stats"]:
                if st["vertices"] > 1000000 or st["triangles"] * 3 > 3000000 or st["parts"] > 4096:
                    raise TrainsError(f"{sp['unit_id']} LOD{st['lod']} is over the add-on's limits (1,000,000 vertices, 3,000,000 indices, 4096 parts)")
            files.update(out["files"])
            entry = out["entry"]
            if include_spec:
                name = stem + SPEC_SUFFIX
                stored = sp
                imp = _import_paths(sp)
                if imp is not None:
                    # never a path of this computer in a mod: the GLB's own name, or the copy written beside it
                    names = {}
                    for i, f in enumerate(imp["lods"]):
                        if not isinstance(f, str) or not f:
                            continue
                        if include_sources:
                            names[i] = f"{stem}_source_lod{i}.glb"
                            try:
                                files[names[i]] = Path(f).read_bytes()
                            except OSError as ex:
                                raise TrainsError(f"{f} cannot be read: {ex.strerror or ex}") from None
                            if len(files[names[i]]) > 50 << 20:
                                warnings.append(f"{names[i]} is {len(files[names[i]]) >> 20} MB: the mod gets that much bigger")
                        else:
                            names[i] = Path(f).name
                    stored = _relative_imports(sp, target, names)
                    if include_sources and names:
                        entry["sources"] = [names[i] for i in sorted(names)]
                files[name] = (json.dumps(stored, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
                entry["spec"] = name
            entry["generator"] = f"{GENERATOR} {GENERATOR_VERSION}"
            entries.append(entry)
        for name in files:
            if not plain_name(name):
                raise TrainsError(f"refusing to write {name!r}: not a plain file name")
        # the manifest, merged
        old_doc, old_raw = None, None
        man_path = target / "manifest.json"
        if man_path.is_file():
            old_raw = man_path.read_bytes()
            with contextlib.suppress(ValueError):
                old_doc = json.loads(old_raw.decode("utf-8-sig"))
            if not isinstance(old_doc, dict):
                warnings.append("the old manifest.json could not be read as JSON: it was replaced (a copy is in the backup)")
                old_doc = None
        doc = dict(old_doc) if old_doc else {}
        old_models = [m for m in (doc.get("models") or []) if isinstance(m, dict)]
        replaced = [m for m in old_models if m.get("unit_id") in unit_ids]
        kept = [m for m in old_models if m.get("unit_id") not in unit_ids]
        if old_doc and old_doc.get("source_workshop_id") not in (None, source) and kept:
            warnings.append(f"the manifest named source_workshop_id {old_doc.get('source_workshop_id')!r}; it now names {source!r} "
                            f"for all {len(kept) + len(entries)} models in it")
        new_models = []
        placed = set()
        for m in old_models:
            u = m.get("unit_id")
            if u in unit_ids:
                if u not in placed:
                    new_models.append(next(e for e in entries if e["unit_id"] == u))
                    placed.add(u)
            else:
                new_models.append(m)
        new_models += [e for e in entries if e["unit_id"] not in placed]
        merged = {"schema": 2, "native_format": "GOV2", "source_workshop_id": source}
        for k, v in doc.items():
            if k not in ("schema", "native_format", "source_workshop_id", "models"):
                merged[k] = v
        merged.setdefault("units", "metres")
        merged.setdefault("axes", {"front": "+X", "up": "+Y", "right": "+Z"})
        merged.setdefault("origin", "vehicle centre X/Z, rail head Y=0")
        merged["editor"] = {"generator": f"{GENERATOR} {GENERATOR_VERSION}", "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
        merged["models"] = new_models
        manifest_bytes = json.dumps(merged, indent=2, ensure_ascii=False).encode("utf-8")
        # files of replaced models no longer named by anything
        still = set()
        for m in kept:
            for v in m.get("variants") or []:
                for k in ("native_mesh", "glb", "rig"):
                    if isinstance(v.get(k), str):
                        still.add(v[k].lower())
            if isinstance(m.get("spec"), str):
                still.add(m["spec"].lower())
            for n in m.get("sources") or []:
                if isinstance(n, str):
                    still.add(n.lower())
        stale = []
        for m in replaced:
            names = [v.get(k) for v in m.get("variants") or [] for k in ("native_mesh", "glb", "rig")] + [m.get("spec")] + list(m.get("sources") or [])
            for n in names:
                if isinstance(n, str) and plain_name(n) and n.lower() not in still and n not in files and n.lower() not in [s.lower() for s in stale]:
                    if (target / n).is_file():
                        stale.append(n)
        with self._export_lock:
            return self._commit(mod, target, files, manifest_bytes, stale, old_raw, source, where, warnings, entries)

    def _commit(self, mod, target, files, manifest_bytes, stale, old_raw, source, where, warnings, entries) -> dict:
        overwritten = [n for n in files if (target / n).is_file()]
        backup_dir = None
        if overwritten or stale or old_raw is not None:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in mod.name)[:60]
            backup_dir = self._state_dir() / "train_backups" / f"{stamp}_{safe}"
            k = 1
            while backup_dir.exists():
                k += 1
                backup_dir = self._state_dir() / "train_backups" / f"{stamp}_{safe}_{k}"
            (backup_dir / "nimby3d").mkdir(parents=True)
            record = {"mod_folder": str(mod), "time": stamp, "files": {}}
            for n in sorted(set(overwritten) | set(stale) | ({"manifest.json"} if old_raw is not None else set())):
                src = target / n
                if src.is_file():
                    shutil.copy2(src, backup_dir / "nimby3d" / n)
                    record["files"][n] = _sha((backup_dir / "nimby3d" / n).read_bytes())
            (backup_dir / "backup.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), "utf-8")
        created_dir = not target.exists()
        target.mkdir(exist_ok=True)
        if _canon(target) != _canon(mod / "nimby3d") or _is_reparse(target):
            raise TrainsError(f"{target} is not a plain folder: nothing was written")
        written, created = [], []
        try:
            for n, data in files.items():
                path = target / n
                if _canon(path.parent) != _canon(target):
                    raise TrainsError(f"refusing to write outside {target}: {n}")
                existed = path.exists()
                _write_atomic(path, data)
                if not existed:
                    created.append(n)
                if _sha(path.read_bytes()) != _sha(data):
                    raise TrainsError(f"{n} did not read back as written")
                written.append({"name": n, "bytes": len(data), "sha256": _sha(data)})
            existed = (target / "manifest.json").exists()
            _write_atomic(target / "manifest.json", manifest_bytes)
            if not existed:
                created.append("manifest.json")
            written.append({"name": "manifest.json", "bytes": len(manifest_bytes), "sha256": _sha(manifest_bytes)})
        except Exception:
            # put back what was there, take away what this export added (only names it wrote)
            for n in created:
                with contextlib.suppress(OSError):
                    (target / n).unlink()
            if backup_dir is not None:
                for f in (backup_dir / "nimby3d").iterdir():
                    with contextlib.suppress(OSError):
                        shutil.copy2(f, target / f.name)
            if created_dir:
                with contextlib.suppress(OSError):
                    target.rmdir()
            raise
        removed = []
        for n in stale:
            with contextlib.suppress(OSError):
                (target / n).unlink()
                removed.append(n)
        check = self.validate_mod(mod)
        self._log(f"train editor: exported {', '.join(e['unit_id'] for e in entries)} into {target} "
                  f"({len(written)} files{', backup in ' + str(backup_dir) if backup_dir else ''})")
        return {"folder": str(mod), "nimby3d": str(target), "source_workshop_id": source, "location": where["location"],
                "written": written, "removed": removed, "backup": str(backup_dir) if backup_dir else None,
                "models": [{"unit_id": e["unit_id"], "triangles": [v["triangles"] for v in e["variants"]]} for e in entries],
                "warnings": warnings, "check": check}


def _import_paths(spec):
    imp = spec.get("import") if isinstance(spec, dict) and (spec.get("body") or {}).get("style") == "import" else None
    return imp if isinstance(imp, dict) and isinstance(imp.get("lods"), list) else None


def _relative_imports(spec, folder: Path, names=None):
    """A copy whose GLB paths are relative to `folder` where they lie in it (or are replaced by
    `names`, lod -> file name); paths elsewhere stay as they are."""
    imp = _import_paths(spec)
    if imp is None:
        return spec
    out = copy.deepcopy(spec)
    lods = out["import"]["lods"]
    for i, f in enumerate(lods):
        if not isinstance(f, str):
            continue
        if names and i in names:
            lods[i] = names[i]
            continue
        with contextlib.suppress(ValueError, OSError):
            rel = Path(f).resolve().relative_to(Path(folder).resolve())
            lods[i] = str(rel)
    return out


def _absolute_imports(spec, folder: Path):
    """A copy whose relative GLB paths are made absolute from `folder` (where the spec file is)."""
    imp = _import_paths(spec)
    if imp is None:
        return spec
    out = copy.deepcopy(spec)
    lods = out["import"]["lods"]
    for i, f in enumerate(lods):
        if isinstance(f, str) and f and not Path(f).is_absolute():
            lods[i] = str(Path(folder) / f)
    return out


def _find_inside(folder: Path, name: str):
    """A file a mod.txt names, inside the mod folder only (letter case as Windows ignores it)."""
    rel = str(name).replace("\\", "/").strip("/")
    if not rel or any(part in ("..", "") for part in rel.split("/")) or ":" in rel:
        return None
    cur = Path(folder)
    for part in rel.split("/"):
        nxt = cur / part
        if not nxt.exists():
            try:
                hit = next((c for c in cur.iterdir() if c.name.lower() == part.lower()), None)
            except OSError:
                hit = None
            if hit is None:
                return None
            nxt = hit
        cur = nxt
    if not cur.is_file() or not _inside(cur, folder):
        return None
    return cur


def _image_info(data: bytes):
    """(mime, width, height) of a PNG or JPEG, or (None, 0, 0)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return "image/png", w, h
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                break
            marker, size = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "image/jpeg", w, h
            i += 2 + size
        return "image/jpeg", 0, 0
    return None, 0, 0


def _is_reparse(p: Path) -> bool:
    """A junction or symbolic link (Windows reparse point)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & 0x400) or os.path.islink(p)


_ZH = [
    ("manifest.json cannot be read as the add-on reads it", "附加组件读不了 manifest.json"),
    ("manifest.json must hold a JSON object", "manifest.json 须为 JSON 对象"),
    ('the manifest must have "schema": 2', 'manifest 须有 "schema": 2（数字）和 "native_format": "GOV2"'),
    ('"source_workshop_id" is', '"source_workshop_id" 与模组文件夹名（创意工坊物品编号）不一致'),
    ('the manifest has no "models" list', 'manifest 里没有 "models" 列表'),
    ("another model for this unit comes first", "manifest 里同一车辆的另一个模型排在前面，这个永远不会被用到"),
    ("skipped without a word", "被附加组件直接跳过：需要 unit_id、大于 0 的 length_m 和 variants 列表"),
]


def _zh_problem(en: str) -> str:
    for key, zh in _ZH:
        if key in en:
            return zh + "（" + en + "）"
    return en
