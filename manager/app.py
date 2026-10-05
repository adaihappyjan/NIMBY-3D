"""Nimby3D: the desktop manager of the nimby3d add-on for NIMBY Rails (install, update, refresh the
save's data, keep it in sync, disable, enable, uninstall, the player's figure).

  pythonw manager/app.py            a window (pywebview on Edge WebView2); without those, the same page
                                    in an Edge app window or the default browser, served on 127.0.0.1
  python manager/app.py --browser   always the browser page
  python manager/app.py --headless  only the local server, nothing opened; prints one JSON line
                                    {"url": ..., "token": ...} and serves until stopped.
                                    For tests: N3D_NO_SHELL=1 keeps Explorer closed; N3D_TEST_PICK_FOLDER,
                                    N3D_TEST_PICK_SAVE and N3D_TEST_PICK_AVATAR answer the file pickers.

Every file operation on the game folder is tools/install.py's (see its docstring for what is put where and the
safety rules); nimby3d.ini is read and changed by manager/nimby3d_ini.py, the shader packs by manager/shaderpacks.py.
The manager keeps its own settings in %LOCALAPPDATA%/Nimby3D (N3D_STATE_DIR).

Pages: Home, Shader packs, Add-on settings, Guide and About are the page's own; more come from scripts that register
themselves in window.N3D_PAGES (see app.js). Their backend calls go through page_call(name, args): a name starting
with "trains." goes to manager/trains.py's TrainsApi (when that module is there), any other to this Api.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import ctypes
import hmac
import importlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
UI = HERE / "ui"
PROJECT = HERE.parent
for p in (str(PROJECT / "tools"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import install as core  # noqa: E402
import nimby3d_ini as nini  # noqa: E402
import shaderpacks as packs  # noqa: E402

def _read_version() -> str:
    try:
        return (PROJECT / "VERSION").read_text("utf-8").strip() or "dev"
    except OSError:
        return "dev"


APP_VERSION = _read_version()
STEAM_APPID = core.STEAM_APPID
# where links on the page may lead (opened in the default browser or Steam, never inside the window): these exact
# beginnings, and anything on the sites below (the train editor's links to mods and their authors)
LINKS = (f"https://store.steampowered.com/app/{STEAM_APPID}", f"steam://store/{STEAM_APPID}")
LINK_HOSTS = ("github.com", "steamcommunity.com", "www.pixiv.net")
# the page's own files (manager/ui), served in browser mode: by their type, nothing outside the folder
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".jpg": "image/jpeg", ".webp": "image/webp",
                ".json": "application/json; charset=utf-8", ".woff2": "font/woff2"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
MAX_BODY = 65536            # an ordinary call
MAX_PAGE_BODY = 64 << 20    # a page's call (the train editor sends models)
PICK_TITLES = {
    "folder": {"zh": "选择 NIMBY Rails 游戏文件夹（含 NimbyRails.exe）", "en": "Choose the NIMBY Rails game folder (with NimbyRails.exe)"},
    "save": {"zh": "选择一个存档", "en": "Choose a save"},
    "avatar": {"zh": "选择 VRM 人物模型", "en": "Choose a VRM model"},
}


# ---------------------------------------------------------------- small helpers

def system_lang() -> str:
    """zh when Windows' display language is a Chinese one, else en."""
    try:
        return "zh" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x04 else "en"
    except Exception:
        return "en"


def system_light() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
    except Exception:
        return False


def webview2_available() -> bool:
    """Is the Edge WebView2 runtime installed (the registry keys its installers write)."""
    try:
        import winreg
    except ImportError:
        return False
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
                      (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
                      (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}")):
        with contextlib.suppress(OSError):
            with winreg.OpenKey(hive, key) as k:
                pv = str(winreg.QueryValueEx(k, "pv")[0])
                if pv and pv != "0.0.0.0":
                    return True
    return False


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    if isinstance(v, Path):
        return str(v)
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _err(ex: Exception) -> dict:
    if isinstance(ex, (core.InstallError, nini.IniError)):
        return {"ok": False, "error": ex.code, "message": str(ex), "params": _jsonable(ex.params)}
    if isinstance(ex, PermissionError):
        name = Path(ex.filename).name if getattr(ex, "filename", None) else "?"
        return {"ok": False, "error": "in_use", "message": f"{name} is in use", "params": {"name": name}}
    traceback.print_exc()
    return {"ok": False, "error": "unexpected", "message": f"{type(ex).__name__}: {ex}", "params": {"message": f"{type(ex).__name__}: {ex}"}}


def _refusal(code: str, message: str, **params) -> dict:
    return {"ok": False, "error": code, "message": message.format(**params) if params else message, "params": params}


def link_allowed(url: str) -> bool:
    """One of the page's own destinations, or a page on one of LINK_HOSTS (https, no user name, no other port)."""
    if any(url == base or url.startswith(base + "/") for base in LINKS):
        return True
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        return False
    return (u.scheme == "https" and u.hostname in LINK_HOSTS and port is None and not u.username and not u.password
            and u.netloc.lower() == u.hostname and not any(c in url for c in "\\\r\n\t "))


def schema_path() -> Path | None:
    """settings_schema.json (tools/dump_settings.cpp): N3D_SETTINGS_SCHEMA, the payload, or the developer's build/."""
    if os.environ.get("N3D_SETTINGS_SCHEMA"):
        return Path(os.environ["N3D_SETTINGS_SCHEMA"])
    p = core.payload_dir() / "settings_schema.json"
    if p.is_file() or not core.dev_allowed():
        return p
    return PROJECT / "build" / "settings_schema.json"


def packinfo_path() -> Path | None:
    """n3d_packinfo.exe (tools/n3d_packinfo.cpp): N3D_PACKINFO, the payload's tools/, or the developer's build/."""
    if os.environ.get("N3D_PACKINFO"):
        return Path(os.environ["N3D_PACKINFO"])
    p = core.payload_dir() / "tools" / "n3d_packinfo.exe"
    if p.is_file() or not core.dev_allowed():
        return p
    return PROJECT / "build" / "n3d_packinfo.exe"


def workshop_dirs(game: Path | None = None) -> list[Path]:
    """steamapps/workshop/content/1134710 of every Steam library (and of the game's own library), those that exist.
    N3D_WORKSHOP_DIRS (folders separated by ';') replaces them (tests)."""
    if os.environ.get("N3D_WORKSHOP_DIRS") is not None:
        return [Path(p) for p in os.environ["N3D_WORKSHOP_DIRS"].split(os.pathsep) if p and Path(p).is_dir()]
    libs = list(core.steam_libraries())
    if game is not None and Path(game).parent.name.lower() == "common" and Path(game).parent.parent.name.lower() == "steamapps":
        libs.append(Path(game).parent.parent.parent)
    return core._unique(lib / "steamapps" / "workshop" / "content" / STEAM_APPID for lib in libs
                        if (lib / "steamapps" / "workshop" / "content" / STEAM_APPID).is_dir())


def local_mods_dir() -> Path | None:
    """The game's own folder of local (not Workshop) mods: Saved Games/Weird and Wry/NIMBY Rails/mods, beside the
    saves (each mod a folder with a mod.txt). N3D_MODS_DIR replaces it (tests). None when the game's Saved Games
    folder is not there; the mods folder itself may not exist yet."""
    if os.environ.get("N3D_MODS_DIR"):
        return Path(os.environ["N3D_MODS_DIR"])
    base = core.find_saves()
    if base is not None and base.is_dir():
        return base / "mods"
    for cand in core.save_dir_candidates():
        if (cand / "mods").is_dir():
            return cand / "mods"
    return None


class PageContext:
    """What a page's own backend (manager/trains.py: TrainsApi(ctx)) gets from the manager."""

    def __init__(self, api: "Api"):
        self._api = api
        self.state_dir: Path = api._state

    def game_dir(self) -> Path | None:
        """The game folder the Home page shows (None when there is none)."""
        return self._api._game_or_none()

    def log(self, line) -> None:
        """A line in the activity log on the Home page."""
        self._api._log(line)

    def workshop_dirs(self) -> list[Path]:
        return workshop_dirs(self.game_dir())

    def local_mods_dir(self) -> Path | None:
        return local_mods_dir()


# ---------------------------------------------------------------- settings and events

# the page's appearance skins (manager/ui/skins, made by tools/make_skins.py); "classic" has no picture
SKINS = ("classic", "afternoon", "sleepy", "nightshift")
SKIN_TYPES = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
SKIN_MAX_BYTES = 8 << 20
SKIN_MIN_SIDE, SKIN_MAX_SIDE = 128, 8192


def picture_info(data: bytes) -> tuple[str, int, int] | None:
    """(type, width, height) of a PNG, JPEG or WebP picture, read from its header; None for anything else."""
    import struct
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
            w, h = struct.unpack(">II", data[16:24])
            return "image/png", w, h
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            kind = data[12:16]
            if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
                w, h = struct.unpack("<HH", data[26:30])
                return "image/webp", w & 0x3FFF, h & 0x3FFF
            if kind == b"VP8L" and data[20] == 0x2F:
                b = int.from_bytes(data[21:25], "little")
                return "image/webp", (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
            if kind == b"VP8X":
                return "image/webp", int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
            return None
        if data[:3] == b"\xff\xd8\xff":
            at = 2
            while at + 9 < len(data):
                if data[at] != 0xFF:
                    at += 1
                    continue
                marker = data[at + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                    at += 1 if marker == 0xFF else 2
                    continue
                size = struct.unpack(">H", data[at + 2:at + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[at + 5:at + 9])
                    return "image/jpeg", w, h
                at += 2 + size
    except (struct.error, IndexError):
        return None
    return None


class Settings:
    DEFAULTS = {"lang": None, "theme": "system", "game_dir": None, "save": None, "log_open": True, "log_tab": "activity", "auto_watch": False,
                "skin": "classic"}
    CHOICES = {"lang": (None, "zh", "en"), "theme": ("system", "light", "dark"), "log_tab": ("activity", "addon", "reshade"), "skin": SKINS}

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.data = dict(self.DEFAULTS)
        with contextlib.suppress(OSError, ValueError):
            loaded = json.loads(path.read_text("utf-8"))
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in self.DEFAULTS})

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value) -> None:
        if key not in self.DEFAULTS:
            raise ValueError(f"unknown setting {key}")
        if key in self.CHOICES and value not in self.CHOICES[key]:
            raise ValueError(f"bad value for {key}")
        if key in ("log_open", "auto_watch"):
            value = bool(value)
        with self.lock:
            self.data[key] = value
            with contextlib.suppress(OSError):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".json.new")
                tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), "utf-8")
                os.replace(tmp, self.path)


