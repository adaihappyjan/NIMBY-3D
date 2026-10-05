"""The train spec: what it holds, its checks (with messages in English and Chinese), and new specs.

A spec is one unit (one [TrainUnit] of a mod.txt). Top level:

  format "nimby3d-train", version 1
  unit_id      the [TrainUnit] id= of the mod.txt the model is for (exactly, case and all)
  label        a name for people
  kind         locomotive | coach | cab_car | emu
  length, width, height   metres (length and width as mod.txt has them, coupler room included)
  body         {style: carbody | hood, ...}   (carbody: profile, stations, end taper, lining...)
  materials    {key: {name, color, alpha, metallic, roughness, emissive, blend, double_sided}}
  windows      [{y0, y1, width, centers[]}]            (carbody)
  window_frame {border, glass_inset, reveal}
  doors        {centers[], width, y0, y1, leaves, travel, open_seconds, close_seconds, window, paint, ...}
  cab          {ends: none | front | both, windscreen, side_lights[], center_lights[], chevrons, horns, interior}
  gangway      {ends: none | front | rear | both, ...}
  logo         {type: none | go, x, y, scale, offset}
  side_ribs    {heights[], ...}
  underfloor   [{x, y, length, height, width, paint}]
  roof         {pantographs: [{x}], ac_units: [{x, length, width, height}]}
  interior     {level: none | simple | detailed, layout: single | bilevel | none, ...}
  bogies       {pivot_fraction, wheel_radius, axles[], frame_length, side_frame_length}
  couplers     {inset, height}
  hood         {sections[[x, w, floor, shoulder, roof]], ring, ring_paint[10], apertures[], cab_interior}  (hood)
  details      [primitive items: box, cylinder, bar, face, aperture, panel, grille, steps, spokes, logo,
                slope_aperture, slope_face, side {items}]
  meta         {generator, asset_version, dimension_source}
"""
from __future__ import annotations

import copy
import math
import re

from . import materials as mats
from .geometry import q

KINDS = ("locomotive", "coach", "cab_car", "emu")
STYLES = ("carbody", "hood", "import")
LEVELS = ("none", "simple", "detailed")
LAYOUTS = ("single", "bilevel", "none")
CAB_ENDS = ("none", "front", "both")
GANGWAY_ENDS = ("none", "front", "rear", "both")
LOGOS = ("none", "go")
DETAIL_TYPES = ("box", "cylinder", "bar", "face", "aperture", "panel", "grille", "steps", "spokes", "logo",
                "slope_aperture", "slope_face", "side")
KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


class SpecError(ValueError):
    """A spec that cannot be built; .problems is the list validate() gives."""

    def __init__(self, problems):
        self.problems = problems
        first = problems["errors"][0] if problems["errors"] else {"path": "", "en": "invalid spec"}
        more = len(problems["errors"]) - 1
        super().__init__(f"{first['path']}: {first['en']}" + (f" (and {more} more)" if more > 0 else ""))


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class Checker:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, path, en, zh):
        self.errors.append({"path": path, "en": en, "zh": zh})

    def warn(self, path, en, zh):
        self.warnings.append({"path": path, "en": en, "zh": zh})

    # ---- typed getters: the value, or None after an error
    def obj(self, d, key, path, required=True):
        v = d.get(key) if isinstance(d, dict) else None
        if v is None:
            if required:
                self.err(path, "is missing", "缺少此项")
            return None
        if not isinstance(v, dict):
            self.err(path, "must be an object { ... }", "须为对象 { ... }")
            return None
        return v

    def num(self, d, key, path, lo=None, hi=None, required=True, default=None, lo_open=False):
        v = d.get(key, default) if isinstance(d, dict) else default
        if v is None:
            if required:
                self.err(path, "is missing (a number)", "缺少此项（数字）")
            return None
        if not _isnum(v):
            self.err(path, "must be a number", "须为数字")
            return None
        if lo is not None and (v < lo or (lo_open and v == lo)):
            self.err(path, f"must be {'more than' if lo_open else 'at least'} {lo} (it is {v})", f"须{'大于' if lo_open else '不小于'} {lo}（现为 {v}）")
            return None
        if hi is not None and v > hi:
            self.err(path, f"must be at most {hi} (it is {v})", f"须不大于 {hi}（现为 {v}）")
            return None
        return v

    def choice(self, d, key, path, options, required=True, default=None):
        v = d.get(key, default) if isinstance(d, dict) else default
        if v is None:
            if required:
                self.err(path, f"is missing (one of {', '.join(options)})", f"缺少此项（可选：{', '.join(options)}）")
            return None
        if v not in options:
            self.err(path, f"must be one of {', '.join(options)} (it is {v!r})", f"须为 {', '.join(options)} 之一（现为 {v!r}）")
            return None
        return v

    def nums(self, d, key, path, n=None, lo=None, hi=None, required=True, min_len=0, increasing=False):
        v = d.get(key) if isinstance(d, dict) else None
        if v is None:
            if required:
                self.err(path, "is missing (a list of numbers)", "缺少此项（数字列表）")
            return None
        if not isinstance(v, list) or not all(_isnum(x) for x in v):
            self.err(path, "must be a list of numbers", "须为数字列表")
            return None
        if n is not None and len(v) != n:
            self.err(path, f"must have {n} numbers", f"须有 {n} 个数")
            return None
        if len(v) < min_len:
            self.err(path, f"needs at least {min_len} numbers", f"至少需要 {min_len} 个数")
            return None
        for i, x in enumerate(v):
            if (lo is not None and x < lo) or (hi is not None and x > hi):
                self.err(f"{path}[{i}]", f"must be between {lo} and {hi} (it is {x})", f"须在 {lo} 到 {hi} 之间（现为 {x}）")
                return None
        if increasing and any(b <= a for a, b in zip(v, v[1:])):
            self.err(path, "must be in increasing order, each more than the one before", "须从小到大排列，后一个大于前一个")
            return None
        return v

    def paint(self, d, key, path, keys, required=True, default=None):
        v = d.get(key, default) if isinstance(d, dict) else default
        if v is None:
            if required:
                self.err(path, "is missing (a material key)", "缺少此项（材质名）")
            return None
        if v not in keys:
            self.err(path, f"names a material that is not in materials: {v!r}", f"引用了材质表中没有的材质：{v!r}")
            return None
        return v

    def flag(self, d, key, path, default=None):
        v = d.get(key, default) if isinstance(d, dict) else default
        if v is not None and not isinstance(v, bool):
            self.err(path, "must be true or false", "须为 true 或 false")
            return None
        return v


# ---------------------------------------------------------------- defaults

def default_bogies(kind):
    if kind == "locomotive":
        return {"pivot_fraction": .31, "wheel_radius": .51, "axles": [-1.4, 1.4], "frame_length": 3.8, "side_frame_length": 3.65}
    return {"pivot_fraction": .345, "wheel_radius": .43, "axles": [-1.15, 1.15], "frame_length": 3.1, "side_frame_length": 2.95}


def normalized(spec: dict) -> dict:
    """A copy with every optional part filled in (what the builders read). Values given are kept as given."""
    s = copy.deepcopy(spec)
    if not isinstance(s, dict):
        return s
    s.setdefault("format", "nimby3d-train")
    s.setdefault("version", 1)
    s.setdefault("label", s.get("unit_id", ""))
    m = s.setdefault("materials", {})
    if isinstance(m, dict):
        for k in mats.STANDARD_KEYS:
            if k not in m:
                m[k] = copy.deepcopy(DEFAULT_MATERIALS[k])
    interior = s.setdefault("interior", {})
    s.setdefault("bogies", default_bogies(s.get("kind")))
    s.setdefault("couplers", {"inset": .30, "height": .85})
    s.setdefault("details", [])
    s.setdefault("meta", {})
    body = s.setdefault("body", {})
    if not isinstance(body, dict):
        return s
    style = body.setdefault("style", "carbody")
    if isinstance(interior, dict):
        interior.setdefault("level", "simple")
        interior.setdefault("layout", "single" if style == "carbody" else "none")
    if style == "carbody":
        hw = (s.get("width") if _isnum(s.get("width")) else 3) / 2
        prof = body.get("profile") or []
        top = prof[-1]["y"] if isinstance(prof, list) and prof and isinstance(prof[-1], dict) and _isnum(prof[-1].get("y")) else (
            s.get("height") if _isnum(s.get("height")) else 4)
        body.setdefault("end_inset", .35)
        body.setdefault("stations", [])
        body.setdefault("underside_paint", "underframe")
        body.setdefault("end_paint", "secondary")
        body.setdefault("aperture_min_z", q(hw * .6))
        body.setdefault("center_y", q(top * .56))
        body.setdefault("lining", {"inset": .075, "roof_from": q(top * .65), "roof_drop": .065, "end_inset": .07})
        s.setdefault("windows", [])
        s.setdefault("window_frame", {})
        d = s.setdefault("doors", {"centers": []})
        if isinstance(d, dict):
            d.setdefault("centers", [])
            if d["centers"]:
                d.setdefault("leaves", 2)
                if _isnum(d.get("width")):
                    d.setdefault("travel", q(d["width"] / 2 + .04) if d["leaves"] == 2 else q(d["width"] + .02))
                d.setdefault("open_seconds", 1.6)
                d.setdefault("close_seconds", .7)
        for key, empty in (("cab", {"ends": "none"}), ("gangway", {"ends": "none"})):
            v = s.setdefault(key, dict(empty))
            if isinstance(v, dict):
                v.setdefault("ends", "none")
        s.setdefault("logo", {"type": "none"})
        s.setdefault("side_ribs", {})
        s.setdefault("underfloor", [])
        s.setdefault("roof", {})
    return s


