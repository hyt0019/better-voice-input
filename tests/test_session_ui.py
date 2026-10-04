import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from better_voice_input.app import MainWindow
from better_voice_input.core import CleanupResult
from better_voice_input.session import SessionGate
from better_voice_input.settings import Settings
from better_voice_input.ui import STYLE


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


def test_warnings_always_require_preview(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: None)
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


def test_target_change_prevents_automatic_input(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "attempt_insert", lambda *args: calls.append(args))
    monkeypatch.setattr(window, "reveal", lambda: None)
    job, _ = window.begin("busy")
    window.target = object()
    window.target_changed = True
    window.on_complete(job, {"result": CleanupResult("你好", "你好。"), "asr_seconds": 1, "duration": 1})
    assert not calls
    assert "输入位置" in window.notice.text()


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
    assert "api_key" not in path.read_text()


def test_cancelled_pipeline_never_calls_api(window, monkeypatch):
    calls = []
    monkeypatch.setattr("better_voice_input.pipeline.DeepSeekCleaner", lambda *args: calls.append(args))
    event = threading.Event()
    event.set()
    window.pipeline._run(1, event, Settings(), "一段文字", "text")
    assert not calls
