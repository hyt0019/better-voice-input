from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

import httpx

from .cleanup import Cancelled


@dataclass(frozen=True)
class ModelFile:
    name: str
    url: str
    size: int
    digest: str
    git_blob: bool = False


_REPO = "https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/2365bae"
FILES = (
    ModelFile(
        "model.int8.onnx",
        f"{_REPO}/model.int8.onnx",
        239233841,
        "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51",
    ),
    ModelFile("tokens.txt", f"{_REPO}/tokens.txt", 315894, "2cfc92fc2ff26aaa690b7c01fd96b41109413881", True),
    ModelFile(
        "silero_vad.onnx",
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
        643854,
        "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
    ),
)


class ModelError(RuntimeError):
    pass


def verify_file(path: Path, spec: ModelFile) -> bool:
    if not path.is_file() or path.stat().st_size != spec.size:
        return False
    hasher = hashlib.sha1() if spec.git_blob else hashlib.sha256()
    if spec.git_blob:
        hasher.update(f"blob {spec.size}\0".encode())
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest() == spec.digest


def models_ready(directory: Path, verify: bool = False) -> bool:
    try:
        return all(
            verify_file(directory / file.name, file)
            if verify
            else (directory / file.name).is_file() and (directory / file.name).stat().st_size == file.size
            for file in FILES
        )
    except OSError:
        return False


def download_models(
    directory: Path, progress: Callable[[int, str], None] | None = None, cancel: Event | None = None
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    total = sum(file.size for file in FILES)
    done = 0
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, connect=20)) as client:
        for spec in FILES:
            if cancel and cancel.is_set():
                raise Cancelled("已取消下载。")
            target = directory / spec.name
            if verify_file(target, spec):
                done += spec.size
                continue
            temp = directory / (spec.name + "." + uuid.uuid4().hex + ".part")
            received = 0
            try:
                with client.stream("GET", spec.url) as response:
                    response.raise_for_status()
                    with temp.open("wb") as file:
                        for chunk in response.iter_bytes(256 * 1024):
                            if cancel and cancel.is_set():
                                raise Cancelled("已取消下载。")
                            received += len(chunk)
                            if received > spec.size:
                                raise ModelError("下载大小与预期不符，请重试。")
                            file.write(chunk)
                            if progress:
                                progress(int((done + received) * 100 / total), spec.name)
                if not verify_file(temp, spec):
                    raise ModelError(f"{spec.name} 校验失败，请重新下载。")
                temp.replace(target)
                done += spec.size
            except httpx.HTTPError:
                raise ModelError("模型下载失败，请检查网络或代理后重试。") from None
            finally:
                temp.unlink(missing_ok=True)
    if progress:
        progress(100, "模型已就绪")