# ---------------------------------------------------------------- validation

def validate(spec) -> dict:
    """{"errors": [...], "warnings": [...]}, each {"path", "en", "zh"}. No errors: it can be built."""
    ck = Checker()
    if not isinstance(spec, dict):
        ck.err("", "a spec must be a JSON object", "规格须为 JSON 对象")
        return {"errors": ck.errors, "warnings": ck.warnings}
    if spec.get("format", "nimby3d-train") != "nimby3d-train":
        ck.err("format", "is not \"nimby3d-train\": this is not a train spec", "不是 \"nimby3d-train\"：这不是列车规格文件")
    if spec.get("version", 1) != 1:
        ck.err("version", "is a version this editor does not know (it knows 1)", "版本未知（本编辑器只认 1）")
    s = normalized(spec)
    for key in ("materials", "interior", "body", "bogies"):
        if not isinstance(s.get(key), dict):
            ck.err(key, "must be an object { ... }", "须为对象 { ... }")
    if ck.errors:
        return {"errors": ck.errors, "warnings": ck.warnings}
    uid = s.get("unit_id")
    if not isinstance(uid, str) or not uid:
        ck.err("unit_id", "is missing: it must be the id= of the [TrainUnit] in the mod's mod.txt",
               "缺少：须与模组 mod.txt 中 [TrainUnit] 的 id= 完全一致")
    elif uid != uid.strip() or len(uid) > 64 or any(ord(ch) < 32 for ch in uid):
        ck.err("unit_id", "must not start or end with spaces, hold control characters or be longer than 64 characters",
               "首尾不能有空格，不能含控制字符，长度不超过 64")
    ck.choice(s, "kind", "kind", KINDS)
    length = ck.num(s, "length", "length", 2, 60)
    width = ck.num(s, "width", "width", 1.5, 4.5)
    ck.num(s, "height", "height", 1.5, 7.5)
    if not isinstance(s.get("label", ""), str):
        ck.err("label", "must be text", "须为文字")
    keys = _check_materials(ck, s)
    level = ck.choice(s["interior"], "level", "interior.level", LEVELS)
    _check_bogies(ck, s, length)
    cp = s["couplers"]
    if isinstance(cp, dict):
        ck.num(cp, "inset", "couplers.inset", 0, 3, required=False)
        ck.num(cp, "height", "couplers.height", .2, 2.5, required=False)
    else:
        ck.err("couplers", "must be an object { ... }", "须为对象 { ... }")
    style = ck.choice(s["body"], "style", "body.style", STYLES)
    if length is not None and width is not None and style:
        if style == "carbody":
            _check_carbody(ck, s, keys, level)
        elif style == "hood":
            _check_hood(ck, s, keys)
        else:
            _check_import(ck, s)
    if not isinstance(s.get("details"), list):
        ck.err("details", "must be a list [ ... ]", "须为列表 [ ... ]")
    else:
        _check_details(ck, s["details"], "details", keys, False)
    meta = s.get("meta")
    if not isinstance(meta, dict):
        ck.err("meta", "must be an object { ... }", "须为对象 { ... }")
    else:
        for k in ("generator", "asset_version", "dimension_source"):
            if k in meta and not isinstance(meta[k], str):
                ck.err(f"meta.{k}", "must be text", "须为文字")
    return {"errors": ck.errors, "warnings": ck.warnings}


def checked(spec) -> dict:
    """The normalized spec, or SpecError when it has errors."""
    problems = validate(spec)
    if problems["errors"]:
        raise SpecError(problems)
    return normalized(spec)


def _check_materials(ck, s):
    m = s["materials"]
    if not isinstance(m, dict):
        ck.err("materials", "must be an object { key: material }", "须为对象 { 名称: 材质 }")
        return set(mats.STANDARD_KEYS)
    if len(m) > 256:
        ck.err("materials", "has more than 256 materials (the add-on's limit)", "材质超过 256 个（附加组件的上限）")
    for k, v in m.items():
        p = f"materials.{k}"
        if not KEY.match(k):
            ck.err(p, "a material key must be lower-case letters, digits and _ (starting with a letter)", "材质名须为小写字母、数字和下划线（以字母开头）")
        if not isinstance(v, dict):
            ck.err(p, "must be an object { ... }", "须为对象 { ... }")
            continue
        name = v.get("name", k)
        if not isinstance(name, str) or not name or len(name.encode("utf-8")) > 200:
            ck.err(p + ".name", "must be text of 1 to 200 bytes", "须为 1 到 200 字节的文字")
        if mats.parse_color(v.get("color")) is None:
            ck.err(p + ".color", "must be [r, g, b] (linear, 0..1) or \"#rrggbb\"", "须为 [r, g, b]（线性，0..1）或 \"#rrggbb\"")
        elif any(not (0 <= c <= 1) for c in mats.parse_color(v.get("color"))):
            ck.err(p + ".color", "each of r, g, b must be between 0 and 1", "r、g、b 须在 0 到 1 之间")
        if v.get("emissive") is not None:
            e = mats.parse_color(v.get("emissive"))
            if e is None or any(not (0 <= c <= 1) for c in e):
                ck.err(p + ".emissive", "must be [r, g, b] between 0 and 1, or \"#rrggbb\"", "须为 0 到 1 之间的 [r, g, b]，或 \"#rrggbb\"")
        ck.num(v, "alpha", p + ".alpha", 0, 1, required=False)
        ck.num(v, "metallic", p + ".metallic", 0, 1, required=False)
        ck.num(v, "roughness", p + ".roughness", 0, 1, required=False)
        ck.flag(v, "blend", p + ".blend")
        ck.flag(v, "double_sided", p + ".double_sided")
    return set(m.keys())


def _check_bogies(ck, s, length):
    b = s["bogies"]
    if not isinstance(b, dict):
        ck.err("bogies", "must be an object { ... }", "须为对象 { ... }")
        return
    pf = ck.num(b, "pivot_fraction", "bogies.pivot_fraction", .05, .49)
    r = ck.num(b, "wheel_radius", "bogies.wheel_radius", .2, 1.5)
    ax = ck.nums(b, "axles", "bogies.axles", lo=-3, hi=3, min_len=1)
    if ax is not None and len(ax) > 4:
        ck.err("bogies.axles", "at most 4 axles per bogie", "每台转向架最多 4 根轴")
    fl = ck.num(b, "frame_length", "bogies.frame_length", .5, 8)
    ck.num(b, "side_frame_length", "bogies.side_frame_length", .5, 8)
    if None not in (pf, fl, length) and length * pf + fl / 2 > length / 2:
        ck.warn("bogies.pivot_fraction", "the bogies reach past the ends of the vehicle", "转向架伸出了车体两端")
    if ax is not None and r is not None and len(ax) > 1 and min(b2 - a for a, b2 in zip(sorted(ax), sorted(ax)[1:])) < 2 * r:
        ck.warn("bogies.axles", "wheels of neighbouring axles overlap (axles closer than a wheel's diameter)", "相邻轮对的车轮重叠（轴距小于车轮直径）")


