"""The Minecraft shader packs the add-on can draw the 3D view with (src/iris), kept where Minecraft keeps them:
%APPDATA%\\.minecraft\\shaderpacks (N3D_SHADERPACKS for tests). A pack is a .zip file or a folder with a
shaders/ folder inside that holds its programs (src/iris/source.h find_root).

Which pack the add-on uses is set in the game folder's nimby3d.ini (src/addon.cpp load_settings and
read_pack_names): shaderpack=0 off; shaderpack=N (N > 0) on, with shaderpack_file=<name> naming the pack (N is only
its place in the in-game panel's list: with a name the name counts, wherever the pack is in that list);
shaderpack_profile= the pack's profile; shaderpack_options=NAME=VALUE NAME=VALUE ... its own options. The ini holds
the options of one pack: the others' are kept in the manager's state folder (shaderpack_options.json) and put back
when that pack is chosen again.

Removing a pack moves it to the Recycle Bin (SHFileOperationW with FOF_ALLOWUNDO), never deletes it.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path

import nimby3d_ini as nini

# src/addon.cpp kKnownPacks: packs known to work, in the order the add-on prefers them (a name containing one)
KNOWN = ("complementaryreimagined", "complementaryshaders", "bsl", "photon", "sildur", "seus-renewed", "sundial",
         "continuum", "kuda", "rre36", "bvs")
OPTION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
OPTION_VALUE = re.compile(r"^[^\s,;=]+$")
PROFILE_NAME = re.compile(r"^[^\s=,;]*$")
MEMORY_NAME = "shaderpack_options.json"


class PackError(nini.IniError):
    pass


def packs_dir() -> Path:
    env = os.environ.get("N3D_SHADERPACKS")
    if env:
        return Path(env)
    return Path(os.environ.get("APPDATA", "")) / ".minecraft" / "shaderpacks"


def known_rank(name: str) -> int | None:
    low = name.lower()
    for i, k in enumerate(KNOWN):
        if k in low:
            return i
    return None


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.lower() == b.lower()  # (the add-on compares with _stricmp)


def _size(p: Path) -> tuple[int, int]:
    """Bytes and files of a folder (or a file)."""
    if p.is_file():
        return p.stat().st_size, 1
    total = n = 0
    for root, dirs, files in os.walk(p):
        for f in files:
            with contextlib.suppress(OSError):
                total += os.stat(os.path.join(root, f)).st_size
                n += 1
    return total, n


def scan(folder: Path | None = None, sizes: bool = True) -> list[dict]:
    """The packs, in the order the in-game panel lists them: those known to work first (in the add-on's order),
    then the rest by name (src/addon.cpp scan_packs). sizes: a folder's size is added up (slower)."""
    folder = folder or packs_dir()
    out = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return out
    for e in entries:
        try:
            is_dir = e.is_dir()
        except OSError:
            continue
        if e.name in (".", "..") or e.name.endswith(".nimby3d-new") or not (is_dir or e.name.lower().endswith(".zip")):
            continue
        p = Path(e.path)
        try:
            st = p.stat()
            size, files = _size(p) if sizes else ((st.st_size, 1) if not is_dir else (None, None))
        except OSError:
            continue
        out.append({"name": e.name, "kind": "folder" if is_dir else "zip", "size": size, "files": files, "mtime": st.st_mtime,
                    "known": known_rank(e.name) is not None})
    out.sort(key=lambda d: d["name"].lower())
    out.sort(key=lambda d: known_rank(d["name"]) if known_rank(d["name"]) is not None else 1000)
    for i, d in enumerate(out):
        d["panel_index"] = i + 1
    return out


# ---------------------------------------------------------------- is it a pack

def _program_in_shaders(names) -> bool:
    """A folder named shaders (anywhere) with a program or shaders.properties in it, as src/iris/source.h finds it."""
    for n in names:
        n = n.replace("\\", "/")
        at = n.rfind("shaders/")
        if at < 0 or (at > 0 and n[at - 1] != "/"):
            continue
        rest = n[at + 8:]
        if rest == "shaders.properties" or (len(rest) > 4 and rest[-4:].lower() in (".fsh", ".vsh", ".csh")):
            return True
    return False


def check_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except (zipfile.BadZipFile, OSError, ValueError) as ex:
        raise PackError("not_a_zip", "{name} is not a ZIP file ({error})", name=Path(path).name, error=str(ex)) from None
    if not _program_in_shaders(names):
        raise PackError("not_a_pack", "{name} is not a shader pack: there is no shaders/ folder with programs in it", name=Path(path).name)


def check_folder(path: Path) -> None:
    root = Path(path)
    if not root.is_dir():
        raise PackError("not_a_pack", "{name} is not a folder", name=root.name)
    names = []
    base = len(str(root)) + 1
    for dirpath, dirs, files in os.walk(root):
        depth = dirpath[base:].count(os.sep) if len(dirpath) > base else 0
        if depth > 4:
            dirs[:] = []
            continue
        names += [os.path.join(dirpath[base:], f).replace("\\", "/") for f in files]
        if len(names) > 20000:
            break
    if not _program_in_shaders(names):
        raise PackError("not_a_pack", "{name} is not a shader pack: there is no shaders/ folder with programs in it", name=root.name)


# ---------------------------------------------------------------- import and remove

def _child(folder: Path, name: str) -> Path:
    """A pack's path in the folder, for a plain name only (no folders, nothing outside it)."""
    if not name or name in (".", "..") or any(c in name for c in '\\/:*?"<>|') or name != name.strip():
        raise PackError("bad_pack", "not a pack name: {name}", name=str(name))
    p = folder / name
    if p.parent != folder:
        raise PackError("bad_pack", "not a pack name: {name}", name=str(name))
    return p


FO_COPY, FO_DELETE = 2, 3
FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x0004, 0x0010, 0x0040, 0x0400
FOF_WANTNUKEWARNING = 0x4000  # where there is no Recycle Bin, ask rather than delete for good


def shell_file_op(func: int, src: str, dst: str | None, flags: int) -> tuple[int, bool]:
    """SHFileOperationW on one path: (its result, whether it was aborted)."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]

    op = SHFILEOPSTRUCTW()
    op.wFunc = func
    op.pFrom = src + "\0\0"  # (a list of paths, each ended by a zero, the list by another)
    op.pTo = (dst + "\0\0") if dst else None
    op.fFlags = flags
    shell = ctypes.WinDLL("shell32")
    shell.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    shell.SHFileOperationW.restype = ctypes.c_int
    rc = shell.SHFileOperationW(ctypes.byref(op))
    return rc, bool(op.fAnyOperationsAborted)


def recycle(path: Path) -> None:
    """Move a file or folder to the Recycle Bin (undoable), with no questions and no progress window."""
    full = os.path.abspath(str(path))
    rc, aborted = shell_file_op(FO_DELETE, full, None, FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_WANTNUKEWARNING)
    if rc != 0 or aborted:
        raise PackError("recycle_failed", "{name} could not be moved to the Recycle Bin (error {rc})", name=Path(path).name, rc=rc)
    if os.path.lexists(full):
        raise PackError("recycle_failed", "{name} is still there after moving it to the Recycle Bin", name=Path(path).name)


def import_pack(src, folder: Path | None = None, replace: bool = False, recycler=None) -> dict:
    """Copy a pack (.zip or folder) into the shader packs folder (made when missing). A name already there is
    refused, or with `replace` the one there goes to the Recycle Bin first."""
    folder = folder or packs_dir()
    src = Path(str(src).strip().strip('"'))
    if not src.exists():
        raise PackError("pack_missing", "{path} does not exist", path=str(src))
    if src.is_dir():
        check_folder(src)
    elif src.suffix.lower() == ".zip":
        check_zip(src)
    else:
        raise PackError("not_a_pack", "{name} is not a shader pack (a .zip file or a folder)", name=src.name)
    with contextlib.suppress(OSError):
        if folder.exists() and src.resolve().parent == folder.resolve():
            raise PackError("already_there", "{name} is already in the shader packs folder", name=src.name)
    folder.mkdir(parents=True, exist_ok=True)
    dst = _child(folder, src.name)
    if os.path.lexists(dst):
        if not replace:
            raise PackError("pack_exists", "a pack named {name} is already there", name=src.name)
        (recycler or recycle)(dst)
    tmp = folder / f".{src.name}.nimby3d-new"
    if os.path.lexists(tmp):
        shutil.rmtree(tmp) if tmp.is_dir() else tmp.unlink()
    try:
        if src.is_dir():
            shutil.copytree(src, tmp)
        else:
            shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            shutil.rmtree(tmp) if tmp.is_dir() else tmp.unlink()
        raise
    size, files = _size(dst)
    return {"name": dst.name, "path": str(dst), "kind": "folder" if dst.is_dir() else "zip", "size": size, "files": files}


def remove_pack(name: str, folder: Path | None = None, recycler=None) -> dict:
    folder = folder or packs_dir()
    p = _child(folder, name)
    if not os.path.lexists(p):
        raise PackError("pack_missing", "{path} does not exist", path=str(p))
    (recycler or recycle)(p)
    return {"name": name, "recycled": True}


# ---------------------------------------------------------------- the pack's own options (n3d_packinfo.exe)

def parse_options(text: str | None) -> dict:
    """shaderpack_options=NAME=VALUE NAME=VALUE ... (spaces, commas, semicolons or tabs between), as the add-on reads it."""
    out = {}
    for word in re.split(r"[ ,;\t]+", text or ""):
        eq = word.find("=")
        if eq > 0 and eq + 1 < len(word):
            out[word[:eq]] = word[eq + 1:]
    return out


def format_options(options: dict) -> str:
    for k, v in options.items():
        if not OPTION_NAME.match(str(k)):
            raise PackError("bad_option", "not an option name: {name}", name=str(k))
        if not OPTION_VALUE.match(str(v)):
            raise PackError("bad_option", "not a value for {name}: {value}", name=str(k), value=str(v))
    return " ".join(f"{k}={v}" for k, v in sorted(options.items(), key=lambda kv: kv[0].lower()))


def check_profile(profile) -> str:
    profile = "" if profile is None else str(profile).strip()
    if not PROFILE_NAME.match(profile):
        raise PackError("bad_option", "not a profile name: {name}", name=profile)
    return profile


_INFO_CACHE: dict = {}
_INFO_LOCK = threading.Lock()


def pack_info(tool: Path | None, path: Path, profile: str | None = None, timeout: float = 90.0) -> dict:
    """What n3d_packinfo.exe says about a pack: its profiles, screens, sliders and options (one JSON object on its
    output). With a profile each option's "default" is its value under that profile. A non-zero exit, output that is
    not JSON or "ok": false is a failure."""
    if tool is None or not Path(tool).is_file():
        raise PackError("packinfo_missing", "the pack reader n3d_packinfo.exe is missing ({path})", path=str(tool or "n3d_packinfo.exe"))
    try:
        st = path.stat()
        tst = Path(tool).stat()
    except OSError:
        raise PackError("pack_missing", "{path} does not exist", path=str(path)) from None
    key = (os.path.normcase(str(path)), st.st_mtime_ns, st.st_size, os.path.normcase(str(tool)), tst.st_mtime_ns, profile or "")
    with _INFO_LOCK:
        if key in _INFO_CACHE:
            return _INFO_CACHE[key]
    args = [str(tool), str(path)] + (["--profile", profile] if profile else [])
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise PackError("packinfo_failed", "the pack reader took longer than {s} s", s=int(timeout)) from None
    except OSError as ex:
        raise PackError("packinfo_failed", "the pack reader could not run: {error}", error=str(ex)) from None
    out = r.stdout.decode("utf-8", errors="replace").strip()
    try:
        info = json.loads(out) if out.startswith("{") else None
    except ValueError:
        info = None
    if not isinstance(info, dict) or r.returncode != 0 or not info.get("ok"):
        why = (info or {}).get("error") if isinstance(info, dict) else None
        err = str(why or r.stderr.decode("utf-8", errors="replace").strip() or out or f"exit code {r.returncode}")[:600]
        raise PackError("packinfo_failed", "the pack reader failed: {error}", error=err)
    for k, default in (("profiles", []), ("screens", {}), ("screen_labels", {}), ("sliders", []), ("options", [])):
        if not isinstance(info.get(k), type(default)):
            info[k] = default
    info["options"] = [o for o in info["options"] if isinstance(o, dict) and o.get("name")]
    with _INFO_LOCK:
        if len(_INFO_CACHE) > 64:
            _INFO_CACHE.clear()
        _INFO_CACHE[key] = info
    return info


def check_against(info: dict, profile: str, options: dict) -> None:
    """A profile the pack has (exactly: an unknown one makes the whole pack fail to open) and options it has, each
    with one of its own values."""
    names = [p.get("name") for p in info.get("profiles") or [] if isinstance(p, dict)]
    if profile and profile not in names:
        raise PackError("bad_profile", "the pack has no profile {name}", name=profile)
    table = {o["name"]: o for o in info.get("options") or []}
    bad = []
    for k, v in options.items():
        o = table.get(k)
        if o is None or str(v) not in [str(x) for x in o.get("values") or []]:
            bad.append(f"{k}={v}")
    if bad:
        raise PackError("bad_option", "the pack does not take {options}", options=", ".join(bad[:8]))


# ---------------------------------------------------------------- the choice in nimby3d.ini

def selection(ini: nini.IniText, packs: list[dict] | None = None) -> dict:
    """What nimby3d.ini chooses. on: shaderpack= is above 0 and there is a pack to open. owner: the pack the file's
    profile and options belong to, the one named (shaderpack_file=), or when on with none named the first the panel
    lists (the add-on then opens that one); "" when none."""
    raw = ini.get("shaderpack")
    x = nini.ini_number(raw) if raw else None
    on_value = bool(x is not None and x == x and round(x) > 0)
    file = ini.get("shaderpack_file") or ""
    first = packs[0]["name"] if packs else ""
    owner = file or (first if on_value else "")
    return {"enabled": on_value and bool(file or first), "on_value": on_value, "file": file, "owner": owner,
            "profile": ini.get("shaderpack_profile") or "", "options": ini.get("shaderpack_options") or ""}


class Memory:
    """The profile and options of each pack not chosen in nimby3d.ini: state/shaderpack_options.json."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        packs = data.get("packs") if isinstance(data, dict) else None
        return packs if isinstance(packs, dict) else {}

    def get(self, name: str) -> dict | None:
        with self.lock:
            e = self._load().get(name.lower())
        return e if isinstance(e, dict) else None

    def put(self, name: str, profile: str, options: str) -> None:
        with self.lock:
            packs = self._load()
            packs[name.lower()] = {"name": name, "profile": profile or "", "options": options or "", "saved": time.time()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            nini.write_atomic(self.path, json.dumps({"packs": packs}, indent=1, ensure_ascii=False).encode("utf-8"))

    def all(self) -> dict:
        with self.lock:
            return self._load()


def _set_pack_lines(ini: nini.IniText, name: str, profile: str, options: str) -> None:
    ini.set("shaderpack_file", name)
    ini.set("shaderpack_profile", profile or None)
    ini.set("shaderpack_options", options or None)


def _pack_name(packs: list[dict], name: str) -> str:
    for p in packs:
        if _same(p["name"], name):
            return p["name"]
    raise PackError("pack_missing", "there is no pack named {name}", path=str(name), name=str(name))


def choose(ini: nini.IniText, name: str, memory: Memory, packs: list[dict]) -> dict:
    """Use this pack: shaderpack=1 and shaderpack_file=<name>. The profile and options of the pack chosen so far go
    into the memory, the new one's come back from it."""
    name = _pack_name(packs, name)
    cur = selection(ini, packs)
    if _same(cur["owner"], name):
        profile, options = cur["profile"], cur["options"]
    else:
        if cur["owner"]:
            memory.put(cur["owner"], cur["profile"], cur["options"])
        saved = memory.get(name) or {}
        profile, options = saved.get("profile", ""), saved.get("options", "")
    ini.set("shaderpack", "1")
    _set_pack_lines(ini, name, profile, options)
    return {"name": name, "profile": profile, "options": options}


def enable(ini: nini.IniText, on: bool, memory: Memory, packs: list[dict]) -> dict:
    """Shader packs on (the pack named, or the first the panel lists when the one named is gone) or off."""
    cur = selection(ini, packs)
    if on:
        if not packs:
            raise PackError("no_packs", "there are no shader packs in {dir}", dir=str(packs_dir()))
        target = cur["file"] if cur["file"] and any(_same(p["name"], cur["file"]) for p in packs) else packs[0]["name"]
        choose(ini, target, memory, packs)
    elif ini.has("shaderpack"):
        ini.set("shaderpack", "0")
    return selection(ini, packs)


def options_of(ini: nini.IniText, name: str, memory: Memory, packs: list[dict]) -> dict:
    """The profile and options of a pack: nimby3d.ini's for the pack chosen there, the memory's for the others."""
    cur = selection(ini, packs)
    if _same(cur["owner"], name):
        return {"profile": cur["profile"], "options": parse_options(cur["options"]), "source": "ini"}
    saved = memory.get(name) or {}
    return {"profile": saved.get("profile", ""), "options": parse_options(saved.get("options", "")), "source": "memory" if saved else "none"}


def save_options(ini: nini.IniText, name: str, profile, options: dict, memory: Memory, packs: list[dict]) -> dict:
    """A pack's profile and the options that differ from its defaults: into nimby3d.ini when it is the pack chosen
    there, and into the memory (always)."""
    name = _pack_name(packs, name)
    profile = check_profile(profile)
    if not isinstance(options, dict):
        raise PackError("bad_option", "options must be NAME -> VALUE")
    text = format_options({str(k): str(v) for k, v in options.items()})
    memory.put(name, profile, text)
    cur = selection(ini, packs)
    in_ini = _same(cur["owner"], name)
    if in_ini:
        if not cur["file"]:
            ini.set("shaderpack_file", name)
        ini.set("shaderpack_profile", profile or None)
        ini.set("shaderpack_options", text or None)
    return {"name": name, "profile": profile, "options": text, "in_ini": in_ini}
