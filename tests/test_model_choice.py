import hashlib
import json
import os
import threading
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from better_voice_input import models, settings as settings_module, ui
from better_voice_input.asr import join_segments, tidy_spacing
from better_voice_input.cleanup import Cancelled
from better_voice_input.models import CATALOG, SENSE_VOICE, VAD, AsrModel, ModelFile, download_model, get_model
from better_voice_input.pipeline import ModelDownloads, Pipeline
from better_voice_input.settings import Settings
from better_voice_input.ui import STYLE, ModelDialog


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    yield app
    app.clipboard().clear()


def test_catalog_keeps_sensevoice_in_place_and_every_model_is_self_contained():
    assert [model.id for model in CATALOG] == ["sensevoice", "xasr", "canary"]
    assert SENSE_VOICE.folder == "" and Settings().asr_model == "sensevoice"
    assert models.FILES == SENSE_VOICE.files
    folders = [model.folder for model in CATALOG]
    assert len(set(folders)) == len(folders)
    for model in CATALOG:
        assert VAD in model.files
        assert len(model.strengths) == 3 and model.tagline and model.caveat
        assert all(spec.url.startswith("https://") and spec.size > 0 for spec in model.files)
        # Pinned revisions keep the verified digests valid.
        assert all("/resolve/main/" not in spec.url for spec in model.files)
    assert get_model("missing") is SENSE_VOICE


def test_changing_download_location_keeps_downloaded_models_in_place(tmp_path, monkeypatch):
    old, new = tmp_path / "old", tmp_path / "new"
    monkeypatch.setattr(settings_module, "models_ready", lambda directory, model: model.id in ("sensevoice", "xasr"))
    value = Settings(model_dir=str(old), asr_model="xasr")
    assert value.models == old / "x-asr-zh-en"
    moved = value.with_download_root(new)
    assert moved.download_root == new
    assert moved.model_path("sensevoice") == old
    assert moved.models == old / "x-asr-zh-en"
    assert moved.model_path("canary") == new / "canary-180m-flash"


def test_model_settings_roundtrip_and_reject_unknown_values(tmp_path):
    path = tmp_path / "settings.json"
    value = Settings(asr_model="canary", download_dir="D:/models", model_paths={"xasr": "E:/x"})
    value.save(path)
    assert Settings.load(path) == value
    path.write_text(
        json.dumps({"asr_model": "qwen3", "model_paths": {"canary": 5, "qwen3": "x", "xasr": "E:/x", "sensevoice": ""}}),
        encoding="utf-8",
    )
    loaded = Settings.load(path)
    assert loaded.asr_model == "sensevoice"
    assert loaded.model_paths == {"xasr": "E:/x"}


def test_transcript_spacing_and_segment_joining():
    assert tidy_spacing("嗯， 我想安排， 先做 Windows 桌面版本 。 测试 API 还有 （备注） 好 的") == (
        "嗯，我想安排，先做 Windows 桌面版本。测试 API 还有（备注）好的"
    )
    assert join_segments(["Hello world.", "Next", "你好。", "下一句"]) == "Hello world. Next你好。下一句"


def fake_model(files: dict[str, bytes]) -> AsrModel:
    specs = tuple(
        ModelFile(name, f"https://models.example/{name}", len(data), hashlib.sha256(data).hexdigest())
        for name, data in files.items()
    )
    return AsrModel("fake", "Fake", "sense_voice", "fake", "", ("a", "b", "c"), "", "", specs)


def mock_client(monkeypatch, files: dict[str, bytes], requests: list, hold: threading.Event | None = None):
    real = httpx.Client

    def handler(request):
        requests.append(request.url.path)
        name = request.url.path.lstrip("/")
        if hold:
            hold.wait(5)
        return httpx.Response(200, content=files[name])

    monkeypatch.setattr(models.httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))