def _check_carbody(ck, s, keys, level):
    body = s["body"]
    L, W = s["length"], s["width"]
    hw = W / 2
    inset = ck.num(body, "end_inset", "body.end_inset", 0, 3)
    if inset is None:
        return
    half = L / 2 - inset
    if half < 1:
        ck.err("body.end_inset", "leaves less than 2 m of body", "车体剩下不到 2 米")
        return
    prof = body.get("profile")
    if not isinstance(prof, list) or len(prof) < 3:
        ck.err("body.profile", "needs at least 3 levels, from the bottom of the side up to the middle of the roof",
               "至少需要 3 层：从侧墙底部到车顶中线")
        return
    ok = True
    for i, lv in enumerate(prof):
        p = f"body.profile[{i}]"
        if not isinstance(lv, dict):
            ck.err(p, "must be {y, w, paint}", "须为 {y, w, paint}")
            ok = False
            continue
        ok &= ck.num(lv, "y", p + ".y", 0.05, 7.5) is not None
        ok &= ck.num(lv, "w", p + ".w", 0, 1) is not None
        ok &= ck.paint(lv, "paint", p + ".paint", keys) is not None
    if not ok:
        return
    ys = [lv["y"] for lv in prof]
    if any(b <= a for a, b in zip(ys, ys[1:])):
        ck.err("body.profile", "the levels' heights (y) must rise from one level to the next", "各层高度 y 须逐层升高")
        return
    if prof[-1]["w"] != 0:
        ck.err(f"body.profile[{len(prof) - 1}].w", "the last level is the middle of the roof: its w must be 0", "最后一层是车顶中线：w 须为 0")
        return
    if max(lv["w"] for lv in prof[:-1]) <= 0:
        ck.err("body.profile", "no level has any width", "没有任何一层有宽度")
        return
    top = ys[-1]
    if _isnum(s.get("height")) and abs(top - s["height"]) > .02:
        ck.warn("height", f"is {s['height']} m but the profile's top is {top} m (the profile is what is built)",
                f"为 {s['height']} 米，但断面最高处为 {top} 米（以断面为准）")
    ck.paint(body, "underside_paint", "body.underside_paint", keys)
    ck.paint(body, "end_paint", "body.end_paint", keys)
    st = ck.nums(body, "stations", "body.stations", increasing=True)
    if st is not None and any(not (-half < x < half) for x in st):
        ck.err("body.stations", f"every station must lie inside the body (between {-half:.3f} and {half:.3f})",
               f"每个截面位置都须在车体内（{-half:.3f} 到 {half:.3f} 之间）")
    T = body.get("end_taper") or {}
    if not isinstance(T, dict):
        ck.err("body.end_taper", "must be an object { ... }", "须为对象 { ... }")
    elif T.get("roof_drop", 0) != 0:
        start = ck.num(T, "start", "body.end_taper.start", 0, half)
        if start is not None and start >= half:
            ck.err("body.end_taper.start", "must be less than half the body length", "须小于车体长度的一半")
        ck.num(T, "roof_from", "body.end_taper.roof_from", 0, top)
        ck.num(T, "roof_span", "body.end_taper.roof_span", 0, 8, lo_open=True)
        ck.num(T, "roof_drop", "body.end_taper.roof_drop", 0, top)
    K = body.get("end_skirt") or {}
    if not isinstance(K, dict):
        ck.err("body.end_skirt", "must be an object { ... }", "须为对象 { ... }")
    elif K.get("rise", 0) != 0:
        for k in ("below", "base", "rise", "from"):
            ck.num(K, k, f"body.end_skirt.{k}", -L, L)
        ck.num(K, "length", "body.end_skirt.length", 0, L, lo_open=True)
    mz = ck.num(body, "aperture_min_z", "body.aperture_min_z", 0, hw, lo_open=True)
    ck.num(body, "center_y", "body.center_y", ys[0], top)
    lin = body.get("lining")
    if not isinstance(lin, dict):
        ck.err("body.lining", "must be an object { ... }", "须为对象 { ... }")
    else:
        ck.num(lin, "inset", "body.lining.inset", .01, .4, required=False)
        ck.num(lin, "roof_from", "body.lining.roof_from", 0, top, required=False)
        ck.num(lin, "roof_drop", "body.lining.roof_drop", 0, .5, required=False)
        ck.num(lin, "end_inset", "body.lining.end_inset", 0, .5, required=False)
    widest = max(lv["w"] for lv in prof)
    if mz is not None and mz >= hw * widest:
        ck.err("body.aperture_min_z", "must be less than the side wall's half width, or no window would be cut",
               "须小于侧墙半宽，否则开不出窗")
    wall = [lv["y"] for lv in prof if lv["w"] == widest]
    wall_lo, wall_hi = wall[0], wall[-1]
    # holes are cut in the bands whose middle is further out than aperture_min_z
    cut = [(a["y"], b["y"]) for a, b in zip(prof, prof[1:]) if mz is not None and (a["w"] + b["w"]) / 2 * hw > mz]
    cut_lo = cut[0][0] if cut else wall_lo
    cut_hi = cut[-1][1] if cut else wall_hi
    # windows and doors
    holes = []
    wins = s.get("windows")
    if not isinstance(wins, list):
        ck.err("windows", "must be a list of rows [ ... ]", "须为窗排列表 [ ... ]")
        wins = []
    for i, row in enumerate(wins):
        p = f"windows[{i}]"
        if not isinstance(row, dict):
            ck.err(p, "must be {y0, y1, width, centers}", "须为 {y0, y1, width, centers}")
            continue
        y0 = ck.num(row, "y0", p + ".y0", ys[0], top)
        y1 = ck.num(row, "y1", p + ".y1", ys[0], top)
        w = ck.num(row, "width", p + ".width", .05, 6)
        cs = ck.nums(row, "centers", p + ".centers")
        if None in (y0, y1, w, cs):
            continue
        if y1 <= y0:
            ck.err(p, "y1 (top) must be above y0 (bottom)", "y1（上沿）须高于 y0（下沿）")
            continue
        if y0 < cut_lo or y1 > cut_hi:
            ck.warn(p, f"reaches off the side wall: holes are only cut between {cut_lo} and {cut_hi} m",
                    f"超出了侧墙：只有 {cut_lo} 到 {cut_hi} 米之间能开洞")
        for j, x in enumerate(cs):
            if x - w / 2 < -half or x + w / 2 > half:
                ck.err(f"{p}.centers[{j}]", "this window reaches past the end of the body", "这扇窗超出了车体端部")
            holes.append((x - w / 2, x + w / 2, y0, y1, f"{p}.centers[{j}]", "window"))
    wf = s.get("window_frame")
    if isinstance(wf, dict):
        ck.num(wf, "border", "window_frame.border", .005, .2, required=False)
        ck.num(wf, "glass_inset", "window_frame.glass_inset", 0, .1, required=False)
        ck.num(wf, "reveal", "window_frame.reveal", 0, .3, required=False)
    else:
        ck.err("window_frame", "must be an object { ... }", "须为对象 { ... }")
    d = s.get("doors")
    if not isinstance(d, dict):
        ck.err("doors", "must be an object { ... }", "须为对象 { ... }")
        d = {"centers": []}
    cs = ck.nums(d, "centers", "doors.centers") or []
    if cs:
        dw = ck.num(d, "width", "doors.width", .3, 3)
        y0 = ck.num(d, "y0", "doors.y0", ys[0] - .5, top)
        y1 = ck.num(d, "y1", "doors.y1", ys[0], top)
        leaves = ck.choice(d, "leaves", "doors.leaves", (1, 2))
        ck.num(d, "travel", "doors.travel", 0, 2, lo_open=True)
        ck.num(d, "open_seconds", "doors.open_seconds", 0, 30, lo_open=True)
        ck.num(d, "close_seconds", "doors.close_seconds", 0, 30, lo_open=True)
        th = ck.num(d, "thickness", "doors.thickness", .005, .2, required=False, default=.036)
        ck.num(d, "pocket_inset", "doors.pocket_inset", 0, .5, required=False)
        ck.paint(d, "paint", "doors.paint", keys, required=False, default="secondary")
        ck.paint(d, "inner_paint", "doors.inner_paint", keys, required=False, default="interior_wall")
        ck.flag(d, "threshold", "doors.threshold")
        ck.flag(d, "grab_handles", "doors.grab_handles")
        if leaves == 1:
            ck.choice(d, "single_direction", "doors.single_direction", (1, -1), required=False, default=1)
        if None not in (dw, y0, y1, leaves):
            if y1 - y0 < .5:
                ck.err("doors", "a doorway must be at least 0.5 m high (y1 above y0)", "门洞至少高 0.5 米（y1 高于 y0）")
            if y1 > wall_hi + .001:
                ck.warn("doors.y1", f"the doorway rises above the vertical side wall (its top is {wall_hi} m)",
                        f"门洞高过侧墙竖直段（其顶部为 {wall_hi} 米）")
            win = d.get("window")
            if win is not None:
                if not isinstance(win, dict):
                    ck.err("doors.window", "must be an object {margin, y0, y1} or null", "须为对象 {margin, y0, y1} 或 null")
                else:
                    h2 = dw / 4 if leaves == 2 else dw / 2
                    mg = ck.num(win, "margin", "doors.window.margin", 0, h2, required=False, default=.11)
                    wy0 = ck.num(win, "y0", "doors.window.y0", 0, y1 - y0)
                    wy1 = ck.num(win, "y1", "doors.window.y1", 0, y1 - y0)
                    if mg is not None and q(h2 - mg) <= 0:
                        ck.err("doors.window.margin", "leaves no window in the leaf", "门扇上已无窗")
                    if None not in (wy0, wy1) and wy1 <= wy0:
                        ck.err("doors.window", "y1 must be above y0 (heights above the door's bottom)", "y1 须高于 y0（从门底算起）")
            for j, x in enumerate(cs):
                if x - dw / 2 < -half or x + dw / 2 > half:
                    ck.err(f"doors.centers[{j}]", "this doorway reaches past the end of the body", "这个门洞超出了车体端部")
                holes.append((x - dw / 2, x + dw / 2, y0, y1, f"doors.centers[{j}]", "door"))
            sc = sorted(cs)
            if any(b - a < dw + .1 for a, b in zip(sc, sc[1:])):
                ck.err("doors.centers", "two doorways overlap (or are closer than 0.1 m)", "有两个门洞重叠（或相距不到 0.1 米）")
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            a, b = holes[i], holes[j]
            if a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3] and not (a[5] == b[5] == "door"):
                ck.warn(b[4], f"overlaps {a[4]}", f"与 {a[4]} 重叠")
    # cab, gangway, logo, ribs, underfloor, roof, interior
    cab = s.get("cab")
    if not isinstance(cab, dict):
        ck.err("cab", "must be an object { ... }", "须为对象 { ... }")
        cab = {"ends": "none"}
    ends = ck.choice(cab, "ends", "cab.ends", CAB_ENDS)
    if ends and ends != "none":
        ws = ck.obj(cab, "windscreen", "cab.windscreen")
        if ws:
            z0 = ck.num(ws, "z0", "cab.windscreen.z0", 0, hw)
            z1 = ck.num(ws, "z1", "cab.windscreen.z1", 0, hw)
            wy0 = ck.num(ws, "y0", "cab.windscreen.y0", ys[0], top)
            wy1 = ck.num(ws, "y1", "cab.windscreen.y1", ys[0], top)
            ck.flag(ws, "split", "cab.windscreen.split")
            ck.num(ws, "frame", "cab.windscreen.frame", 0, .5, required=False)
            if None not in (z0, z1) and z1 <= z0 and ws.get("split", True):
                ck.err("cab.windscreen", "z1 (outer edge) must be more than z0 (inner edge)", "z1（外缘）须大于 z0（内缘）")
            if None not in (wy0, wy1) and wy1 <= wy0:
                ck.err("cab.windscreen", "y1 must be above y0", "y1 须高于 y0")
        for key in ("side_lights", "center_lights"):
            lst = cab.get(key) or []
            if not isinstance(lst, list):
                ck.err(f"cab.{key}", "must be a list", "须为列表")
                continue
            for i, lt in enumerate(lst):
                p = f"cab.{key}[{i}]"
                if not isinstance(lt, dict):
                    ck.err(p, "must be {y, z, radius, depth, offset, paint}", "须为 {y, z, radius, depth, offset, paint}")
                    continue
                ck.num(lt, "y", p + ".y", 0, top)
                ck.num(lt, "z", p + ".z", -hw, hw)
                ck.num(lt, "radius", p + ".radius", 0, 1, lo_open=True)
                ck.num(lt, "depth", p + ".depth", 0, 1, lo_open=True)
                ck.num(lt, "offset", p + ".offset", -1, 1)
                ck.paint(lt, "paint", p + ".paint", keys, required=False, default="headlamp")
        ch = cab.get("chevrons")
        if ch is not None:
            if not isinstance(ch, dict):
                ck.err("cab.chevrons", "must be an object or null", "须为对象或 null")
            else:
                ck.nums(ch, "rows", "cab.chevrons.rows", lo=0, hi=top)
                for k in ("half_width", "rise", "height"):
                    ck.num(ch, k, f"cab.chevrons.{k}", 0, hw, lo_open=True)
                ck.paint(ch, "paint", "cab.chevrons.paint", keys, required=False, default="primary")
        hn = cab.get("horns")
        if hn is not None:
            if not isinstance(hn, dict):
                ck.err("cab.horns", "must be an object or null", "须为对象或 null")
            else:
                ck.num(hn, "offset", "cab.horns.offset", 0, half)
                ck.num(hn, "y", "cab.horns.y", 0, 7.5)
                ck.nums(hn, "z", "cab.horns.z", lo=-hw, hi=hw)
                ck.num(hn, "radius", "cab.horns.radius", 0, .5, lo_open=True)
                ck.num(hn, "length", "cab.horns.length", 0, 2, lo_open=True)
        if level != "none":
            ci = ck.obj(cab, "interior", "cab.interior")
            if ci:
                ck.num(ci, "x", "cab.interior.x", 0, half, lo_open=True)
                ck.num(ci, "floor", "cab.interior.floor", .2, top)
                ck.num(ci, "length", "cab.interior.length", .3, 5)
    g = s.get("gangway")
    if not isinstance(g, dict):
        ck.err("gangway", "must be an object { ... }", "须为对象 { ... }")
    else:
        gends = ck.choice(g, "ends", "gangway.ends", GANGWAY_ENDS)
        if gends and gends != "none":
            ck.num(g, "center_y", "gangway.center_y", 0, top)
            ck.num(g, "height", "gangway.height", 0, top, lo_open=True)
            ck.num(g, "width", "gangway.width", 0, W, lo_open=True)
            ck.num(g, "depth", "gangway.depth", 0, 1, lo_open=True)
            for sub, fields in (("door", ("center_y", "height", "width", "thickness", "offset")), ("window", ("y0", "y1", "half_width", "offset"))):
                v = g.get(sub)
                if v is None:
                    continue
                if not isinstance(v, dict):
                    ck.err(f"gangway.{sub}", "must be an object or null", "须为对象或 null")
                    continue
                for k in fields:
                    ck.num(v, k, f"gangway.{sub}.{k}", -1, 7.5)
    lg = s.get("logo")
    if not isinstance(lg, dict):
        ck.err("logo", "must be an object { ... }", "须为对象 { ... }")
    elif ck.choice(lg, "type", "logo.type", LOGOS) == "go":
        ck.num(lg, "x", "logo.x", -half, half)
        ck.num(lg, "y", "logo.y", 0, top)
        ck.num(lg, "scale", "logo.scale", 0, 3, lo_open=True)
        ck.num(lg, "offset", "logo.offset", 0, .5, required=False)
    rb = s.get("side_ribs")
    if not isinstance(rb, dict):
        ck.err("side_ribs", "must be an object { ... }", "须为对象 { ... }")
    elif rb.get("heights"):
        ck.nums(rb, "heights", "side_ribs.heights", lo=0, hi=top)
        ck.num(rb, "radius", "side_ribs.radius", 0, .2, required=False, lo_open=True)
    uf = s.get("underfloor")
    if not isinstance(uf, list):
        ck.err("underfloor", "must be a list [ ... ]", "须为列表 [ ... ]")
    else:
        for i, b in enumerate(uf):
            p = f"underfloor[{i}]"
            if not isinstance(b, dict):
                ck.err(p, "must be {x, y, length, height, width}", "须为 {x, y, length, height, width}")
                continue
            ck.num(b, "x", p + ".x", -half, half)
            ck.num(b, "y", p + ".y", 0, top)
            for k in ("length", "height", "width"):
                ck.num(b, k, f"{p}.{k}", 0, L, lo_open=True)
            ck.paint(b, "paint", p + ".paint", keys, required=False, default="underframe")
    roof = s.get("roof")
    if not isinstance(roof, dict):
        ck.err("roof", "must be an object { ... }", "须为对象 { ... }")
    else:
        for i, pg in enumerate(roof.get("pantographs") or []):
            p = f"roof.pantographs[{i}]"
            if not isinstance(pg, dict):
                ck.err(p, "must be {x}", "须为 {x}")
                continue
            ck.num(pg, "x", p + ".x", -half + .8, half - .8)
            ck.num(pg, "head_width", p + ".head_width", .3, 2.5, required=False)
            ck.choice(pg, "facing", p + ".facing", (1, -1), required=False, default=1)
        for i, ac in enumerate(roof.get("ac_units") or []):
            p = f"roof.ac_units[{i}]"
            if not isinstance(ac, dict):
                ck.err(p, "must be {x, length, width, height}", "须为 {x, length, width, height}")
                continue
            ck.num(ac, "x", p + ".x", -half, half)
            ck.num(ac, "length", p + ".length", .2, L, lo_open=True)
            ck.num(ac, "width", p + ".width", .2, W)
            ck.num(ac, "height", p + ".height", .05, 1.5)
            ck.paint(ac, "paint", p + ".paint", keys, required=False, default="roof")
    I = s["interior"]
    layout = ck.choice(I, "layout", "interior.layout", LAYOUTS)
    if layout == "single":
        ck.num(I, "floor_y", "interior.floor_y", .2, top - 1, required=False)
        ck.num(I, "ceiling_y", "interior.ceiling_y", .5, top, required=False)
        ck.num(I, "seat_pitch", "interior.seat_pitch", .5, 3, required=False)
        ck.num(I, "aisle", "interior.aisle", .2, 2, required=False)
    elif layout == "bilevel" and I.get("bilevel") is not None and not isinstance(I.get("bilevel"), dict):
        ck.err("interior.bilevel", "must be an object of overrides { ... }", "须为覆盖项对象 { ... }")


