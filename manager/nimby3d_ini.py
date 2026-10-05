"""nimby3d.ini in the game folder, read and changed the way the add-on itself does it (src/settings.h:
ini_text, ini_key, ini_read, ini_value, ini_write; src/addon.cpp: read_pack_names).

Only the lines of the keys being changed are touched. Comments, blank lines, keys the add-on's table does not
have (shaderpack_file=, shaderpack_options= ...), the byte order mark, the encoding (UTF-8, or UTF-16 as
Notepad's "Unicode" saves it) and each line's own line end stay exactly as they were. A changed line becomes
`key=value`; a key that has no line gets one at the end (after the add-on's header comment when the file has
none). The file is written whole or not at all: a temporary file beside it, then put in its place.

The settings themselves are described by settings_schema.json (made by tools/dump_settings.cpp from
src/settings.h): {"version":1, "pages":[{"id","name":{"en","zh"}}], "settings":[{"key","kind","default","min",
"max","step","pages","flags","name","hint","choices":[{"value","label"}]}]}.
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

INI_NAME = "nimby3d.ini"
STATIONS_NAME = "nimby3d_stations.txt"
HEADER = "# NIMBY 3D settings (the panel in the game writes this file: F10)"
ZONE_AUTO = -99.0
# a setting with one of these flags is not kept in nimby3d.ini (src/settings.h: kStation, kNoFile)
NOT_IN_FILE = ("station", "nofile")


class IniError(Exception):
    def __init__(self, code: str, text: str, **params):
        super().__init__(text.format(**params) if params else text)
        self.code = code
        self.params = params


# ---------------------------------------------------------------- the file's text

def detect(raw: bytes) -> tuple[str, bool]:
    """(encoding, has a byte order mark), as src/settings.h ini_text decides it."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8", True
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le", True
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be", True
    n = len(raw)
    if n >= 2 and b"\0" in raw:
        # no mark: UTF-16 when a quarter of the bytes or more are zeros, all on one side of their pairs
        even = sum(1 for k in range(0, n, 2) if raw[k] == 0)
        odd = sum(1 for k in range(1, n, 2) if raw[k] == 0)
        if odd * 4 >= n and even * 16 <= odd:
            return "utf-16-le", False
        if even * 4 >= n and odd * 16 <= even:
            return "utf-16-be", False
    return "utf-8", False


def _strip(s: str) -> str:
    return s.strip(" \t\r\n")


def line_key(line: str) -> tuple[str | None, str]:
    """The key a line sets (None for a comment, a section or anything else) and its value text (src/settings.h ini_key)."""
    t = _strip(line)
    if t.startswith("﻿"):
        t = _strip(t[1:])
    if not t or t[0] in "#;[":
        return None, ""
    eq = t.find("=")
    if eq < 0:
        return None, ""
    return _strip(t[:eq]), _strip(t[eq + 1:])


