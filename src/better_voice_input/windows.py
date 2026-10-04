from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]


class GUIThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


@dataclass(frozen=True)
class InputTarget:
    window: int
    focus: int
    caret: tuple[int, int, int, int]
    process: int


def current_target() -> InputTarget | None:
    window = user32.GetForegroundWindow()
    if not window:
        return None
    pid = wintypes.DWORD()
    thread = user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    info = GUIThreadInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetGUIThreadInfo(thread, ctypes.byref(info)):
        return None
    rect = info.rcCaret
    return InputTarget(
        int(window), int(info.hwndFocus or 0), (rect.left, rect.top, rect.right, rect.bottom), pid.value
    )


def is_password(target: InputTarget) -> bool:
    # Native Edit controls expose ES_PASSWORD. Custom web fields may not expose it.
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW(target.focus, buffer, 256)
    return buffer.value.lower() == "edit" and bool(user32.GetWindowLongW(target.focus, -16) & 0x20)


HOTKEYS = {
    "Ctrl+Shift+Space": (0x0002 | 0x0004, 0x20),
    "Ctrl+Alt+Space": (0x0002 | 0x0001, 0x20),
    "Alt+Shift+Space": (0x0001 | 0x0004, 0x20),
}


def shortcut_held(name: str) -> bool:
    modifiers, key = HOTKEYS[name]
    keys = [key] + [vk for bit, vk in ((1, 0x12), (2, 0x11), (4, 0x10)) if modifiers & bit]
    return all(user32.GetAsyncKeyState(vk) & 0x8000 for vk in keys)


def modifiers_held() -> bool:
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


class HotkeyEvents(QObject):
    triggered = Signal(int)


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self):
        super().__init__()
        self.events = HotkeyEvents()
        self.registered: set[int] = set()

    def register(self, identifier: int, modifiers: int, key: int) -> bool:
        self.unregister(identifier)
        success = bool(user32.RegisterHotKey(None, identifier, modifiers | 0x4000, key))
        if success:
            self.registered.add(identifier)
        return success

    def unregister(self, identifier: int):
        if identifier in self.registered:
            user32.UnregisterHotKey(None, identifier)
            self.registered.discard(identifier)

    def close(self):
        for identifier in tuple(self.registered):
            self.unregister(identifier)

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and int(msg.wParam) in self.registered:
            self.events.triggered.emit(int(msg.wParam))
            return True, 0
        return False, 0


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


class PasteError(RuntimeError):
    pass


def paste_text(text: str, target: InputTarget, clipboard, restore_callback=None) -> None:
    """Paste once, with a focus check immediately before the Win32 input call."""
    from PySide6.QtCore import QMimeData

    if not text.strip():
        raise PasteError("没有可输入的文字。")
    if not user32.IsWindow(target.window) or current_target() != target:
        raise PasteError("输入位置已经变化，结果已保留。请回到目标输入框后按 Ctrl+Alt+V。")
    if is_password(target):
        raise PasteError("密码输入框不支持自动输入，请切换到普通文本框。")
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(target.window, class_name, 256)
    if class_name.value.lower() in ("consolewindowclass", "cascadia_hosting_window_class", "mintty"):
        raise PasteError("终端窗口请使用复制结果后手动粘贴，避免多行文字被当作命令执行。")
    if modifiers_held():
        raise PasteError("请松开快捷键后重试输入。")
    original = QMimeData()
    mime = clipboard.mimeData()
    if mime:
        for format_name in mime.formats():
            original.setData(format_name, mime.data(format_name))
    clipboard.setText(text)
    sequence = user32.GetClipboardSequenceNumber()

    def restore():
        if user32.GetClipboardSequenceNumber() == sequence:
            clipboard.setMimeData(original)
        if restore_callback:
            restore_callback()

    if current_target() != target:
        restore()
        raise PasteError("输入位置已经变化，已取消自动输入。")
    events = (INPUT * 4)()
    for event, (key, flags) in zip(events, ((0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)), strict=True):
        event.type = 1
        event.ki = KEYBDINPUT(key, 0, flags, 0, 0)
    sent = user32.SendInput(4, ctypes.byref(events), ctypes.sizeof(INPUT))
    QTimer.singleShot(1000, restore)
    if sent != 4:
        # Always release the simulated keys if Windows accepted only part of the input.
        releases = (INPUT * 2)(events[2], events[3])
        user32.SendInput(2, ctypes.byref(releases), ctypes.sizeof(INPUT))
        raise PasteError("Windows 未完成输入，可能是目标程序权限较高。请复制结果后手动粘贴。")
