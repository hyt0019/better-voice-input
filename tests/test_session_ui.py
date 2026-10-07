import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from better_voice_input.app import MainWindow
from better_voice_input.core import CleanupResult
from better_voice_input.session import SessionGate
from better_voice_input.settings import Settings
from better_voice_input.ui import STYLE, SettingsDialog
from better_voice_input.windows import InputTarget, PasteError


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    return app


@pytest.fixture
def window(qt_app):
    widget = MainWindow(Settings(), native=False)
    yield widget
    widget.shutdown()
    widget.close()


def test_session_rejects_stale_cancelled_and_duplicate_results():
    gate = SessionGate()
    first, event = gate.begin()
    second, _ = gate.begin()
    assert event.is_set()
    assert not gate.accepts(first)
    assert gate.claim_insert(second)
    assert not gate.claim_insert(second)
    gate.cancel()
    assert not gate.accepts(second)


def test_cancel_does_not_allow_late_result_to_replace_text(window):
    job, _ = window.begin("busy")
    window.original.setPlainText("保留原文")
    window.cancel()
    window.on_complete(
        job, {"result": CleanupResult("old", "错误的迟到结果"), "asr_seconds": 0, "duration": 0}
    )
    assert window.original.toPlainText() == "保留原文"
    assert window.result.toPlainText() == ""
    assert window.state == "idle"


def test_long_ambiguous_result_is_inserted_without_review(window, monkeypatch):
    window.from_hotkey = True
    calls = []
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("Global recording must not steal focus"))
    job, _ = window.begin("busy")
    window.target = object()
    window.on_complete(
        job,
        {
            "result": CleanupResult("预算不是5000。" * 100, "预算不是5000。" * 100, ("核对数字",)),
            "asr_seconds": 1,
            "duration": 110,
        },
    )
    assert calls == [(job, window.target)]
    assert "核对数字" in window.notice.text()
    assert window.result.toPlainText() == "预算不是5000。" * 100


def test_hold_release_cleanup_and_automatic_input_stay_in_background(window, monkeypatch):
    target = InputTarget(1, 2, (3, 4, 5, 6), os.getpid() + 1)
    recording = []
    jobs = []
    pastes = []
    held = [True]
    samples = object()
    monkeypatch.setattr("better_voice_input.app.models_ready", lambda _: True)
    monkeypatch.setattr("better_voice_input.app.current_target", lambda: target)
    monkeypatch.setattr("better_voice_input.app.shortcut_held", lambda _: held[0])
    monkeypatch.setattr("better_voice_input.app.modifiers_held", lambda: False)
    monkeypatch.setattr(
        "better_voice_input.app.paste_text", lambda text, dest, _: pastes.append((text, dest))
    )
    monkeypatch.setattr(window.recorder, "start", lambda _: recording.append("start"))
    monkeypatch.setattr(window.recorder, "stop", lambda: samples)
    monkeypatch.setattr(window.pipeline, "start", lambda *args: jobs.append(args))
    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("Dictation must not activate main window"))
    window.recorder.started = time.monotonic()

    window.on_hotkey(1)
    window.on_hotkey(1)  # A repeat notification must not stop hold-to-talk.
    window.tick()
    assert recording == ["start"]
    assert window.state == "recording"
    assert not jobs
    assert window.target == target
    assert not window.isVisible()

    # A temporarily unavailable foreground snapshot during a long recording
    # must not permanently prevent insertion when the original field returns.
    window.recorder.started = time.monotonic() - 75
    monkeypatch.setattr("better_voice_input.app.current_target", lambda: None)
    window.tick()
    monkeypatch.setattr("better_voice_input.app.current_target", lambda: target)
    held[0] = False
    window.tick()
    window.tick()
    assert window.state == "busy"
    assert len(jobs) == 1 and jobs[0][3] is samples
    job = jobs[0][0]
    data = {"result": CleanupResult("明天，不对后天开会", "后天开会。"), "asr_seconds": 1, "duration": 4}
    window.on_complete(job, data)
    window.on_complete(job, data)  # Duplicate delivery must not insert twice.
    assert pastes == [("后天开会。", target)]
    assert window.gate.inserted
    assert not window.isVisible()


