"""The "carbody" style: a passenger car body (coach, cab car, multiple-unit car, or a box-cab
locomotive) lofted through a cross-section profile at a row of stations, with real window and door
apertures, sliding door leaves, gangways, cab ends, a lining and an interior.

Generalised from go_train.py's coach(): with the GO example specs every number below is the one that
code had, and the operations are done in the same order, so the output is byte-identical.
"""
from __future__ import annotations

import math

from .geometry import box_center, aperture_face, q
from . import parts
from . import interior


def cab_at(spec, end):
    ends = (spec.get("cab") or {}).get("ends", "none")
    return ends == "both" or (ends == "front" and end == 1)


def gangway_at(spec, end):
    g = spec.get("gangway") or {}
    ends = g.get("ends", "none")
    return ends == "both" or (ends == "front" and end == 1) or (ends == "rear" and end == -1)


def openings(spec):
    """The window and door apertures of the side walls, (x0, x1, y0, y1) each, windows first."""
    windows = []
    for row in spec.get("windows") or []:
        hw = row["width"] / 2
        windows += [(x - hw, x + hw, row["y0"], row["y1"]) for x in row["centers"]]
    d = spec.get("doors") or {}
    doors = []
    if d.get("centers"):
        hw = d["width"] / 2
        doors = [(x - hw, x + hw, d["y0"], d["y1"]) for x in d["centers"]]
    return windows, doors


def profile_levels(spec):
    return spec["body"]["profile"]


def make_profile(spec, half):
    body = spec["body"]
    levels = body["profile"]
    hw = spec["width"] / 2
    T = body.get("end_taper") or {}
    K = body.get("end_skirt") or {}
    t_start = T.get("start", half)
    roof_from, roof_span, roof_drop = T.get("roof_from", 0), T.get("roof_span", 1), T.get("roof_drop", 0)
    tapered = roof_drop != 0 and t_start < half
    skirt = bool(K) and K.get("rise", 0) != 0

    def profile(x):
        end = max(0, min(1, (abs(x) - t_start) / (half - t_start))) if tapered else 0
        out = []
        for lv in levels:
            y, w = lv["y"], lv["w"]
            h = y - (max(0, y - roof_from) / roof_span) * roof_drop * end if tapered else y
            if skirt and y < K["below"]:
                h = max(h, K["base"] + K["rise"] * max(0, min(1, (abs(x) - K["from"]) / K["length"])))
            out.append((h, w * hw))
        return [(y, -z) for y, z in out[:-1]] + list(reversed(out))
    return profile


def segment_paints(spec):
    """The paint of each segment of a ring: a band is painted as its lower level says; the closing
    segment (the underside) as body.underside_paint."""
    levels = spec["body"]["profile"]
    n = len(levels)
    count = 2 * n - 1

    def level_of(k):
        return k if k <= n - 2 else 2 * n - 2 - k
    out = []
    for i in range(count):
        if i == count - 1:
            out.append(spec["body"].get("underside_paint", "underframe"))
        else:
            out.append(levels[min(level_of(i), level_of(i + 1))]["paint"])
    return out


def wall_z(spec):
    """The side wall's half width as a function of height, for frames and reveals: vertical up to
    the top of the widest band, then following the profile inwards."""
    levels = spec["body"]["profile"]
    hw = spec["width"] / 2
    widest = max(lv["w"] for lv in levels)
    first = next(i for i, lv in enumerate(levels) if lv["w"] == widest)
    top = first
    while top + 1 < len(levels) and levels[top + 1]["w"] == widest:
        top += 1
    z_wall = hw * widest
    pieces = []
    za = z_wall
    for k in range(top, len(levels) - 1):
        ya, yb = levels[k]["y"], levels[k + 1]["y"]
        zb = q(hw * levels[k + 1]["w"])
        pieces.append((ya, yb, za, q(yb - ya), q(za - zb)))
        za = zb
    y_top = levels[top]["y"]

    def z(y):
        if y <= y_top or not pieces:
            return z_wall
        for ya, yb, za_, dy, dz in pieces:
            if y <= yb or (ya, yb, za_, dy, dz) == pieces[-1]:
                return za_ - (y - ya) / dy * dz
        return z_wall
    return z


def windscreen_holes(cab):
    w = cab["windscreen"]
    if w.get("split", True):
        return [(-w["z1"], -w["z0"], w["y0"], w["y1"]), (w["z0"], w["z1"], w["y0"], w["y1"])]
    return [(-w["z1"], w["z1"], w["y0"], w["y1"])]


