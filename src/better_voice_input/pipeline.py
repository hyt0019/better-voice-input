from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .audio import decode_audio
from .cleanup import ApiCleaner, Cancelled, CleanupError
from .core import CleanupResult
from .models import download_models
from .settings import Settings, read_key


class Events(QObject):
    stage = Signal(int, str)
    transcript = Signal(int, str)
    completed = Signal(int, object)
    failed = Signal(int, str)
    level = Signal(float)
    downloaded = Signal(int)


class Pipeline:
    def __init__(self, events: Events):
        self.events = events
        self.recognizer = None
        self.lock = threading.Lock()

    def start(self, job: int, cancel: threading.Event, settings: Settings, source, kind: str):
        snapshot = Settings(**vars(settings))
        # Thread.args would retain the recording until the later API call finishes.
        # Transfer ownership out of this container as soon as the worker starts.
        pending = [source]

        def run():
            self._run(job, cancel, snapshot, pending.pop(), kind)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def _run(self, job: int, cancel: threading.Event, settings: Settings, source, kind: str):
        try:
            if kind == "download":
                download_models(
                    settings.models,
                    lambda value, _: self.events.stage.emit(job, f"正在下载模型 {value}%"),
                    cancel,
                )
                self.events.downloaded.emit(job)
                return
            started = time.monotonic()
            if kind == "text":
                text = source
                duration = 0
            else:
                samples = decode_audio(Path(source)) if kind == "file" else source
                source = None
                duration = samples.size / 16000
                try:
                    self.events.stage.emit(job, "正在本地识别…")
                    with self.lock:
                        if cancel.is_set():
                            raise Cancelled("已取消。")
                        if self.recognizer is None or self.recognizer.directory != settings.models:
                            from .asr import LocalRecognizer

                            self.recognizer = LocalRecognizer(settings.models)
                        text = self.recognizer.transcribe(
                            samples, cancel, lambda value: self.events.transcript.emit(job, value)
                        )
                finally:
                    samples = None  # Audio is no longer needed while waiting for the text API.
                self.events.transcript.emit(job, text)
                if not text.strip():
                    raise RuntimeError("没有检测到清晰语音，请检查麦克风或靠近一些重试。")
            asr_seconds = time.monotonic() - started
            if cancel.is_set():
                raise Cancelled("已取消。")
            self.events.stage.emit(job, "正在整理你的表达…")
            used_original = False
            cleanup_started = time.monotonic()
            try:
                result = ApiCleaner(
                    read_key(api_base_url=settings.api_base_url),
                    settings.model,
                    settings.api_timeout,
                    base_url=settings.api_base_url,
                ).clean(text, settings.glossary, cancel)
            except Cancelled:
                raise
            except CleanupError as exc:
                if kind == "text":
                    raise
                used_original = True
                result = CleanupResult(
                    text,
                    text,
                    (f"API 整理未完成，已使用识别原文。{exc}",),
                    elapsed=time.monotonic() - cleanup_started,
                )
            if cancel.is_set():
                raise Cancelled("已取消。")
            self.events.completed.emit(
                job,
                {
                    "result": result,
                    "asr_seconds": asr_seconds,
                    "duration": duration,
                    "used_original": used_original,
                },
            )
        except Cancelled:
            return
        except Exception as exc:
            if not cancel.is_set():
                from .audio import AudioError
                from .models import ModelError

                message = (
                    str(exc)
                    if isinstance(exc, (AudioError, CleanupError, ModelError, OSError))
                    else "处理未完成，请检查模型、音频文件或设备后重试。"
                )
                if isinstance(exc, RuntimeError) and str(exc).startswith("没有检测"):
                    message = str(exc)
                self.events.failed.emit(job, message)
