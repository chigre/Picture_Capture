from __future__ import annotations

"""Windows/Tk 8.6 compatibility for direct non-BMP Unicode text input.

Tk 8.6 on Windows can lose supplementary-plane characters while translating
WM_CHAR messages through its historical ANSI key-input path. A typical CJK
Extension-B character (for example U+28906) may therefore reach an Entry as
``??`` even though Python strings and the project's UTF-8 persistence layer can
store it perfectly.

The compatibility bridge is deliberately narrow:

* active only on Windows with Tk < 9;
* observes committed IME result strings through the Unicode IMM32 API;
* also watches WM_CHAR surrogate pairs when Windows exposes them to the thread
  message hook;
* repairs only commits containing at least one code point above U+FFFF;
* normal BMP input, shortcuts and widget bindings remain owned by Tk.

No OCR, PDIC, collation or normalization semantics are changed here.
"""

from collections import deque
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import platform
import time
from typing import Any


WM_CHAR = 0x0102
WM_IME_STARTCOMPOSITION = 0x010D
WM_IME_ENDCOMPOSITION = 0x010E
WM_IME_COMPOSITION = 0x010F
GCS_RESULTSTR = 0x0800
WH_GETMESSAGE = 3
WH_CALLWNDPROC = 4


@dataclass(frozen=True)
class TextSnapshot:
    text: str
    insert: int
    selection: tuple[int, int] | None = None


@dataclass(frozen=True)
class NativeCommit:
    text: str
    source: str
    created_at: float


def contains_non_bmp(text: str) -> bool:
    return any(ord(char) > 0xFFFF for char in str(text or ""))