class Events:
    """What happened, numbered: the page asks for everything after the last number it saw (long poll)."""

    def __init__(self, keep: int = 800):
        self.cv = threading.Condition()
        self.items: list[dict] = []
        self.seq = 0
        self.keep = keep

    def push(self, type_: str, **data) -> None:
        with self.cv:
            self.seq += 1
            self.items.append({"seq": self.seq, "t": time.time(), "type": type_, **_jsonable(data)})
            if len(self.items) > self.keep:
                del self.items[:-self.keep]
            self.cv.notify_all()

    def since(self, seq: int, timeout: float) -> dict:
        deadline = time.time() + timeout
        with self.cv:
            if seq > self.seq:  # the page saw a manager that has since restarted
                return {"seq": self.seq, "events": list(self.items[-200:]), "reset": True}
            while self.seq <= seq:
                left = deadline - time.time()
                if left <= 0:
                    break
                self.cv.wait(left)
            return {"seq": self.seq, "events": [e for e in self.items if e["seq"] > seq][-500:]}


# ---------------------------------------------------------------- the API the page calls

class Api:
    """Every public method is callable from the page: through pywebview's js_api in the window, or as
    POST /api/<name> {"args": [...]} with the session token in browser mode. Each returns a dict
    with "ok"; long operations return at once and report through events()."""

    def __init__(self, settings: Settings, mode: str, dry_shell: bool = False):
        self._settings = settings
        self._mode = mode
        self._events = Events()
        self._lock = threading.Lock()  # one operation on the game folder at a time
        self._op: dict | None = None
        self._watch_thread: threading.Thread | None = None
        self._watch_stop: threading.Event | None = None
        self._window = None
        self._dry = dry_shell
        self._progress_last = (None, -1.0, 0.0)
        self._state = Path(settings.path).parent       # the manager's own folder (settings.json, shaderpack_options.json)
        self._ini_lock = threading.Lock()              # one change of nimby3d.ini at a time
        self._trains_lock = threading.Lock()
        self._trains_api = None
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="n3d-page")

    # ------------------------------------------------ internals
    def _lang(self) -> str:
        return self._settings.get("lang") or system_lang()

    def _game_arg(self) -> tuple[str | None, str]:
        manual = self._settings.get("game_dir")
        return (manual, "manual") if manual else (None, "argument")

    def _game(self) -> Path:
        manual, how = self._game_arg()
        found = core.find_game(manual, how=how)
        if not found["valid"]:
            return core.resolve_game(manual)  # raises with the right code
        return Path(found["dir"])

    def _save(self) -> Path | None:
        pinned = self._settings.get("save")
        return Path(pinned) if pinned else None

    def _log(self, line) -> None:
        self._events.push("log", text=str(line), key=getattr(line, "key", None), params=getattr(line, "params", None))

    def _progress(self, fraction: float, step: str) -> None:
        last_step, last_fraction, last_t = self._progress_last
        now = time.time()
        if step != last_step or abs(fraction - last_fraction) >= 0.01 or now - last_t > 0.25 or fraction >= 1.0:
            self._progress_last = (step, fraction, now)
            self._events.push("progress", op=(self._op or {}).get("name"), fraction=round(fraction, 4), step=step)

    def _run(self, name: str, fn, **kwargs) -> dict:
        if not self._lock.acquire(blocking=False):
            return _refusal("busy", "another operation is running", op=(self._op or {}).get("name"))
        self._op = {"name": name, "started": time.time()}
        self._progress_last = (None, -1.0, 0.0)

        def work():
            self._events.push("op_start", op=name)
            try:
                result = fn(log=self._log, progress=self._progress, **kwargs)
                self._events.push("op_end", op=name, ok=True, result=result)
            except Exception as ex:  # noqa: BLE001 - every failure goes to the page
                self._events.push("op_end", op=name, **_err(ex))
            finally:
                self._op = None
                self._lock.release()
                self._events.push("status_changed")

        threading.Thread(target=work, name=f"n3d-{name}", daemon=True).start()
        return {"ok": True, "op": name}

    def _watching(self) -> bool:
        return bool(self._watch_thread and self._watch_thread.is_alive())

    class _SyncLock:
        """The lock the save watch takes for each refresh: shown on the page as the operation "sync"."""

        def __init__(self, api: "Api"):
            self.api = api

        def __enter__(self):
            stop = self.api._watch_stop
            while not self.api._lock.acquire(timeout=0.5):
                if stop is not None and stop.is_set():
                    raise core.InstallError("watch_stopped", "auto-sync stopped")
            self.api._op = {"name": "sync", "started": time.time()}
            self.api._events.push("op_start", op="sync")
            return self

        def __exit__(self, exc_type, exc, tb):
            ok = exc_type is None
            data = {"ok": True} if ok else (_err(exc) if isinstance(exc, Exception) else {"ok": False, "error": "unexpected", "message": "", "params": {}})
            self.api._op = None
            self.api._lock.release()
            self.api._events.push("op_end", op="sync", **data)
            self.api._events.push("status_changed")
            return False

    def _watch_loop(self, game: Path, save: Path | None, stop: threading.Event) -> None:
        self._events.push("watch", running=True)
        error = {}
        try:
            core.watch(game, save=save, stop=stop, log=self._log, lock=Api._SyncLock(self),
                       on_refresh=lambda r: self._events.push("synced", result=r))
        except core.InstallError as ex:
            if ex.code != "watch_stopped":
                error = _err(ex)
        except Exception as ex:  # noqa: BLE001
            error = _err(ex)
        if error:
            self._settings.set("auto_watch", False)
        self._events.push("watch", running=False, **error)
        self._events.push("status_changed")

    def _stop_watch(self, wait: float = 3.0) -> None:
        if self._watch_stop:
            self._watch_stop.set()
        t = self._watch_thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(wait)

    def _pick(self, kind: str, initial: str | None = None) -> str | None:
        env = os.environ.get({"folder": "N3D_TEST_PICK_FOLDER", "save": "N3D_TEST_PICK_SAVE", "avatar": "N3D_TEST_PICK_AVATAR"}[kind])
        if env is not None:
            return env or None
        if self._mode == "headless":
            raise core.InstallError("no_dialog", "no file dialog in headless mode")
        title = PICK_TITLES[kind][self._lang()]
        if self._mode == "window" and self._window is not None:
            import webview
            if kind == "folder":
                res = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial or "")
            else:
                types = ("NIMBY Rails save (*.nimbyrails5)", "All files (*.*)") if kind == "save" else ("VRM model (*.vrm;*.glb)", "All files (*.*)")
                res = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=initial or "", file_types=types)
            if not res:
                return None
            return res[0] if isinstance(res, (list, tuple)) else str(res)
        import dialogs
        if kind == "folder":
            return dialogs.pick_folder(title, initial)
        filters = [("NIMBY Rails save", "*.nimbyrails5")] if kind == "save" else [("VRM model", "*.vrm;*.glb")]
        return dialogs.open_file(title, filters + [("All files", "*.*")], initial)

    def _shell_open(self, path: Path, select: bool = False) -> dict:
        if self._dry or os.environ.get("N3D_NO_SHELL"):
            return {"ok": True, "path": str(path), "dry": True}
        try:
            if select and path.exists():
                subprocess.Popen(f'explorer /select,"{path}"')
            else:
                os.startfile(str(path if path.is_dir() else path.parent))
        except OSError as ex:
            return _err(ex)
        return {"ok": True, "path": str(path)}

    def _shutdown(self) -> None:
        self._stop_watch(wait=2.0)
        api = self._trains_api
        if api is not None and callable(getattr(api, "close", None)):
            with contextlib.suppress(Exception):
                api.close()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _game_or_none(self) -> Path | None:
        manual, how = self._game_arg()
        found = core.find_game(manual, how=how)
        return Path(found["dir"]) if found["valid"] else None

    def _memory(self) -> packs.Memory:
        return packs.Memory(self._state / packs.MEMORY_NAME)

    def _running(self, game: Path | None) -> bool:
        if game is None:
            return False
        try:
            return bool(core.game_running(game))
        except Exception:  # noqa: BLE001
            return False

    def _edit_ini(self, fn, log_line=None) -> dict:
        """Read nimby3d.ini afresh, let fn(ini, packs) change it, write it back (only when it changed)."""
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if (self._op or {}).get("name") == "remove":
            return _refusal("busy", "another operation is running", op="remove")
        path = game / nini.INI_NAME
        with self._ini_lock:
            try:
                ini = nini.IniText.load(path)
                result = fn(ini, packs.scan(sizes=False))
                if ini.changed:
                    ini.save(path)
            except Exception as ex:  # noqa: BLE001
                return _err(ex)
        if ini.changed and log_line is not None:
            self._log(log_line(result) if callable(log_line) else log_line)
        self._events.push("ini_changed")
        return {"ok": True, "result": _jsonable(result), "written": ini.changed, "path": str(path), "running": self._running(game)}

    def _load_schema(self) -> tuple[dict | None, Path | None, dict | None]:
        p = schema_path()
        try:
            return nini.check_schema(json.loads(p.read_text("utf-8"))), p, None
        except FileNotFoundError:
            return None, p, {"error": "no_schema", "message": f"settings_schema.json is missing ({p})", "params": {"path": str(p)}}
        except (OSError, ValueError, nini.IniError) as ex:
            return None, p, {"error": "bad_schema", "message": f"settings_schema.json could not be read: {ex}", "params": {"path": str(p), "error": str(ex)}}

    def _trains(self):
        """manager/trains.py's TrainsApi, made once (the module is imported only when a page first asks)."""
        with self._trains_lock:
            if self._trains_api is None:
                try:
                    mod = importlib.import_module("trains")
                except ModuleNotFoundError as ex:
                    if ex.name == "trains":
                        raise core.InstallError("no_train_editor", "train editor not installed") from None
                    raise core.InstallError("train_editor_broken", "the train editor could not be loaded: {error}", error=str(ex)) from None
                if not hasattr(mod, "TrainsApi"):
                    raise core.InstallError("no_train_editor", "train editor not installed")
                self._trains_api = mod.TrainsApi(PageContext(self))
            return self._trains_api

    # ------------------------------------------------ public: state
    def hello(self) -> dict:
        return {"ok": True, "version": APP_VERSION, "mode": self._mode, "default_lang": system_lang(), "system_lang": system_lang(),
                "prefs": {k: self._settings.get(k) for k in ("lang", "theme", "log_open", "log_tab", "skin")}, "seq": self._events.seq,
                "skin_pictures": self._skin_pictures()}

    def status(self) -> dict:
        try:
            manual, how = self._game_arg()
            s = core.status(manual, how=how, save=self._save())
            s["app"] = {"version": APP_VERSION, "mode": self._mode, "busy": (self._op or {}).get("name"),
                        "watch_own": self._watching(), "auto_watch": bool(self._settings.get("auto_watch")),
                        "pinned_save": self._settings.get("save"), "manual_game": manual}
            s["pack"] = None  # the shader pack nimby3d.ini chooses (for the Home page's card)
            if s.get("game", {}).get("found"):
                with contextlib.suppress(Exception):
                    sel = packs.selection(nini.IniText.load(Path(s["game"]["dir"]) / nini.INI_NAME), packs.scan(sizes=False))
                    s["pack"] = {"enabled": sel["enabled"], "name": sel["owner"] or None}
            return {"ok": True, "status": _jsonable(s)}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def events(self, since=0, timeout=10) -> dict:
        try:
            since, timeout = int(since), max(0.0, min(float(timeout), 25.0))
        except (TypeError, ValueError):
            since, timeout = 0, 0.0
        return {"ok": True, **self._events.since(since, timeout)}

    def set_pref(self, key, value) -> dict:
        if key not in ("lang", "theme", "log_open", "log_tab", "skin"):
            return _refusal("bad_pref", "unknown setting {key}", key=str(key))
        try:
            self._settings.set(key, value)
        except ValueError as ex:
            return _refusal("bad_pref", str(ex), key=str(key))
        return {"ok": True}

    # ------------------------------------------------ public: the skins' own pictures (in the state folder)
    def _skin_dir(self) -> Path:
        return self._state / "skins"

    def _skin_file(self, skin: str) -> Path | None:
        for ext in SKIN_TYPES:
            p = self._skin_dir() / f"{skin}{ext}"
            if p.is_file():
                return p
        return None

    def _skin_pictures(self) -> dict:
        out = {}
        for skin in SKINS[1:]:
            p = self._skin_file(skin)
            if p is not None:
                with contextlib.suppress(OSError):
                    st = p.stat()
                    out[skin] = {"name": p.name, "size": st.st_size, "version": st.st_mtime_ns}
        return out

    def skin_picture(self, skin) -> dict:
        """A skin's own picture (one the player put in) as a data: URL; None when the skin has its default."""
        import base64
        skin = str(skin)
        if skin not in SKINS[1:]:
            return _refusal("bad_skin", "no such skin: {skin}", skin=skin)
        p = self._skin_file(skin)
        if p is None:
            return {"ok": True, "skin": skin, "data": None}
        try:
            data = p.read_bytes()
        except OSError as ex:
            return _err(ex)
        info = picture_info(data)
        if info is None:
            return {"ok": True, "skin": skin, "data": None}
        return {"ok": True, "skin": skin, "data": f"data:{info[0]};base64," + base64.b64encode(data).decode("ascii"), "width": info[1], "height": info[2]}

    def skin_set_picture(self, skin, path=None) -> dict:
        """A picture of the player's own (PNG, WebP or JPEG, up to 8 MB, 128 to 8192 pixels a side) for a skin:
        copied into the manager's state folder, where it replaces the skin's own until restored."""
        skin = str(skin)
        if skin not in SKINS[1:]:
            return _refusal("bad_skin", "no such skin: {skin}", skin=skin)
        if not path:
            return _refusal("bad_picture", "no picture given", name="")
        src = Path(str(path).strip().strip('"'))
        ext = src.suffix.lower()
        try:
            if ext not in SKIN_TYPES:
                return _refusal("bad_picture", "{name} is not a PNG, WebP or JPEG picture", name=src.name)
            size = src.stat().st_size
            if size > SKIN_MAX_BYTES:
                return _refusal("picture_too_big", "{name} is larger than {mb} MB", name=src.name, mb=SKIN_MAX_BYTES >> 20)
            data = src.read_bytes()
        except FileNotFoundError:
            return _refusal("pack_missing", "{path} does not exist", path=str(src))
        except OSError as ex:
            return _err(ex)
        info = picture_info(data)
        if info is None or info[0] != SKIN_TYPES[ext]:
            return _refusal("bad_picture", "{name} is not a PNG, WebP or JPEG picture", name=src.name)
        _, w, h = info
        if not (SKIN_MIN_SIDE <= w <= SKIN_MAX_SIDE and SKIN_MIN_SIDE <= h <= SKIN_MAX_SIDE):
            return _refusal("picture_size", "{name} is {w}×{h} pixels: each side must be {lo} to {hi}", name=src.name, w=w, h=h,
                            lo=SKIN_MIN_SIDE, hi=SKIN_MAX_SIDE)
        try:
            self._skin_dir().mkdir(parents=True, exist_ok=True)
            dst = self._skin_dir() / f"{skin}{'.jpg' if ext == '.jpeg' else ext}"
            nini.write_atomic(dst, data)
            for e in SKIN_TYPES:
                other = self._skin_dir() / f"{skin}{e}"
                if other != dst and other.is_file():
                    other.unlink()
        except OSError as ex:
            return _err(ex)
        return self.skin_picture(skin)

    def skin_reset_picture(self, skin) -> dict:
        """Back to the skin's own picture (the copy of the player's picture in the state folder is deleted)."""
        skin = str(skin)
        if skin not in SKINS[1:]:
            return _refusal("bad_skin", "no such skin: {skin}", skin=skin)
        try:
            for ext in SKIN_TYPES:
                p = self._skin_dir() / f"{skin}{ext}"
                if p.is_file():
                    p.unlink()
        except OSError as ex:
            return _err(ex)
        return {"ok": True, "skin": skin}

    # ------------------------------------------------ public: operations
    def _launch_game(self, game: Path) -> str:
        """Start NIMBY Rails through Steam (as its desktop shortcut does); without Steam's handler, the game itself."""
        if self._dry or os.environ.get("N3D_NO_SHELL"):
            return "dry"
        try:
            os.startfile(f"steam://rungameid/{STEAM_APPID}")
            return "steam"
        except OSError:
            subprocess.Popen([str(game / core.GAME_EXE)], cwd=str(game))
            return "exe"

    def _then_play(self, fn, play: bool):
        """An operation that, when asked and when it went well, starts the game afterwards (not while it already runs)."""
        def run(game, log, progress, **kw):
            result = fn(game=game, log=log, progress=progress, **kw)
            if play and not core.game_running(game):
                result["launched"] = self._launch_game(game)
                log(core.Msg("launched", "starting NIMBY Rails"))
            return result
        return run

    def install(self, play=False) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return self._run("install", self._then_play(core.install, bool(play)), game=game, save=self._save())

    def play(self) -> dict:
        """Start NIMBY Rails (through Steam)."""
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if core.game_running(game):
            return _refusal("already_running", "NIMBY Rails is already running")
        try:
            return {"ok": True, "launched": self._launch_game(game)}
        except OSError as ex:
            return _err(ex)

    def open_url(self, url) -> dict:
        """Open one of the page's links (GitHub, the game's Steam page, Steam Workshop, pixiv) outside the window."""
        url = str(url)
        if not link_allowed(url):
            return _refusal("bad_link", "not a link of this page")
        if self._dry or os.environ.get("N3D_NO_SHELL"):
            return {"ok": True, "url": url, "dry": True}
        try:
            if url.startswith("steam://"):
                try:
                    os.startfile(url)
                except OSError:  # no Steam: its store page in the browser
                    webbrowser.open(f"https://store.steampowered.com/app/{STEAM_APPID}")
            else:
                webbrowser.open(url)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return {"ok": True, "url": url}

    def refresh(self) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return self._run("refresh", core.refresh, game=game, save=self._save())

    def disable(self) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return self._run("disable", core.disable, game=game)

    def enable(self, play=False) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return self._run("enable", self._then_play(core.enable, bool(play)), game=game)

    def remove_plan(self, purge=False) -> dict:
        try:
            return {"ok": True, "plan": _jsonable(core.remove_plan(self._game(), purge=bool(purge)))}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def remove(self, purge=False) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if self._op:
            return _refusal("busy", "another operation is running", op=self._op.get("name"))
        if self._watching():
            self._stop_watch()
            self._settings.set("auto_watch", False)
        return self._run("remove", core.remove, game=game, purge=bool(purge))

    def watch_start(self) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if self._watching():
            return {"ok": True, "already": True}
        if not core.Manifest(game).exists:
            return _refusal("not_installed", "not installed; run install first")
        other = core.watch_state()
        if other and int(other.get("pid", 0)) != os.getpid():
            return _refusal("watch_elsewhere", "another program (pid {pid}) is already syncing the saves", pid=other.get("pid"))
        self._watch_stop = threading.Event()
        self._watch_thread = threading.Thread(target=self._watch_loop, args=(game, self._save(), self._watch_stop), name="n3d-watch", daemon=True)
        self._watch_thread.start()
        self._settings.set("auto_watch", True)
        return {"ok": True}

    def watch_stop(self) -> dict:
        self._settings.set("auto_watch", False)
        self._stop_watch()
        return {"ok": True}

    # ------------------------------------------------ public: choices
    def choose_game_folder(self) -> dict:
        try:
            current = self._settings.get("game_dir") or core.find_game().get("dir")
            path = self._pick("folder", current)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if not path:
            return {"ok": False, "cancelled": True}
        return self.set_game_folder(path)

    def set_game_folder(self, path) -> dict:
        if not path or not str(path).strip():
            return _refusal("bad_folder", "that folder does not contain NimbyRails.exe", path="")
        found = core.game_folder_from(str(path).strip().strip('"'))
        if found is None:
            return _refusal("bad_folder", "that folder does not contain NimbyRails.exe", path=str(path))
        if self._op:
            return _refusal("busy", "another operation is running", op=self._op.get("name"))
        old = self._settings.get("game_dir")
        if self._watching() and os.path.normcase(str(found)) != os.path.normcase(str(old or "")):
            self._stop_watch()
        self._settings.set("game_dir", str(found))
        self._events.push("status_changed")
        return {"ok": True, "dir": str(found)}

    def auto_game_folder(self) -> dict:
        if self._op:
            return _refusal("busy", "another operation is running", op=self._op.get("name"))
        if self._settings.get("game_dir") and self._watching():
            self._stop_watch()
        self._settings.set("game_dir", None)
        found = core.find_game()
        self._events.push("status_changed")
        return {"ok": True, "found": _jsonable(found)}

    def _after_save_change(self) -> dict:
        refreshing = False
        try:
            game = self._game()
            if core.Manifest(game).exists and not self._op:
                refreshing = self.refresh().get("ok", False)
        except Exception:  # noqa: BLE001 - the choice stands; the page shows the state
            pass
        if self._watching():  # follow the new choice
            self._stop_watch()
            self.watch_start()
        self._events.push("status_changed")
        return {"ok": True, "save": self._settings.get("save"), "refreshing": refreshing}

    def choose_save(self) -> dict:
        try:
            saves = core.find_saves()
            path = self._pick("save", str(saves) if saves else None)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if not path:
            return {"ok": False, "cancelled": True}
        p = Path(path)
        if not p.is_file() or p.suffix.lower() != ".nimbyrails5":
            return _refusal("bad_save", "{name} is not a NIMBY Rails save (.nimbyrails5)", name=p.name)
        self._settings.set("save", str(p))
        return self._after_save_change()

    def use_newest_save(self) -> dict:
        self._settings.set("save", None)
        return self._after_save_change()

    def choose_avatar(self) -> dict:
        try:
            game = self._game()
            path = self._pick("avatar", None)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        if not path:
            return {"ok": False, "cancelled": True}
        try:
            core.check_vrm(Path(path))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return self._run("avatar", core.set_avatar, path=Path(path), game=game)

    def clear_avatar(self) -> dict:
        try:
            game = self._game()
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        return self._run("clear_avatar", core.clear_avatar, game=game)

    # ------------------------------------------------ public: looking
    def open_game_folder(self) -> dict:
        try:
            return self._shell_open(self._game())
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def open_log(self, name="nimby3d_probe.log") -> dict:
        if name not in ("nimby3d_probe.log", "ReShade.log"):
            return _refusal("bad_log", "unknown log {name}", name=str(name))
        try:
            return self._shell_open(self._game() / name, select=True)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def read_log(self, name="nimby3d_probe.log", lines=200) -> dict:
        try:
            return {"ok": True, "log": _jsonable(core.tail_log(self._game(), str(name), int(lines)))}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    GAME_FILES = (nini.INI_NAME, nini.STATIONS_NAME, "nimby3d_probe.log", "ReShade.log", "ReShade.ini")

    def open_game_file(self, name=nini.INI_NAME) -> dict:
        """Show one of the add-on's files in Explorer (or its folder when it is not there yet); "state" is the
        manager's own folder, "shaderpacks" the shader packs folder."""
        name = str(name)
        try:
            if name == "state":
                self._state.mkdir(parents=True, exist_ok=True)
                return self._shell_open(self._state)
            if name == "shaderpacks":
                return self.packs_open_folder()
            if name not in self.GAME_FILES:
                return _refusal("bad_file", "not one of the add-on's files: {name}", name=name)
            return self._shell_open(self._game() / name, select=True)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ------------------------------------------------ public: dialogs for the pages
    def pick_file(self, title=None, filters=None, save=False, name=None) -> dict:
        """A file dialog: {"path": the file chosen, or None when cancelled}. filters: [[label, "*.json;*.gov"], ...]."""
        env = os.environ.get("N3D_TEST_PICK_FILE")
        if env is not None:
            return {"ok": True, "path": env or None}
        if self._mode == "headless":
            return _refusal("no_dialog", "no file dialog in headless mode")
        clean = []
        for f in filters or []:
            if isinstance(f, (list, tuple)) and len(f) == 2:
                label = re.sub(r"[^\w ]+", " ", str(f[0])).strip() or "Files"
                pattern = str(f[1]).replace(" ", "")
                if re.fullmatch(r"\*(?:\.(?:\w+|\*))*(?:;\*(?:\.(?:\w+|\*))*)*", pattern):
                    clean.append((label, pattern))
        if not any(p == "*.*" for _, p in clean):
            clean.append(("All files", "*.*"))
        title = str(title or "")
        try:
            if self._mode == "window" and self._window is not None:
                import webview
                kind = webview.FileDialog.SAVE if save else webview.FileDialog.OPEN
                res = self._window.create_file_dialog(kind, directory="", save_filename=str(name or ""),
                                                      file_types=tuple(f"{label} ({pattern})" for label, pattern in clean))
                if not res:
                    return {"ok": True, "path": None}
                return {"ok": True, "path": res[0] if isinstance(res, (list, tuple)) else str(res)}
            import dialogs
            path = dialogs.save_file(title, clean, str(name or "")) if save else dialogs.open_file(title, clean, None)
            return {"ok": True, "path": path or None}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def pick_dir(self, title=None) -> dict:
        """A folder dialog: {"path": the folder chosen, or None when cancelled}."""
        env = os.environ.get("N3D_TEST_PICK_DIR")
        if env is not None:
            return {"ok": True, "path": env or None}
        if self._mode == "headless":
            return _refusal("no_dialog", "no file dialog in headless mode")
        try:
            if self._mode == "window" and self._window is not None:
                import webview
                res = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory="")
                if not res:
                    return {"ok": True, "path": None}
                return {"ok": True, "path": res[0] if isinstance(res, (list, tuple)) else str(res)}
            import dialogs
            return {"ok": True, "path": dialogs.pick_folder(str(title or ""), None) or None}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    # ------------------------------------------------ public: the shader packs page
    def packs_list(self) -> dict:
        """The packs in the shader packs folder, which one nimby3d.ini chooses, and where things are."""
        try:
            folder = packs.packs_dir()
            items = packs.scan(folder)
            game = self._game_or_none()
            sel, ini_path = None, None
            if game is not None:
                ini_path = game / nini.INI_NAME
                sel = packs.selection(nini.IniText.load(ini_path), items)
                sel["option_count"] = len(packs.parse_options(sel["options"]))
            memory = self._memory().all()
            for it in items:
                it["selected"] = bool(sel and sel["owner"] and sel["owner"].lower() == it["name"].lower())
                saved = memory.get(it["name"].lower()) or {}
                it["saved"] = bool(saved.get("options") or saved.get("profile"))
            tool = packinfo_path()
            return {"ok": True, "dir": str(folder), "exists": folder.is_dir(), "packs": items, "selection": sel,
                    "game": str(game) if game else None, "ini": str(ini_path) if ini_path else None,
                    "ini_exists": bool(ini_path and ini_path.is_file()), "running": self._running(game),
                    "packinfo": {"path": str(tool) if tool else None, "exists": bool(tool and tool.is_file())}}
        except Exception as ex:  # noqa: BLE001
            return _err(ex)

    def packs_select(self, name) -> dict:
        """Use this pack (shaderpack=1, shaderpack_file=<name>); its remembered profile and options come back."""
        return self._edit_ini(lambda ini, items: packs.choose(ini, str(name), self._memory(), items),
                              lambda r: core.Msg("pack_chosen", "shader pack: {name} (nimby3d.ini)", name=r["name"]))

    def packs_enable(self, on=True) -> dict:
        on = bool(on)
        return self._edit_ini(lambda ini, items: packs.enable(ini, on, self._memory(), items),
                              core.Msg("packs_on", "shader packs on (nimby3d.ini)") if on else core.Msg("packs_off", "shader packs off (nimby3d.ini)"))

    def packs_import(self, path=None, replace=False) -> dict:
        """Copy a pack (a .zip or a folder) into the shader packs folder."""
        if not path:
            return _refusal("pack_missing", "no pack given")
        try:
            r = packs.import_pack(str(path), replace=bool(replace))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        self._log(core.Msg("pack_imported", "shader pack added: {name}", name=r["name"]))
        self._events.push("status_changed")
        return {"ok": True, **_jsonable(r)}

    def packs_remove(self, name) -> dict:
        """Move a pack to the Recycle Bin. When nimby3d.ini chooses it, shader packs are turned off."""
        name = str(name or "")
        try:
            before = packs.scan(sizes=False)
            r = packs.remove_pack(name)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        self._log(core.Msg("pack_removed", "shader pack moved to the Recycle Bin: {name}", name=name))
        game = self._game_or_none()
        r["turned_off"] = False
        if game is not None and (self._op or {}).get("name") != "remove":
            path = game / nini.INI_NAME
            with self._ini_lock:
                with contextlib.suppress(Exception):
                    ini = nini.IniText.load(path)
                    sel = packs.selection(ini, before)
                    if sel["on_value"] and sel["owner"].lower() == name.lower():
                        ini.set("shaderpack", "0")
                        ini.save(path)
                        r["turned_off"] = True
            if r["turned_off"]:
                self._log(core.Msg("packs_off", "shader packs off (nimby3d.ini)"))
        self._events.push("status_changed")
        return {"ok": True, **_jsonable(r)}

    def packs_open_folder(self) -> dict:
        folder = packs.packs_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            return _err(ex)
        return self._shell_open(folder)

    def packs_info(self, name, profile=None) -> dict:
        """A pack's profiles, screens and options (n3d_packinfo.exe) and its profile and options now; with a profile
        also each option's value under it ("profile_defaults"). When the reader is missing or fails, "error" says why
        and the rest is still there."""
        name = str(name or "")
        try:
            folder = packs.packs_dir()
            path = packs._child(folder, name)
            if not os.path.lexists(path):
                raise packs.PackError("pack_missing", "{path} does not exist", path=str(path))
            items = packs.scan(folder, sizes=False)
            game = self._game_or_none()
            ini = nini.IniText.load(game / nini.INI_NAME) if game is not None else nini.IniText()
            current = packs.options_of(ini, name, self._memory(), items)
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        info, error, profile_defaults = None, None, None
        try:
            info = packs.pack_info(packinfo_path(), path)
            want = current["profile"] if profile is None else str(profile)
            if want and want in [p.get("name") for p in info.get("profiles") or []]:
                profile_defaults = {o["name"]: o.get("default") for o in packs.pack_info(packinfo_path(), path, want)["options"]}
        except packs.PackError as ex:
            error = {"error": ex.code, "message": str(ex), "params": _jsonable(ex.params)}
        except Exception as ex:  # noqa: BLE001
            error = _err(ex)
        sel = packs.selection(ini, items)
        tool = packinfo_path()
        return {"ok": True, "name": name, "info": _jsonable(info), "error": error, "current": current,
                "profile_defaults": profile_defaults, "selected": bool(sel["owner"] and sel["owner"].lower() == name.lower()),
                "enabled": sel["enabled"], "running": self._running(game), "packinfo": str(tool) if tool else None}

    def packs_save_options(self, name, profile="", options=None) -> dict:
        """A pack's profile and the options that differ from its defaults ({NAME: VALUE}). With the pack reader at
        hand both are checked against the pack (a profile it does not have would keep the pack from opening);
        without it only options can be set."""
        name = str(name or "")
        options = options if isinstance(options, dict) else {}
        try:
            profile = packs.check_profile(profile)
            path = packs._child(packs.packs_dir(), name)
            info = packs.pack_info(packinfo_path(), path)
        except packs.PackError as ex:
            if ex.code not in ("packinfo_missing", "packinfo_failed"):
                return _err(ex)
            if profile:
                return _refusal("bad_profile", "a profile can only be chosen with the pack reader (n3d_packinfo.exe): {error}", error=str(ex))
        except Exception as ex:  # noqa: BLE001
            return _err(ex)
        else:
            try:
                packs.check_against(info, profile, {str(k): str(v) for k, v in options.items()})
            except packs.PackError as ex:
                return _err(ex)
        return self._edit_ini(lambda ini, items: packs.save_options(ini, name, profile, options, self._memory(), items),
                              lambda r: core.Msg("pack_options", "shader pack options: {name}, {n} set", name=r["name"],
                                                 n=len(packs.parse_options(r["options"]))))

    # ------------------------------------------------ public: the add-on settings page
    def _where(self, game: Path | None) -> list[dict]:
        rows = []

        def row(id_, path: Path | None, **extra):
            e = {"id": id_, "path": str(path) if path else None, "exists": bool(path and path.exists())}
            if path is not None and path.is_file():
                with contextlib.suppress(OSError):
                    st = path.stat()
                    e.update(size=st.st_size, mtime=st.st_mtime)
            e.update(extra)
            rows.append(e)

        if game is not None:
            row(nini.INI_NAME, game / nini.INI_NAME)
            row(nini.STATIONS_NAME, game / nini.STATIONS_NAME, stations=nini.station_rules(game / nini.STATIONS_NAME))
            row("nimby3d_probe.log", game / "nimby3d_probe.log")
            row("ReShade.log", game / "ReShade.log")
            row("ReShade.ini", game / "ReShade.ini")
        row("shaderpacks", packs.packs_dir())
        row("state", self._state)
        return rows

    def settings_get(self) -> dict:
        """The settings schema, each setting's value in nimby3d.ini (missing: its default) and where the files are."""
        schema, spath, serr = self._load_schema()
        game = self._game_or_none()
        out = {"ok": True, "schema": schema, "schema_path": str(spath) if spath else None, "schema_error": serr,
               "game": str(game) if game else None, "values": {}, "lines": {}, "unknown_keys": [], "ini": None,
               "running": self._running(game), "files": self._where(game)}
        if game is None:
            return out
        path = game / nini.INI_NAME
        try:
            ini = nini.IniText.load(path)
        except OSError as ex:
            return _err(ex)
        st = path.stat() if path.is_file() else None
        out["ini"] = {"path": str(path), "exists": st is not None, "encoding": ini.encoding, "bom": ini.bom,
                      "newline": "crlf" if ini.newline == "\r\n" else "lf", "size": st.st_size if st else 0, "mtime": st.st_mtime if st else None}
        if schema:
            out.update(nini.read_values(ini, schema))
            known = {s.get("key") for s in schema.get("settings") or []}
            out["unknown_keys"] = [k for k in ini.keys() if k not in known]
        return out

    def settings_set(self, changes=None) -> dict:
        """Change settings in nimby3d.ini: {key: value}; a value of None puts the setting back to its default."""
        schema, _, serr = self._load_schema()
        if schema is None:
            return {"ok": False, **serr}
        changes = changes if isinstance(changes, dict) else {}
        return self._edit_ini(lambda ini, items: nini.apply_changes(ini, schema, changes),
                              lambda r: core.Msg("settings_written", "nimby3d.ini: {keys}", keys=", ".join(r)))

    def settings_reset_all(self) -> dict:
        """Every setting of the settings page back to its default; the rest of nimby3d.ini stays."""
        schema, _, serr = self._load_schema()
        if schema is None:
            return {"ok": False, **serr}
        return self._edit_ini(lambda ini, items: nini.reset_all(ini, schema),
                              lambda r: core.Msg("settings_reset", "nimby3d.ini: {n} settings back to their defaults", n=len(r)))

    # ------------------------------------------------ public: the pages' calls
    def page_call(self, name, args=None) -> dict:
        """A registered page's call: {"ok": true, "result": value} or {"ok": false, "error", "message"}.
        "trains.<method>": TrainsApi(ctx).<method>(**args) on a worker thread; any other name: this Api's method."""
        name = str(name or "")
        if args is None:
            args = {}
        if not isinstance(args, (dict, list)):
            return _refusal("bad_request", "args must be an object or a list")
        try:
            if name.startswith("trains."):
                method = name[len("trains."):]
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", method):
                    return _refusal("no_such_call", "no such call: {name}", name=name)
                api = self._trains()
                fn = getattr(api, method, None)
                if not callable(fn):
                    return _refusal("no_such_call", "no such call: {name}", name=name)
                future = self._pool.submit(fn, **args) if isinstance(args, dict) else self._pool.submit(fn, *args)
                return {"ok": True, "result": _jsonable(future.result())}
            if name in PUBLIC and name not in ("page_call", "events"):
                fn = getattr(self, name)
                r = fn(**args) if isinstance(args, dict) else fn(*args)
                if isinstance(r, dict) and r.get("ok") is False:
                    return r
                return {"ok": True, "result": r}
            return _refusal("no_such_call", "no such call: {name}", name=name)
        except TypeError as ex:
            return {"ok": False, "error": "bad_request", "message": str(ex), "params": {"message": str(ex)}}
        except (core.InstallError, nini.IniError) as ex:
            return _err(ex)
        except Exception as ex:  # noqa: BLE001 - the page shows it
            code = getattr(ex, "code", None)
            traceback.print_exc()
            return {"ok": False, "error": code if isinstance(code, str) and code else "page_error", "message": str(ex) or type(ex).__name__,
                    "params": {"message": str(ex) or type(ex).__name__}}


