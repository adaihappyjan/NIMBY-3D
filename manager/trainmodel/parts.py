"""Pieces every body style uses: window frames and panels on the side walls, seats, the driver's
cab, the logo, bogies, couplers, and the free list of detail primitives a spec may add.

Ported from go_train.py; the arithmetic of each piece is kept as it was there (see geometry.py).
"""
from __future__ import annotations

import math

from .geometry import Model, box_center, aperture_face, logo_shapes, q
from . import materials as mats


class Ctx:
    """One model being built: the spec, the level of detail, the Model and the material indices."""

    def __init__(self, spec: dict, lod: int):
        self.spec = spec
        self.lod = lod
        level = (spec.get("interior") or {}).get("level", "simple")
        self.interior = level != "none" and lod < 2       # interior parts and wall lining at all
        self.idetail = level == "detailed" and lod == 0     # the fine interior detail (seat legs, levers)
        table, index = mats.table(spec["materials"], lod, opaque_glass=(level == "none"))
        self.materials = table
        self.index = index
        self.m = Model(spec["unit_id"], spec["length"], spec["width"], lod, table)

    def mat(self, key):
        return self.index[key]


# ---------------------------------------------------------------- side walls

def side_panel(c, p, x0, x1, y0, y1, z_func, side, mat, frame=True):
    m = c.m
    gasket = c.mat("gasket")

    def quad(a, b, cc, d, material, epsilon):
        m.face(p, material, [(a, cc, side * (z_func(cc) + epsilon)), (b, cc, side * (z_func(cc) + epsilon)),
                             (b, d, side * (z_func(d) + epsilon)), (a, d, side * (z_func(d) + epsilon))], (0, 0, side))
    if frame:
        quad(x0 - .045, x1 + .045, y0 - .04, y1 + .04, gasket, .010)
    quad(x0, x1, y0, y1, mat, .017)


def window_frame(c, p, hole, z_func, side, glass=True, style=None):
    """A real aperture's border, reveal and glass; no opaque plate behind glass."""
    m = c.m
    st = style or {}
    t = st.get("border", .035)
    inset = st.get("glass_inset", .022)
    reveal = st.get("reveal", .075)
    a, b, cc, d = hole
    for x0, x1, y0, y1 in ((a - t, a, cc - t, d + t), (b, b + t, cc - t, d + t), (a, b, cc - t, cc), (a, b, d, d + t)):
        side_panel(c, p, x0, x1, y0, y1, z_func, side, c.mat("gasket"), False)
    pts = [(a, cc), (b, cc), (b, d), (a, d)]
    if glass:
        m.face(p, c.mat("glass"), [(x, y, side * (z_func(y) - inset)) for x, y in pts], (0, 0, side))
    if m.lod < 2:
        wall = c.mat("interior_wall")
        for j, ((x, y), (X, Y)) in enumerate(zip(pts, pts[1:] + pts[:1])):
            normals = ((0, 1, 0), (-1, 0, 0), (0, -1, 0), (1, 0, 0))
            m.face(p, wall, [(x, y, side * z_func(y)), (X, Y, side * z_func(Y)), (X, Y, side * (z_func(Y) - reveal)), (x, y, side * (z_func(y) - reveal))], normals[j])


def go_mark(c, p, x, y, z, side, scale=.36):
    m = c.m
    logo = c.mat("logo")
    for poly in logo_shapes((64, 32, 16)[m.lod]):
        # Each side reads left-to-right to an observer outside the vehicle.
        pts = [(x + side * (u - 230) * scale / 110, y + (110 - v) * scale / 110, z) for u, v in poly]
        m.face(p, logo, pts, (0, 0, side))


# ---------------------------------------------------------------- interior pieces

def seating(c, p, x, floor, z, facing=1):
    m = c.m
    seat = c.mat("seat")
    box_center(m, p, seat, (x, floor + .45, z), (.48, .13, .47))
    box_center(m, p, seat, (x - facing * .24, floor + .84, z), (.10, .74, .47))
    if c.idetail:
        box_center(m, p, c.mat("underframe"), (x, floor + .21, z), (.28, .36, .28))
        for s in (-1, 1):
            box_center(m, p, c.mat("steel"), (x, floor + .69, z + s * .24), (.43, .035, .035))


