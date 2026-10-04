from __future__ import annotations

import os
from pathlib import Path
from threading import Event
from typing import Callable

import numpy as np
import sherpa_onnx

from .audio import SAMPLE_RATE
from .cleanup import Cancelled
from .models import ModelError, models_ready


class LocalRecognizer:
    def __init__(self, directory: Path):
        if not models_ready(directory, verify=True):
            raise ModelError("本地语音模型未就绪或校验失败，请在设置中下载模型。")
        self.directory = directory
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(directory / "model.int8.onnx"),
            tokens=str(directory / "tokens.txt"),
            num_threads=min(4, max(1, (os.cpu_count() or 2) // 2)),
            language="auto",
            use_itn=True,
        )

    def transcribe(
        self, samples: np.ndarray, cancel: Event | None = None, partial: Callable[[str], None] | None = None
    ) -> str:
        if samples.size == 0 or float(np.max(np.abs(samples))) < 0.0001:
            return ""
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(self.directory / "silero_vad.onnx")
        config.silero_vad.threshold = 0.35
        config.silero_vad.min_silence_duration = 0.55
        config.silero_vad.min_speech_duration = 0.15
        config.silero_vad.max_speech_duration = 18
        config.sample_rate = SAMPLE_RATE
        vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=130)
        segments = []
        step = config.silero_vad.window_size
        for start in range(0, samples.size, step):
            if cancel and cancel.is_set():
                raise Cancelled("已取消识别。")
            window = samples[start : start + step]
            if len(window) < step:
                window = np.pad(window, (0, step - len(window)))
            vad.accept_waveform(window)
            while not vad.empty():
                item = vad.front
                segments.append((item.start, item.start + len(item.samples)))
                vad.pop()
        vad.flush()
        while not vad.empty():
            item = vad.front
            segments.append((item.start, item.start + len(item.samples)))
            vad.pop()
        texts = []
        for index, (start, end) in enumerate(segments):
            if cancel and cancel.is_set():
                raise Cancelled("已取消识别。")
            # Add context without ever overlapping adjacent recognized segments.
            previous = segments[index - 1][1] if index else 0
            following = segments[index + 1][0] if index + 1 < len(segments) else samples.size
            left = max(0, start - 2400, (previous + start) // 2)
            right = min(samples.size, end + 2400, (following + end) // 2)
            stream = self.recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, samples[left:right])
            self.recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                texts.append(text)
                if partial:
                    partial("".join(texts))
        if cancel and cancel.is_set():
            raise Cancelled("已取消识别。")
        return "".join(texts)