class IniText:
    """The file as lines that each keep their own line end; changed in place, written back in its own encoding."""

    def __init__(self, raw: bytes = b""):
        self.encoding, self.bom = detect(raw)
        body = raw
        if self.bom:
            body = raw[3:] if self.encoding == "utf-8" else raw[2:]
        if self.encoding == "utf-8":
            text = body.decode("utf-8", errors="surrogateescape")
        else:
            self._odd = body[len(body) - (len(body) % 2):]  # an odd last byte, kept as it was
            text = body[:len(body) - (len(body) % 2)].decode(self.encoding, errors="surrogatepass")
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.chunks: list[str] = re.findall(r"[^\n]*\n|[^\n]+$", text)
        self.changed = False

    @classmethod
    def load(cls, path: Path) -> "IniText":
        try:
            return cls(Path(path).read_bytes())
        except FileNotFoundError:
            return cls(b"")

    # ------------------------------------------------ reading
    @staticmethod
    def _split(chunk: str) -> tuple[str, str]:
        if chunk.endswith("\r\n"):
            return chunk[:-2], "\r\n"
        if chunk.endswith("\n"):
            return chunk[:-1], "\n"
        return chunk, ""

    def entries(self):
        """(index, key, value) of every line that sets a key."""
        for i, c in enumerate(self.chunks):
            key, value = line_key(self._split(c)[0])
            if key:
                yield i, key, value

    def get(self, key: str) -> str | None:
        """The value of a key; with several lines for it the last one counts, as the add-on reads it."""
        found = None
        for _, k, v in self.entries():
            if k == key:
                found = v
        return found

    def has(self, key: str) -> bool:
        return any(k == key for _, k, _ in self.entries())

    def keys(self) -> list[str]:
        return list(dict.fromkeys(k for _, k, _ in self.entries()))

    @property
    def text(self) -> str:
        return "".join(self.chunks)

    # ------------------------------------------------ changing
    def set(self, key: str, value: str | None, header: bool = True) -> bool:
        """key=value on the key's first line (later lines for it are dropped, as the add-on does), or a new line
        at the end; None takes every line of the key out. True when the text changed."""
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", key or ""):
            raise IniError("bad_key", "not a key: {key}", key=str(key))
        if value is not None:
            value = str(value)
            if "\n" in value or "\r" in value:
                raise IniError("bad_value", "a value cannot hold a line break")
        before = list(self.chunks)
        hits = [i for i, k, _ in self.entries() if k == key]
        if value is None:
            for i in reversed(hits):
                del self.chunks[i]
        elif hits:
            first = hits[0]
            content, end = self._split(self.chunks[first])
            line = f"{key}={value}"
            if _strip(content) != line:
                self.chunks[first] = line + (end or "")
            for i in reversed(hits[1:]):
                del self.chunks[i]
        else:
            if self.chunks and not self.chunks[-1].endswith("\n"):
                self.chunks[-1] += self.newline
            if header and "# NIMBY 3D" not in self.text:
                self.chunks.append(HEADER + self.newline)
            self.chunks.append(f"{key}={value}{self.newline}")
        if self.chunks != before:
            self.changed = True
            return True
        return False

    def to_bytes(self) -> bytes:
        text = self.text
        if self.encoding == "utf-8":
            return (b"\xef\xbb\xbf" if self.bom else b"") + text.encode("utf-8", errors="surrogateescape")
        mark = (b"\xff\xfe" if self.encoding == "utf-16-le" else b"\xfe\xff") if self.bom else b""
        return mark + text.encode(self.encoding, errors="surrogatepass") + getattr(self, "_odd", b"")

    def save(self, path: Path) -> None:
        write_atomic(Path(path), self.to_bytes())


def write_atomic(path: Path, data: bytes) -> None:
    """A temporary file beside it, flushed to the disk, then put in its place (retried while a reader holds it)."""
    import time
    tmp = path.with_name(path.name + ".nimby3d-new")
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
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            time.sleep(0.1)


# ---------------------------------------------------------------- values (src/settings.h)