def build(c):
    spec = c.spec
    m = c.m
    body = spec["body"]
    p = m.part("body_shell", parent=m.root)
    lining = m.part("interior_lining", parent=m.root, role="interior", detail="lining") if c.interior else None
    windows, doors = openings(spec)
    half = m.length / 2 - body["end_inset"]
    stations = [-half] + list(body["stations"]) + [half]
    profile = make_profile(spec, half)
    paints = [c.mat(k) for k in segment_paints(spec)]
    L = body.get("lining") or {}
    l_inset, l_roof_from, l_roof_drop, l_end = L.get("inset", .075), L.get("roof_from", 3), L.get("roof_drop", .065), L.get("end_inset", .07)
    min_z = body["aperture_min_z"]
    center_y = body["center_y"]
    wall = c.mat("interior_wall")
    rings = [[(x, y, z) for y, z in profile(x)] for x in stations]
    for a, b in zip(rings, rings[1:]):
        for i in range(len(a)):
            j = (i + 1) % len(a)
            midy = (a[i][1] + a[j][1] + b[i][1] + b[j][1]) / 4
            mat = paints[i]
            z = (a[i][2] + a[j][2]) / 2
            hint = (0, midy - center_y, z)
            poly = [a[i], b[i], b[j], a[j]]
            holes = windows + doors if abs(z) > min_z else []
            aperture_face(m, p, mat, poly, hint, holes)
            if lining is not None and abs(z) > min_z:
                inner = [(x, y, zz - math.copysign(l_inset, zz)) for x, y, zz in poly]
                aperture_face(m, lining, wall, inner, tuple(-v for v in hint), holes)
            elif lining is not None and midy > l_roof_from:
                aperture_face(m, lining, wall, [(x, y - l_roof_drop, zz) for x, y, zz in poly], tuple(-v for v in hint))
    # Cross-section is convex at the ends; fan triangulation is valid here.
    cab = spec.get("cab") or {}
    end_paint = c.mat(body.get("end_paint", "secondary"))
    for idx, sgn in ((0, -1), (-1, 1)):
        holes = windscreen_holes(cab) if cab_at(spec, sgn) else []
        aperture_face(m, p, end_paint, rings[idx], (sgn, 0, 0), holes, (2, 1))
        if lining is not None:
            aperture_face(m, lining, wall, [(x - sgn * l_end, y, z) for x, y, z in rings[idx]], (-sgn, 0, 0), holes, (2, 1))
    zbody = wall_z(spec)
    style = spec.get("window_frame") or {}
    d = spec.get("doors") or {}
    hw = spec["width"] / 2
    logo = spec.get("logo") or {}
    ribs = spec.get("side_ribs") or {}
    for s in (-1, 1):
        for hole in windows:
            parts.window_frame(c, p, hole, zbody, s, True, style)
        for j, x in enumerate(d.get("centers") or []):
            parts.window_frame(c, p, doors[j], zbody, s, False, style)
            door_leaves(c, s, j, x)
            if m.lod < 2:
                if d.get("threshold", True):
                    box_center(m, p, c.mat("safety_yellow"), (x, q(d["y0"] - .025), s * q(hw - .04)), (q(d["width"] + .03), .05, .16))
                if d.get("grab_handles", True):
                    gx = q(d["width"] / 2 + .18)
                    for dx in (-gx, gx):
                        m.bar(p, c.mat("steel"), (x + dx, q(d["y0"] + .07), s * q(hw + .04)), (x + dx, q(d["y1"] - .32), s * q(hw + .04)), .022)
        if logo.get("type", "none") == "go":
            parts.go_mark(c, p, logo["x"], logo["y"], s * q(hw + logo.get("offset", .026)), s, logo["scale"])
        if m.lod == 0 and ribs.get("heights"):
            side_ribs(c, p, s, half, ribs, d)
    for end in (-1, 1):
        x = end * (half + (spec.get("gangway") or {}).get("offset", .015))
        if gangway_at(spec, end):
            gangway(c, p, x, end)
        if cab_at(spec, end):
            cab_front(c, p, x, end, cab)
    if m.lod < 2:
        for box in spec.get("underfloor") or []:
            box_center(m, p, c.mat(box.get("paint", "underframe")), (box["x"], box["y"], box.get("z", 0)), (box["length"], box["height"], box["width"]))
        horns = cab.get("horns")
        if horns:
            for end in (-1, 1):
                if cab_at(spec, end):
                    for z in horns["z"]:
                        m.cylinder(p, c.mat(horns.get("paint", "underframe")), (end * (half - horns["offset"]), horns["y"], z), horns["radius"], horns["length"], "x")
    roof_equipment(c, half, profile)
    parts.details(c, p, spec.get("details") or [])
    interior.build(c, half)
    if c.interior:
        for end in (-1, 1):
            if cab_at(spec, end):
                ci = cab.get("interior") or {}
                parts.cabin(c, end * ci["x"], ci["floor"], ci["length"], end, "driver_cab" if end == 1 else "driver_cab_rear",
                            parts.cab_width(spec))
    parts.bogies(c)
    parts.couplers(c)