PUBLIC = tuple(n for n in dir(Api) if not n.startswith("_") and callable(getattr(Api, n)))


def static_file(url_path: str) -> Path | None:
    """The page's own file for a URL path: a file under manager/ui of a known type, nothing hidden, nothing outside."""
    rel = unquote(url_path).lstrip("/") or "index.html"
    if "\\" in rel or "\0" in rel or any(part in ("", ".", "..") or part.startswith(".") for part in rel.split("/")):
        return None
    p = UI.joinpath(*rel.split("/"))
    try:
        p = p.resolve()
        if UI.resolve() not in p.parents or not p.is_file():
            return None
    except (OSError, ValueError):
        return None
    return p if p.suffix.lower() in STATIC_TYPES else None


# ---------------------------------------------------------------- browser mode: a local server

class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, api: Api, token: str, port: int = 0):
        super().__init__(("127.0.0.1", port), Handler)
        self.api = api
        self.token = token
        self.last_seen = time.time()


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "Nimby3D"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _refuse(self, code: int, obj) -> None:
        """An answer before the request's body was read: the connection is closed after it (a browser reuses its
        connections, across its tabs too: what is left of the body would be read as the next request)."""
        self.close_connection = True
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", {"Connection": "close"})

    def do_GET(self):
        self.server.last_seen = time.time()
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        path = urlsplit(self.path).path
        file = static_file(path)
        if file is None:
            return self._send(404, b"not found", "text/plain")
        try:
            body = file.read_bytes()
        except OSError:
            return self._send(404, b"not found", "text/plain")
        self._send(200, body, STATIC_TYPES[file.suffix.lower()], {"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})

    do_HEAD = do_GET

    def do_POST(self):
        self.server.last_seen = time.time()
        if not self._host_ok():
            return self._refuse(403, {"ok": False, "error": "forbidden"})
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return self._refuse(403, {"ok": False, "error": "forbidden"})
        if not hmac.compare_digest(self.headers.get("X-Nimby3D-Token", ""), self.server.token):
            return self._refuse(401, {"ok": False, "error": "token"})
        path = urlsplit(self.path).path
        name = path[len("/api/"):] if path.startswith("/api/") else ""
        page = name == "page_call" or name.startswith("trains.")
        if not page and name not in PUBLIC:
            return self._refuse(404, {"ok": False, "error": "no_such_call"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._refuse(400, {"ok": False, "error": "bad_request"})
        if length > (MAX_PAGE_BODY if page else MAX_BODY):
            left = length if length <= MAX_PAGE_BODY else 0  # (read what was sent, so the caller sees the answer)
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                left -= len(chunk)
            return self._refuse(413, {"ok": False, "error": "too_large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            args = body.get("args")
            if name.startswith("trains."):  # POST /api/trains.<method> {"args": {...}}: the same as page_call
                if args is not None and not isinstance(args, (dict, list)):
                    raise ValueError("args")
                return self._json(200, self.server.api.page_call(name, args))
            args = args or []
            if not isinstance(args, list):
                raise ValueError("args")
        except (ValueError, AttributeError):
            return self._json(400, {"ok": False, "error": "bad_request"})
        try:
            result = getattr(self.server.api, name)(*args)
        except TypeError as ex:
            return self._json(400, {"ok": False, "error": "bad_request", "message": str(ex)})
        self._json(200, result)


def open_browser(url: str) -> str:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        exe = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if exe.is_file():
            with contextlib.suppress(OSError):
                subprocess.Popen([str(exe), f"--app={url}", "--window-size=1100,760"])
                return "edge"
    webbrowser.open(url)
    return "browser"


def serve(api: Api, port: int = 0) -> tuple[Server, str]:
    token = secrets.token_urlsafe(24)
    server = Server(api, token, port)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, name="n3d-http", daemon=True).start()
    return server, token


# ---------------------------------------------------------------- the window

def run_window(api: Api, theme: str) -> bool:
    """The page in a pywebview window. False when pywebview or WebView2 is missing (then the browser takes over)."""
    if os.environ.get("N3D_FORCE_BROWSER") or not webview2_available():
        return False
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
                          "--disable-background-timer-throttling --disable-renderer-backgrounding --disk-cache-size=1")
    try:
        import webview
    except Exception:  # noqa: BLE001
        return False
    light = theme == "light" or (theme == "system" and system_light())
    try:
        with contextlib.suppress(Exception):  # the taskbar groups the window as Nimby3D, with its icon (not Python's)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("adaihappyjan.Nimby3D")
        window = webview.create_window("Nimby3D", url=str(UI / "index.html"), js_api=api, width=1100, height=720,
                                       min_size=(900, 600), background_color="#f4f6fb" if light else "#0b0f17")
        api._window = window
        icon = UI / "assets" / "nimby3d.ico"
        webview.start(gui="edgechromium", private_mode=True, debug=bool(os.environ.get("N3D_DEBUG")),
                      icon=str(icon) if icon.is_file() else None)
        return True
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        api._window = None
        return False


# ---------------------------------------------------------------- one at a time

_MUTEX = None


def first_instance() -> bool:
    global _MUTEX
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        _MUTEX = k32.CreateMutexW(None, False, "Local\\Nimby3D.Manager")
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    except Exception:  # noqa: BLE001
        return True


def show_running_instance(state: Path) -> None:
    try:
        user = ctypes.windll.user32
        hwnd = user.FindWindowW(None, "Nimby3D")
        if hwnd:
            user.ShowWindow(hwnd, 9)  # SW_RESTORE
            user.SetForegroundWindow(hwnd)
            return
    except Exception:  # noqa: BLE001
        pass
    with contextlib.suppress(OSError, ValueError, KeyError):
        info = json.loads((state / "server.json").read_text("utf-8"))
        open_browser(info["url"])


def quiet_output(state: Path) -> None:
    """pythonw has no console: keep what would go there in a log file."""
    if sys.stdout is not None and sys.stderr is not None and "pythonw" not in Path(sys.executable).name.lower():
        return
    with contextlib.suppress(OSError):
        state.mkdir(parents=True, exist_ok=True)
        log = state / "manager.log"
        if log.exists() and log.stat().st_size > (1 << 20):
            os.replace(log, state / "manager.old.log")
        f = open(log, "a", encoding="utf-8", buffering=1)
        f.write(f"\n--- Nimby3D {APP_VERSION} started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        sys.stdout = sys.stderr = f


def unblock_tree(root: Path) -> int:
    """Files extracted from a downloaded ZIP carry the Mark of the Web (a Zone.Identifier stream). .NET (which
    the window uses) refuses to load such assemblies, so take it off this program's own files, as Windows'
    "Unblock" does. Nimby3D.exe does the same before it starts Python; this covers Nimby3D.cmd."""
    n = 0
    if os.name != "nt":
        return n
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("build", "src", "tests", ".git", "__pycache__")]
        for f in filenames:
            try:
                os.remove(os.path.join(dirpath, f) + ":Zone.Identifier")
                n += 1
            except OSError:
                pass
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Nimby3D manager")
    ap.add_argument("--browser", action="store_true", help="the page in a browser instead of a window")
    ap.add_argument("--headless", action="store_true", help="only the local server (tests)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--idle-exit", type=float, default=None, help="browser mode: stop when no page has called for this many seconds")
    args = ap.parse_args()
    state = core.state_dir()
    quiet_output(state)
    unblock_tree(PROJECT)
    if not args.headless and not first_instance():
        show_running_instance(state)
        return 0
    settings = Settings(state / "settings.json")
    mode = "headless" if args.headless else "browser" if args.browser else "window"
    api = Api(settings, mode, dry_shell=bool(os.environ.get("N3D_NO_SHELL")))
    if settings.get("auto_watch"):
        with contextlib.suppress(Exception):
            if not api.watch_start().get("ok"):
                settings.set("auto_watch", True)  # keep the wish; it starts once installed
    try:
        if mode == "window" and run_window(api, settings.get("theme")):
            return 0
        if mode == "window":
            mode = api._mode = "browser"
        server, token = serve(api, args.port)
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/#t={token}"
        if mode == "headless":
            print(json.dumps({"url": url, "token": token, "port": port, "pid": os.getpid()}), flush=True)
        else:
            with contextlib.suppress(OSError):
                (state / "server.json").write_text(json.dumps({"url": url, "pid": os.getpid()}), "utf-8")
            open_browser(url)
        idle = args.idle_exit if args.idle_exit is not None else (None if mode == "headless" else 120.0)
        while True:
            time.sleep(1.0)
            if idle and time.time() - server.last_seen > idle and not api._op:
                break
        server.shutdown()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        api._shutdown()
        with contextlib.suppress(OSError, ValueError):
            info = json.loads((state / "server.json").read_text("utf-8"))
            if info.get("pid") == os.getpid():
                (state / "server.json").unlink()


if __name__ == "__main__":
    sys.exit(main())
