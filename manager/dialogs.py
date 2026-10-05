"""Native Windows file and folder pickers through ctypes, for when the manager runs without
pywebview (the page in a browser). No dependencies; each call blocks the calling thread until
the person picks something or cancels."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

_comdlg = ctypes.WinDLL("comdlg32")
_shell = ctypes.WinDLL("shell32")
_ole = ctypes.WinDLL("ole32")
_user = ctypes.WinDLL("user32")


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND), ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR), ("lpstrCustomFilter", wintypes.LPWSTR), ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR), ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR), ("nMaxFileTitle", wintypes.DWORD), ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD), ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD), ("lpstrDefExt", wintypes.LPCWSTR), ("lCustData", wintypes.LPARAM),
                ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wintypes.LPCWSTR), ("pvReserved", ctypes.c_void_p),
                ("dwReserved", wintypes.DWORD), ("FlagsEx", wintypes.DWORD)]


BFFCALLBACK = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.UINT, wintypes.LPARAM, wintypes.LPARAM)


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [("hwndOwner", wintypes.HWND), ("pidlRoot", ctypes.c_void_p), ("pszDisplayName", wintypes.LPWSTR),
                ("lpszTitle", wintypes.LPCWSTR), ("ulFlags", wintypes.UINT), ("lpfn", BFFCALLBACK), ("lParam", wintypes.LPARAM),
                ("iImage", ctypes.c_int)]


_comdlg.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
_comdlg.GetSaveFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
_shell.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
_shell.SHBrowseForFolderW.restype = ctypes.c_void_p
_shell.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
_ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
_user.GetForegroundWindow.restype = wintypes.HWND
_user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def open_file(title: str, filters: list[tuple[str, str]], initial_dir: str | None = None) -> str | None:
    """filters: [("VRM model", "*.vrm"), ...]. Returns the chosen path or None."""
    spec = "".join(f"{label} ({pattern})\0{pattern}\0" for label, pattern in filters) + "\0"
    filt = ctypes.create_unicode_buffer(spec, len(spec) + 1)
    buf = ctypes.create_unicode_buffer(4096)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = _user.GetForegroundWindow()
    ofn.lpstrFilter = ctypes.cast(filt, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = 4096
    ofn.lpstrTitle = title
    if initial_dir and os.path.isdir(initial_dir):
        ofn.lpstrInitialDir = initial_dir
    # OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_HIDEREADONLY | OFN_EXPLORER
    ofn.Flags = 0x1000 | 0x800 | 0x8 | 0x4 | 0x80000
    return buf.value if _comdlg.GetOpenFileNameW(ctypes.byref(ofn)) else None


def save_file(title: str, filters: list[tuple[str, str]], name: str = "", initial_dir: str | None = None) -> str | None:
    """A save dialog (asks before replacing a file). The first filter's first extension is added when none is typed."""
    spec = "".join(f"{label} ({pattern})\0{pattern}\0" for label, pattern in filters) + "\0"
    filt = ctypes.create_unicode_buffer(spec, len(spec) + 1)
    buf = ctypes.create_unicode_buffer(os.path.basename(name or "")[:4000], 4096)
    ext = ""
    if filters:
        first = filters[0][1].split(";")[0]
        if first.startswith("*.") and "*" not in first[2:]:
            ext = first[2:]
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = _user.GetForegroundWindow()
    ofn.lpstrFilter = ctypes.cast(filt, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = 4096
    ofn.lpstrTitle = title
    if ext:
        ofn.lpstrDefExt = ext
    if initial_dir and os.path.isdir(initial_dir):
        ofn.lpstrInitialDir = initial_dir
    # OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_HIDEREADONLY | OFN_EXPLORER
    ofn.Flags = 0x2 | 0x800 | 0x8 | 0x4 | 0x80000
    return buf.value if _comdlg.GetSaveFileNameW(ctypes.byref(ofn)) else None


def pick_folder(title: str, initial_dir: str | None = None) -> str | None:
    _ole.CoInitializeEx(None, 0x2)  # apartment-threaded, as the shell dialog wants
    try:
        start = ctypes.create_unicode_buffer(initial_dir) if initial_dir and os.path.isdir(initial_dir) else None

        def on_event(hwnd, msg, lparam, data):
            if msg == 1 and start is not None:  # BFFM_INITIALIZED -> BFFM_SETSELECTIONW
                _user.SendMessageW(hwnd, 0x467, 1, ctypes.addressof(start))
            return 0

        callback = BFFCALLBACK(on_event)
        name = ctypes.create_unicode_buffer(260)
        bi = BROWSEINFOW()
        bi.hwndOwner = _user.GetForegroundWindow()
        bi.pszDisplayName = ctypes.cast(name, wintypes.LPWSTR)
        bi.lpszTitle = title
        bi.ulFlags = 0x1 | 0x40 | 0x10  # BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_EDITBOX
        bi.lpfn = callback
        pidl = _shell.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None
        out = ctypes.create_unicode_buffer(1024)
        ok = _shell.SHGetPathFromIDListW(pidl, out)
        _ole.CoTaskMemFree(pidl)
        return out.value if ok else None
    finally:
        _ole.CoUninitialize()