def door_leaves(c, s, j, x):
    """The sliding leaves of one doorway on side s: bi-parting (two leaves sliding apart) or one leaf."""
    m = c.m
    spec = c.spec
    d = spec["doors"]
    hw = spec["width"] / 2
    dw = d["width"]
    lh = q(d["y1"] - d["y0"])
    th = d.get("thickness", .036)
    t2 = th / 2
    pz = q(hw - d.get("pocket_inset", .035))
    win = d.get("window") or {}
    two = d.get("leaves", 2) == 2
    leaves = (-1, 1) if two else (d.get("single_direction", 1),)
    lw = dw / 2 if two else dw
    h2 = dw / 4 if two else dw / 2
    paint, inner = c.mat(d.get("paint", "secondary")), c.mat(d.get("inner_paint", "interior_wall"))
    for leaf in leaves:
        cx = x + leaf * h2 if two else x
        name = f"door_{s}_{j}_{leaf}" if two else f"door_{s}_{j}_0"
        qp = m.part(name, (cx, d["y0"], s * pz), m.root, "door_leaf", slide_axis=[leaf, 0, 0], travel_m=d["travel"],
                    side='right' if s == 1 else 'left', animation_ready=True, open_seconds=d["open_seconds"], close_seconds=d["close_seconds"])
        # Pocket sliding leaves between outer shell and lining.
        holes = []
        if win:
            wx = q(h2 - win.get("margin", .11))
            hole = (-wx, wx, win["y0"], win["y1"])
            holes = [hole]
        for ss in (-1, 1):
            aperture_face(m, qp, paint if ss == s else inner, [(-h2, 0, ss * t2), (h2, 0, ss * t2), (h2, lh, ss * t2), (-h2, lh, ss * t2)], (0, 0, ss), holes)
        for xx in (-h2, h2):
            box_center(m, qp, c.mat("gasket"), (xx, lh / 2, 0), (.012, lh, .04))
        for yy in (t2, q(lh - t2)):
            box_center(m, qp, paint, (0, yy, 0), (lw, th, th))
        if holes:
            zc = q(t2 + .002)
            parts.window_frame(c, qp, holes[0], lambda y: zc, s, True, spec.get("window_frame"))


def side_ribs(c, p, s, half, ribs, d):
    m = c.m
    hw = c.spec["width"] / 2
    inset = ribs.get("end_inset", .15)
    z = s * q(hw + ribs.get("offset", .008))
    radius = ribs.get("radius", .011)
    centers = sorted(d.get("centers") or [])
    gap = q(d["width"] / 2 + ribs.get("door_gap", .02)) if centers else 0
    for yy in ribs["heights"]:
        if not centers or yy > d["y1"]:
            spans = [(-half + inset, half - inset)]
        else:
            spans = []
            start = -half + inset
            for x in centers:
                spans.append((start, q(x - gap)))
                start = q(x + gap)
            spans.append((start, half - inset))
        for a, b in spans:
            if b > a:
                m.bar(p, c.mat(ribs.get("paint", "steel")), (a, yy, z), (b, yy, z), radius)


def gangway(c, p, x, end):
    m = c.m
    g = c.spec["gangway"]
    # End gangway, inset window and collision-free coupled spacing.
    box_center(m, p, c.mat(g.get("paint", "gasket")), (x, g["center_y"], 0), (g["depth"], g["height"], g["width"]))
    dr = g.get("door")
    if dr:
        box_center(m, p, c.mat(dr.get("paint", "secondary")), (x + end * dr["offset"], dr["center_y"], 0), (dr["thickness"], dr["height"], dr["width"]))
    w = g.get("window")
    if w:
        xo = x + end * w["offset"]
        hz = w["half_width"]
        m.face(p, c.mat("glass"), [(xo, w["y0"], -hz), (xo, w["y0"], hz), (xo, w["y1"], hz), (xo, w["y1"], -hz)], (end, 0, 0))


