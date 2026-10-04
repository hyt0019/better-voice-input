"""Verify hotkeys and paste only against this script's own native test window."""

import ctypes
import json
import os

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from better_voice_input.windows import Hotkeys, INPUT, KEYBDINPUT, current_target, paste_text, user32

app = QApplication([])
window = QWidget()
window.setWindowTitle("Better Voice Input — isolated input test")
layout = QVBoxLayout(window)
layout.addWidget(QLabel("仅用于验证当前测试窗口的快捷键和粘贴，稍后自动关闭。"))
editor = QPlainTextEdit()
layout.addWidget(editor)
window.resize(600, 240)
hotkeys = Hotkeys()
app.installNativeEventFilter(hotkeys)
result = {
    "hotkey_registered": hotkeys.register(91, 2 | 4, 0x20),
    "hotkey_received": False,
    "paste_matches": False,
    "clipboard_restored": False,
}
hotkeys.events.triggered.connect(lambda identifier: result.update(hotkey_received=identifier == 91))
saved = QMimeData()
old = app.clipboard().mimeData()
if old:
    for format_name in old.formats():
        saved.setData(format_name, old.data(format_name))
window.show()
window.activateWindow()
editor.setFocus()
result["activated"] = bool(user32.SetForegroundWindow(int(window.winId())))


def verify_focus():
    target = current_target()
    return target and target.process == os.getpid()


def trigger():
    if not verify_focus() or not result["hotkey_registered"]:
        result["error"] = "Test window is not focused or hotkey unavailable; no input was sent."
        finish()
        return
    events = (INPUT * 6)()
    for event, (key, flags) in zip(
        events, ((0x11, 0), (0x10, 0), (0x20, 0), (0x20, 2), (0x10, 2), (0x11, 2)), strict=True
    ):
        event.type = 1
        event.ki = KEYBDINPUT(key, 0, flags, 0, 0)
    user32.SendInput(6, ctypes.byref(events), ctypes.sizeof(INPUT))
    QTimer.singleShot(300, paste)


def paste():
    if not verify_focus():
        result["error"] = "Focus changed; no paste was sent."
        finish()
        return
    app.clipboard().setText("BVI clipboard restore sentinel")
    try:
        paste_text("语音输入测试 123", current_target(), app.clipboard())
    except Exception as exc:
        result["error"] = str(exc)
    QTimer.singleShot(1400, finish)


def finish():
    result["paste_matches"] = editor.toPlainText() == "语音输入测试 123"
    result["clipboard_restored"] = app.clipboard().text() == "BVI clipboard restore sentinel"
    if result["clipboard_restored"]:
        app.clipboard().setMimeData(saved)
    hotkeys.close()
    app.removeNativeEventFilter(hotkeys)
    print(json.dumps(result), flush=True)
    app.exit(
        0
        if all(
            result.get(k)
            for k in ("hotkey_registered", "hotkey_received", "paste_matches", "clipboard_restored")
        )
        else 1
    )


QTimer.singleShot(700, trigger)
raise SystemExit(app.exec())
