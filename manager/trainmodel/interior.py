"""Interiors of carbody vehicles: "bilevel" (the GO BiLevel layout: lower saloon, upper deck, end
mezzanines and stairs) and "single" (one floor, seats in the bays between the doors).

The bilevel layout's numbers are the GO reference model's; a spec may override any of them under
interior.bilevel (same keys as BILEVEL below).
"""
from __future__ import annotations

from .geometry import box_center, q
from . import parts

BILEVEL = {
    "lower_floor": {"y": .79, "length": 14.45, "width": 2.80, "thickness": .10},
    "upper_floor": {"y": 2.78, "length": 15.20, "width": 2.72, "thickness": .12},
    "mezzanine": {"x": 10.2, "y": 1.33, "length": 4.35, "width": 2.77, "thickness": .12},
    "stairs_lower": {"x": 7.27, "dx": .20, "count": 4, "base": .84, "rise": .55, "depth": .205, "width": .88},
    "stairs_upper": {"x": 9.51, "dx": .225, "count": 9, "base": 1.39, "rise": 1.45, "z": .81, "depth": .23, "width": .78},
    "stair_rails": {"a": [9.74, 2.30], "b": [7.65, 3.75], "z": [.38, 1.23], "radius": .022},
    "lights": {"x": 3.55, "lower_y": 2.707, "upper_y": 4.28, "z": [-1.05, 1.05], "upper_z_factor": .68, "size": [6.8, .025, .09]},
    "poles": {"x": 6.9, "y0": .90, "y1": 2.59, "z": [-1.30, 1.30], "radius": .024},
    "seats_lower": {"floor": .84, "first": -4.65, "pitch": 1.03, "count": 10},
    "seats_upper": {"floor": 2.84, "first": -6.45, "pitch": 1.08, "count": 13},
    "seat_z": [-1.10, -.58, .58, 1.10],
    "mezzanine_seats": {"floor": 1.39, "x": [10.25, 11.33], "z": [-1.08, -.57, .57, 1.08]},
}


def _bilevel_params(spec):
    over = (spec.get("interior") or {}).get("bilevel") or {}
    out = {}
    for k, v in BILEVEL.items():
        if isinstance(v, dict):
            out[k] = {**v, **(over.get(k) or {})}
        else:
            out[k] = over.get(k, v)
    return out


def build(c, half):
    if not c.interior:
        return
    layout = (c.spec.get("interior") or {}).get("layout", "single")
    if layout == "bilevel":
        bilevel(c)
    elif layout == "single":
        single(c, half)


def bilevel(c):
    from .carbody import cab_at
    m = c.m
    B = _bilevel_params(c.spec)
    floor, steel, light = c.mat("interior_floor"), c.mat("steel"), c.mat("interior_light")
    p = m.part('interior_structure', parent=m.root, role='interior', detail='structure')
    # Lower saloon, full-width entrance vestibules, raised end mezzanines.
    lf, uf, mz = B["lower_floor"], B["upper_floor"], B["mezzanine"]
    box_center(m, p, floor, (0, lf["y"], 0), (lf["length"], lf["thickness"], lf["width"]))
    box_center(m, p, floor, (0, uf["y"], 0), (uf["length"], uf["thickness"], uf["width"]))
    sl, su, rails, lights, poles = B["stairs_lower"], B["stairs_upper"], B["stair_rails"], B["lights"], B["poles"]
    for s in (-1, 1):
        box_center(m, p, floor, (s * mz["x"], mz["y"], 0), (mz["length"], mz["thickness"], mz["width"]))
        # Stairs from lower vestibule to mezzanine, then on one side to upper deck.
        for j in range(sl["count"]):
            top = sl["base"] + (j + 1) * sl["rise"] / sl["count"]
            box_center(m, p, floor, (s * (sl["x"] + j * sl["dx"]), (top + sl["base"]) / 2, 0), (sl["depth"], top - sl["base"], sl["width"]))
        for j in range(su["count"]):
            top = su["base"] + (j + 1) * su["rise"] / su["count"]
            box_center(m, p, floor, (s * (su["x"] - j * su["dx"]), (top + su["base"]) / 2, su["z"]), (su["depth"], top - su["base"], su["width"]))
        # Rail beside the staircase; open central aisle stays clear.
        if c.idetail:
            for z in rails["z"]:
                m.bar(p, steel, (s * rails["a"][0], rails["a"][1], z), (s * rails["b"][0], rails["b"][1], z), rails["radius"])
        for z in lights["z"]:
            box_center(m, p, light, (s * lights["x"], lights["lower_y"], z), tuple(lights["size"]))
            box_center(m, p, light, (s * lights["x"], lights["upper_y"], z * lights["upper_z_factor"]), tuple(lights["size"]))
        for z in poles["z"]:
            m.bar(p, steel, (s * poles["x"], poles["y0"], z), (s * poles["x"], poles["y1"], z), poles["radius"])
    seats = m.part('interior_seats', parent=m.root, role='interior', detail='seating')
    # Simplified representative layout, not a certified operator seating plan.
    lo, up = B["seats_lower"], B["seats_upper"]
    for level, rows in ((lo["floor"], [lo["first"] + i * lo["pitch"] for i in range(lo["count"])]),
                        (up["floor"], [up["first"] + i * up["pitch"] for i in range(up["count"])])):
        for x in rows:
            for z in B["seat_z"]:
                parts.seating(c, seats, x, level, z, 1 if x < 0 else -1)
    ms = B["mezzanine_seats"]
    for s in (-1, 1):
        for x in ms["x"]:
            if cab_at(c.spec, s):
                continue
            for z in ms["z"]:
                parts.seating(c, seats, s * x, ms["floor"], z, -s)