def test_download_creates_nested_files_verifies_and_reuses(tmp_path, monkeypatch):
    files = {"model.onnx": b"weights" * 100, "tokenizer/vocab.json": b'{"a": 1}'}
    requests, progress = [], []
    mock_client(monkeypatch, files, requests)
    model = fake_model(files)
    download_model(model, tmp_path / "m", lambda value, name: progress.append(value))
    assert (tmp_path / "m" / "tokenizer" / "vocab.json").read_bytes() == files["tokenizer/vocab.json"]
    assert models.models_ready(tmp_path / "m", verify=True, model=model)
    assert progress[-1] == 100
    assert not list((tmp_path / "m").rglob("*.part"))
    requests.clear()
    download_model(model, tmp_path / "m")
    assert requests == []  # Verified files are reused, not downloaded again.


def test_corrupt_download_is_rejected_and_cleaned(tmp_path, monkeypatch):
    files = {"model.onnx": b"weights"}
    model = fake_model(files)
    mock_client(monkeypatch, {"model.onnx": b"tampers"}, [])
    with pytest.raises(models.ModelError, match="校验失败"):
        download_model(model, tmp_path)
    assert not list(tmp_path.iterdir())


def test_cancelled_download_leaves_no_partial_file(tmp_path, monkeypatch):
    files = {"model.onnx": b"x" * 1000}
    cancel = threading.Event()
    cancel.set()
    mock_client(monkeypatch, files, [])
    with pytest.raises(Cancelled):
        download_model(fake_model(files), tmp_path, cancel=cancel)
    assert not list(tmp_path.rglob("*.part"))


def test_background_download_reports_success_and_allows_one_at_a_time(qt_app, tmp_path, monkeypatch):
    calls, events = [], []
    release = threading.Event()

    def fake_download(model, directory, progress, cancel):
        calls.append((model.id, directory))
        progress(50, "file")
        release.wait(5)

    monkeypatch.setattr("better_voice_input.pipeline.download_model", fake_download)
    downloads = ModelDownloads()
    downloads.progress.connect(lambda *args: events.append(("progress", args)))
    downloads.finished.connect(lambda *args: events.append(("finished", args)))
    assert downloads.start("canary", tmp_path)
    assert not downloads.start("xasr", tmp_path)
    release.set()
    downloads.thread.join(5)
    qt_app.processEvents()
    assert calls == [("canary", tmp_path)]
    assert downloads.active is None
    assert ("progress", ("canary", 50)) in events and ("finished", ("canary",)) in events


@pytest.fixture
def model_dialog(qt_app, tmp_path, monkeypatch):
    ready = {"sensevoice"}
    applied = []
    starts = []
    monkeypatch.setattr(ui, "models_ready", lambda directory, model: model.id in ready)
    downloads = ModelDownloads()
    monkeypatch.setattr(downloads, "start", lambda model_id, directory: starts.append((model_id, directory)) or True)
    value = Settings(download_dir=str(tmp_path), model_paths={"sensevoice": str(tmp_path / "legacy")})
    dialog = ModelDialog(value, downloads, lambda new: applied.append(new) or True)
    yield SimpleNamespace(dialog=dialog, ready=ready, applied=applied, starts=starts, root=tmp_path)
    dialog.close()


def test_model_dialog_downloads_into_chosen_location_then_switches(model_dialog):
    view = model_dialog
    card = view.dialog.cards["xasr"]
    assert "下载" in card.action.text()
    card.action.click()
    assert view.starts == [("xasr", view.root / "x-asr-zh-en")]
    assert view.applied == []  # Downloading never switches the active model by itself.
    view.ready.add("xasr")
    view.dialog.refresh()
    assert card.action.text() == "使用此模型"
    card.action.click()
    assert view.applied[-1].asr_model == "xasr"
    assert view.dialog.cards["xasr"].property("active")
    assert not view.dialog.cards["sensevoice"].property("active")
    assert not view.dialog.cards["sensevoice"].delete_button.isVisibleTo(view.dialog)


def test_model_dialog_deletes_only_model_files(model_dialog, monkeypatch):
    view = model_dialog
    folder = view.root / "canary-180m-flash"
    folder.mkdir(parents=True)
    for spec in get_model("canary").files:
        (folder / spec.name).write_bytes(b"x")
    keep = view.root / "notes.txt"
    keep.write_text("keep", encoding="utf-8")
    view.ready.add("canary")
    view.dialog.refresh()
    assert view.dialog.cards["canary"].delete_button.isVisibleTo(view.dialog)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    view.dialog.cards["canary"].delete_button.click()
    assert not folder.exists()
    assert keep.read_text(encoding="utf-8") == "keep"


