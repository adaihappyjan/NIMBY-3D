"""Mesh building blocks: a model of named parts, each with triangles bucketed by material.

Ported from the GO Train reference generator (experiments/go_train_assets_v1/go_train.py by the
same author). The arithmetic is kept exactly as it was there, operation for operation, so that the
GO example specs reproduce the published GOV2 files byte for byte: do not "simplify" an expression
here (a+b-c is not a+(b-c) in floating point).

Coordinates: metres, +X the vehicle's front, +Y up, +Z right; origin at the middle of the vehicle on
the rail head. Standard library only.
"""
from __future__ import annotations

import math


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def normal(v):
    d = math.sqrt(dot(v, v))
    if d < 1e-10:
        raise ValueError("degenerate normal")
    return tuple(x / d for x in v)


def q(x):
    """A derived length snapped to the micrometre grid: specs give metres with at most 6 decimals,
    so 2.72 - 0.84 becomes 1.88 again (not 1.8800000000000003)."""
    return round(x, 6)


class Model:
    """Parts in order (a parent always before its children); per part, primitives keyed by material
    index, each a list of vertices (x, y, z, nx, ny, nz, u, v) and triangle indices."""

    def __init__(self, unit_id, length, width, lod, materials=None):
        self.unit_id, self.length, self.width, self.lod = unit_id, length, width, lod
        self.materials = materials or []
        self.parts = []
        self.root = self.part(unit_id, role="vehicle_root")

    def part(self, name, translation=(0, 0, 0), parent=None, role="static", **extras):
        p = {"name": name, "translation": list(translation), "parent": parent,
             "extras": {"role": role, **extras}, "primitives": {}}
        self.parts.append(p)
        return len(self.parts) - 1

    def face(self, p, mat, pts, outward):
        pts = list(pts)
        n = cross(sub(pts[1], pts[0]), sub(pts[2], pts[0]))
        if dot(n, outward) < 0:
            pts.reverse()
        n = normal(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])))
        prim = self.parts[p]["primitives"].setdefault(mat, {"vertices": [], "indices": []})
        at = len(prim["vertices"])
        # Per-face UVs, metres on the face; procedural materials do not require textures.
        u = normal(sub(pts[1], pts[0]))
        v = cross(n, u)
        for qq in pts:
            rel = sub(qq, pts[0])
            prim["vertices"].append((*qq, *n, dot(rel, u), dot(rel, v)))
        for i in range(1, len(pts) - 1):
            tri_n = cross(sub(pts[i], pts[0]), sub(pts[i + 1], pts[0]))
            # Collinear boundary vertices can legitimately occur on an end cap.
            if dot(tri_n, tri_n) > 1e-16:
                prim["indices"].extend((at, at + i, at + i + 1))

    def box(self, p, mat, lo, hi):
        x, y, z = lo
        X, Y, Z = hi
        if min(X - x, Y - y, Z - z) <= 0:
            raise ValueError("invalid box")
        for pts, n in [
                ([(x, y, z), (x, Y, z), (x, Y, Z), (x, y, Z)], (-1, 0, 0)),
                ([(X, y, z), (X, y, Z), (X, Y, Z), (X, Y, z)], (1, 0, 0)),
                ([(x, y, z), (x, y, Z), (X, y, Z), (X, y, z)], (0, -1, 0)),
                ([(x, Y, z), (X, Y, z), (X, Y, Z), (x, Y, Z)], (0, 1, 0)),
                ([(x, y, z), (X, y, z), (X, Y, z), (x, Y, z)], (0, 0, -1)),
                ([(x, y, Z), (x, Y, Z), (X, Y, Z), (X, y, Z)], (0, 0, 1))]:
            self.face(p, mat, pts, n)

    def cylinder(self, p, mat, center, radius, length, axis="z", sides=None):
        sides = sides or (16, 10, 6)[self.lod]

        def point(t, a):
            qq = (radius * math.cos(a), radius * math.sin(a), t)
            if axis == "y":
                qq = (qq[0], qq[2], qq[1])
            if axis == "x":
                qq = (qq[2], qq[0], qq[1])
            return tuple(center[i] + qq[i] for i in range(3))
        rings = [[point(t, i * math.tau / sides) for i in range(sides)] for t in (-length / 2, length / 2)]
        for i in range(sides):
            j = (i + 1) % sides
            mid = tuple((rings[0][i][k] + rings[1][j][k]) / 2 - center[k] for k in range(3))
            self.face(p, mat, [rings[0][i], rings[0][j], rings[1][j], rings[1][i]], mid)
        for end, sign in ((0, -1), (1, 1)):
            n = {"x": (sign, 0, 0), "y": (0, sign, 0), "z": (0, 0, sign)}[axis]
            self.face(p, mat, rings[end], n)

    def bar(self, p, mat, a, b, radius=0.025):
        direction = normal(sub(b, a))
        u = normal(cross(direction, (0, 1, 0) if abs(direction[1]) < .9 else (1, 0, 0)))
        v = cross(direction, u)
        rings = [[tuple(c[k] + radius * (math.cos(i * math.tau / 6) * u[k] + math.sin(i * math.tau / 6) * v[k]) for k in range(3))
                  for i in range(6)] for c in (a, b)]
        for i in range(6):
            j = (i + 1) % 6
            out = tuple(rings[0][i][k] - a[k] for k in range(3))
            self.face(p, mat, [rings[0][i], rings[0][j], rings[1][j], rings[1][i]], out)
        self.face(p, mat, rings[0], tuple(-qq for qq in direction))
        self.face(p, mat, rings[1], direction)

    def stats(self):
        return {"parts": len(self.parts),
                "vertices": sum(len(pr["vertices"]) for n in self.parts for pr in n["primitives"].values()),
                "triangles": sum(len(pr["indices"]) // 3 for n in self.parts for pr in n["primitives"].values())}


def box_center(m, p, mat, c, size):
    m.box(p, mat, tuple(c[i] - size[i] / 2 for i in range(3)), tuple(c[i] + size[i] / 2 for i in range(3)))


def clip_polygon(poly, axis, bound, greater):
    """Clip a convex 3D polygon by an axis-aligned plane, retaining winding."""
    out = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        ia = a[axis] >= bound if greater else a[axis] <= bound
        ib = b[axis] >= bound if greater else b[axis] <= bound
        if ia:
            out.append(a)
        if ia != ib:
            t = (bound - a[axis]) / (b[axis] - a[axis])
            out.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
    clean = []
    for qq in out:
        if not clean or dot(sub(qq, clean[-1]), sub(qq, clean[-1])) > 1e-16:
            clean.append(qq)
    if len(clean) > 1 and dot(sub(clean[0], clean[-1]), sub(clean[0], clean[-1])) < 1e-16:
        clean.pop()
    return clean


def cut_rectangles(poly, holes, axes=(0, 1)):
    """Subtract rectangular apertures, returning disjoint convex face fragments."""
    pieces = [poly]
    for u0, u1, v0, v1 in holes:
        result = []
        for qq in pieces:
            if (max(v[axes[0]] for v in qq) <= u0 or min(v[axes[0]] for v in qq) >= u1 or
                    max(v[axes[1]] for v in qq) <= v0 or min(v[axes[1]] for v in qq) >= v1):
                result.append(qq)
                continue
            inside = qq
            for axis, bound, keep_greater in ((axes[0], u0, True), (axes[0], u1, False), (axes[1], v0, True), (axes[1], v1, False)):
                outside = clip_polygon(inside, axis, bound, not keep_greater)
                if len(outside) >= 3:
                    result.append(outside)
                inside = clip_polygon(inside, axis, bound, keep_greater)
                if len(inside) < 3:
                    break
        pieces = result
    return pieces


def aperture_face(m, p, mat, poly, outward, holes=(), axes=(0, 1)):
    for qq in cut_rectangles(poly, holes, axes):
        # Remove collinear vertices introduced at existing face boundaries.
        while len(qq) > 3:
            bad = next((i for i in range(len(qq)) if dot(cross(sub(qq[i], qq[i - 1]), sub(qq[(i + 1) % len(qq)], qq[i])),
                                                          cross(sub(qq[i], qq[i - 1]), sub(qq[(i + 1) % len(qq)], qq[i]))) < 1e-18), None)
            if bad is None:
                break
            qq.pop(bad)
        if len(qq) >= 3 and dot(cross(sub(qq[1], qq[0]), sub(qq[2], qq[0])), cross(sub(qq[1], qq[0]), sub(qq[2], qq[0]))) > 1e-18:
            m.face(p, mat, qq, outward)


def logo_shapes(segments=64):
    """Vector reconstruction of the user-supplied 460 x 220 transparent GO mark.

    The G is a clipped left circle, top-right quadrant and square lower-right;
    it is NOT an outlined letter. The O is split by a 20 px horizontal gap.
    """
    def clipped(poly, axis, value, greater):
        out = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            ia = (a[axis] >= value) if greater else (a[axis] <= value)
            ib = (b[axis] >= value) if greater else (b[axis] <= value)
            if ia:
                out.append(a)
            if ia != ib:
                t = (value - a[axis]) / (b[axis] - a[axis])
                out.append(tuple(a[i] + t * (b[i] - a[i]) for i in range(2)))
        return out

    def circle(cx):
        return [(cx + 110 * math.cos(i * math.tau / segments), 110 + 110 * math.sin(i * math.tau / segments)) for i in range(segments)]
    left = circle(110)
    right = circle(350)
    return [clipped(left, 0, 100, False), clipped(clipped(left, 0, 120, True), 1, 100, False),
            [(120, 120), (220, 120), (220, 220), (120, 220)],
            clipped(right, 1, 100, False), clipped(right, 1, 120, True)]