def _check_hood(ck, s, keys):
    H = ck.obj(s, "hood", "hood")
    if not H:
        return
    L, W = s["length"], s["width"]
    secs = H.get("sections")
    if not isinstance(secs, list) or len(secs) < 2:
        ck.err("hood.sections", "needs at least 2 sections [x, half width, floor, shoulder, roof]", "至少需要 2 个截面 [x, 半宽, 底, 肩, 顶]")
        return
    good = True
    for i, sec in enumerate(secs):
        p = f"hood.sections[{i}]"
        if not isinstance(sec, list) or len(sec) != 5 or not all(_isnum(v) for v in sec):
            ck.err(p, "must be 5 numbers [x, half width, floor, shoulder, roof]", "须为 5 个数 [x, 半宽, 底, 肩, 顶]")
            good = False
            continue
        x, w, low, sh, rf = sec
        if abs(x) > L / 2:
            ck.err(p, "x lies outside the vehicle's length", "x 超出了车长范围")
        if not (0 < w <= W / 2 + .2):
            ck.err(p, f"the half width must be between 0 and {W / 2 + .2:.2f}", f"半宽须在 0 到 {W / 2 + .2:.2f} 之间")
        if not (0 < low < sh <= rf):
            ck.err(p, "heights must rise: 0 < floor < shoulder <= roof", "高度须递增：0 < 底 < 肩 <= 顶")
    if good and any(b[0] <= a[0] for a, b in zip(secs, secs[1:])):
        ck.err("hood.sections", "x must increase from one section to the next", "各截面的 x 须逐个增大")
    R = ck.obj(H, "ring", "hood.ring")
    if R:
        for k in ("bottom_z", "belt_y", "upper_y", "upper_above", "upper_drop", "roof_z"):
            ck.num(R, k, f"hood.ring.{k}", 0, 8)
    rp = H.get("ring_paint")
    if not isinstance(rp, list) or len(rp) != 10:
        ck.err("hood.ring_paint", "must list 10 material keys, one per segment of a section", "须列出 10 个材质名，每段一个")
    else:
        for i, k in enumerate(rp):
            if k not in keys:
                ck.err(f"hood.ring_paint[{i}]", f"names a material that is not in materials: {k!r}", f"引用了材质表中没有的材质：{k!r}")
    ck.paint(H, "end_paint", "hood.end_paint", keys, required=False, default="primary")
    ck.num(H, "center_y", "hood.center_y", 0, 8)
    for i, r in enumerate(H.get("apertures") or []):
        p = f"hood.apertures[{i}]"
        if not isinstance(r, dict):
            ck.err(p, "must be {segments, holes, axes}", "须为 {segments, holes, axes}")
            continue
        sg = r.get("segments")
        if not isinstance(sg, list) or not all(isinstance(v, int) and 0 <= v <= 9 for v in sg):
            ck.err(p + ".segments", "must list segment numbers 0..9", "须列出段号 0..9")
        _check_holes(ck, r.get("holes"), p + ".holes")
        if r.get("axes", "xy") not in ("xy", "zy"):
            ck.err(p + ".axes", "must be \"xy\" (side) or \"zy\" (front)", "须为 \"xy\"（侧面）或 \"zy\"（正面）")
        ck.num(r, "x_min", p + ".x_min", -L, L, required=False)
        ck.num(r, "x_max", p + ".x_max", -L, L, required=False)
    ci = H.get("cab_interior")
    if ci is not None:
        if not isinstance(ci, dict):
            ck.err("hood.cab_interior", "must be an object or null", "须为对象或 null")
        else:
            ck.num(ci, "x", "hood.cab_interior.x", -L / 2, L / 2)
            ck.num(ci, "floor", "hood.cab_interior.floor", .2, 7)
            ck.num(ci, "length", "hood.cab_interior.length", .3, 5)