def ini_number(text: str) -> float | None:
    """A number at the start of the text, written with a '.' (std::from_chars after an optional '+')."""
    t = text[1:] if text.startswith("+") else text
    m = re.match(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", t)
    if not m:
        m = re.match(r"-?(?:inf(?:inity)?|nan)", t, re.I)
        if not m:
            return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _round_half_away(x: float) -> float:
    return math.copysign(math.floor(abs(x) + 0.5), x)


def clamp(setting: dict, x: float) -> float:
    """Settings::clamp_value: what the add-on makes of a value."""
    kind = setting.get("kind")
    if kind == "toggle":
        return 1.0 if x != 0 else 0.0
    if kind == "choice":
        values = [float(c.get("value", 0)) for c in setting.get("choices") or []] or [float(setting.get("default", 0))]
        if x != x:
            return values[0]
        best = 0
        for k in range(1, len(values)):
            if abs(values[k] - x) < abs(values[best] - x):
                best = k
        return values[best]
    if kind == "pick":
        return 0.0 if x != x else float(max(0, int(_round_half_away(x))))
    if kind == "date":
        if x != x or math.isinf(x):
            return 0.0
        ix = int(x)
        if ix < 0:
            return 0.0
        m, d = ix // 100, ix % 100
        return float(m * 100 + d) if 1 <= m <= 12 and 1 <= d <= 31 else 0.0
    if kind == "zone":
        if x != x or x < -12.01 or x > 14.01:
            return ZONE_AUTO
        return _round_half_away(x * 2.0) / 2.0
    if x != x:
        return float(setting.get("default", 0))
    lo, hi = float(setting.get("min", x)), float(setting.get("max", x))
    return lo if x < lo else hi if x > hi else x


def parse(setting: dict, text: str | None) -> float | None:
    """The value a line gives a setting (ini_read), None when it gives none (then the default stays)."""
    if text is None or text == "":
        return None
    if setting.get("kind") == "date":
        m = re.match(r"\s*([+-]?\d+)-\s*([+-]?\d+)", text)
        return clamp(setting, int(m.group(1)) * 100 + int(m.group(2))) if m else None
    x = ini_number(text)
    if x is None:
        return None
    key = setting.get("key")
    if key == "labels" and x < 0:
        return 2.0  # (labels=-1 meant upright too)
    if key == "weather" and x < 0:
        return -1.0
    return clamp(setting, x)


def omitted(setting: dict, x: float) -> bool:
    """A value that needs no line: the computer's date, the time zone by the longitude."""
    return (setting.get("kind") == "date" and x == 0) or (setting.get("kind") == "zone" and x == ZONE_AUTO)


def format_value(setting: dict, x: float) -> str:
    """ini_value: as few digits as the step needs, with a '.'; a date as MM-DD."""
    kind = setting.get("kind")
    if kind == "date":
        ix = int(x)
        return f"{ix // 100:02d}-{ix % 100:02d}"
    step = float(setting.get("step") or 1.0) if kind in ("slider", "zone") else 1.0
    digits, s = 0, step
    while digits < 3 and abs(s - round(s)) > 1e-6:
        digits += 1
        s *= 10
    if x == 0:
        x = 0.0  # (not "-0")
    return f"{x:.{digits}f}"


# ---------------------------------------------------------------- the schema

def editable(schema: dict) -> dict[str, dict]:
    """The settings the settings page shows: kept in nimby3d.ini and not the shader pack (its own page)."""
    out = {}
    for s in schema.get("settings") or []:
        if not isinstance(s, dict) or not s.get("key"):
            continue
        flags = set(s.get("flags") or [])
        if s.get("kind") == "pick" or flags & set(NOT_IN_FILE):
            continue
        out[str(s["key"])] = s
    return out


def check_schema(schema) -> dict:
    if not isinstance(schema, dict) or not isinstance(schema.get("settings"), list) or not schema["settings"]:
        raise IniError("bad_schema", "settings_schema.json does not list the settings")
    return schema


def read_values(ini: IniText, schema: dict) -> dict:
    """Every setting of the page: its value (the file's, else the default) and the text of its line."""
    values, lines = {}, {}
    for key, s in editable(schema).items():
        text = ini.get(key)
        v = parse(s, text)
        values[key] = float(s.get("default", 0)) if v is None else v
        if text is not None:
            lines[key] = text
    return {"values": values, "lines": lines}


def apply_changes(ini: IniText, schema: dict, changes: dict) -> list[str]:
    """Set the given settings (None: back to the default, its line taken out). Returns the keys changed in the text."""
    table = editable(schema)
    if not isinstance(changes, dict):
        raise IniError("bad_value", "changes must be key -> value")
    done = []
    for key, v in changes.items():
        s = table.get(key)
        if s is None:
            raise IniError("bad_setting", "{key} is not a setting of nimby3d.ini", key=str(key))
        if v is None:
            if ini.set(key, None):
                done.append(key)
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            raise IniError("bad_value", "{key}: {value} is not a number", key=key, value=str(v)) from None
        x = clamp(s, x)
        if omitted(s, x):
            changed = ini.set(key, None)
        elif ini.has(key) or abs(x - float(s.get("default", 0))) >= 1e-9:
            changed = ini.set(key, format_value(s, x))
        else:
            changed = False
        if changed:
            done.append(key)
    return done


def reset_all(ini: IniText, schema: dict) -> list[str]:
    """Every setting of the page back to its default (their lines taken out); everything else stays."""
    return [key for key in editable(schema) if ini.set(key, None)]


def station_rules(path: Path) -> int:
    """How many stations nimby3d_stations.txt sets on their own (lines `name<TAB>...`, # comments)."""
    try:
        text = Path(path).read_text("utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if line and not line.startswith("#") and "\t" in line)