def single(c, half):
    """One floor the length of the car, ceiling light strips, grab poles by the doors, and 2+2 (or
    as the width allows) seats in the bays between doorways and cabs."""
    from .carbody import cab_at
    m = c.m
    spec = c.spec
    I = spec.get("interior") or {}
    floor_y = I.get("floor_y", 1.15)
    ceiling = I.get("ceiling_y", q(floor_y + 2.15))
    hw = spec["width"] / 2
    inner = q(spec["width"] - 2 * ((spec["body"].get("lining") or {}).get("inset", .075)) - .04)
    floor, steel, light = c.mat("interior_floor"), c.mat("steel"), c.mat("interior_light")
    p = m.part('interior_structure', parent=m.root, role='interior', detail='structure')
    length = q(2 * half - .2)
    box_center(m, p, floor, (0, q(floor_y - .05), 0), (length, .10, inner))
    for z in (-1, 1):
        box_center(m, p, light, (0, ceiling, z * q(inner * .28)), (q(length - .6), .025, .09))
    d = spec.get("doors") or {}
    doors = sorted(d.get("centers") or [])
    dw = d.get("width", 1.3)
    pole_z = q(inner / 2 - .45)
    for x in doors:
        for dx in (-1, 1):
            m.bar(p, steel, (x + dx * q(dw / 2 + .25), floor_y, pole_z * dx), (x + dx * q(dw / 2 + .25), ceiling, pole_z * dx), .02)
    # free bays along the car
    blocked = [(x - dw / 2 - .35, x + dw / 2 + .35) for x in doors]
    cab = spec.get("cab") or {}
    ci = cab.get("interior") or {}
    lo, hi = -half + .35, half - .35
    if cab_at(spec, 1):
        hi = min(hi, q(ci.get("x", half - 1.2) - ci.get("length", 1.8) / 2 - .9))
    if cab_at(spec, -1):
        lo = max(lo, -q(ci.get("x", half - 1.2) - ci.get("length", 1.8) / 2 - .9))
    bays = []
    start = lo
    for a, b in sorted(blocked):
        if a > start:
            bays.append((start, min(a, hi)))
        start = max(start, b)
    if start < hi:
        bays.append((start, hi))
    pitch = I.get("seat_pitch", .9)
    aisle = I.get("aisle", .55)
    seat_w = .5
    zs = []
    z = aisle / 2 + seat_w / 2
    while z + seat_w / 2 <= inner / 2 - .02 and len(zs) < 3:
        zs.append(q(z))
        z += seat_w
    zs = [-zz for zz in reversed(zs)] + zs
    seats = m.part('interior_seats', parent=m.root, role='interior', detail='seating')
    seat_floor = q(floor_y)
    for a, b in bays:
        n = int((b - a) // pitch)
        if n < 1:
            continue
        x0 = (a + b) / 2 - (n - 1) * pitch / 2
        for k in range(n):
            x = q(x0 + k * pitch)
            facing = 1 if k < n / 2 else -1
            for z in zs:
                parts.seating(c, seats, x, seat_floor, z, facing)