def _check_import(ck, s):
    """A model imported from GLB files: LOD0's file must be there; the others are optional (made
    from LOD0 by leaving out small parts and the interior)."""
    imp = ck.obj(s, "import", "import")
    if not imp:
        return
    lods = imp.get("lods")
    if not isinstance(lods, list) or not lods or len(lods) > 3:
        ck.err("import.lods", "must list up to three GLB files, LOD0's first", "须列出最多三个 GLB 文件，LOD0 在前")
        return
    for i, f in enumerate(lods):
        p = f"import.lods[{i}]"
        if f is None and i > 0:
            continue
        if not isinstance(f, str) or not f.strip():
            ck.err(p, "must be the path of a .glb file" + (" (LOD0 is required)" if i == 0 else ""), "须为 .glb 文件路径" + ("（LOD0 必须有）" if i == 0 else ""))
            continue
        import os
        if not os.path.isfile(f):
            ck.err(p, f"the file {f} cannot be found", f"找不到文件 {f}")
        elif not f.lower().endswith(".glb"):
            ck.warn(p, "is not a .glb file", "不是 .glb 文件")
    ck.num(imp, "scale", "import.scale", 0, 1000, required=False, lo_open=True)
    ck.flag(imp, "turn", "import.turn")
    off = imp.get("offset")
    if off is not None and (not isinstance(off, list) or len(off) != 3 or not all(_isnum(v) for v in off)):
        ck.err("import.offset", "must be 3 numbers [x, y, z]", "须为 3 个数 [x, y, z]")
    ck.flag(imp, "lod2_drop_interior", "import.lod2_drop_interior")
    ck.num(imp, "lod1_drop_below", "import.lod1_drop_below", 0, 10, required=False)
    ck.num(imp, "lod2_drop_below", "import.lod2_drop_below", 0, 10, required=False)


def _check_holes(ck, holes, path):
    if not isinstance(holes, list):
        ck.err(path, "must be a list of [u0, u1, v0, v1]", "须为 [u0, u1, v0, v1] 的列表")
        return
    for i, h in enumerate(holes):
        if not isinstance(h, list) or len(h) != 4 or not all(_isnum(v) for v in h) or h[1] <= h[0] or h[3] <= h[2]:
            ck.err(f"{path}[{i}]", "must be [u0, u1, v0, v1] with u0 < u1 and v0 < v1", "须为 [u0, u1, v0, v1]，且 u0 < u1、v0 < v1")


def _point(ck, v, path, n=3):
    if not isinstance(v, list) or len(v) != n or not all(_isnum(x) for x in v):
        ck.err(path, f"must be {n} numbers", f"须为 {n} 个数")
        return False
    return True


def _check_details(ck, items, path, keys, in_side):
    for i, it in enumerate(items):
        p = f"{path}[{i}]"
        if not isinstance(it, dict):
            ck.err(p, "must be an object {type, ...}", "须为对象 {type, ...}")
            continue
        t = it.get("type")
        if t not in DETAIL_TYPES:
            ck.err(p + ".type", f"must be one of {', '.join(DETAIL_TYPES)}", f"须为 {', '.join(DETAIL_TYPES)} 之一")
            continue
        lods = it.get("lods")
        if lods is not None and (not isinstance(lods, list) or not all(v in (0, 1, 2) for v in lods)):
            ck.err(p + ".lods", "must list levels of detail (0, 1, 2)", "须列出细节层级（0、1、2）")
        if t == "side":
            if in_side:
                ck.err(p, "a side group cannot hold another side group", "镜像组里不能再套镜像组")
            elif not isinstance(it.get("items"), list):
                ck.err(p + ".items", "must be a list", "须为列表")
            else:
                _check_details(ck, it["items"], p + ".items", keys, True)
            continue
        if t != "logo":
            ck.paint(it, "paint", p + ".paint", keys)
        if t == "box":
            _point(ck, it.get("center"), p + ".center")
            if _point(ck, it.get("size"), p + ".size") and min(it["size"]) <= 0:
                ck.err(p + ".size", "every size must be more than 0", "每个尺寸须大于 0")
        elif t == "cylinder":
            _point(ck, it.get("center"), p + ".center")
            ck.num(it, "radius", p + ".radius", 0, 5, lo_open=True)
            ck.num(it, "length", p + ".length", 0, 60, lo_open=True)
            ck.choice(it, "axis", p + ".axis", ("x", "y", "z"), required=False, default="z")
            if it.get("sides") is not None and not (isinstance(it["sides"], int) and 3 <= it["sides"] <= 64):
                ck.err(p + ".sides", "must be a whole number from 3 to 64", "须为 3 到 64 的整数")
        elif t == "bar":
            if _point(ck, it.get("a"), p + ".a") and _point(ck, it.get("b"), p + ".b") and it["a"] == it["b"]:
                ck.err(p, "a and b must be different points", "a 与 b 须为不同的点")
            ck.num(it, "radius", p + ".radius", 0, 2, lo_open=True, required=False)
        elif t in ("face", "aperture"):
            pts = it.get("points")
            if not isinstance(pts, list) or len(pts) < 3:
                ck.err(p + ".points", "needs at least 3 points [x, y, z]", "至少需要 3 个点 [x, y, z]")
            else:
                for j, pt in enumerate(pts):
                    _point(ck, pt, f"{p}.points[{j}]")
            _point(ck, it.get("normal"), p + ".normal")
            if t == "aperture":
                _check_holes(ck, it.get("holes", []), p + ".holes")
                ck.choice(it, "axes", p + ".axes", ("xy", "zy", "xz", "yz", "yx", "zx"), required=False, default="xy")
        elif t in ("panel", "grille"):
            if t == "panel" or "x0" in it:
                x0 = ck.num(it, "x0", p + ".x0", -60, 60)
                x1 = ck.num(it, "x1", p + ".x1", -60, 60)
                if None not in (x0, x1) and x1 <= x0:
                    ck.err(p, "x1 must be more than x0", "x1 须大于 x0")
            else:
                ck.num(it, "x", p + ".x", -60, 60)
                ck.num(it, "half", p + ".half", 0, 30, lo_open=True)
            y0 = ck.num(it, "y0", p + ".y0", 0, 8)
            y1 = ck.num(it, "y1", p + ".y1", 0, 8)
            if None not in (y0, y1) and y1 <= y0:
                ck.err(p, "y1 must be above y0", "y1 须高于 y0")
            ck.num(it, "z", p + ".z", 0, 5)
            sl = it.get("slats")
            if t == "grille" and sl is not None:
                if not isinstance(sl, dict):
                    ck.err(p + ".slats", "must be an object or null", "须为对象或 null")
                else:
                    c3 = sl.get("counts")
                    if not isinstance(c3, list) or len(c3) != 3 or not all(isinstance(v, int) and 0 <= v <= 200 for v in c3):
                        ck.err(p + ".slats.counts", "must be 3 whole numbers (slats at LOD 0, 1, 2)", "须为 3 个整数（LOD 0、1、2 的格栅数）")
                    if "start" not in sl and "inset" not in sl:
                        ck.err(p + ".slats", "needs start (x of the first slat) or inset (from x)", "需要 start（第一根的 x）或 inset（距 x）")
                    ck.num(sl, "span", p + ".slats.span", 0, 60)
                    ck.num(sl, "y", p + ".slats.y", 0, 8)
                    ck.num(sl, "z", p + ".slats.z", 0, 5)
                    _point(ck, sl.get("size"), p + ".slats.size")
                    ck.paint(sl, "paint", p + ".slats.paint", keys, required=False, default="steel")
        elif t == "steps":
            _point(ck, it.get("start"), p + ".start")
            _point(ck, it.get("step"), p + ".step")
            _point(ck, it.get("size"), p + ".size")
            if not isinstance(it.get("count"), int) or not 1 <= it["count"] <= 50:
                ck.err(p + ".count", "must be a whole number from 1 to 50", "须为 1 到 50 的整数")
        elif t == "spokes":
            _point(ck, it.get("center"), p + ".center")
            if not isinstance(it.get("count"), int) or not 1 <= it["count"] <= 64:
                ck.err(p + ".count", "must be a whole number from 1 to 64", "须为 1 到 64 的整数")
            ck.num(it, "length", p + ".length", 0, 5, lo_open=True)
        elif t == "logo":
            ck.num(it, "x", p + ".x", -60, 60)
            ck.num(it, "y", p + ".y", 0, 8)
            ck.num(it, "z", p + ".z", 0, 5)
            ck.num(it, "scale", p + ".scale", 0, 3, lo_open=True, required=False)
        elif t in ("slope_aperture", "slope_face"):
            sl = ck.obj(it, "slope", p + ".slope")
            if sl:
                for k in ("x0", "y0", "dx"):
                    ck.num(sl, k, f"{p}.slope.{k}", -60, 60)
                ck.num(sl, "dy", p + ".slope.dy", 0, 60, lo_open=True)
            pts = it.get("points")
            if not isinstance(pts, list) or len(pts) < 3:
                ck.err(p + ".points", "needs at least 3 points [y, z]", "至少需要 3 个点 [y, z]")
            else:
                for j, pt in enumerate(pts):
                    _point(ck, pt, f"{p}.points[{j}]", 2)
            _point(ck, it.get("normal"), p + ".normal")
            if t == "slope_aperture":
                _check_holes(ck, it.get("holes", []), p + ".holes")


