"""Install or remove the nimby3d add-on in the NIMBY Rails folder.

Usage:
  python install.py install [<save.nimbyrails5>]   the add-on and the save's data; without a save: the newest one in the game's save folder
  python install.py refresh [<save.nimbyrails5>]   only the save's data (stations, track, platforms, signals); the running game reads it within a few seconds
  python install.py watch                          refresh whenever the game writes a save (an autosave too), until stopped with Ctrl+C
  python install.py remove [--purge]               --purge also deletes the add-on's settings and what it learnt (nimby3d.ini, nimby3d_units.txt, nimby3d_dumps ...)
  python install.py disable                        keep the files but start the game without ReShade and the add-on (the game must be closed)
  python install.py enable                         undo disable (takes effect the next time the game starts)
  python install.py avatar <model.vrm> | --clear   put a VRM model of your own in the game folder as the player's figure, or take it out
  python install.py status                         what is installed where, as JSON

What the add-on takes from the save: where the stations and the track are (to find out where
the view is), platforms and signals, and the track beyond what the game has on screen. The
track on screen it reads from the game itself, so newly built track shows without a refresh;
its platforms and signals come with the next refresh.

Install adds exactly these files to the game folder and records them in nimby3d_install.json:
  dxgi.dll (ReShade 6.8.0 add-on build), ReShade.ini, nimby3d.addon64,
  nimby3d_data.bin (stations and track nodes from the save), nimby3d_tracks.bin (the track
  graph with each node's level: ground, tunnel or viaduct; the platforms of every station; the
  signals with the direction they face), nimby3d_dem.bin (elevation tiles
  around the network, copied out of the game's own dem400.pmtiles), nimby3d_shaders.bin (the
  add-on's shaders already compiled, from the last replay-host run, merged with those the game
  has kept: so the game does not spend half a minute compiling them before its first picture),
  the folder nimby3d_ambient (the traffic's and the boats' own 3D models, assets/ambient_vehicles:
  manifest.json and the GLB files it lists), and nimby3d_textures.bin (the surfaces' textures and the
  rooms seen through windows: CC0 materials of ambientCG and indoor panoramas of Poly Haven, made by
  tools/make_textures.py), and nimby3d_avatar.vrm (the player's figure: a VRM model of the player's own,
  chosen in the manager or given by N3D_AVATAR; never part of the package)

Install works while the game is running: the add-on the game has loaded is renamed aside and
the new one put in its place, so the change takes effect the next time the game starts.
Remove needs the game closed. It deletes the files above plus the logs ReShade and the add-on
write next to them. Game files and saves are never touched, and a dxgi.dll this tool did not
install is never overwritten.

Safety rules the code keeps (the install record, nimby3d_install.json, is the proof):
  - dxgi.dll is only overwritten, disabled or deleted when its SHA-256 is one this tool put there.
  - ReShade.ini is written whole only when it is absent, or when the tool wrote it and it is
    unchanged since; otherwise only the keys the add-on needs and the file lacks are added, and
    remove takes back only those keys. ReShade's own logs and ReShadePreset.ini are deleted only
    when they were not there before the first install and the ReShade being removed is this tool's.
  - The save's data is exported into scratch files first; nothing in the game folder changes when
    the save cannot be read. Every file is recorded in the install record as soon as it is put.
  - A file the game holds open is renamed aside as <name>.old<N> (the first free N), recorded,
    and deleted by the next install, enable or remove that finds it free.

Where things are found, in order: an explicit argument, then environment variables, then a
payload/ folder next to the manager (manager/payload, or N3D_PAYLOAD), then the developer's
own locations (build/, and the folder tools beside the project's parent folder). A released package
(the file .nimby3d-package.json next to Nimby3D.cmd) and N3D_NO_DEV=1 never use the developer's
locations. Environment variables:
  N3D_GAME_DIR      the game folder (default: found through Steam's library folders)
  N3D_SAVES_DIR     the folder with the saves (default: Saved Games/Weird and Wry/NIMBY Rails)
  N3D_TOOLS         the developer's tools folder (default: ../../tools from tools/install.py)
  N3D_NO_DEV        1: only arguments, environment variables and the payload folder; no developer locations
  N3D_PAYLOAD       the payload folder
  N3D_ADDON, N3D_RESHADE, N3D_TEXTURES, N3D_LANDCOVER, N3D_LANDCOVER_OVERVIEW, N3D_AMBIENT,
  N3D_SHADER_CACHE, N3D_AVATAR, N3D_DEM, N3D_SHOTS   single files or folders
  N3D_STATE_DIR     where the manager keeps its settings (default %LOCALAPPDATA%/Nimby3D)
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

GAME_EXE = "NimbyRails.exe"
STEAM_APPID = "1134710"
DEV_TOOLS = PROJECT.parents[1] / "tools"  # the developer's tools folder, beside the project's parent folder
PACKAGE_MARKER = ".nimby3d-package.json"  # written by tools/package_release.py into a released package
MANIFEST_NAME = "nimby3d_install.json"
AMBIENT_DIR = "nimby3d_ambient"
AVATAR_NAME = "nimby3d_avatar.vrm"
DISABLED_SUFFIX = ".nimby3d-disabled"
NEW_SUFFIX = ".nimby3d-new"
TMP_PREFIX = "nimby3d_tmp_"
LANDCOVER_TIF_NAME = "PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif"

# what the first versions of this tool put into the game folder (an install record of theirs lists only three)
INSTALLED = ["dxgi.dll", "ReShade.ini", "nimby3d.addon64", "nimby3d_data.bin", "nimby3d_dem.bin", "nimby3d_tracks.bin", "nimby3d_shaders.bin", MANIFEST_NAME,
             "nimby3d_landcover.tif", "nimby3d_landcover.bin", "nimby3d_textures.bin", AVATAR_NAME]
# written by ReShade itself next to its dll
RESHADE_GENERATED = ["ReShade.log", "ReShade.log1", "ReShade.log2", "ReShadePreset.ini"]
# written by the add-on while the game runs
ADDON_LOGS = ["nimby3d_probe.log"]
GENERATED = RESHADE_GENERATED + ADDON_LOGS
# the add-on's settings and what it learns or the player writes for it: kept unless asked (remove --purge)
USER_DATA = ["nimby3d.ini", "nimby3d_units.txt", "nimby3d_stations.txt", "nimby3d_vehicles.txt", "nimby3d_dumps"]
# other dlls that load a ReShade (or another injector) into a D3D11 game
OTHER_PROXIES = ["d3d11.dll", "d3d12.dll", "dxgi.dll", "opengl32.dll", "dinput8.dll", "d3d9.dll", "version.dll", "winmm.dll"]
DATA_FILES = ["nimby3d_data.bin", "nimby3d_tracks.bin", "nimby3d_dem.bin"]


# ---------------------------------------------------------------- messages and errors

class Msg(str):
    """A log line: English text for the console, plus a key and values the manager words in its own languages."""
    key: str
    params: dict

    def __new__(cls, key: str, text: str, **params):
        params = {k: (str(v) if isinstance(v, Path) else v) for k, v in params.items()}
        self = str.__new__(cls, text.format(**params) if params else text)
        self.key = key
        self.params = params
        return self


class InstallError(Exception):
    """A refusal or failure with a code the manager can word; str() is the English text."""

    def __init__(self, code: str, text: str, **params):
        params = {k: (str(v) if isinstance(v, Path) else v) for k, v in params.items()}
        super().__init__(text.format(**params) if params else text)
        self.code = code
        self.params = params


def _noop(*_a, **_k):
    pass


class _Steps:
    """progress(fraction, step) when given; the CLI passes none."""

    def __init__(self, progress):
        self.progress = progress or _noop

    def __call__(self, fraction: float, step: str):
        with contextlib.suppress(Exception):
            self.progress(max(0.0, min(1.0, fraction)), step)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- hashing

_SHA_CACHE: dict[tuple, str] = {}
_SHA_LOCK = threading.Lock()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ident(path: Path) -> tuple[int, int] | None:
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def sha_cached(path: Path) -> str:
    """SHA-256 of a file, remembered for as long as its size and modification time stay the same."""
    ident = _ident(path)
    if ident is None:
        raise FileNotFoundError(str(path))
    key = (os.path.normcase(str(path)),) + ident
    with _SHA_LOCK:
        if key in _SHA_CACHE:
            return _SHA_CACHE[key]
    value = sha(path)
    with _SHA_LOCK:
        if len(_SHA_CACHE) > 512:
            _SHA_CACHE.clear()
        _SHA_CACHE[key] = value
    return value


# ---------------------------------------------------------------- where things are

def state_dir() -> Path:
    env = os.environ.get("N3D_STATE_DIR")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Nimby3D"


def dev_allowed() -> bool:
    """May the developer's own locations be used? Not in a released package, and not with N3D_NO_DEV=1."""
    return not os.environ.get("N3D_NO_DEV") and not (PROJECT / PACKAGE_MARKER).exists()


def tools_dir() -> Path:
    return Path(os.environ.get("N3D_TOOLS") or DEV_TOOLS)


def payload_dir() -> Path:
    return Path(os.environ.get("N3D_PAYLOAD") or (PROJECT / "manager" / "payload"))


def _dev_shots() -> Path | None:
    if not dev_allowed():
        return None
    t = tools_dir()
    return t / "captures" / "shots" if t.is_dir() else None


