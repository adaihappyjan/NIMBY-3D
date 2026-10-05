"""The material table of a model: sixteen standard slots (the order the add-on's first pack used),
then any materials a spec adds of its own.

A spec's "materials" maps a key to {name, color, alpha, metallic, roughness, emissive, blend,
double_sided}. color/emissive are linear RGB in 0..1 (as GOV2 stores them), or "#rrggbb" (sRGB, as a
colour picker gives it; converted to linear). Body parts name the key they are painted with.
"""
from __future__ import annotations

import re

# key, the GO pack's name, what it is for (en, zh)
STANDARD = [
    ("primary", "Primary livery colour", "主涂装色"),
    ("secondary", "Secondary livery colour", "副涂装色"),
    ("glass", "Window glass", "车窗玻璃"),
    ("gasket", "Window frames and seals", "窗框与密封条"),
    ("underframe", "Underframe, bogies, dark parts", "车底、转向架、深色部件"),
    ("steel", "Bare steel, handrails, wheels", "金属本色、扶手、车轮"),
    ("roof", "Roof", "车顶"),
    ("headlamp", "Headlights", "前照灯"),
    ("tail_lamp", "Tail lights", "尾灯"),
    ("safety_yellow", "Safety yellow (door thresholds)", "警示黄（门槛）"),
    ("logo", "Logo", "标志"),
    ("interior_wall", "Interior walls", "车内墙面"),
    ("interior_floor", "Interior floors and stairs", "车内地板与楼梯"),
    ("seat", "Seats", "座椅"),
    ("interior_light", "Ceiling lights", "车顶灯带"),
    ("display", "Driver's displays", "司机台显示屏"),
]
STANDARD_KEYS = [k for k, _, _ in STANDARD]

# The GO Transit reference pack's palette (linear RGB), the default for new specs too.
GO_MATERIALS = {
    "primary": {"name": "go_green", "color": [0.035, 0.29, 0.17], "alpha": 1, "metallic": 0.12, "roughness": 0.38},
    "secondary": {"name": "warm_white", "color": [0.87, 0.90, 0.85], "alpha": 1, "metallic": 0.12, "roughness": 0.42},
    "glass": {"name": "window_glass", "color": [0.12, 0.24, 0.27], "alpha": .24, "metallic": 0.05, "roughness": 0.15,
              "blend": True, "double_sided": True},
    "gasket": {"name": "window_gasket", "color": [0.018, 0.024, 0.025], "alpha": 1, "metallic": 0, "roughness": 0.72},
    "underframe": {"name": "underframe", "color": [0.045, 0.053, 0.054], "alpha": 1, "metallic": 0.55, "roughness": 0.64},
    "steel": {"name": "steel", "color": [0.31, 0.35, 0.36], "alpha": 1, "metallic": 0.82, "roughness": 0.32},
    "roof": {"name": "roof_silver", "color": [0.60, 0.65, 0.64], "alpha": 1, "metallic": 0.45, "roughness": 0.52},
    "headlamp": {"name": "headlamp", "color": [1.0, 0.86, 0.59], "alpha": 1, "metallic": 0, "roughness": 0.18, "emissive": [.8, .56, .23]},
    "tail_lamp": {"name": "tail_lamp", "color": [0.54, 0.022, 0.012], "alpha": 1, "metallic": 0, "roughness": 0.24},
    "safety_yellow": {"name": "safety_yellow", "color": [0.95, 0.66, 0.045], "alpha": 1, "metallic": 0, "roughness": 0.5},
    "logo": {"name": "go_logo_4a7729", "color": [0.0684781698, 0.1844749945, 0.0221738848], "alpha": 1, "metallic": 0, "roughness": 0.50},
    "interior_wall": {"name": "interior_wall", "color": [.62, .65, .61], "alpha": 1, "metallic": 0, "roughness": .82},
    "interior_floor": {"name": "interior_floor", "color": [.075, .092, .10], "alpha": 1, "metallic": 0, "roughness": .94},
    "seat": {"name": "seat_fabric", "color": [.055, .18, .22], "alpha": 1, "metallic": 0, "roughness": .96},
    "interior_light": {"name": "interior_light", "color": [.96, .94, .80], "alpha": 1, "metallic": 0, "roughness": .35, "emissive": [.8, .74, .53]},
    "display": {"name": "instrument_display", "color": [.018, .16, .23], "alpha": 1, "metallic": 0, "roughness": .4, "emissive": [.015, .21, .30]},
}

HEX = re.compile(r"^#([0-9a-fA-F]{6})$")


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    c = min(1.0, max(0.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def parse_color(v):
    """[r, g, b] linear (kept as given), or "#rrggbb" sRGB -> linear rounded to 4 decimals. None if neither."""
    if isinstance(v, str):
        mt = HEX.match(v.strip())
        if not mt:
            return None
        h = mt.group(1)
        return [round(srgb_to_linear(int(h[i:i + 2], 16) / 255), 4) for i in (0, 2, 4)]
    if isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return list(v)
    return None


def hex_of(rgb) -> str:
    """Linear RGB as the "#rrggbb" a screen shows (the add-on converts the same way)."""
    return "#" + "".join(f"{int(round(linear_to_srgb(float(c)) * 255)):02x}" for c in rgb)


def table(materials: dict, lod: int, opaque_glass: bool = False):
    """The model's material table for one level of detail: a list of dicts (name, rgba, metallic,
    roughness, emissive, blend, double_sided) and the index of each key."""
    keys = STANDARD_KEYS + [k for k in materials if k not in STANDARD_KEYS]
    out, index = [], {}
    for k in keys:
        spec = materials.get(k) or GO_MATERIALS.get(k) or {}
        rgba = list(parse_color(spec.get("color", [0.5, 0.5, 0.5])) or [0.5, 0.5, 0.5])
        rgba.append(spec.get("alpha", 1))
        emissive = parse_color(spec.get("emissive")) if spec.get("emissive") is not None else None
        emissive = tuple(emissive) if emissive else (0, 0, 0)
        blend = bool(spec.get("blend", False))
        double = bool(spec.get("double_sided", False))
        if blend and (lod == 2 or opaque_glass):
            # the coarsest level (and a car without an interior) shows glass as opaque: nothing behind it is modelled
            rgba[3] = 1
            blend = False
        index[k] = len(out)
        out.append({"key": k, "name": str(spec.get("name") or k), "rgba": rgba, "metallic": spec.get("metallic", 0),
                    "roughness": spec.get("roughness", 0.5), "emissive": emissive, "blend": blend, "double_sided": double})
    return out, index