# ---------------------------------------------------------------- new specs

# The default palette of a new spec: neutral names (a model's material names show in its files).
DEFAULT_MATERIALS = {
    "primary": {"name": "livery_primary", "color": [0.012, 0.13, 0.42], "alpha": 1, "metallic": 0.12, "roughness": 0.38},
    "secondary": {"name": "livery_secondary", "color": [0.82, 0.84, 0.85], "alpha": 1, "metallic": 0.2, "roughness": 0.4},
    "glass": {"name": "window_glass", "color": [0.12, 0.24, 0.27], "alpha": .24, "metallic": 0.05, "roughness": 0.15, "blend": True, "double_sided": True},
    "gasket": {"name": "window_gasket", "color": [0.018, 0.024, 0.025], "alpha": 1, "metallic": 0, "roughness": 0.72},
    "underframe": {"name": "underframe", "color": [0.045, 0.053, 0.054], "alpha": 1, "metallic": 0.55, "roughness": 0.64},
    "steel": {"name": "steel", "color": [0.31, 0.35, 0.36], "alpha": 1, "metallic": 0.82, "roughness": 0.32},
    "roof": {"name": "roof", "color": [0.30, 0.32, 0.33], "alpha": 1, "metallic": 0.45, "roughness": 0.52},
    "headlamp": {"name": "headlamp", "color": [1.0, 0.86, 0.59], "alpha": 1, "metallic": 0, "roughness": 0.18, "emissive": [.8, .56, .23]},
    "tail_lamp": {"name": "tail_lamp", "color": [0.54, 0.022, 0.012], "alpha": 1, "metallic": 0, "roughness": 0.24},
    "safety_yellow": {"name": "safety_yellow", "color": [0.95, 0.66, 0.045], "alpha": 1, "metallic": 0, "roughness": 0.5},
    "logo": {"name": "logo", "color": [0.9, 0.9, 0.9], "alpha": 1, "metallic": 0, "roughness": 0.5},
    "interior_wall": {"name": "interior_wall", "color": [.62, .65, .61], "alpha": 1, "metallic": 0, "roughness": .82},
    "interior_floor": {"name": "interior_floor", "color": [.075, .092, .10], "alpha": 1, "metallic": 0, "roughness": .94},
    "seat": {"name": "seat_fabric", "color": [.06, .09, .22], "alpha": 1, "metallic": 0, "roughness": .96},
    "interior_light": {"name": "interior_light", "color": [.96, .94, .80], "alpha": 1, "metallic": 0, "roughness": .35, "emissive": [.8, .74, .53]},
    "display": {"name": "instrument_display", "color": [.018, .16, .23], "alpha": 1, "metallic": 0, "roughness": .4, "emissive": [.015, .21, .30]},
}

NEW_META = {"generator": "Nimby3D train editor", "asset_version": "1.0.0",
            "dimension_source": "mod.txt length and width; height and details from the editor"}


def _gangway(floor):
    return {"ends": "both", "offset": .015, "center_y": q(floor + 1.09), "height": 2.12, "width": .97, "depth": .12, "paint": "gasket",
            "door": {"center_y": q(floor + 1.08), "height": 1.91, "width": .72, "thickness": .028, "offset": .071, "paint": "secondary"},
            "window": {"y0": q(floor + 1.29), "y1": q(floor + 1.86), "half_width": .25, "offset": .09}}


def _cab(floor, hw, half, split):
    return {
        "ends": "front",
        "windscreen": ({"z0": .1, "z1": q(hw - .32), "y0": q(floor + 1.0), "y1": q(floor + 1.8), "split": True, "frame": .06, "frame_offset": .04, "glass_offset": .045}
                       if split else
                       {"z0": 0, "z1": q(hw - .3), "y0": q(floor + 0.95), "y1": q(floor + 1.85), "split": False, "frame": .06, "frame_offset": .04, "glass_offset": .045}),
        "side_lights": [
            {"y": q(floor + .1), "z": q(hw - .4), "radius": .1, "depth": .07, "offset": .07, "paint": "headlamp"},
            {"y": q(floor + .1), "z": q(hw - .7), "radius": .07, "depth": .07, "offset": .07, "paint": "tail_lamp"},
        ],
        "center_lights": [{"y": q(floor + 2.15), "z": 0, "radius": .09, "depth": .07, "offset": .07, "paint": "headlamp"}],
        "chevrons": None,
        "horns": None,
        "interior": {"x": q(half - 1.1), "floor": floor, "length": 1.6},
    }