# name -> (environment variable, name in the payload folder, the developer's location)
SOURCES = {
    "addon": ("N3D_ADDON", "nimby3d.addon64", lambda: PROJECT / "build" / "nimby3d.addon64"),
    "reshade": ("N3D_RESHADE", "ReShade64.dll", lambda: tools_dir() / "reshade" / "ReShade64.dll"),
    "shader_cache": ("N3D_SHADER_CACHE", "nimby3d_shaders.bin", lambda: PROJECT / "build" / "replay" / "nimby3d_shaders.bin"),
    "textures": ("N3D_TEXTURES", "nimby3d_textures.bin", lambda: PROJECT / "build" / "nimby3d_textures.bin"),
    # the global land cover map (Copernicus CGLS-LC100 2019, CC BY 4.0) and the overview tools/make_landcover.cpp makes of it
    "landcover": ("N3D_LANDCOVER", "nimby3d_landcover.tif", lambda: tools_dir() / "landcover" / LANDCOVER_TIF_NAME),
    "landcover_overview": ("N3D_LANDCOVER_OVERVIEW", "nimby3d_landcover.bin", lambda: PROJECT / "build" / "nimby3d_landcover.bin"),
    # the traffic's and the boats' own models (made by tools/make_ambient_models.py), copied as nimby3d_ambient
    "ambient": ("N3D_AMBIENT", "ambient_vehicles", lambda: PROJECT / "assets" / "ambient_vehicles"),
    # the player's figure: a VRM model of the player's own, kept on this machine (never in the toolkit)
    "avatar": ("N3D_AVATAR", "nimby3d_avatar.vrm", lambda: tools_dir() / "avatar" / "Model.vrm"),
}


def source(name: str, sources: dict | None = None) -> tuple[Path | None, str]:
    """Where a file to install comes from, and how that was decided: argument, env, payload or dev."""
    env, payload_name, dev = SOURCES[name]
    if sources and sources.get(name):
        return Path(sources[name]), "argument"
    if os.environ.get(env):
        return Path(os.environ[env]), "env"
    p = payload_dir() / payload_name
    if p.exists():
        return p, "payload"
    if dev_allowed():
        d = dev()
        if d.exists():
            return d, "dev"
    return None, "none"


def shots_dir() -> Path | None:
    """ReShade's screenshot folder: N3D_SHOTS, or the developer's captures folder; else ReShade's own default."""
    if os.environ.get("N3D_SHOTS"):
        return Path(os.environ["N3D_SHOTS"])
    return _dev_shots()