def test_default_keeps_warnings_available_without_interrupting_dictation(window, monkeypatch):
    window.from_hotkey = True
    calls = []
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("Warnings must not open main window"))
    job, _ = window.begin("busy")
    window.target = object()
    result = CleanupResult("项目名称", "项目名称。", ("请核对专有名词",))
    window.on_complete(job, {"result": result, "asr_seconds": 1, "duration": 2})
    assert calls == [(job, window.target)]
    assert "请核对专有名词" in window.notice.text()


@pytest.mark.parametrize("failure", ["models", "microphone", "pipeline", "paste"])
def test_global_errors_keep_main_window_hidden(window, monkeypatch, failure):
    from better_voice_input.audio import AudioError

    def mic_failure(_):
        raise AudioError("麦克风不可用")

    def paste_failure(*_):
        raise PasteError("无法输入")

    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("Errors must not steal focus"))
    monkeypatch.setattr("better_voice_input.app.current_target", lambda: None)
    monkeypatch.setattr("better_voice_input.app.models_ready", lambda _: failure != "models")
    monkeypatch.setattr("better_voice_input.app.modifiers_held", lambda: False)
    window.from_hotkey = True
    if failure in ("models", "microphone"):
        monkeypatch.setattr(window.recorder, "start", mic_failure)
        window.on_hotkey(1)
    elif failure == "pipeline":
        job, _ = window.begin("busy")
        window.on_error(job, "网络异常")
    else:
        monkeypatch.setattr("better_voice_input.app.paste_text", paste_failure)
        job, _ = window.gate.begin()
        window.result.setPlainText("保留结果")
        window.attempt_insert(job, object())
        assert not window.gate.inserted
    assert window.state == "idle"
    assert window.notice.text()
    assert window.overlay.isVisible()
    assert not window.isVisible()


def test_status_overlay_cannot_take_keyboard_focus(window):
    overlay = window.overlay
    assert overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    overlay.show_message("已输入", "继续录音")
    assert overlay.dismiss_timer.isActive()
    overlay.show_near_bottom()
    assert not overlay.dismiss_timer.isActive()  # Previous toast cannot hide a new recording.


def test_manual_cleanup_after_dictation_does_not_reuse_background_target(window, monkeypatch):
    window.from_hotkey = True
    window.target = object()
    window.original.setPlainText("需要整理的文字")
    monkeypatch.setattr(window.pipeline, "start", lambda *args: None)
    window.clean_text()
    assert not window.from_hotkey
    assert window.target is None


def test_failure_preserves_raw_and_unlocks_ui(window, monkeypatch):
    monkeypatch.setattr(window, "reveal", lambda: None)
    job, _ = window.begin("busy")
    window.original.setPlainText("重要原文")
    window.on_error(job, "网络异常")
    assert window.original.toPlainText() == "重要原文"
    assert window.clean_button.isEnabled()
    assert not window.original.isReadOnly()


def test_clear_invalidates_queued_tasks(window):
    job, _ = window.gate.begin()
    window.result.setPlainText("旧结果")
    window.clear()
    assert not window.gate.accepts(job)
    assert not window.result.toPlainText()