def new_spec(kind: str = "emu", style: str | None = None) -> dict:
    """A complete, buildable spec to start from: a single-level EMU car with a cab, a coach, a cab car,
    or a locomotive (style "hood": a North American hood unit; "carbody": a box cab with two cabs)."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if kind == "locomotive" and (style or "hood") == "hood":
        return _hood_locomotive()
    if kind == "locomotive":
        return _box_cab()
    if style == "hood":
        raise ValueError("the hood style is for locomotives only")
    L = {"emu": 24.0, "coach": 26.4, "cab_car": 26.4}[kind]
    W = 2.9
    floor = 1.15 if kind == "emu" else 1.25
    top = 3.85 if kind == "emu" else 4.1
    half = q(L / 2 - .35)
    hw = W / 2
    wall_top = q(floor + 1.95)
    profile = [
        {"y": q(floor - .2), "w": .93, "paint": "primary"},
        {"y": q(floor + .1), "w": 1, "paint": "secondary"},
        {"y": q(floor + .7), "w": 1, "paint": "primary"},
        {"y": q(floor + .82), "w": 1, "paint": "secondary"},
        {"y": wall_top, "w": 1, "paint": "secondary"},
        {"y": q(wall_top + (top - wall_top) * .35), "w": .88, "paint": "roof"},
        {"y": q(top - .2), "w": .55, "paint": "roof"},
        {"y": top, "w": 0, "paint": "roof"},
    ]
    taper = kind == "emu"
    spec = {
        "format": "nimby3d-train", "version": 1,
        "unit_id": {"emu": "my_emu_car", "coach": "my_coach", "cab_car": "my_cab_car"}[kind],
        "label": {"emu": "New EMU car", "coach": "New coach", "cab_car": "New cab car"}[kind],
        "kind": kind,
        "length": L, "width": W, "height": top,
        "body": {
            "style": "carbody",
            "end_inset": .35,
            "stations": [q(-half + .7), q(-half + 1.5), 0, q(half - 1.5), q(half - .7)],
            "profile": profile,
            "underside_paint": "underframe",
            "end_paint": "secondary",
            "end_taper": {"start": q(half - 1.5), "roof_from": q(wall_top + .1), "roof_span": q(top - wall_top - .1), "roof_drop": .28} if taper else {},
            "end_skirt": {},
            "aperture_min_z": q(hw * .6),
            "center_y": q(floor + 1.1),
            "lining": {"inset": .075, "roof_from": q(wall_top - .1), "roof_drop": .065, "end_inset": .07},
        },
        "windows": [],
        "window_frame": {"border": .035, "glass_inset": .022, "reveal": .075},
        "doors": {
            "centers": [], "width": 1.3, "y0": floor, "y1": q(floor + 1.9),
            "leaves": 2, "travel": .68, "open_seconds": 1.6, "close_seconds": .7,
            "pocket_inset": .035, "thickness": .036,
            "window": {"margin": .12, "y0": .95, "y1": 1.6},
            "paint": "secondary", "inner_paint": "interior_wall", "threshold": True, "grab_handles": True,
        },
        "cab": {"ends": "none"},
        "gangway": _gangway(floor),
        "logo": {"type": "none"},
        "side_ribs": {},
        "underfloor": [
            {"x": -4.2, "y": .75, "length": 3.0, "height": .45, "width": 2.0, "paint": "underframe"},
            {"x": 4.2, "y": .75, "length": 3.0, "height": .45, "width": 2.0, "paint": "underframe"},
        ],
        "roof": {"pantographs": [], "ac_units": [{"x": 0, "length": 2.8, "width": 1.6, "height": .3, "paint": "roof"}]},
        "interior": {"level": "detailed", "layout": "single", "floor_y": floor, "seat_pitch": .9, "aisle": .55},
        "bogies": {"pivot_fraction": .345 if kind != "emu" else .36, "wheel_radius": .43, "axles": [-1.25, 1.25], "frame_length": 3.3, "side_frame_length": 3.1},
        "couplers": {"inset": .30, "height": .85},
        "details": [],
        "materials": copy.deepcopy(DEFAULT_MATERIALS),
        "meta": dict(NEW_META),
    }
    if kind in ("emu", "cab_car"):
        spec["cab"] = _cab(floor, hw, half, split=(kind == "cab_car"))
        spec["gangway"]["ends"] = "rear"
    if kind == "emu":
        spec["roof"]["pantographs"] = [{"x": q(-half + 4.2), "head_width": 1.0}]
        spec["roof"]["ac_units"] = [{"x": q(half - 6.0), "length": 2.8, "width": 1.6, "height": .3, "paint": "roof"}]
    arrange(spec, 3 if kind == "emu" else 2, 1.2, .5)
    return spec


def _hood_locomotive():
    from pathlib import Path
    import json
    here = Path(__file__).resolve().parent.parent / "examples" / "go_train" / "mp40_bl.train.json"
    spec = json.loads(here.read_text("utf-8"))
    spec["unit_id"] = "my_locomotive"
    spec["label"] = "New hood locomotive"
    spec["materials"] = copy.deepcopy(DEFAULT_MATERIALS)
    spec["meta"] = dict(NEW_META)

    def strip(items):
        out = []
        for it in items:
            if it.get("type") == "logo":
                continue
            if it.get("type") == "side":
                it = dict(it, items=strip(it["items"]))
            out.append(it)
        return out
    spec["details"] = strip(spec["details"])
    return spec


def _box_cab():
    L, W, top = 19.0, 3.0, 3.95
    half = q(L / 2 - .3)
    hw = W / 2
    floor = 1.35
    spec = {
        "format": "nimby3d-train", "version": 1,
        "unit_id": "my_electric_locomotive", "label": "New box-cab locomotive", "kind": "locomotive",
        "length": L, "width": W, "height": top,
        "body": {
            "style": "carbody", "end_inset": .3,
            "stations": [q(-half + .6), q(-half + 1.4), 0, q(half - 1.4), q(half - .6)],
            "profile": [
                {"y": 1.05, "w": .95, "paint": "secondary"},
                {"y": 1.3, "w": 1, "paint": "primary"},
                {"y": 2.0, "w": 1, "paint": "secondary"},
                {"y": 2.12, "w": 1, "paint": "primary"},
                {"y": 3.3, "w": 1, "paint": "primary"},
                {"y": 3.62, "w": .86, "paint": "roof"},
                {"y": 3.86, "w": .5, "paint": "roof"},
                {"y": top, "w": 0, "paint": "roof"},
            ],
            "underside_paint": "underframe", "end_paint": "primary",
            "end_taper": {"start": q(half - 1.4), "roof_from": 3.3, "roof_span": .65, "roof_drop": .3},
            "end_skirt": {},
            "aperture_min_z": q(hw * .6), "center_y": 2.4,
            "lining": {"inset": .075, "roof_from": 3.2, "roof_drop": .065, "end_inset": .07},
        },
        "windows": [{"y0": 2.3, "y1": 2.95, "width": .7, "centers": [q(-half + 1.0), q(half - 1.0)]},
                    {"y0": 2.45, "y1": 2.95, "width": 1.0, "centers": [-4.5, -1.5, 1.5, 4.5]}],
        "window_frame": {"border": .035, "glass_inset": .022, "reveal": .075},
        "doors": {"centers": []},
        "cab": {
            "ends": "both",
            "windscreen": {"z0": .08, "z1": 1.12, "y0": 2.35, "y1": 3.1, "split": True, "frame": .06, "frame_offset": .04, "glass_offset": .045},
            "side_lights": [
                {"y": 1.65, "z": 1.05, "radius": .1, "depth": .07, "offset": .07, "paint": "headlamp"},
                {"y": 1.65, "z": .78, "radius": .07, "depth": .07, "offset": .07, "paint": "tail_lamp"},
            ],
            "center_lights": [{"y": 3.45, "z": 0, "radius": .1, "depth": .07, "offset": .07, "paint": "headlamp"}],
            "chevrons": None,
            "horns": {"offset": 1.2, "y": 3.86, "z": [-.25, .25], "radius": .06, "length": .3, "paint": "underframe"},
            "interior": {"x": q(half - 1.05), "floor": floor, "length": 1.7},
        },
        "gangway": {"ends": "none"},
        "logo": {"type": "none"},
        "side_ribs": {"heights": [2.07], "radius": .012, "offset": .008, "end_inset": .15, "door_gap": .02, "paint": "steel"},
        "underfloor": [{"x": 0, "y": .8, "length": 5.0, "height": .6, "width": 2.2, "paint": "underframe"}],
        "roof": {"pantographs": [{"x": q(-half + 3.0), "head_width": 1.0, "facing": 1}, {"x": q(half - 3.0), "head_width": 1.0, "facing": -1}],
                 "ac_units": [{"x": 0, "length": 4.0, "width": 1.2, "height": .35, "paint": "steel"}]},
        "interior": {"level": "detailed", "layout": "none"},
        "bogies": {"pivot_fraction": .27, "wheel_radius": .58, "axles": [-1.3, 1.3], "frame_length": 3.6, "side_frame_length": 3.5},
        "couplers": {"inset": .30, "height": .9},
        "details": [
            {"type": "side", "items": [
                {"type": "panel", "name": "crew door", "x0": q(half - 2.35), "x1": q(half - 1.7), "y0": 1.35, "y1": 3.2, "z": hw, "paint": "primary", "frame": True},
                {"type": "panel", "name": "crew door", "x0": q(-half + 1.7), "x1": q(-half + 2.35), "y0": 1.35, "y1": 3.2, "z": hw, "paint": "primary", "frame": True},
                {"type": "steps", "name": "crew steps", "start": [q(half - 2.03), 1.15, q(hw - .05)], "step": [0, -.25, 0], "count": 2, "size": [.6, .05, .2], "paint": "steel", "lods": [0, 1]},
                {"type": "steps", "name": "crew steps", "start": [q(-half + 2.03), 1.15, q(hw - .05)], "step": [0, -.25, 0], "count": 2, "size": [.6, .05, .2], "paint": "steel", "lods": [0, 1]},
            ]},
        ],
        "materials": copy.deepcopy(DEFAULT_MATERIALS),
        "meta": dict(NEW_META),
    }
    spec["materials"]["primary"]["color"] = [0.30, 0.012, 0.01]
    return spec


# ---------------------------------------------------------------- layout helpers

def arrange(spec: dict, doors_per_side: int | None = None, window_width: float | None = None, pillar: float | None = None) -> dict:
    """Space the doorways evenly along a carbody (leaving room for cabs), then fill each bay between
    them with as many windows of window_width (pillar apart) as fit, centred. Changes and returns spec."""
    if spec.get("body", {}).get("style", "carbody") != "carbody":
        raise ValueError("arranging doors and windows is for the carbody style")
    s = normalized(spec)
    half = s["length"] / 2 - s["body"]["end_inset"]
    d = spec.setdefault("doors", {})
    n = len(d.get("centers") or []) if doors_per_side is None else int(doors_per_side)
    if n < 0 or n > 8:
        raise ValueError("doors per side must be 0 to 8")
    dw = d.get("width", 1.3)
    cab = s.get("cab") or {}
    ci = cab.get("interior") or {}
    from .carbody import cab_at
    lo, hi = -half + .3, half - .3
    if cab_at(s, 1):
        hi = q(ci.get("x", half - 1.1) - ci.get("length", 1.6) / 2 - .5)
    if cab_at(s, -1):
        lo = -q(ci.get("x", half - 1.1) - ci.get("length", 1.6) / 2 - .5)
    if n:
        if n == 1:
            centers = [q((lo + hi) / 2)]
        else:
            # doors a quarter bay in from each end, the rest evenly between
            edge = (hi - lo) / (n * 2 + 1) * 1.2
            a, b = lo + edge + dw / 2, hi - edge - dw / 2
            centers = [q(a + (b - a) * k / (n - 1)) for k in range(n)]
        d["centers"] = centers
        d.setdefault("width", dw)
    else:
        d["centers"] = []
    ww = window_width or 1.2
    gap = pillar if pillar is not None else .5
    rows = spec.get("windows") or []
    floor = (s.get("interior") or {}).get("floor_y", d.get("y0", 1.2))
    if rows:
        y0, y1 = rows[0]["y0"], rows[0]["y1"]
    else:
        y0, y1 = q(floor + .82), q(floor + 1.72)
    blocked = sorted((x - dw / 2 - .35, x + dw / 2 + .35) for x in d["centers"])
    bays, start = [], lo
    for a, b in blocked:
        if a > start:
            bays.append((start, a))
        start = max(start, b)
    if start < hi:
        bays.append((start, hi))
    centers = []
    for a, b in bays:
        k = int((b - a + gap) // (ww + gap))
        if k < 1:
            continue
        mid = (a + b) / 2
        for i in range(k):
            centers.append(q(mid + (i - (k - 1) / 2) * (ww + gap)))
    row = {"y0": y0, "y1": y1, "width": ww, "centers": centers}
    spec["windows"] = [row] + list(rows[1:])
    return spec


def _scale_x(v, fx):
    return round(v * fx, 4)


def fit(spec: dict, length: float | None = None, width: float | None = None, height: float | None = None) -> dict:
    """The spec stretched to a new length, width and/or height: positions along the car scale with
    the length, across with the width, up with the height (sizes of doors, lamps and seats stay)."""
    s = copy.deepcopy(spec)
    L0, W0, H0 = s["length"], s["width"], s.get("height") or 4
    L1, W1, H1 = length or L0, width or W0, height or H0
    for v, name in ((L1, "length"), (W1, "width"), (H1, "height")):
        if not _isnum(v) or v <= 0:
            raise ValueError(f"{name} must be a positive number")
    style = s.get("body", {}).get("style", "carbody")
    inset = s.get("body", {}).get("end_inset", .35) if style == "carbody" else 0
    half0, half1 = L0 / 2 - inset, L1 / 2 - inset
    fx = half1 / half0 if style == "carbody" else L1 / L0
    fz = W1 / W0
    fy = H1 / H0
    X = lambda v: round(v * fx, 4)  # noqa: E731
    Y = lambda v: round(v * fy, 4)  # noqa: E731
    Z = lambda v: round(v * fz, 4)  # noqa: E731
    s["length"], s["width"], s["height"] = L1, W1, H1
    if style == "carbody":
        b = s["body"]
        b["stations"] = [X(v) for v in b.get("stations", [])]
        for lv in b.get("profile", []):
            lv["y"] = Y(lv["y"])
        T = b.get("end_taper") or {}
        if T:
            T["start"] = X(T["start"])
            for k in ("roof_from", "roof_span", "roof_drop"):
                if k in T:
                    T[k] = Y(T[k])
        K = b.get("end_skirt") or {}
        if K:
            for k in ("below", "base", "rise"):
                K[k] = Y(K[k])
            K["from"], K["length"] = X(K["from"]), X(K["length"])
        if "aperture_min_z" in b:
            b["aperture_min_z"] = Z(b["aperture_min_z"])
        if "center_y" in b:
            b["center_y"] = Y(b["center_y"])
        for lk in ("roof_from",):
            if lk in (b.get("lining") or {}):
                b["lining"][lk] = Y(b["lining"][lk])
        for row in s.get("windows", []):
            row["centers"] = [X(v) for v in row["centers"]]
            row["y0"], row["y1"] = Y(row["y0"]), Y(row["y1"])
        d = s.get("doors") or {}
        if d.get("centers"):
            d["centers"] = [X(v) for v in d["centers"]]
            d["y0"], d["y1"] = Y(d["y0"]), Y(d["y1"])
        cab = s.get("cab") or {}
        if cab.get("ends", "none") != "none":
            ws = cab.get("windscreen") or {}
            for k in ("z0", "z1"):
                if k in ws:
                    ws[k] = Z(ws[k])
            for k in ("y0", "y1"):
                if k in ws:
                    ws[k] = Y(ws[k])
            for lt in (cab.get("side_lights") or []) + (cab.get("center_lights") or []):
                lt["y"], lt["z"] = Y(lt["y"]), Z(lt["z"])
            if cab.get("chevrons"):
                cab["chevrons"]["rows"] = [Y(v) for v in cab["chevrons"]["rows"]]
            if cab.get("horns"):
                cab["horns"]["y"] = Y(cab["horns"]["y"])
                cab["horns"]["z"] = [Z(v) for v in cab["horns"]["z"]]
            ci = cab.get("interior")
            if ci:
                ci["x"] = round(ci["x"] + (half1 - half0), 4)
                ci["floor"] = Y(ci["floor"])
        g = s.get("gangway") or {}
        if g.get("ends", "none") != "none":
            g["center_y"] = Y(g["center_y"])
            if g.get("door"):
                g["door"]["center_y"] = Y(g["door"]["center_y"])
            if g.get("window"):
                g["window"]["y0"], g["window"]["y1"] = Y(g["window"]["y0"]), Y(g["window"]["y1"])
        lg = s.get("logo") or {}
        if lg.get("type", "none") != "none":
            lg["x"], lg["y"] = X(lg["x"]), Y(lg["y"])
        rb = s.get("side_ribs") or {}
        if rb.get("heights"):
            rb["heights"] = [Y(v) for v in rb["heights"]]
        for box in s.get("underfloor") or []:
            box["x"] = X(box["x"])
        for pg in (s.get("roof") or {}).get("pantographs") or []:
            pg["x"] = X(pg["x"])
        for ac in (s.get("roof") or {}).get("ac_units") or []:
            ac["x"] = X(ac["x"])
        I = s.get("interior") or {}
        for k in ("floor_y", "ceiling_y"):
            if k in I:
                I[k] = Y(I[k])
    else:
        H = s["hood"]
        H["sections"] = [[X(x), Z(w), Y(lo), Y(sh), Y(rf)] for x, w, lo, sh, rf in H["sections"]]
        R = H["ring"]
        for k in ("belt_y", "upper_y", "upper_above", "upper_drop"):
            R[k] = Y(R[k])
        H["center_y"] = Y(H["center_y"])
        for r in H.get("apertures") or []:
            ax = r.get("axes", "xy")
            r["holes"] = [[X(a), X(b), Y(c), Y(d)] if ax == "xy" else [Z(a), Z(b), Y(c), Y(d)] for a, b, c, d in r["holes"]]
            for k in ("x_min", "x_max"):
                if k in r:
                    r[k] = X(r[k])
        ci = H.get("cab_interior")
        if ci:
            ci["x"], ci["floor"] = X(ci["x"]), Y(ci["floor"])
    s["details"] = [_fit_item(it, X, Y, Z) for it in s.get("details") or []]
    return s


def _fit_item(it, X, Y, Z):
    it = copy.deepcopy(it)
    P = lambda p: [X(p[0]), Y(p[1]), Z(p[2])]  # noqa: E731
    t = it.get("type")
    if t == "side":
        it["items"] = [_fit_item(i, X, Y, Z) for i in it["items"]]
    elif t in ("box", "cylinder", "spokes"):
        it["center"] = P(it["center"])
        if t == "box":
            it["size"] = P(it["size"])
    elif t == "bar":
        it["a"], it["b"] = P(it["a"]), P(it["b"])
    elif t in ("face", "aperture"):
        it["points"] = [P(p) for p in it["points"]]
        if t == "aperture":
            ax = it.get("axes", "xy")
            f = {"x": X, "y": Y, "z": Z}
            it["holes"] = [[f[ax[0]](a), f[ax[0]](b), f[ax[1]](c), f[ax[1]](d)] for a, b, c, d in it.get("holes", [])]
    elif t in ("panel", "grille"):
        for k in ("x0", "x1", "x"):
            if k in it:
                it[k] = X(it[k])
        if "half" in it:
            it["half"] = X(it["half"])
        it["y0"], it["y1"], it["z"] = Y(it["y0"]), Y(it["y1"]), Z(it["z"])
        sl = it.get("slats")
        if sl:
            for k in ("start", "inset", "span"):
                if k in sl:
                    sl[k] = X(sl[k])
            sl["y"], sl["z"] = Y(sl["y"]), Z(sl["z"])
    elif t == "steps":
        it["start"] = P(it["start"])
    elif t == "logo":
        it["x"], it["y"], it["z"] = X(it["x"]), Y(it["y"]), Z(it["z"])
    elif t in ("slope_aperture", "slope_face"):
        sl = it["slope"]
        sl["x0"], sl["y0"], sl["dx"], sl["dy"] = X(sl["x0"]), Y(sl["y0"]), X(sl["dx"]), Y(sl["dy"])
        it["points"] = [[Y(a), Z(b)] for a, b in it["points"]]
        it["holes"] = [[Z(a), Z(b), Y(c), Y(d)] for a, b, c, d in it.get("holes", [])]
    return it