def steam_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                     (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                     (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(Path(str(winreg.QueryValueEx(k, value)[0])))
                except OSError:
                    pass
        except ImportError:
            pass
    else:
        roots += [Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"]
    return _unique(r for r in roots if r.is_dir())


def _unique(paths) -> list[Path]:
    out, seen = [], set()
    for p in paths:
        try:
            key = os.path.normcase(str(Path(p).resolve()))
        except OSError:
            key = os.path.normcase(str(p))
        if key not in seen:
            seen.add(key)
            out.append(Path(p))
    return out


def steam_libraries() -> list[Path]:
    """Every Steam library: the Steam folders from the registry and each path in their libraryfolders.vdf."""
    libs: list[Path] = []
    for root in steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text("utf-8", errors="replace")
        except OSError:
            continue
        for p in re.findall(r'"path"\s+"([^"]+)"', text):
            libs.append(Path(p.replace("\\\\", "\\")))
    return _unique(l for l in libs if l.is_dir())


def _installdir(lib: Path) -> str:
    acf = lib / "steamapps" / f"appmanifest_{STEAM_APPID}.acf"
    with contextlib.suppress(OSError):
        m = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text("utf-8", errors="replace"))
        if m:
            return m.group(1)
    return "NIMBY Rails"


def game_folder_from(path) -> Path | None:
    """The game folder for a folder someone picked: the folder itself, or the game inside a Steam library they picked."""
    p = Path(path)
    for cand in (p, p / "NIMBY Rails", p / "common" / "NIMBY Rails", p / "steamapps" / "common" / "NIMBY Rails"):
        if (cand / GAME_EXE).is_file():
            return cand
    return None


def find_game(explicit=None, how: str = "argument") -> dict:
    """The game folder: explicit → N3D_GAME_DIR → Steam libraries.
    An explicit folder or N3D_GAME_DIR that is not a game folder is reported as such and never
    replaced by another one."""
    if explicit:
        p = game_folder_from(explicit)
        return {"dir": str(p or Path(explicit)), "how": how, "valid": p is not None}
    if os.environ.get("N3D_GAME_DIR"):
        e = Path(os.environ["N3D_GAME_DIR"])
        p = game_folder_from(e)
        return {"dir": str(p or e), "how": "env", "valid": p is not None}
    for lib in steam_libraries():
        cand = lib / "steamapps" / "common" / _installdir(lib)
        if (cand / GAME_EXE).is_file():
            return {"dir": str(cand), "how": "steam", "valid": True}
    return {"dir": None, "how": None, "valid": False}


def resolve_game(game=None) -> Path:
    found = find_game(game)
    if not found["valid"]:
        if found["dir"]:
            raise InstallError("game_not_found", "game not found at {dir}", dir=found["dir"])
        raise InstallError("game_not_found_anywhere", "NIMBY Rails was not found in any Steam library; give its folder (N3D_GAME_DIR)")
    return Path(found["dir"])


def _known_saved_games() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        fid = GUID(0x4C5C32FF, 0xBB9D, 0x43B0, (ctypes.c_ubyte * 8)(0xB5, 0xB4, 0x2D, 0x72, 0xE5, 0x4E, 0xAA, 0xA4))
        ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(ptr)) == 0 and ptr.value:
            p = Path(ptr.value)
            ctypes.windll.ole32.CoTaskMemFree(ptr)
            return p
    except Exception:
        return None
    return None


def save_dir_candidates() -> list[Path]:
    tail = ("Weird and Wry", "NIMBY Rails")
    cands = []
    known = _known_saved_games()
    if known:
        cands.append(known.joinpath(*tail))
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    cands += [home.joinpath("Saved Games", *tail), home.joinpath("OneDrive", "Saved Games", *tail), home.joinpath("Documents", "Saved Games", *tail)]
    return _unique(cands)


def find_saves(explicit=None) -> Path | None:
    """The folder with the saves: explicit → N3D_SAVES_DIR (or the toolkit's NIMBY_SAVE_DIR) → Saved Games."""
    if explicit:
        return Path(explicit)
    for env in ("N3D_SAVES_DIR", "NIMBY_SAVE_DIR"):
        if os.environ.get(env):
            return Path(os.environ[env])
    cands = save_dir_candidates()
    for c in cands:
        with contextlib.suppress(OSError):
            if c.is_dir() and any(c.glob("*.nimbyrails5")):
                return c
    for c in cands:
        if c.is_dir():
            return c
    return cands[0] if cands else None


# kept for the original callers
SAVES = find_saves()


def list_saves(saves_dir=None) -> list[Path]:
    d = find_saves(saves_dir)
    if not d or not d.is_dir():
        return []
    out = []
    for p in d.glob("*.nimbyrails5"):
        with contextlib.suppress(OSError):
            out.append((p.stat().st_mtime, p))
    return [p for _, p in sorted(out)]


def newest_save(saves_dir=None) -> Path:
    saves = list_saves(saves_dir)
    if not saves:
        raise InstallError("no_saves", "no saves in {dir}", dir=str(find_saves(saves_dir)))
    return saves[-1]


# ---------------------------------------------------------------- processes

def _processes(image: str) -> list[tuple[int, str | None]]:
    """(pid, full path or None) of the running processes with this file name."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        raise OSError("no process snapshot")
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == image.lower():
                path = None
                h = k32.OpenProcess(0x1000, False, e.th32ProcessID)  # PROCESS_QUERY_LIMITED_INFORMATION
                if h:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        path = buf.value
                    k32.CloseHandle(h)
                out.append((int(e.th32ProcessID), path))
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return out


def game_running(game=None) -> bool:
    """Is NIMBY Rails running — from this game folder when one is given (a game whose path cannot be read counts)."""
    try:
        procs = _processes(GAME_EXE)
    except Exception:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return GAME_EXE.lower() in out.lower()
    if game is None:
        return bool(procs)
    want = os.path.normcase(os.path.abspath(str(Path(game) / GAME_EXE)))
    return any(p is None or os.path.normcase(os.path.abspath(p)) == want for _, p in procs)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = wintypes.DWORD()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    except Exception:
        return False


# ---------------------------------------------------------------- the install record

def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + NEW_SUFFIX)
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
                with contextlib.suppress(OSError):
                    tmp.unlink()
                raise
            time.sleep(0.1)


class Manifest:
    """nimby3d_install.json. "files" stays name -> SHA-256 as the first versions wrote it; the rest is
    new: "meta" (size, time, kind, where it came from), "history" (every SHA this tool put under a
    name), "aside" (renamed-aside copies), "disabled", "reshade_ini", "preexisting", "avatar"."""

    def __init__(self, game: Path):
        self.game = Path(game)
        self.path = self.game / MANIFEST_NAME
        self.exists = self.path.exists()
        self.data: dict = {}
        for attempt in range(3) if self.exists else ():
            try:  # another process may be replacing it right now
                self.data = json.loads(self.path.read_text("utf-8"))
                break
            except (OSError, ValueError):
                time.sleep(0.05)
        # a record of the first versions (no "format"; "files" name -> sha), or one migrated from it: those versions
        # wrote ReShade.ini whole and put every file of INSTALLED there. A record that cannot be read proves nothing.
        old_format = "format" not in self.data and isinstance(self.data.get("files"), dict) and bool(self.data.get("files"))
        self.legacy = self.exists and (old_format or bool(self.data.get("legacy")))
        if self.legacy:
            self.data["legacy"] = True
        self.data.setdefault("files", {})
        for key in ("meta", "history"):
            self.data.setdefault(key, {})
        self.data.setdefault("aside", [])
        for name, v in list(self.data["files"].items()):  # first versions: name -> sha
            if isinstance(v, dict):
                self.data["files"][name] = v.get("sha")
        for name, v in self.data["files"].items():
            if v and v not in self.data["history"].setdefault(name, []):
                self.data["history"][name].append(v)

    @property
    def files(self) -> dict:
        return self.data["files"]

    def save(self) -> None:
        self.data["format"] = 2
        self.data["tool"] = "nimby3d tools/install.py"
        self.data["updated"] = _now()
        _write_atomic(self.path, json.dumps(self.data, indent=1, ensure_ascii=False).encode("utf-8"))
        self.exists = True

    def intend(self, name: str, digest: str) -> None:
        """Before a file is put: its SHA goes into the history, so a crash right after still proves it ours."""
        h = self.data["history"].setdefault(name, [])
        if digest not in h:
            h.append(digest)
            del h[:-16]
            self.save()

    def record(self, name: str, path: Path, kind: str, digest: str | None = None, src: Path | None = None) -> None:
        unblock(path)
        digest = digest or sha_cached(path)
        st = path.stat()
        meta = {"sha": digest, "size": st.st_size, "mtime_ns": st.st_mtime_ns, "kind": kind}
        if src is not None:
            s = src.stat()
            meta["src"] = {"path": str(src), "size": s.st_size, "mtime_ns": s.st_mtime_ns}
        self.data["files"][name] = digest
        self.data["meta"][name] = meta
        h = self.data["history"].setdefault(name, [])
        if digest not in h:
            h.append(digest)
            del h[:-16]
        self.save()

    def forget(self, name: str, save: bool = True) -> None:
        self.data["files"].pop(name, None)
        self.data["meta"].pop(name, None)
        if save:
            self.save()

    def known(self, name: str) -> set:
        out = set(self.data["history"].get(name, []))
        if self.data["files"].get(name):
            out.add(self.data["files"][name])
        return out

    def current_sha(self, name: str, path: Path) -> str | None:
        """The SHA of a file in the game folder, taken from the record while its size and time are the recorded ones."""
        ident = _ident(path)
        if ident is None:
            return None
        meta = self.data["meta"].get(name)
        if meta and (meta.get("size"), meta.get("mtime_ns")) == ident and meta.get("sha"):
            return meta["sha"]
        return sha_cached(path)

    def is_ours(self, name: str, path: Path) -> bool:
        """The file is byte for byte one this tool put under this name."""
        if not path.exists():
            return False
        known = self.known(name)
        return bool(known) and self.current_sha(name, path) in known

    def add_aside(self, name: str) -> None:
        if name not in self.data["aside"]:
            self.data["aside"].append(name)
        self.save()


# ---------------------------------------------------------------- putting files

def unblock(path: Path) -> bool:
    """Take the Mark of the Web (the Zone.Identifier stream a downloaded file carries) off a file put into the
    game folder, as Windows' "Unblock" does. Copies made here do not carry it; this is for certain."""
    if os.name != "nt":
        return False
    try:
        os.remove(str(path) + ":Zone.Identifier")
        return True
    except OSError:
        return False


def _copy(src: Path, dst: Path, step=None, lo=0.0, hi=0.0, label="") -> None:
    """Copy in 4 MB blocks, reporting progress for large files."""
    total = max(1, src.stat().st_size)
    done = 0
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            b = fi.read(4 << 20)
            if not b:
                break
            fo.write(b)
            done += len(b)
            if step and total > (32 << 20):
                step(lo + (hi - lo) * done / total, label)
    shutil.copystat(src, dst)


def free_aside(game: Path, name: str) -> Path:
    """<name>.old<N> with the first N not taken."""
    n = 0
    while (game / f"{name}.old{n}").exists():
        n += 1
    return game / f"{name}.old{n}"


def _place(game: Path, man: Manifest, new: Path, name: str) -> str:
    """Move a finished scratch file into place: atomically, or, when the game holds the old one,
    by renaming that one aside first (allowed for a loaded module; the game keeps using it)."""
    dst = game / name
    for attempt in range(4):  # a reader that holds it for a moment; a loaded module stays held
        try:
            os.replace(new, dst)
            return "copied"
        except PermissionError:
            if not dst.exists():
                raise
            if attempt < 3:
                time.sleep(0.05 * (2 ** attempt))
    aside = free_aside(game, name)
    try:
        dst.rename(aside)
    except OSError:
        with contextlib.suppress(OSError):
            new.unlink()
        raise InstallError("in_use", "{name} is in use and cannot be replaced; close the game and try again", name=name)
    man.add_aside(aside.name)
    os.replace(new, dst)
    return "staged"


def put(game: Path, man: Manifest, src: Path, name: str, kind: str, step=None, lo=0.0, hi=0.0) -> str:
    """Copy `src` to the game folder as `name` and record it. A file the game holds open is renamed aside first."""
    dst = game / name
    digest = sha_cached(src)
    if dst.exists() and man.current_sha(name, dst) == digest:
        man.record(name, dst, kind, digest, src)
        return "unchanged"
    man.intend(name, digest)
    new = game / (name + NEW_SUFFIX)
    _copy(src, new, step, lo, hi, kind)
    result = _place(game, man, new, name)
    man.record(name, dst, kind, digest, src)
    return result


def put_large(game: Path, man: Manifest, src: Path | None, name: str, running: bool, kind: str = "asset", step=None, lo=0.0, hi=0.0) -> str:
    """A large data file. Unchanged when the record says the copy in the game folder (same size and
    time) came from this same source (same size and time), or when the SHA-256 of both agree. The
    game reads these while it runs: an existing one is not replaced then."""
    dst = game / name
    if src is None or not src.exists():
        return "not made"
    meta = man.data["meta"].get(name) or {}
    ident_dst, ident_src = _ident(dst), _ident(src)
    if (dst.exists() and meta.get("src") and ident_dst == (meta.get("size"), meta.get("mtime_ns"))
            and (meta["src"].get("size"), meta["src"].get("mtime_ns")) == ident_src
            and os.path.normcase(meta["src"].get("path", "")) == os.path.normcase(str(src))):
        return "unchanged"
    digest = sha_cached(src)
    if dst.exists() and man.current_sha(name, dst) == digest:
        man.record(name, dst, kind, digest, src)
        return "unchanged"
    if running and dst.exists():
        return "not copied while the game runs"
    man.intend(name, digest)
    new = game / (name + NEW_SUFFIX)
    _copy(src, new, step, lo, hi, kind)
    result = _place(game, man, new, name)
    man.record(name, dst, kind, digest, src)
    return "copied" if result == "copied" else result


def put_ambient(game: Path, man: Manifest, ambient: Path | None, running: bool) -> str:
    """The traffic's and the boats' models: manifest.json and the files it lists, into nimby3d_ambient.
    The add-on reads them once, when it first draws them: a changed pack while the game runs is
    copied all the same and read at the next start."""
    if ambient is None or not (ambient / "manifest.json").exists():
        return "not there (assets/ambient_vehicles)"
    man_file = ambient / "manifest.json"
    names = ["manifest.json"] + [lod["file"] for m in json.loads(man_file.read_text(encoding="utf-8"))["models"] for lod in m["lods"]]
    dst = game / AMBIENT_DIR
    dst.mkdir(exist_ok=True)
    copied = busy = 0
    for n in names:
        if "/" in n or "\\" in n or n.startswith("."):
            continue  # only plain file names inside the folder
        src, out = ambient / n, dst / n
        key = f"{AMBIENT_DIR}/{n}"
        digest = sha_cached(src)
        if out.exists() and man.current_sha(key, out) == digest:
            if man.files.get(key) != digest:
                man.record(key, out, "ambient", digest, src)
            continue
        man.intend(key, digest)
        tmp = dst / (n + NEW_SUFFIX)
        _copy(src, tmp)
        try:
            os.replace(tmp, out)
        except PermissionError:
            with contextlib.suppress(OSError):
                tmp.unlink()
            busy += 1
            continue
        man.record(key, out, "ambient", digest, src)
        copied += 1
    note = f", {busy} in use (next time)" if busy else ""
    return f"{copied} of {len(names)} files copied{note}" if copied or busy else f"unchanged ({len(names)} files)"


def read_shaders(path: Path) -> dict:
    """The compiled shaders in a cache file of the add-on: key -> bytes ("N3DS", u32 n, then u64 key, u32 size, bytes)."""
    out = {}
    if not path.exists():
        return out
    d = path.read_bytes()
    if d[:4] != b"N3DS":
        return out
    n = int.from_bytes(d[4:8], "little")
    at = 8
    for _ in range(n):
        if at + 12 > len(d):
            break
        key = int.from_bytes(d[at:at + 8], "little")
        size = int.from_bytes(d[at + 8:at + 12], "little")
        out[key] = d[at + 12:at + 12 + size]
        at += 12 + size
    return out


def merge_shaders(game: Path, man: Manifest, cache: Path | None) -> str:
    """The replay host's compiled shaders and the game's own, together (keys are hashes of the source)."""
    if cache is None or not cache.exists():
        return "none compiled yet (run a replay first)"
    dst = game / "nimby3d_shaders.bin"
    have = read_shaders(dst)
    new = read_shaders(cache)
    merged = {**have, **new}
    if merged == have and dst.exists():
        if "nimby3d_shaders.bin" not in man.files:
            man.record("nimby3d_shaders.bin", dst, "cache")
        return f"unchanged ({len(have)} shaders)"
    blob = b"N3DS" + len(merged).to_bytes(4, "little") + b"".join(k.to_bytes(8, "little") + len(v).to_bytes(4, "little") + v for k, v in merged.items())
    tmp = game / ("nimby3d_shaders.bin" + NEW_SUFFIX)
    tmp.write_bytes(blob)
    _place(game, man, tmp, "nimby3d_shaders.bin")
    man.record("nimby3d_shaders.bin", dst, "cache")
    return f"{len(new)} from the replay host, {len(merged)} in all"


# ---------------------------------------------------------------- ReShade.ini

def reshade_keys(shots: Path | None) -> list[list[str]]:
    """What the add-on wants of ReShade: Home would open ReShade's own menu; move that to Shift+F2 so it is not hit by accident."""
    keys = [["GENERAL", "NoReloadOnInit", "1"], ["INPUT", "KeyOverlay", "113,0,1,0"],
            ["OVERLAY", "TutorialProgress", "4"], ["OVERLAY", "ShowClock", "0"], ["OVERLAY", "ShowFPS", "0"]]
    if shots:
        keys.append(["SCREENSHOT", "SavePath", str(shots)])
    keys.append(["SCREENSHOT", "FileFormat", "1"])
    return keys


def render_ini(keys) -> str:
    sections: dict[str, list[str]] = {}
    for sec, key, val in keys:
        sections.setdefault(sec, []).append(f"{key}={val}")
    return "\n".join(f"[{s}]\n" + "\n".join(lines) + "\n" for s, lines in sections.items())


def _find_section(lines: list[str], name: str) -> tuple[int | None, int | None]:
    start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if start is not None:
                return start, i
            if s[1:-1].strip().lower() == name.lower():
                start = i
    return (start, len(lines)) if start is not None else (None, None)


def _ini_get(lines: list[str], sec: str, key: str):
    a, b = _find_section(lines, sec)
    if a is None:
        return None
    for i in range(a + 1, b):
        k, sep, v = lines[i].partition("=")
        if sep and k.strip().lower() == key.lower():
            return i, v.strip()
    return None


def _ini_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw[3 if bom else 0:].decode("utf-8", errors="surrogateescape"), bom


def _ini_bytes(text: str, bom: bool) -> bytes:
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8", errors="surrogateescape")


def _ini_lines(text: str) -> tuple[list[str], str]:
    """Lines split at line ends only (str.splitlines would also split at form feeds and the like), and the line end used."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines, nl


def ini_merge_missing(text: str, keys) -> tuple[str, list, list]:
    """Add the keys the file lacks, keeping everything else as it is. Returns (text, keys added, sections added)."""
    lines, nl = _ini_lines(text)
    added, new_sections = [], []
    for sec, key, val in keys:
        if _ini_get(lines, sec, key) is not None:
            continue
        a, b = _find_section(lines, sec)
        if a is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines += [f"[{sec}]", f"{key}={val}"]
            new_sections.append(sec)
        else:
            j = b
            while j - 1 > a and not lines[j - 1].strip():
                j -= 1
            lines.insert(j, f"{key}={val}")
        added.append([sec, key, val])
    return nl.join(lines) + nl, added, new_sections


def ini_strip(text: str, added, sections) -> str:
    """Take back the keys this tool added that still hold its value, and the sections it added if they are empty now
    (with the blank line put before them)."""
    lines, nl = _ini_lines(text)
    for sec, key, val in added:
        hit = _ini_get(lines, sec, key)
        if hit and hit[1] == val:
            del lines[hit[0]]
    for sec in sections:
        a, b = _find_section(lines, sec)
        if a is not None and all(not l.strip() for l in lines[a + 1:b]):
            del lines[a:b]
            if a > 0 and not lines[a - 1].strip():
                del lines[a - 1]
    return nl.join(lines) + nl if lines else ""


def put_reshade_ini(game: Path, man: Manifest, running: bool) -> str:
    ini = game / "ReShade.ini"
    keys = reshade_keys(shots_dir())
    wanted = render_ini(keys)
    rec = man.data.get("reshade_ini") or ({"mode": "legacy"} if man.legacy else None)
    if not ini.exists():
        _write_atomic(ini, wanted.encode("utf-8"))
        man.data["reshade_ini"] = {"mode": "created", "sha": sha(ini), "added": keys, "sections": []}
        man.save()
        return "written"
    if running:  # ReShade rewrites its ini when the game exits
        if rec is None:
            man.data["reshade_ini"] = {"mode": "foreign", "sha": sha(ini), "added": [], "sections": []}
            man.save()
        return "left as it is while the game runs"
    if rec and rec.get("mode") == "created" and rec.get("sha") == sha(ini):
        if ini.read_text("utf-8", errors="replace") == wanted:
            return "unchanged"
        _write_atomic(ini, wanted.encode("utf-8"))
        rec.update({"sha": sha(ini), "added": keys})
        man.save()
        return "updated"
    # someone's own settings, or ReShade's after the game ran: add only what is missing
    text, bom = _ini_text(ini)
    merged, added, sections = ini_merge_missing(text, keys)
    mode = rec["mode"] if rec and rec.get("mode") in ("created", "legacy") else "merged"
    rec = dict(rec or {})
    rec["mode"] = mode
    rec["added"] = [k for k in (rec.get("added") or []) if k not in added] + added if mode == "merged" else (rec.get("added") or keys)
    rec["sections"] = list(dict.fromkeys((rec.get("sections") or []) + sections))
    if added:
        _write_atomic(ini, _ini_bytes(merged, bom))
    rec["sha"] = sha(ini)
    man.data["reshade_ini"] = rec
    man.save()
    return f"kept your settings, added {len(added)} the add-on needs" if added else "kept as it is (it has what the add-on needs)"


# ---------------------------------------------------------------- the save's data

def _exporters():
    from export_data import export, export_dem, export_tracks
    return export, export_dem, export_tracks


def dem_path(game: Path) -> Path | None:
    if os.environ.get("N3D_DEM"):
        return Path(os.environ["N3D_DEM"])
    p = game / "resources" / "maps" / "dem400.pmtiles"
    return p if p.is_file() else None


def _scratch(game: Path) -> Path:
    return Path(tempfile.mkdtemp(prefix=TMP_PREFIX, dir=str(game)))


def _clean_scratch(game: Path, older_than: float = 3600.0) -> None:
    now = time.time()
    for p in game.glob(TMP_PREFIX + "*"):
        with contextlib.suppress(OSError):
            if now - p.stat().st_mtime > older_than:
                shutil.rmtree(p, ignore_errors=True)
    for p in game.glob("*" + NEW_SUFFIX):
        with contextlib.suppress(OSError):
            if now - p.stat().st_mtime > older_than:
                p.unlink()


def export_save(save: Path, scratch: Path, game: Path, step, log, dem: bool = True) -> dict:
    """The save's data into scratch files (nothing in the game folder changes here)."""
    export, export_dem, export_tracks = _exporters()
    info: dict = {"files": []}
    try:
        step(0.08, "export_data")
        ns, nn = export(save, scratch / "nimby3d_data.bin")
        info.update(stations=ns, nodes=nn)
        info["files"].append("nimby3d_data.bin")
        step(0.18, "export_tracks")
        tr = export_tracks(save, scratch / "nimby3d_tracks.bin")
        info.update(tracks=tr)
        info["files"].append("nimby3d_tracks.bin")
        if dem:
            step(0.28, "export_dem")
            d = dem_path(game)
            if d is None:
                log(Msg("no_dem", "no elevation file in the game folder (resources/maps/dem400.pmtiles): nimby3d_dem.bin left as it is"))
            else:
                info["dem_tiles"] = export_dem(save, scratch / "nimby3d_dem.bin", dem=d)
                info["files"].append("nimby3d_dem.bin")
    except InstallError:
        raise
    except Exception as ex:
        raise InstallError("export_failed", "could not read the save {name}: {error}", name=save.name, error=f"{type(ex).__name__}: {ex}") from ex
    return info


def _place_exports(game: Path, man: Manifest, scratch: Path, info: dict) -> list[tuple[str, str]]:
    results = []
    for name in info["files"]:
        results.append((name, _place(game, man, scratch / name, name)))
        man.record(name, game / name, "data")
    return results


def _not_made(hint: str) -> str:
    """A file this install has no source for: the developer is told how to make it; a package just lacks it."""
    return f"not made ({hint})" if dev_allowed() else "not included"


def _put_msg(name: str, result: str) -> Msg:
    return Msg("put", "{name}: {result}", name=name, result=result)


def _save_info(man: Manifest, save: Path, info: dict) -> None:
    st = save.stat()
    man.data.update({"save": str(save), "save_mtime": st.st_mtime, "exported_at": _now(), "stations": info.get("stations"), "nodes": info.get("nodes")})
    tr = info.get("tracks") or {}
    for k in ("platforms", "signals", "special"):
        if k in tr:
            man.data[k] = tr[k]
    if "dem_tiles" in info:
        man.data["dem_tiles"] = info["dem_tiles"]
    man.save()


def _data_line(save: Path, info: dict) -> Msg:
    tr = info.get("tracks") or {}
    return Msg("data_from", "data from {save}: {stations} stations, {nodes} track nodes ({special} of {all} on viaducts or in tunnels), "
               "{platforms} platforms, {signals} signals, {dem} elevation tiles",
               save=save.name, stations=info.get("stations"), nodes=info.get("nodes"), special=tr.get("special", 0), all=tr.get("nodes", 0),
               platforms=tr.get("platforms", 0), signals=tr.get("signals", 0), dem=info.get("dem_tiles", "no"))


# ---------------------------------------------------------------- cleaning up after earlier installs

def _ours_by_name(name: str) -> bool:
    return name.lower().startswith("nimby3d")


def _aside_candidates(game: Path, man: Manifest) -> list[Path]:
    """Renamed-aside copies this tool made: those recorded, those of the add-on, and dxgi.dll ones that are byte for byte a ReShade it put."""
    out = []
    for n in man.data.get("aside", []):
        p = game / n
        if p.exists():
            out.append(p)
    for p in game.glob("*.old*"):
        if p in out or not re.fullmatch(r".+\.old\d+", p.name):
            continue
        base = p.name.rsplit(".old", 1)[0]
        if _ours_by_name(base) or (base in man.files or base in man.data["history"]) and man.current_sha(base, p) in man.known(base):
            out.append(p)
    return out


def cleanup_aside(game: Path, man: Manifest, log=_noop) -> list[str]:
    left = []
    for p in _aside_candidates(game, man):
        try:
            p.unlink()
        except OSError:
            left.append(p.name)  # still loaded by a running game
    man.data["aside"] = left
    if man.exists:
        man.save()
    return left


# ---------------------------------------------------------------- install, refresh, watch

def install(game=None, save=None, *, saves_dir=None, sources: dict | None = None, log=print, progress=None) -> dict:
    step = _Steps(progress)
    step(0.0, "prepare")
    game = resolve_game(game)
    addon, _ = source("addon", sources)
    reshade, _ = source("reshade", sources)
    for what, p in (("addon", addon), ("reshade", reshade)):
        if p is None or not p.is_file():
            env, _, dev = SOURCES[what]
            raise InstallError("missing_source", "missing {path}", path=str(p or dev()), what=what)
    save = Path(save) if save else newest_save(saves_dir)
    if not save.is_file():
        raise InstallError("save_missing", "save not found: {path}", path=str(save))
    running = game_running(game)
    man = Manifest(game)
    dxgi = game / "dxgi.dll"
    if dxgi.exists() and not man.is_ours("dxgi.dll", dxgi):
        raise InstallError("foreign_dxgi", "a dxgi.dll that this tool did not install is already in the game folder; not overwriting it")
    _clean_scratch(game)
    step(0.04, "export_data")
    log(Msg("exporting", "reading {save}", save=save.name))
    scratch = _scratch(game)
    try:
        info = export_save(save, scratch, game, step, log)
        # from here on every file is recorded as soon as it is in place
        if not man.exists or "preexisting" not in man.data:
            man.data["preexisting"] = [n for n in RESHADE_GENERATED + ["ReShade.ini"] if (game / n).exists()] if not man.exists else []
            man.data.setdefault("installed_at", _now())
        man.save()
        cleanup_aside(game, man)
        shots = shots_dir()
        if shots:
            with contextlib.suppress(OSError):
                shots.mkdir(parents=True, exist_ok=True)
        results = {}
        step(0.40, "reshade")
        results["dxgi.dll"] = put(game, man, reshade, "dxgi.dll", "reshade")
        log(_put_msg("dxgi.dll", results["dxgi.dll"]))
        step(0.44, "reshade_ini")
        results["ReShade.ini"] = put_reshade_ini(game, man, running)
        log(_put_msg("ReShade.ini", results["ReShade.ini"]))
        step(0.48, "addon")
        results["nimby3d.addon64"] = put(game, man, addon, "nimby3d.addon64", "addon")
        log(_put_msg("nimby3d.addon64", results["nimby3d.addon64"]))
        _drop_disabled(game, man)  # only now that the new ones are in place
        man.save()
        step(0.52, "data")
        for name, r in _place_exports(game, man, scratch, info):
            log(_put_msg(name, r))
        _save_info(man, save, info)
        step(0.58, "shaders")
        results["nimby3d_shaders.bin"] = merge_shaders(game, man, source("shader_cache", sources)[0])
        log(_put_msg("nimby3d_shaders.bin", results["nimby3d_shaders.bin"]))
        step(0.62, "landcover")
        r = put_large(game, man, source("landcover", sources)[0], "nimby3d_landcover.tif", running, "landcover", step, 0.62, 0.74)
        log(_put_msg("nimby3d_landcover.tif", _not_made("see README: land cover") if r == "not made" else r))
        r = put_large(game, man, source("landcover_overview", sources)[0], "nimby3d_landcover.bin", running, "landcover", step, 0.74, 0.80)
        log(_put_msg("nimby3d_landcover.bin", _not_made("see README: land cover") if r == "not made" else r))
        step(0.80, "ambient")
        log(_put_msg(AMBIENT_DIR, put_ambient(game, man, source("ambient", sources)[0], running)))
        step(0.86, "textures")
        r = put_large(game, man, source("textures", sources)[0], "nimby3d_textures.bin", running, "textures", step, 0.86, 0.92)
        log(_put_msg("nimby3d_textures.bin", _not_made("tools/make_textures.py") if r == "not made" else r))
        step(0.92, "avatar")
        log(_put_msg(AVATAR_NAME, _install_avatar(game, man, running, sources, step)))
        man.data.pop("disabled", None)
        man.data["installed_at_last"] = _now()
        man.save()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    step(1.0, "done")
    log(Msg("installed", "installed into {game}", game=game))
    log(_data_line(save, info))
    staged = [n for n, r in results.items() if r == "staged"]
    if running:
        log(Msg("running_next_start", "The game is running: it keeps using the version it started with. Restart the game to get this one."))
    return {"game": str(game), "save": str(save), "running": running, "staged": staged, "results": results,
            "stations": info.get("stations"), "nodes": info.get("nodes")}


def _install_avatar(game: Path, man: Manifest, running: bool, sources, step) -> str:
    rec = man.data.get("avatar") or {}
    dst = game / AVATAR_NAME
    if rec.get("cleared"):
        return "none (taken out in the manager; choose one there)"
    if rec.get("source"):  # chosen by the player: kept, refreshed when the chosen file changed
        src = Path(rec["source"])
        if not src.exists():
            return "kept (the chosen file is no longer there)" if dst.exists() else "none (the chosen file is no longer there)"
        return put_large(game, man, src, AVATAR_NAME, running, "avatar", step, 0.92, 0.99)
    src, _ = source("avatar", sources)
    if dst.exists() and AVATAR_NAME not in man.files and not man.legacy:
        return "kept the one already there (not put there by this tool)"
    if src is None or not src.exists():
        if src is None and not dev_allowed():
            return "none (choose a VRM model of your own in Nimby3D; the third person shows no one without it)"
        return f"none at {src or SOURCES['avatar'][2]()} (a VRM model of your own; the third person shows no one without it)"
    return put_large(game, man, src, AVATAR_NAME, running, "avatar", step, 0.92, 0.99)


def refresh(game=None, save=None, *, saves_dir=None, log=print, progress=None) -> dict:
    """The save's data only. The add-on notices the files changing and reads them again."""
    step = _Steps(progress)
    game = resolve_game(game)
    man = Manifest(game)
    if not man.exists:
        raise InstallError("not_installed", "not installed; run install first")
    save = Path(save) if save else newest_save(saves_dir)
    if not save.is_file():
        raise InstallError("save_missing", "save not found: {path}", path=str(save))
    scratch = _scratch(game)
    try:
        info = export_save(save, scratch, game, step, log, dem=False)
        step(0.8, "data")
        _place_exports(game, man, scratch, info)
        _save_info(man, save, info)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    step(1.0, "done")
    tr = info.get("tracks") or {}
    log(Msg("refreshed", "{time} data from {save}: {stations} stations, {nodes} track nodes, {platforms} platforms, {signals} signals",
            time=time.strftime("%H:%M:%S"), save=save.name, stations=info.get("stations"), nodes=info.get("nodes"),
            platforms=tr.get("platforms", 0), signals=tr.get("signals", 0)))
    return {"game": str(game), "save": str(save), "stations": info.get("stations"), "nodes": info.get("nodes")}


def watch_heartbeat_path() -> Path:
    return state_dir() / "watch.json"


def watch_state() -> dict | None:
    """The watch that is running (this process's or another's), from its heartbeat."""
    p = watch_heartbeat_path()
    try:
        d = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not pid_alive(int(d.get("pid", 0))) or time.time() - float(d.get("beat", 0)) > 60:
        return None
    return d


def watch(game=None, *, saves_dir=None, save=None, stop: threading.Event | None = None, log=print, lock=None,
          interval: float = 5.0, settle: float = 2.0, on_refresh=None) -> None:
    """Refresh whenever the game writes a save (the newest in the folder, or `save` when given), until `stop` is set."""
    game = resolve_game(game)
    saves = find_saves(saves_dir)
    stop = stop or threading.Event()
    man = Manifest(game)
    if not man.exists:
        raise InstallError("not_installed", "not installed; run install first")
    log(Msg("watching", "watching {dir} for saves; Ctrl+C stops", dir=str(Path(save).parent if save else saves)))
    last = None
    with contextlib.suppress(Exception):  # the data already comes from this very save: nothing to do yet
        first = Path(save) if save else newest_save(saves)
        if man.data.get("save") == str(first) and abs(float(man.data.get("save_mtime", 0)) - first.stat().st_mtime) < 1e-3:
            last = (first, first.stat().st_mtime, first.stat().st_size)
    beat = watch_heartbeat_path()
    since = time.time()
    try:
        while not stop.is_set():
            with contextlib.suppress(OSError):
                beat.parent.mkdir(parents=True, exist_ok=True)
                beat.write_text(json.dumps({"pid": os.getpid(), "game": str(game), "since": since, "beat": time.time(),
                                            "save": str(save) if save else None}), "utf-8")
            try:
                current = Path(save) if save else newest_save(saves)
                stamp = (current, current.stat().st_mtime, current.stat().st_size)
            except (InstallError, OSError):
                stop.wait(interval)
                continue
            if stamp != last:
                if stop.wait(settle):  # let the game finish writing it
                    break
                with contextlib.suppress(OSError):
                    if (current.stat().st_mtime, current.stat().st_size) == stamp[1:]:
                        try:
                            with (lock if lock is not None else contextlib.nullcontext()):
                                result = refresh(game, current, log=log)
                            last = stamp
                            if on_refresh:
                                on_refresh(result)
                        except InstallError as ex:
                            if ex.code in ("not_installed", "watch_stopped"):
                                raise
                            log(Msg("watch_failed", "could not read {name} - {error}", name=current.name, error=str(ex)))
                        except Exception as ex:  # a save caught half written: try again on the next round
                            log(Msg("watch_failed", "could not read {name} - {error}", name=current.name, error=str(ex)))
            stop.wait(interval)
    finally:
        with contextlib.suppress(OSError, ValueError):
            d = json.loads(beat.read_text("utf-8"))
            if int(d.get("pid", 0)) == os.getpid():
                beat.unlink()


# ---------------------------------------------------------------- disable, enable

def _disabled_name(name: str) -> str:
    return name + DISABLED_SUFFIX


def _drop_disabled(game: Path, man: Manifest) -> None:
    """A fresh install replaces disabled copies of this tool's files."""
    for name in ("dxgi.dll", "nimby3d.addon64"):
        p = game / _disabled_name(name)
        if p.exists() and (name == "nimby3d.addon64" or man.current_sha(name, p) in man.known(name)):
            with contextlib.suppress(OSError):
                p.unlink()
    man.data.pop("disabled", None)


def is_disabled(game: Path, man: Manifest | None = None) -> bool:
    return (game / _disabled_name("nimby3d.addon64")).exists() and not (game / "nimby3d.addon64").exists()


def disable(game=None, *, log=print, progress=None) -> dict:
    """Keep the files but make the game start without ReShade and the add-on."""
    game = resolve_game(game)
    if game_running(game):
        raise InstallError("game_running", "NIMBY Rails is running; quit the game first")
    man = Manifest(game)
    addon = game / "nimby3d.addon64"
    if not addon.exists():
        if is_disabled(game):
            return {"game": str(game), "disabled": man.data.get("disabled", {}), "already": True}
        raise InstallError("not_installed", "not installed; run install first")
    done = {}
    dxgi = game / "dxgi.dll"
    todo = ["nimby3d.addon64"]
    if dxgi.exists():
        if man.is_ours("dxgi.dll", dxgi):
            todo.insert(0, "dxgi.dll")
        else:
            log(Msg("dxgi_not_ours_kept", "dxgi.dll was not put there by this tool: left as it is (only the add-on is turned off)"))
    for name in todo:
        on, off = game / name, game / _disabled_name(name)
        try:
            if off.exists():  # a stale disabled copy of this tool's
                off.unlink()
            on.rename(off)
        except OSError as ex:
            man.data["disabled"] = done
            man.save()
            raise InstallError("in_use", "{name} is in use and cannot be replaced; close the game and try again", name=name) from ex
        done[name] = off.name
        man.data["disabled"] = done  # recorded as it happens
        man.data["disabled_at"] = _now()
        man.save()
        log(Msg("disabled_file", "{name} -> {to}", name=name, to=off.name))
    log(Msg("disabled", "disabled: the game starts without ReShade and the add-on until you enable it again"))
    return {"game": str(game), "disabled": done}


def enable(game=None, *, log=print, progress=None) -> dict:
    """Undo disable. Works while the game runs; takes effect the next time it starts."""
    game = resolve_game(game)
    man = Manifest(game)
    done, notes = {}, []
    for name in ("dxgi.dll", "nimby3d.addon64"):
        off, on = game / _disabled_name(name), game / name
        if not off.exists():
            continue
        if on.exists():
            if name == "dxgi.dll" and not man.is_ours(name, on):
                notes.append("foreign_dxgi")
                log(Msg("enable_foreign_dxgi", "a dxgi.dll of someone else's is in place: Nimby3D's ReShade stays off"))
                continue
            with contextlib.suppress(OSError):  # the one in place is newer (a later install): drop the disabled copy
                off.unlink()
            done[name] = name
            continue
        try:
            off.rename(on)
        except OSError as ex:
            raise InstallError("in_use", "{name} is in use and cannot be replaced; close the game and try again", name=off.name) from ex
        done[name] = name
        log(Msg("enabled_file", "{from_} -> {name}", from_=off.name, name=name))
    if not done and not (game / "nimby3d.addon64").exists():
        raise InstallError("not_installed", "not installed; run install first")
    man.data.pop("disabled", None)
    man.data.pop("disabled_at", None)
    if man.exists or done:
        man.save()
    running = game_running(game)
    log(Msg("enabled_running", "enabled: takes effect the next time the game starts") if running else Msg("enabled", "enabled"))
    return {"game": str(game), "enabled": done, "notes": notes, "running": running}


# ---------------------------------------------------------------- avatar

def check_vrm(path: Path) -> None:
    p = Path(path)
    if not p.is_file():
        raise InstallError("avatar_missing", "file not found: {path}", path=str(p))
    if p.suffix.lower() not in (".vrm", ".glb"):
        raise InstallError("avatar_bad", "{name} is not a VRM model (.vrm)", name=p.name)
    with open(p, "rb") as f:
        head = f.read(12)
    if head[:4] != b"glTF":
        raise InstallError("avatar_bad", "{name} is not a VRM model (.vrm)", name=p.name)
    if p.stat().st_size > (2 << 30):
        raise InstallError("avatar_bad", "{name} is larger than 2 GB", name=p.name)


def set_avatar(path, game=None, *, log=print, progress=None) -> dict:
    """Copy a VRM model of the player's own to nimby3d_avatar.vrm in the game folder (read when the game starts)."""
    step = _Steps(progress)
    src = Path(path)
    check_vrm(src)
    game = resolve_game(game)
    man = Manifest(game)
    dst = game / AVATAR_NAME
    if dst.exists() and AVATAR_NAME not in man.files and not man.legacy:
        log(Msg("avatar_replacing", "replacing a nimby3d_avatar.vrm that was not put there by this tool"))
    step(0.02, "avatar")
    digest = sha_cached(src)
    if dst.exists() and man.current_sha(AVATAR_NAME, dst) == digest:
        result = "unchanged"
        man.record(AVATAR_NAME, dst, "avatar", digest, src)
    else:
        man.intend(AVATAR_NAME, digest)
        new = game / (AVATAR_NAME + NEW_SUFFIX)
        _copy(src, new, step, 0.05, 0.95, "avatar")
        result = _place(game, man, new, AVATAR_NAME)
        man.record(AVATAR_NAME, dst, "avatar", digest, src)
    man.data["avatar"] = {"source": str(src), "name": src.name, "set_at": _now()}
    man.save()
    step(1.0, "done")
    running = game_running(game)
    size = f"{src.stat().st_size / 1048576:.1f}"
    log(Msg("avatar_set_running", "player's figure: {name} ({size} MB), from the next start of the game", name=src.name, size=size) if running
        else Msg("avatar_set", "player's figure: {name} ({size} MB)", name=src.name, size=size))
    return {"game": str(game), "avatar": src.name, "result": result, "running": running}


def clear_avatar(game=None, *, log=print, progress=None) -> dict:
    game = resolve_game(game)
    man = Manifest(game)
    dst = game / AVATAR_NAME
    if dst.exists():
        if AVATAR_NAME not in man.files and not man.legacy:
            raise InstallError("avatar_not_ours", "nimby3d_avatar.vrm was not put there by this tool; delete it yourself if you want it gone")
        try:
            dst.unlink()
        except PermissionError:
            raise InstallError("in_use", "{name} is in use and cannot be replaced; close the game and try again", name=AVATAR_NAME)
    man.forget(AVATAR_NAME, save=False)
    man.data["avatar"] = {"cleared": True, "cleared_at": _now()}
    man.save()
    log(Msg("avatar_cleared", "player's figure taken out"))
    return {"game": str(game), "cleared": True}


# ---------------------------------------------------------------- remove

def _dir_size(p: Path) -> tuple[int, int]:
    n = size = 0
    for f in p.rglob("*"):
        with contextlib.suppress(OSError):
            if f.is_file():
                n += 1
                size += f.stat().st_size
    return n, size


def _foreign_proxies(game: Path, man: Manifest) -> list[str]:
    out = []
    for n in OTHER_PROXIES:
        p = game / n
        if p.exists() and not (n == "dxgi.dll" and man.is_ours(n, p)):
            out.append(n)
    return out


def remove_plan(game=None, *, purge: bool = False) -> dict:
    """Exactly what remove would delete, edit and keep (and why)."""
    game = resolve_game(game)
    man = Manifest(game)
    delete, keep, edit = [], [], []

    def add(lst, name, reason, **extra):
        p = game / name
        entry = {"name": name, "reason": reason}
        if p.is_dir():
            n, size = _dir_size(p)
            entry.update(dir=True, files=n, size=size)
        elif p.exists():
            with contextlib.suppress(OSError):
                entry["size"] = p.stat().st_size
        entry.update(extra)
        lst.append(entry)

    seen = set()
    dxgi = game / "dxgi.dll"
    ours_dxgi = man.is_ours("dxgi.dll", dxgi)
    dxgi_off = game / _disabled_name("dxgi.dll")
    reshade_ours = ours_dxgi or (not dxgi.exists() and bool(man.known("dxgi.dll")))
    proxies = _foreign_proxies(game, man)
    for name in ("dxgi.dll", _disabled_name("dxgi.dll")):
        p = game / name
        seen.add(name)
        if not p.exists():
            continue
        if man.is_ours("dxgi.dll", p):
            add(delete, name, "reshade")
        else:
            add(keep, name, "not_ours" if man.exists else "no_record")
    # ReShade.ini and what ReShade writes
    rec = man.data.get("reshade_ini") or ({"mode": "legacy"} if man.legacy else None)
    ini = game / "ReShade.ini"
    seen.add("ReShade.ini")
    if ini.exists():
        if not man.exists or rec is None:
            add(keep, "ReShade.ini", "no_record")
        elif rec.get("mode") in ("created", "legacy") and reshade_ours and not proxies:
            add(delete, "ReShade.ini", "reshade")
        elif rec.get("mode") == "merged" and rec.get("added"):
            add(edit, "ReShade.ini", "strip_keys", keys=[f"[{s}] {k}" for s, k, _ in rec["added"]])
        else:
            add(keep, "ReShade.ini", "not_ours" if rec.get("mode") in ("merged", "foreign") else "in_use_by_other_reshade")
    pre = set(man.data.get("preexisting") or [])
    for name in RESHADE_GENERATED:
        seen.add(name)
        if not (game / name).exists():
            continue
        if man.exists and reshade_ours and not proxies and name not in pre:
            add(delete, name, "reshade_generated")
        else:
            add(keep, name, "not_ours" if name in pre or proxies else "no_record")
    # the add-on and what it was installed with
    names = set(INSTALLED) - {"dxgi.dll", "ReShade.ini", MANIFEST_NAME}
    names |= {n for n in man.files if "/" not in n}
    for name in sorted(names):
        if name in seen:
            continue
        if name == AVATAR_NAME and name not in man.files and not man.legacy:
            continue  # a copy this tool did not put there: with the user data below
        seen.add(name)
        if not (game / name).exists():
            continue
        meta = man.data["meta"].get(name) or {}
        modified = False
        if meta.get("kind") not in ("cache", None) and name in man.files:
            with contextlib.suppress(OSError):
                modified = man.current_sha(name, game / name) != man.files[name]
        add(delete, name, "addon", modified=modified)
    for name in ("nimby3d.addon64" + DISABLED_SUFFIX,):
        seen.add(name)
        if (game / name).exists():
            add(delete, name, "addon")
    for p in _aside_candidates(game, man):
        seen.add(p.name)
        add(delete, p.name, "aside")
    if (game / AMBIENT_DIR).is_dir():
        seen.add(AMBIENT_DIR)
        add(delete, AMBIENT_DIR, "addon")
    for name in ADDON_LOGS:
        seen.add(name)
        if (game / name).exists():
            add(delete, name, "addon_log")
    for p in sorted(game.glob(TMP_PREFIX + "*")) + sorted(game.glob("nimby3d*" + NEW_SUFFIX)) + sorted(game.glob("nimby3d*.bin.new")):
        if p.name not in seen:
            seen.add(p.name)
            add(delete, p.name, "scratch")
    # the add-on's settings, what it learnt, and anything else of its name
    seen.add(MANIFEST_NAME)
    for p in sorted(game.iterdir()):
        if p.name in seen or not _ours_by_name(p.name):
            continue
        seen.add(p.name)
        add(delete if purge else keep, p.name, "user_data")
    if man.exists:
        add(delete, MANIFEST_NAME, "record")
    blocked = None
    if game_running(game):
        blocked = "game_running"
    return {"game": str(game), "purge": purge, "delete": delete, "edit": edit, "keep": keep, "blocked": blocked,
            "installed": man.exists or (game / "nimby3d.addon64").exists()}


def remove(game=None, *, purge: bool = False, log=print, progress=None) -> dict:
    step = _Steps(progress)
    game = resolve_game(game)
    if game_running(game):
        raise InstallError("game_running", "NIMBY Rails is running; quit the game first")
    plan = remove_plan(game, purge=purge)
    man = Manifest(game)
    removed, failed = [], []
    items = [e for e in plan["delete"] if e["name"] != MANIFEST_NAME]
    for i, e in enumerate(items):
        step(0.05 + 0.85 * i / max(1, len(items)), "remove")
        p = game / e["name"]
        try:
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
            removed.append(e["name"] + ("/" if e.get("dir") else ""))
            man.forget(e["name"], save=False)
            if e["name"] == AMBIENT_DIR:
                for k in [k for k in man.files if k.startswith(AMBIENT_DIR + "/")]:
                    man.forget(k, save=False)
        except OSError as ex:
            failed.append({"name": e["name"], "error": str(ex)})
    for e in plan["edit"]:
        if e["reason"] == "strip_keys":
            ini = game / "ReShade.ini"
            rec = man.data.get("reshade_ini") or {}
            try:
                text, bom = _ini_text(ini)
                stripped = ini_strip(text, rec.get("added") or [], rec.get("sections") or [])
                if stripped != text:
                    _write_atomic(ini, _ini_bytes(stripped, bom))
                log(Msg("ini_stripped", "ReShade.ini: took back the settings this tool added, kept yours"))
            except OSError as ex:
                failed.append({"name": "ReShade.ini", "error": str(ex)})
    step(0.95, "remove")
    if man.exists:
        if failed:
            man.save()  # what is left stays recorded, so a second remove finishes the job
        else:
            with contextlib.suppress(OSError):
                man.path.unlink()
                removed.append(MANIFEST_NAME)
    for e in plan["keep"]:
        if e["reason"] in ("not_ours", "no_record", "in_use_by_other_reshade"):
            log(Msg("kept_file", "kept {name} (not installed by this tool)", name=e["name"]))
    step(1.0, "done")
    log(Msg("removed", "removed: {names}", names=", ".join(removed) if removed else "nothing to remove"))
    if failed:
        log(Msg("remove_failed", "could not delete: {names}", names=", ".join(f["name"] for f in failed)))
    return {"game": str(game), "removed": removed, "failed": failed, "kept": [e["name"] for e in plan["keep"]]}


# ---------------------------------------------------------------- status

def shaderpacks() -> list[str]:
    base = os.environ.get("N3D_SHADERPACKS") or os.path.join(os.environ.get("APPDATA", ""), ".minecraft", "shaderpacks")
    out = []
    with contextlib.suppress(OSError):
        for p in sorted(Path(base).iterdir(), key=lambda p: p.name.lower()):
            if p.is_dir() or p.suffix.lower() == ".zip":
                out.append(p.name)
    return out


def tail_log(game, name: str = "nimby3d_probe.log", lines: int = 200) -> dict:
    """The last lines of the add-on's log or ReShade's (read-only; the game may be writing it)."""
    if name not in ("nimby3d_probe.log", "ReShade.log"):
        raise InstallError("bad_log", "unknown log {name}", name=name)
    p = resolve_game(game) / name
    if not p.exists():
        return {"name": name, "path": str(p), "exists": False, "lines": []}
    lines = max(1, min(int(lines), 2000))
    with open(p, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        block, data = 64 << 10, b""
        while size > 0 and data.count(b"\n") <= lines:
            take = min(block, size)
            size -= take
            f.seek(size)
            data = f.read(take) + data
    text = data.decode("utf-8", errors="replace").splitlines()[-lines:]
    st = p.stat()
    return {"name": name, "path": str(p), "exists": True, "size": st.st_size, "mtime": st.st_mtime, "lines": text}


def _file_state(game: Path, man: Manifest, name: str) -> dict:
    p = game / name
    meta = man.data["meta"].get(name) or {}
    kind = meta.get("kind") or ("reshade" if name == "dxgi.dll" else "addon" if name == "nimby3d.addon64" else "data")
    entry = {"name": name, "kind": kind}
    if not p.exists():
        off = game / _disabled_name(name)
        entry["state"] = "disabled" if off.exists() else "missing"
        return entry
    entry["size"] = p.stat().st_size
    if kind == "cache":
        entry["state"] = "ok"
    elif name in man.files and man.files[name]:
        try:
            entry["state"] = "ok" if man.current_sha(name, p) == man.files[name] else "modified"
        except OSError:
            entry["state"] = "unreadable"
    else:
        entry["state"] = "present"
    return entry


def status(game=None, *, saves_dir=None, sources: dict | None = None, save=None, how: str = "argument") -> dict:
    """Everything the manager shows, as plain JSON-able values. Never raises for a missing piece."""
    out: dict = {"time": time.time(), "dev": dev_allowed()}
    found = find_game(game, how=how)
    out["game"] = {"dir": found["dir"], "how": found["how"], "found": found["valid"], "exe": GAME_EXE, "running": False}
    out["sources"] = {}
    for name in SOURCES:
        p, h = source(name, sources)
        out["sources"][name] = {"path": str(p) if p else None, "how": h, "exists": bool(p and p.exists())}
    addon_src = source("addon", sources)[0]
    reshade_src = source("reshade", sources)[0]
    available = {}
    if addon_src is not None and addon_src.is_file():  # a package missing its add-on shows no build, it does not fail
        with contextlib.suppress(OSError):
            st = addon_src.stat()
            available = {"sha": sha_cached(addon_src), "mtime": st.st_mtime, "size": st.st_size, "path": str(addon_src)}
    out["available"] = available
    saves = find_saves(saves_dir)
    out["saves"] = {"dir": str(saves) if saves else None, "count": 0, "newest": None, "chosen": str(save) if save else None}
    with contextlib.suppress(Exception):
        all_saves = list_saves(saves_dir)
        out["saves"]["count"] = len(all_saves)
        if all_saves:
            n = all_saves[-1]
            out["saves"]["newest"] = {"path": str(n), "name": n.name, "mtime": n.stat().st_mtime, "size": n.stat().st_size}
    if save:
        with contextlib.suppress(OSError):
            s = Path(save)
            out["saves"]["chosen_info"] = {"path": str(s), "name": s.name, "exists": s.exists(), "mtime": s.stat().st_mtime if s.exists() else None}
    out["shaderpacks"] = shaderpacks()
    w = watch_state()
    out["watch"] = {"running": bool(w), "pid": w.get("pid") if w else None, "game": w.get("game") if w else None, "since": w.get("since") if w else None}
    if not found["valid"]:
        out["state"] = "no_game"
        return out
    g = Path(found["dir"])
    with contextlib.suppress(Exception):
        out["game"]["running"] = game_running(g)
    man = Manifest(g)
    addon, addon_off = g / "nimby3d.addon64", g / _disabled_name("nimby3d.addon64")
    dxgi, dxgi_off = g / "dxgi.dll", g / _disabled_name("dxgi.dll")
    if addon.exists():
        state = "installed"
    elif addon_off.exists():
        state = "disabled"
    elif man.exists and any(n in man.files for n in ("nimby3d.addon64", "dxgi.dll")):
        state = "incomplete"
    else:
        state = "not_installed"
    out["state"] = state
    out["manifest"] = {"exists": man.exists, "legacy": man.legacy, "installed_at": man.data.get("installed_at"),
                       "updated": man.data.get("updated")}
    inst = {}
    for p in (addon, addon_off):
        if p.exists():
            with contextlib.suppress(OSError):
                inst = {"sha": man.current_sha("nimby3d.addon64", p), "mtime": p.stat().st_mtime, "size": p.stat().st_size}
            break
    out["installed"] = inst
    reshade_update = False
    with contextlib.suppress(OSError):
        for p in (dxgi, dxgi_off):
            if reshade_src is not None and reshade_src.is_file() and p.exists() and man.is_ours("dxgi.dll", p):
                reshade_update = sha_cached(reshade_src) != man.current_sha("dxgi.dll", p)
                break
    out["update_available"] = bool(state in ("installed", "disabled") and ((inst.get("sha") and available.get("sha") and inst["sha"] != available["sha"]) or reshade_update))
    out["reshade"] = {"present": dxgi.exists() or dxgi_off.exists(), "ours": man.is_ours("dxgi.dll", dxgi) or man.is_ours("dxgi.dll", dxgi_off),
                      "foreign_dxgi": dxgi.exists() and not man.is_ours("dxgi.dll", dxgi),
                      "other_proxies": [n for n in _foreign_proxies(g, man) if n != "dxgi.dll"],
                      "ini": (man.data.get("reshade_ini") or {}).get("mode") or ("legacy" if man.legacy else None),
                      "update": reshade_update}
    names = ["dxgi.dll", "nimby3d.addon64"] + [n for n in man.files if n not in ("dxgi.dll", "nimby3d.addon64") and "/" not in n]
    if man.legacy:
        names += [n for n in INSTALLED if n not in names and n not in ("ReShade.ini", MANIFEST_NAME) and (g / n).exists()]
    files = [_file_state(g, man, n) for n in names if n in man.files or (g / n).exists() or (g / _disabled_name(n)).exists()]
    amb = [n for n in man.files if n.startswith(AMBIENT_DIR + "/")]
    if amb or (g / AMBIENT_DIR).is_dir():
        states = [_file_state(g, man, n)["state"] for n in amb]
        bad = [s for s in states if s not in ("ok", "present")]
        files.append({"name": AMBIENT_DIR + "/", "kind": "ambient", "files": len(amb) or _dir_size(g / AMBIENT_DIR)[0],
                      "state": ("missing" if all(s == "missing" for s in states) else "modified") if bad else "ok"})
    if (g / "ReShade.ini").exists():
        files.append({"name": "ReShade.ini", "kind": "reshade_ini", "state": "present", "size": (g / "ReShade.ini").stat().st_size})
    out["files"] = files
    out["files_summary"] = {"total": len(files), "ok": sum(f["state"] in ("ok", "present") for f in files),
                            "missing": sum(f["state"] == "missing" for f in files), "modified": sum(f["state"] == "modified" for f in files),
                            "disabled": sum(f["state"] == "disabled" for f in files)}
    out["staged"] = [p.name for p in _aside_candidates(g, man)]
    data = {k: man.data.get(k) for k in ("save", "save_mtime", "exported_at", "stations", "nodes", "platforms", "signals", "dem_tiles")}
    if data.get("save"):
        data["save_name"] = Path(data["save"]).name
    record_mtime = None
    with contextlib.suppress(OSError):
        record_mtime = man.path.stat().st_mtime if man.exists else None
    if not data.get("exported_at") and data.get("save") and record_mtime:  # first versions' record: no time of its own
        data["exported_at"] = datetime.datetime.fromtimestamp(record_mtime).isoformat(timespec="seconds")
    basis = float(data.get("save_mtime") or record_mtime or 0)
    newest = out["saves"].get("newest")
    target = out["saves"].get("chosen_info") or newest
    data["stale"] = bool(target and data.get("save") and (os.path.normcase(target["path"]) != os.path.normcase(data["save"])
                                                       or (target.get("mtime") or 0) > basis + 1))
    out["data"] = data
    av = g / AVATAR_NAME
    rec = man.data.get("avatar") or {}
    out["avatar"] = {"present": av.exists(), "size": av.stat().st_size if av.exists() else None, "name": rec.get("name"),
                     "source": rec.get("source"), "ours": AVATAR_NAME in man.files or man.legacy, "cleared": bool(rec.get("cleared")),
                     "default_available": bool(source("avatar", sources)[0])}
    logs = []
    for n in ("nimby3d_probe.log", "ReShade.log"):
        p = g / n
        logs.append({"name": n, "path": str(p), "exists": p.exists(), "size": p.stat().st_size if p.exists() else 0,
                     "mtime": p.stat().st_mtime if p.exists() else None})
    out["logs"] = logs
    out["user_data"] = [n for n in USER_DATA if (g / n).exists()]
    return out


# ---------------------------------------------------------------- command line

def _cli() -> None:
    args = sys.argv[1:]
    try:
        if len(args) in (1, 2) and args[0] == "install":
            install(save=Path(args[1]) if len(args) == 2 else None)
        elif len(args) in (1, 2) and args[0] == "refresh":
            refresh(save=Path(args[1]) if len(args) == 2 else None)
        elif args == ["watch"]:
            try:
                watch()
            except KeyboardInterrupt:
                pass
        elif args in (["remove"], ["remove", "--purge"]):
            remove(purge=len(args) == 2)
        elif args == ["disable"]:
            disable()
        elif args == ["enable"]:
            enable()
        elif len(args) == 2 and args[0] == "avatar":
            clear_avatar() if args[1] == "--clear" else set_avatar(Path(args[1]))
        elif args == ["status"]:
            print(json.dumps(status(), indent=1))  # ASCII-escaped: readable whatever the console's code page
        else:
            sys.exit(__doc__)
    except InstallError as ex:
        sys.exit(str(ex))


if __name__ == "__main__":
    _cli()
