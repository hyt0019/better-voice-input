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
from better_voice_input.ui import STYLE
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


def test_optional_review_pauses_input_without_showing_main_window(window, monkeypatch):
    window.settings.review_warnings = True
    window.from_hotkey = True
    calls = []
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("Global recording must not steal focus"))
    job, _ = window.begin("busy")
    window.target = object()
    window.on_complete(
        job,
        {
            "result": CleanupResult("预算不是5000", "预算5000", ("核对数字",)),
            "asr_seconds": 1,
            "duration": 10,
        },
    )
    assert not calls
    assert "核对数字" in window.notice.text()
    assert window.result.toPlainText() == "预算5000"
    assert window.overlay.isVisible()


def test_target_change_prevents_automatic_input(window, monkeypatch):
    window.from_hotkey = True
    calls = []
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: pytest.fail("Focus change must not open main window"))
    job, _ = window.begin("busy")
    window.target = object()
    window.target_changed = True
    window.on_complete(job, {"result": CleanupResult("你好", "你好。"), "asr_seconds": 1, "duration": 1})
    assert not calls
    assert "输入位置" in window.notice.text()


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
    settings = Settings(glossary=["项目甲"], hold_to_talk=True, auto_insert=False)
    settings.save(path)
    assert Settings.load(path) == settings
    assert "api_key" not in path.read_text(encoding="utf-8")


def test_cancelled_pipeline_never_calls_api(window, monkeypatch):
    calls = []
    monkeypatch.setattr("better_voice_input.pipeline.DeepSeekCleaner", lambda *args: calls.append(args))
    event = threading.Event()
    event.set()
    window.pipeline._run(1, event, Settings(), "一段文字", "text")
    assert not calls