def test_settings_roundtrip_contains_no_key(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(glossary=["项目甲"], hold_to_talk=True)
    settings.save(path)
    assert Settings.load(path) == settings
    assert "api_key" not in path.read_text(encoding="utf-8")


def test_settings_dialog_startup_choice_is_optional_and_saved(window):
    dialog = SettingsDialog(Settings(), window)
    assert not dialog.startup.isChecked()
    dialog.startup.setChecked(True)
    dialog.save()
    assert dialog.updated.start_on_login
    dialog.close()


def test_failed_startup_change_keeps_existing_window_settings(window, monkeypatch):
    from better_voice_input.startup import StartupError

    class Dialog:
        def __init__(self, settings, parent):
            self.updated = Settings(start_on_login=True)

        def exec(self):
            return 1  # QDialog.Accepted

    def deny_save(_):
        raise StartupError("无法修改开机自启动设置")

    monkeypatch.setattr("better_voice_input.app.SettingsDialog", Dialog)
    monkeypatch.setattr("better_voice_input.app.startup_enabled", lambda: False)
    monkeypatch.setattr("better_voice_input.app.save_settings_with_startup", deny_save)
    window.open_settings()
    assert not window.settings.start_on_login
    assert "无法修改开机自启动" in window.notice.text()


def test_cancelled_pipeline_never_calls_api(window, monkeypatch):
    calls = []
    monkeypatch.setattr("better_voice_input.pipeline.DeepSeekCleaner", lambda *args: calls.append(args))
    event = threading.Event()
    event.set()
    window.pipeline._run(1, event, Settings(), "一段文字", "text")
    assert not calls


@pytest.mark.parametrize("cancelled", [False, True])
def test_audio_api_failure_inserts_original_unless_cancelled(window, monkeypatch, cancelled):
    from types import SimpleNamespace
    from better_voice_input.cleanup import Cancelled, CleanupError

    calls = []
    source = "周三或者周四，还没确定。" * 60
    window.from_hotkey = True
    window.target = object()
    job, cancel = window.begin("busy")
    window.pipeline.recognizer = SimpleNamespace(
        directory=window.settings.models, transcribe=lambda *args: source
    )

    def clean(*args):
        if cancelled:
            cancel.set()
            raise Cancelled("取消")
        raise CleanupError("返回内容不完整")

    monkeypatch.setattr("better_voice_input.pipeline.read_key", lambda *args, **kwargs: "test")
    monkeypatch.setattr(
        "better_voice_input.pipeline.DeepSeekCleaner", lambda *args, **kwargs: SimpleNamespace(clean=clean)
    )
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("No review window during dictation"))
    window.pipeline._run(job, cancel, window.settings, SimpleNamespace(size=120 * 16000), "audio")
    assert bool(calls) is not cancelled
    if not cancelled:
        assert window.result.toPlainText() == source
        assert "识别原文" in window.notice.text()


@pytest.mark.parametrize("change", ["caret", "window", "focus", "process", "unavailable"])
def test_paste_ignores_caret_geometry_but_checks_destination(window, monkeypatch, change):
    from dataclasses import replace
    from better_voice_input import windows

    target = InputTarget(100, 101, (1, 2, 3, 4), 200)
    changes = {"caret": (0, 0, 0, 0), "window": 102, "focus": 103, "process": 201}
    current = None if change == "unavailable" else replace(target, **{change: changes[change]})
    sent = []
    clipboard = QApplication.clipboard()
    clipboard.setText("previous")
    monkeypatch.setattr(windows, "current_target", lambda: current)
    monkeypatch.setattr(windows, "is_password", lambda _: False)
    monkeypatch.setattr(windows, "modifiers_held", lambda: False)
    monkeypatch.setattr(windows.user32, "IsWindow", lambda _: True)
    monkeypatch.setattr(windows.user32, "GetClassNameW", lambda *args: 0)
    monkeypatch.setattr(windows.user32, "SendInput", lambda count, *args: sent.append(count) or count)
    monkeypatch.setattr(windows.QTimer, "singleShot", lambda *args: None)
    if change == "caret":
        windows.paste_text("较长的整理结果。" * 100, target, clipboard)
        assert sent == [4]
    else:
        with pytest.raises(PasteError, match="输入位置"):
            windows.paste_text("结果", target, clipboard)
        assert not sent
        assert clipboard.text() == "previous"