def cabin(c, x, floor, length, d=1, name="driver_cab", width=2.60, zc=.70):
    """The driver's cab: floor, two seats, consoles, displays, controls, back wall, light.
    d = 1 for a cab facing +X (the front), -1 for one facing -X."""
    if not c.interior:
        return
    m = c.m
    black, steel, display = c.mat("underframe"), c.mat("steel"), c.mat("display")
    p = m.part(name, parent=m.root, role="interior", detail="cab")
    box_center(m, p, c.mat("interior_floor"), (x, floor - .05, 0), (length, .10, width))
    for s in (-1, 1):
        seating(c, p, x - d * .16, floor, s * zc, d)
        box_center(m, p, black, (x + d * .61, floor + .81, s * zc), (.47, .61, .78))
        box_center(m, p, black, (x + d * .64, floor + .26, s * zc), (.26, .52, .52))
        box_center(m, p, display, (x + d * .365, floor + 1.02, s * zc), (.014, .20, .33))
        box_center(m, p, display, (x + d * .57, floor + 1.123, s * zc), (.23, .012, .32))
        if c.idetail:
            m.bar(p, steel, (x + d * .32, floor + .98, s * .45), (x + d * .23, floor + 1.12, s * .45), .025)
            box_center(m, p, black, (x + d * .23, floor + 1.12, s * .45), (.12, .05, .05))
            for j in range(4):
                m.cylinder(p, c.mat("tail_lamp") if j == 0 else steel, (x + d * .75, floor + 1.135, s * zc + (j - 1.5) * .11), .025, .025, 'y', 6)
    box_center(m, p, c.mat("interior_wall"), (x - d * .94, floor + .81, 0), (.07, 1.62, q(width + .01)))
    box_center(m, p, c.mat("interior_light"), (x - d * .4, floor + 1.73, 0), (.70, .024, .13))


def cab_width(spec):
    """The cab's floor width: 2.60 m (as the GO models have it) unless the body is narrower."""
    return 2.60 if spec["width"] >= 2.9 else q(spec["width"] - .3)


# ---------------------------------------------------------------- running gear

def bogies(c):
    m = c.m
    bg = c.spec["bogies"]
    black, steel = c.mat("underframe"), c.mat("steel")
    span = m.length * bg["pivot_fraction"]
    radius = bg["wheel_radius"]
    axles = bg["axles"]
    for idx, x in enumerate((-span, span)):
        p = m.part(f"bogie_{idx}", (x, radius, 0), m.root, "bogie", rotation_axis=[0, 1, 0])
        box_center(m, p, black, (0, .3, 0), (bg["frame_length"], .42, 1.7))
        for side in (-1, 1):
            box_center(m, p, black, (0, .14, side * 1.04), (bg["side_frame_length"], .31, .2))
        for j, ax in enumerate(axles):
            wheel = m.part(f"wheelset_{idx}_{j}", (ax, 0, 0), p, "wheelset", rotation_axis=[0, 0, 1], radius_m=radius)
            if m.lod < 2:
                m.cylinder(wheel, steel, (0, 0, 0), .10, 2.02)
            for s in (-1, 1):
                m.cylinder(wheel, black, (0, 0, s * .76), radius, .18)
                if m.lod < 2:
                    m.cylinder(wheel, steel, (0, 0, s * .862), radius * .71, .03)
                    m.cylinder(wheel, black, (0, 0, s * 1.075), .14, .12)
                    if m.lod == 0:
                        for dx in (-.29, .29):
                            m.cylinder(p, steel, (ax + dx, .32, s * 1.035), .10, .24, "y", 8)


def couplers(c):
    m = c.m
    cp = c.spec.get("couplers") or {}
    inset = cp.get("inset", .30)
    height = cp.get("height", .85)
    for side in (-1, 1):
        p = m.part(f"coupler_{side}", (side * (m.length / 2 - inset), height, 0), m.root, "coupler")
        box_center(m, p, c.mat("underframe"), (0, 0, 0), (.56, .2, .23))
        box_center(m, p, c.mat("steel"), (side * .12, 0, .07), (.22, .26, .28))


# ---------------------------------------------------------------- free details

AXES = {"xy": (0, 1), "zy": (2, 1), "xz": (0, 2), "yz": (1, 2), "yx": (1, 0), "zx": (2, 0)}


def _present(item, lod):
    lods = item.get("lods")
    return lods is None or lod in lods


