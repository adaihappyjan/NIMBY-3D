"""The "hood" style: a North American hood-unit locomotive (the GO example's MP40), lofted through
cross-sections (x, half width, floor, shoulder, roof), with windscreen and cab-window holes cut where
the spec's aperture rules say, and everything else (doors, grilles, lamps, steps, fans...) as the
spec's list of detail primitives. Generalised from go_train.py's locomotive().
"""
from __future__ import annotations

from .geometry import aperture_face
from . import parts


def rings_of(spec):
    H = spec["hood"]
    R = H["ring"]
    bz, belt, upper, above, drop, rz = R["bottom_z"], R["belt_y"], R["upper_y"], R["upper_above"], R["upper_drop"], R["roof_z"]
    rings = []
    for x, w, low, shoulder, roof in H["sections"]:
        up = upper if shoulder > above else shoulder - drop
        rings.append([(x, low, -w * bz), (x, belt, -w), (x, up, -w), (x, shoulder, -w), (x, roof, -w * rz),
                      (x, roof, w * rz), (x, shoulder, w), (x, up, w), (x, belt, w), (x, low, w * bz)])
    return rings


def _rule(rules, i, xa, xb):
    for r in rules:
        if i not in r["segments"]:
            continue
        if "x_min" in r and not xa >= r["x_min"]:
            continue
        if "x_max" in r and not xb <= r["x_max"]:
            continue
        return [tuple(h) for h in r["holes"]], parts.AXES[r.get("axes", "xy")]
    return [], (0, 1)


def build(c):
    spec = c.spec
    m = c.m
    H = spec["hood"]
    p = m.part("body_shell", parent=m.root)
    rings = rings_of(spec)
    paints = [c.mat(k) for k in H["ring_paint"]]
    rules = H.get("apertures") or []
    center_y = H["center_y"]
    for a, b in zip(rings, rings[1:]):
        for i in range(len(a)):
            j = (i + 1) % len(a)
            mat = paints[i]
            y = (a[i][1] + a[j][1] + b[i][1] + b[j][1]) / 4
            poly = [a[i], b[i], b[j], a[j]]
            hint = (0, y - center_y, (a[i][2] + a[j][2]) / 2)
            holes, axes = _rule(rules, i, a[0][0], b[0][0])
            if axes == (0, 1):
                aperture_face(m, p, mat, poly, hint, holes)
            else:
                aperture_face(m, p, mat, poly, hint, holes, axes)
    end = c.mat(H.get("end_paint", "primary"))
    m.face(p, end, rings[0], (-1, 0, 0))
    m.face(p, end, rings[-1], (1, 0, 0))
    parts.details(c, p, spec.get("details") or [])
    ci = H.get("cab_interior")
    if ci and c.interior:
        parts.cabin(c, ci["x"], ci["floor"], ci["length"], 1, "driver_cab", parts.cab_width(spec))
    parts.bogies(c)
    parts.couplers(c)