def cab_front(c, p, x, end, cab):
    m = c.m
    w = cab["windscreen"]
    fr, fo, go = w.get("frame", .06), w.get("frame_offset", .04), w.get("glass_offset", .045)
    holes = windscreen_holes(cab)
    gasket, glass = c.mat("gasket"), c.mat("glass")
    fy0, fy1 = q(w["y0"] - fr), q(w["y1"] + fr)
    split = w.get("split", True)
    if not split:
        z1 = q(w["z1"] + fr)
        aperture_face(m, p, gasket, [(x + end * fo, fy0, -z1), (x + end * fo, fy0, z1), (x + end * fo, fy1, z1), (x + end * fo, fy1, -z1)], (end, 0, 0), holes, (2, 1))
        m.face(p, glass, [(x + end * go, w["y0"], -w["z1"]), (x + end * go, w["y0"], w["z1"]), (x + end * go, w["y1"], w["z1"]), (x + end * go, w["y1"], -w["z1"])], (end, 0, 0))
    for s in (-1, 1):
        if split:
            z0, z1 = q(w["z0"] - fr), q(w["z1"] + fr)
            aperture_face(m, p, gasket, [(x + end * fo, fy0, s * z0), (x + end * fo, fy0, s * z1), (x + end * fo, fy1, s * z1), (x + end * fo, fy1, s * z0)], (end, 0, 0), holes, (2, 1))
            m.face(p, glass, [(x + end * go, w["y0"], s * w["z0"]), (x + end * go, w["y0"], s * w["z1"]), (x + end * go, w["y1"], s * w["z1"]), (x + end * go, w["y1"], s * w["z0"])], (end, 0, 0))
        for lt in cab.get("side_lights") or []:
            m.cylinder(p, c.mat(lt.get("paint", "headlamp")), (x + end * lt["offset"], lt["y"], s * lt["z"]), lt["radius"], lt["depth"], "x")
    for lt in cab.get("center_lights") or []:
        m.cylinder(p, c.mat(lt.get("paint", "headlamp")), (x + end * lt["offset"], lt["y"], lt["z"]), lt["radius"], lt["depth"], "x")
    ch = cab.get("chevrons")
    if ch:
        o = ch.get("offset", .095)
        hz, rise, hgt = ch["half_width"], ch["rise"], ch["height"]
        top = q(rise + hgt)
        for yy in ch["rows"]:
            for s in (-1, 1):
                m.face(p, c.mat(ch.get("paint", "primary")), [(x + end * o, yy, s * hz), (x + end * o, yy + rise, 0), (x + end * o, yy + top, 0), (x + end * o, yy + hgt, s * hz)], (end, 0, 0))


def roof_top(spec, profile, x):
    """The height of the roof's middle at x (where the profile's last level is)."""
    return max(y for y, z in profile(x))


def roof_equipment(c, half, profile):
    spec = c.spec
    m = c.m
    roof = spec.get("roof") or {}
    for k, ac in enumerate(roof.get("ac_units") or []):
        y = roof_top(spec, profile, ac["x"]) - .04
        p = m.part(f"roof_unit_{k}", (ac["x"], y, 0), m.root, "static")
        box_center(m, p, c.mat(ac.get("paint", "roof")), (0, ac["height"] / 2, 0), (ac["length"], ac["height"], ac["width"]))
        if m.lod < 2:
            for dx in (-.25, .25):
                m.cylinder(p, c.mat("underframe"), (q(ac["length"] / 4) * (1 if dx > 0 else -1), ac["height"] + .005, 0), min(.32, ac["width"] / 4), .02, "y")
    for k, pg in enumerate(roof.get("pantographs") or []):
        y = roof_top(spec, profile, pg["x"]) - .02
        pantograph(c, pg, y, k)


def pantograph(c, pg, y, k):
    """A lowered single-arm pantograph on insulators (static: it does not rise)."""
    m = c.m
    steel, dark = c.mat("steel"), c.mat("underframe")
    p = m.part(f"pantograph_{k}", (pg["x"], y, 0), m.root, "static", detail="pantograph")
    d = pg.get("facing", 1)
    for ix in (-.5, .5):
        for iz in (-.38, .38):
            m.cylinder(p, c.mat("secondary") if m.lod < 2 else dark, (ix, .08, iz), .05, .16, "y", 8 if m.lod < 2 else 4)
    box_center(m, p, dark, (0, .19, 0), (1.25, .06, .95))
    knee = (d * .62, .42, 0)
    base = (-d * .45, .25, 0)
    head = (-d * .52, .52, 0)
    m.bar(p, steel, base, knee, .04)
    m.bar(p, steel, knee, head, .028)
    if m.lod < 2:
        m.bar(p, steel, (-d * .2, .25, 0), knee, .015)
    hw = pg.get("head_width", 1.0)
    m.bar(p, steel, (head[0] - .1, .56, -hw / 2), (head[0] - .1, .56, hw / 2), .025)
    m.bar(p, steel, (head[0] + .1, .56, -hw / 2), (head[0] + .1, .56, hw / 2), .025)
    for zz in (-1, 1):
        m.bar(p, steel, (head[0], .52, zz * .2), (head[0], .56, zz * hw / 2), .02)