def _z(v, s):
    """A point of a detail in a side group: its Z on side s (s None: as given)."""
    return v if s is None else s * v


def details(c, p, items, s=None):
    """The spec's list of detail primitives, in order. A "side" item repeats its own items on the
    left (Z negated) and then the right side; within one, every Z is mirrored."""
    m = c.m
    for it in items:
        if not _present(it, m.lod):
            continue
        kind = it["type"]
        if kind == "side":
            for side in (-1, 1):
                details(c, p, it["items"], side)
            continue
        mat = c.mat(it["paint"]) if "paint" in it else None
        if kind == "box":
            cx, cy, cz = it["center"]
            box_center(m, p, mat, (cx, cy, _z(cz, s)), tuple(it["size"]))
        elif kind == "cylinder":
            cx, cy, cz = it["center"]
            m.cylinder(p, mat, (cx, cy, _z(cz, s)), it["radius"], it["length"], it.get("axis", "z"), it.get("sides"))
        elif kind == "bar":
            a, b = it["a"], it["b"]
            m.bar(p, mat, (a[0], a[1], _z(a[2], s)), (b[0], b[1], _z(b[2], s)), it.get("radius", .025))
        elif kind in ("face", "aperture"):
            pts = [(x, y, _z(z, s)) for x, y, z in it["points"]]
            nx, ny, nz = it["normal"]
            outward = (nx, ny, _z(nz, s))
            if kind == "face":
                m.face(p, mat, pts, outward)
            else:
                aperture_face(m, p, mat, pts, outward, [tuple(h) for h in it.get("holes", [])], AXES[it.get("axes", "xy")])
        elif kind == "panel":
            side = 1 if s is None else s
            zc = it["z"]
            side_panel(c, p, it["x0"], it["x1"], it["y0"], it["y1"], lambda y: zc, side, mat, it.get("frame", True))
        elif kind == "grille":
            side = 1 if s is None else s
            zc = it["z"]
            x0 = it["x0"] if "x0" in it else it["x"] - it["half"]
            x1 = it["x1"] if "x1" in it else it["x"] + it["half"]
            side_panel(c, p, x0, x1, it["y0"], it["y1"], lambda y: zc, side, mat, it.get("frame", False))
            sl = it.get("slats")
            if sl:
                n = sl["counts"][m.lod]
                start = sl["start"] if "start" in sl else it["x"] - sl["inset"]
                smat = c.mat(sl.get("paint", "steel"))
                for k in range(n):
                    xx = start + k * (sl["span"] / (n - 1)) if n > 1 else start
                    box_center(m, p, smat, (xx, sl["y"], side * sl["z"]), tuple(sl["size"]))
        elif kind == "steps":
            sx, sy, sz = it["start"]
            dx, dy, dz = it["step"]
            for k in range(it["count"]):
                box_center(m, p, mat, (sx + k * dx, sy + k * dy, _z(sz + k * dz, s)), tuple(it["size"]))
        elif kind == "spokes":
            cx, cy, cz = it["center"]
            n, length = it["count"], it["length"]
            for i in range(n):
                a = i * math.tau / n
                z = cz + length * math.sin(a) if cz else length * math.sin(a)
                m.bar(p, mat, (cx, cy, _z(cz, s)), (cx + length * math.cos(a), cy, _z(z, s)), it.get("radius", .019))
        elif kind == "logo":
            side = 1 if s is None else s
            if it.get("logo", "go") == "go":
                go_mark(c, p, it["x"], it["y"], side * it["z"], side, it.get("scale", .36))
        elif kind in ("slope_aperture", "slope_face"):
            sl = it["slope"]
            x0, y0, ddx, ddy = sl["x0"], sl["y0"], sl["dx"], sl["dy"]

            def front_x(y):
                return x0 + (y0 - y) * ddx / ddy
            off = it.get("offset", 0)
            pts = [(front_x(y) + off, y, _z(z, s)) for y, z in it["points"]]
            nx, ny, nz = it["normal"]
            outward = (nx, ny, _z(nz, s))
            if kind == "slope_face":
                m.face(p, mat, pts, outward)
            else:
                aperture_face(m, p, mat, pts, outward, [tuple(h) for h in it.get("holes", [])], AXES[it.get("axes", "zy")])
        else:
            raise ValueError(f"unknown detail type {kind}")