def test_model_dialog_warns_before_download_without_disk_space(model_dialog, monkeypatch):
    warnings = []
    monkeypatch.setattr(ui, "free_space", lambda path: 10_000_000)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1]))
    model_dialog.dialog.cards["canary"].action.click()
    assert warnings == ["磁盘空间不足"]
    assert model_dialog.starts == []


def test_pipeline_loads_selected_model_and_reloads_after_switch(monkeypatch):
    created = []

    class Recognizer:
        def __init__(self, directory, model):
            created.append(model)
            self.directory, self.model = directory, model

        def transcribe(self, *args):
            return "识别文字"

    emitted = []
    events = SimpleNamespace(**{
        name: SimpleNamespace(emit=lambda *args, name=name: emitted.append((name, args)))
        for name in ("stage", "transcript", "completed", "failed")
    })
    monkeypatch.setattr("better_voice_input.asr.LocalRecognizer", Recognizer)
    monkeypatch.setattr("better_voice_input.pipeline.read_key", lambda **kwargs: "")
    pipeline = Pipeline(events)
    pipeline.recognizer = Recognizer(Settings().models, "sensevoice")
    created.clear()
    samples = SimpleNamespace(size=16000)
    pipeline._run(1, threading.Event(), Settings(), samples, "audio")
    assert created == []  # Same model stays loaded.
    pipeline._run(2, threading.Event(), Settings(asr_model="xasr"), samples, "audio")
    assert created == ["xasr"]
    assert ("stage", (2, "正在加载 X-ASR 中英…")) in emitted
    assert pipeline.release_recognizer() and pipeline.recognizer is None


def test_main_window_applies_model_choice_and_shows_download_progress(qt_app, monkeypatch):
    from better_voice_input.app import MainWindow

    monkeypatch.setattr("better_voice_input.ui.read_key", lambda *args, **kwargs: "")
    saved = []
    monkeypatch.setattr(Settings, "save", lambda self, path=None: saved.append(self))
    window = MainWindow(Settings(), native=False)
    try:
        window.pipeline.recognizer = object()
        assert window.apply_model_settings(replace(window.settings, asr_model="canary"))
        assert saved[-1].asr_model == "canary" and window.settings.asr_model == "canary"
        assert window.pipeline.recognizer is None
        assert "Canary" in window.model_chip.text()
        window.on_download_progress("canary", 40)
        assert "40%" in window.download_status.text()
        assert window.download_progress.value() == 40
        window.on_download_failed("canary", "模型下载失败，请检查网络或代理后重试。")
        assert "Canary 180M Flash" in window.notice.text()
        assert window.download_progress.isHidden()
    finally:
        window.shutdown()
        window.close()


def test_each_model_uses_its_sherpa_onnx_loader_with_catalog_files(tmp_path, monkeypatch):
    from better_voice_input import asr

    calls = {}
    for name in ("from_sense_voice", "from_transducer", "from_nemo_canary"):
        monkeypatch.setattr(
            asr.sherpa_onnx.OfflineRecognizer, name, staticmethod(lambda name=name, **kw: calls.update({name: kw}))
        )
    for model in CATALOG:
        asr.create_recognizer(tmp_path, model.id)
    names = {spec.name for model in CATALOG for spec in model.files}
    for kwargs in calls.values():
        for key, value in kwargs.items():
            if isinstance(value, str) and value.startswith(str(tmp_path)):
                assert value[len(str(tmp_path)) + 1:] in names, (key, value)
    assert calls["from_nemo_canary"]["src_lang"] == calls["from_nemo_canary"]["tgt_lang"] == "en"
    assert calls["from_sense_voice"]["use_itn"]
    assert set(calls) == {"from_sense_voice", "from_transducer", "from_nemo_canary"}