def legacy_tk_renderings(text: str) -> tuple[str, ...]:
    """Return common Tk-8.6 damaged representations of a Unicode commit."""
    question: list[str] = []
    replacement: list[str] = []
    for char in str(text or ""):
        if ord(char) <= 0xFFFF:
            question.append(char)
            replacement.append(char)
            continue
        units = max(2, len(char.encode("utf-16-le")) // 2)
        question.append("?" * units)
        replacement.append("\ufffd" * units)
    values: list[str] = []
    for value in ("".join(question), "".join(replacement)):
        if value and value != text and value not in values:
            values.append(value)
    return tuple(values)


def plan_non_bmp_repair(
    current: TextSnapshot,
    committed: str,
    previous: TextSnapshot | None = None,
) -> TextSnapshot | None:
    """Plan a conservative repair after Tk has processed one native commit."""
    committed = str(committed or "")
    if not committed or not contains_non_bmp(committed):
        return None

    text = str(current.text)
    insert = max(0, min(len(text), int(current.insert)))
    start = max(0, insert - len(committed))
    if text[start:insert] == committed:
        return None

    for damaged in legacy_tk_renderings(committed):
        if len(damaged) <= insert and text[insert - len(damaged):insert] == damaged:
            left = insert - len(damaged)
            repaired = text[:left] + committed + text[insert:]
            return TextSnapshot(repaired, left + len(committed), None)

    if previous is None:
        return None

    previous_text = str(previous.text)
    old_insert = max(0, min(len(previous_text), int(previous.insert)))
    if previous.selection is not None:
        lo, hi = sorted((int(previous.selection[0]), int(previous.selection[1])))
        lo = max(0, min(len(previous_text), lo))
        hi = max(lo, min(len(previous_text), hi))
        base = previous_text[:lo] + previous_text[hi:]
        old_insert = lo
    else:
        base = previous_text

    expected = base[:old_insert] + committed + base[old_insert:]
    if text == expected:
        return None
    if text == base:
        return TextSnapshot(expected, old_insert + len(committed), None)

    for damaged in legacy_tk_renderings(committed):
        broken = base[:old_insert] + damaged + base[old_insert:]
        if text == broken:
            return TextSnapshot(expected, old_insert + len(committed), None)
    return None


def _python_index_from_tk_units(text: str, tk_units: int) -> int:
    """Translate Tk-8.6/Windows UTF-16-style units to a Python string index."""
    target = max(0, int(tk_units))
    units = 0
    for index, char in enumerate(str(text)):
        step = 2 if ord(char) > 0xFFFF else 1
        if units + step > target:
            return index
        units += step
        if units == target:
            return index + 1
    return len(str(text))


def _tk_units_from_python_prefix(text: str, python_index: int) -> int:
    prefix = str(text)[: max(0, int(python_index))]
    return sum(2 if ord(char) > 0xFFFF else 1 for char in prefix)


def _read_widget_snapshot(widget: Any) -> TextSnapshot | None:
    try:
        klass = str(widget.winfo_class())
        if klass in {"Entry", "TEntry"}:
            text = str(widget.get())
            insert = _python_index_from_tk_units(text, int(widget.index("insert")))
            selection = None
            try:
                if bool(widget.selection_present()):
                    first = _python_index_from_tk_units(text, int(widget.index("sel.first")))
                    last = _python_index_from_tk_units(text, int(widget.index("sel.last")))
                    selection = (first, last)
            except Exception:
                selection = None
            return TextSnapshot(text, insert, selection)
        if klass == "Text":
            text = str(widget.get("1.0", "end-1c"))
            units = int(widget.count("1.0", "insert", "chars")[0])
            insert = _python_index_from_tk_units(text, units)
            selection = None
            try:
                ranges = widget.tag_ranges("sel")
                if len(ranges) >= 2:
                    first_units = int(widget.count("1.0", ranges[0], "chars")[0])
                    last_units = int(widget.count("1.0", ranges[1], "chars")[0])
                    selection = (
                        _python_index_from_tk_units(text, first_units),
                        _python_index_from_tk_units(text, last_units),
                    )
            except Exception:
                selection = None
            return TextSnapshot(text, insert, selection)
    except Exception:
        return None
    return None


def _write_widget_snapshot(widget: Any, state: TextSnapshot) -> bool:
    try:
        klass = str(widget.winfo_class())
        if klass in {"Entry", "TEntry"}:
            widget.delete(0, "end")
            widget.insert(0, state.text)
            widget.icursor(_tk_units_from_python_prefix(state.text, state.insert))
            return True
        if klass == "Text":
            widget.delete("1.0", "end")
            widget.insert("1.0", state.text)
            units = _tk_units_from_python_prefix(state.text, state.insert)
            widget.mark_set("insert", f"1.0 + {units} chars")
            return True
    except Exception:
        return False
    return False


class _WindowsNonBmpBridge:
    """Observe native Unicode commits and repair Tk 8.6 after message handling."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._commits: deque[NativeCommit] = deque()
        self._last_snapshot: tuple[Any, TextSnapshot, float] | None = None
        self._composition_snapshot: tuple[Any, TextSnapshot, float] | None = None
        self._composition_active = False
        self._pending_high_surrogate: int | None = None
        self._hook_getmessage = None
        self._hook_callwndproc = None
        self._getmessage_callback = None
        self._callwndproc_callback = None
        self._last_native: tuple[str, float] | None = None
        self._closed = False
        self._install_hooks()
        self._schedule_poll()

    @staticmethod
    def _read_ime_result(hwnd: int) -> str:
        imm32 = ctypes.windll.imm32
        imm32.ImmGetContext.argtypes = [wintypes.HWND]
        imm32.ImmGetContext.restype = wintypes.HANDLE
        imm32.ImmGetCompositionStringW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        imm32.ImmGetCompositionStringW.restype = wintypes.LONG
        imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        imm32.ImmReleaseContext.restype = wintypes.BOOL

        target = wintypes.HWND(hwnd)
        himc = imm32.ImmGetContext(target)
        if not himc:
            return ""
        try:
            size = int(imm32.ImmGetCompositionStringW(himc, GCS_RESULTSTR, None, 0))
            if size <= 0:
                return ""
            buffer = ctypes.create_string_buffer(size + 2)
            copied = int(
                imm32.ImmGetCompositionStringW(
                    himc,
                    GCS_RESULTSTR,
                    ctypes.cast(buffer, ctypes.c_void_p),
                    size,
                )
            )
            if copied <= 0:
                return ""
            return bytes(buffer.raw[:copied]).decode("utf-16-le", errors="surrogatepass")
        finally:
            imm32.ImmReleaseContext(target, himc)

    def _queue_commit(self, text: str, source: str) -> None:
        text = str(text or "")
        if not contains_non_bmp(text):
            return
        now = time.monotonic()
        if self._last_native is not None:
            previous_text, previous_at = self._last_native
            if previous_text == text and now - previous_at < 0.12:
                return
        self._last_native = (text, now)
        self._commits.append(NativeCommit(text, source, now))

    def _install_hooks(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        lresult_type = ctypes.c_ssize_t
        hhook_type = wintypes.HANDLE

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]

        class CWPSTRUCT(ctypes.Structure):
            _fields_ = [
                ("lParam", wintypes.LPARAM),
                ("wParam", wintypes.WPARAM),
                ("message", wintypes.UINT),
                ("hwnd", wintypes.HWND),
            ]

        hook_proc_type = ctypes.WINFUNCTYPE(
            lresult_type,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.CallNextHookEx.argtypes = [
            hhook_type,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = lresult_type
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            hook_proc_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = hhook_type
        user32.UnhookWindowsHookEx.argtypes = [hhook_type]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        @hook_proc_type
        def getmessage_proc(code, wparam, lparam):
            try:
                if code >= 0 and lparam:
                    msg = ctypes.cast(lparam, ctypes.POINTER(MSG)).contents
                    if int(msg.message) == WM_CHAR:
                        unit = int(msg.wParam) & 0xFFFF
                        if 0xD800 <= unit <= 0xDBFF:
                            self._pending_high_surrogate = unit
                        elif 0xDC00 <= unit <= 0xDFFF and self._pending_high_surrogate is not None:
                            high = self._pending_high_surrogate
                            self._pending_high_surrogate = None
                            codepoint = 0x10000 + ((high - 0xD800) << 10) + (unit - 0xDC00)
                            if codepoint <= 0x10FFFF:
                                self._queue_commit(chr(codepoint), "wm_char")
                        elif unit not in {0, 0xFFFF}:
                            self._pending_high_surrogate = None
            except Exception:
                pass
            return user32.CallNextHookEx(self._hook_getmessage, code, wparam, lparam)

        @hook_proc_type
        def callwndproc_proc(code, wparam, lparam):
            try:
                if code >= 0 and lparam:
                    packet = ctypes.cast(lparam, ctypes.POINTER(CWPSTRUCT)).contents
                    message = int(packet.message)
                    if message == WM_IME_STARTCOMPOSITION:
                        self._composition_active = True
                        self._composition_snapshot = None
                    elif message == WM_IME_ENDCOMPOSITION:
                        self._composition_active = False
                    elif message == WM_IME_COMPOSITION and (int(packet.lParam) & GCS_RESULTSTR):
                        hwnd = int(packet.hwnd or 0)
                        committed = self._read_ime_result(hwnd) if hwnd else ""
                        if committed:
                            self._queue_commit(committed, "ime")
            except Exception:
                pass
            return user32.CallNextHookEx(self._hook_callwndproc, code, wparam, lparam)

        thread_id = int(kernel32.GetCurrentThreadId())
        self._getmessage_callback = getmessage_proc
        self._callwndproc_callback = callwndproc_proc
        self._hook_getmessage = user32.SetWindowsHookExW(
            WH_GETMESSAGE, getmessage_proc, None, thread_id
        )
        self._hook_callwndproc = user32.SetWindowsHookExW(
            WH_CALLWNDPROC, callwndproc_proc, None, thread_id
        )

    def _capture_focus(self) -> tuple[Any, TextSnapshot, float] | None:
        try:
            widget = self.app.focus_get()
        except Exception:
            return None
        if widget is None:
            return None
        snapshot = _read_widget_snapshot(widget)
        if snapshot is None:
            return None
        return widget, snapshot, time.monotonic()

    def _process_one(self, commit: NativeCommit) -> None:
        focused = self._capture_focus()
        if focused is None:
            return
        widget, current, _now = focused
        previous = None
        candidate = self._composition_snapshot or self._last_snapshot
        if candidate is not None:
            previous_widget, previous_state, previous_at = candidate
            if previous_widget is widget and commit.created_at - previous_at < 3.0:
                previous = previous_state

        planned = plan_non_bmp_repair(current, commit.text, previous)
        if planned is None:
            return
        if _write_widget_snapshot(widget, planned):
            try:
                widget.event_generate("<<Modified>>")
            except Exception:
                pass

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            while self._commits:
                self._process_one(self._commits.popleft())

            focused = self._capture_focus()
            if focused is not None:
                self._last_snapshot = focused
                if self._composition_active and self._composition_snapshot is None:
                    self._composition_snapshot = focused
            if not self._composition_active:
                self._composition_snapshot = None
        finally:
            self._schedule_poll()

    def _schedule_poll(self) -> None:
        if self._closed:
            return
        try:
            self.app.after(8, self._poll)
        except Exception:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            user32 = ctypes.windll.user32
            if self._hook_getmessage:
                user32.UnhookWindowsHookEx(self._hook_getmessage)
            if self._hook_callwndproc:
                user32.UnhookWindowsHookEx(self._hook_callwndproc)
        except Exception:
            pass
        self._hook_getmessage = None
        self._hook_callwndproc = None
        self._getmessage_callback = None
        self._callwndproc_callback = None


def _needs_windows_tk8_bridge(app: Any) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        patchlevel = str(app.tk.call("info", "patchlevel"))
        major = int(patchlevel.split(".", 1)[0])
    except Exception:
        major = 8
    return major < 9


def attach_nonbmp_unicode_input(app: Any) -> Any | None:
    """Attach the Windows/Tk 8 compatibility bridge after app initialization."""
    existing = getattr(app, "_pc_nonbmp_unicode_bridge", None)
    if existing is not None:
        return existing

    app._pc_nonbmp_unicode_bridge = None
    if not _needs_windows_tk8_bridge(app):
        return None
    try:
        bridge = _WindowsNonBmpBridge(app)
    except Exception:
        return None
    app._pc_nonbmp_unicode_bridge = bridge
    return bridge


def close_nonbmp_unicode_input(app: Any) -> None:
    """Close and detach the app-level compatibility bridge if one is active."""
    bridge = getattr(app, "_pc_nonbmp_unicode_bridge", None)
    if bridge is None:
        return
    try:
        bridge.close()
    except Exception:
        pass
    finally:
        app._pc_nonbmp_unicode_bridge = None


__all__ = [
    "NativeCommit",
    "TextSnapshot",
    "attach_nonbmp_unicode_input",
    "close_nonbmp_unicode_input",
    "contains_non_bmp",
    "legacy_tk_renderings",
    "plan_non_bmp_repair",
]
