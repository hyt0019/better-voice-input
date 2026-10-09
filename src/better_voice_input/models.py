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


@dataclass(frozen=True)
class AsrModel:
    id: str
    name: str
    kind: str
    # Sub-folder under the download location. SenseVoice keeps its original
    # place directly in the models folder so existing installs stay untouched.
    folder: str
    tagline: str
    strengths: tuple[str, ...]
    caveat: str
    languages: str
    files: tuple[ModelFile, ...]

    @property
    def size(self) -> int:
        return sum(file.size for file in self.files)

    @property
    def size_label(self) -> str:
        megabytes = self.size / 1_000_000
        return f"约 {megabytes / 1000:.1f} GB" if megabytes >= 950 else f"约 {round(megabytes, -1):.0f} MB"


def _hf(repo: str, revision: str) -> Callable[..., ModelFile]:
    def file(name: str, size: int, digest: str, git_blob: bool = False) -> ModelFile:
        return ModelFile(name, f"https://huggingface.co/{repo}/resolve/{revision}/{name}", size, digest, git_blob)

    return file


VAD = ModelFile(
    "silero_vad.onnx",
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
    643854,
    "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
)

_sense = _hf("csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17", "2365bae")
_xasr = _hf(
    "csukuangfj2/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03",
    "ce812cc05d858539a68dd42e86f4fd7a9ce1acf0",
)
_canary = _hf(
    "csukuangfj/sherpa-onnx-nemo-canary-180m-flash-en-es-de-fr-int8", "9077164e0d3dd1d5353743e89ceaa1d3a770838c"
)

SENSE_VOICE = AsrModel(
    id="sensevoice",
    name="SenseVoice Small",
    kind="sense_voice",
    folder="",
    tagline="均衡默认",
    strengths=("识别最快，75 秒录音约 1 秒", "中文准确，自带标点", "体积小，老电脑也流畅"),
    caveat="中文里的英文词和人名偶尔听成近音词，例如 DeepSeek、王五。",
    languages="中 · 英 · 日 · 韩 · 粤",
    files=(
        _sense("model.int8.onnx", 239233841, "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51"),
        _sense("tokens.txt", 315894, "2cfc92fc2ff26aaa690b7c01fd96b41109413881", True),
        VAD,
    ),
)

X_ASR = AsrModel(
    id="xasr",
    name="X-ASR 中英",
    kind="transducer",
    folder="x-asr-zh-en",
    tagline="体积最小",
    strengths=("英文和中英混说更准，大小写规范", "体积最小，速度与 SenseVoice 相当", "自带标点"),
    caveat="2026 年新发布，社区验证较少；个别中文近音词仍会出错。",
    languages="中 · 英",
    files=(
        _xasr(
            "encoder-epoch-99-avg-1.int8.onnx",
            161744450,
            "fe0198b52626f2a1012ebb6d6a7259c5137c4c964f3a524135e353f4687b5d14",
        ),
        _xasr(
            "decoder-epoch-99-avg-1.onnx", 11309084, "a9fe7c320337e6f510809c028a8accf074d45f42aab852e2d29830babc41a3f9"
        ),
        _xasr(
            "joiner-epoch-99-avg-1.int8.onnx",
            2581422,
            "aedb7fa697b2ab43f20499826fff7c997eea7d67db77be97769aeeeb726e63b3",
        ),
        _xasr("tokens.txt", 58806, "8ab5e8e441ec0c2028fa05b200ad1514d19b134e", True),
        VAD,
    ),
)

CANARY = AsrModel(
    id="canary",
    name="Canary 180M Flash",
    kind="nemo_canary",
    folder="canary-180m-flash",
    tagline="英文最强",
    strengths=(
        "英文准确率超过 Whisper-large-v3（公开榜单平均错误率 7.1%）",
        "体积小，CPU 上约 20 倍实时",
        "自带标点和大小写",
    ),
    caveat="只识别英文（另支持德、法、西班牙语），说中文时请切回其他模型。",
    languages="英 · 德 · 法 · 西",
    files=(
        _canary("encoder.int8.onnx", 132678643, "7a75b4e2a5857a6dcc0819503bbe3fad66943db4a3ccf21d3f27c633667d303f"),
        _canary("decoder.int8.onnx", 74437848, "e41a2ab9c0c2fe81a1e8ade5a45fb02a74bc4db7d1f91b89a54a25e2cf79cba2"),
        _canary("tokens.txt", 53555, "da5e7fa593e5f2e3d7a6daa6688da7adebc8336a", True),
        VAD,
    ),
)

CATALOG = (SENSE_VOICE, X_ASR, CANARY)
DEFAULT_MODEL = SENSE_VOICE.id
# Kept for callers that predate the model catalog.
FILES = SENSE_VOICE.files


def get_model(model_id: str) -> AsrModel:
    for model in CATALOG:
        if model.id == model_id:
            return model
    return SENSE_VOICE


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


def models_ready(directory: Path, verify: bool = False, model: str | AsrModel = DEFAULT_MODEL) -> bool:
    spec = get_model(model) if isinstance(model, str) else model
    try:
        return all(
            verify_file(directory / file.name, file)
            if verify
            else (directory / file.name).is_file() and (directory / file.name).stat().st_size == file.size
            for file in spec.files
        )
    except OSError:
        return False


def download_model(
    model: AsrModel,
    directory: Path,
    progress: Callable[[int, str], None] | None = None,
    cancel: Event | None = None,
) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ModelError("无法创建模型文件夹，请选择有写入权限的位置。") from None
    total = model.size
    done = 0
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, connect=20)) as client:
        for spec in model.files:
            if cancel and cancel.is_set():
                raise Cancelled("已取消下载。")
            target = directory / spec.name
            if verify_file(target, spec):
                done += spec.size
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.part")
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
            except OSError:
                raise ModelError("模型写入失败，请检查磁盘空间和文件夹权限。") from None
            finally:
                temp.unlink(missing_ok=True)
    if progress:
        progress(100, "模型已就绪")


def download_models(
    directory: Path, progress: Callable[[int, str], None] | None = None, cancel: Event | None = None
) -> None:
    download_model(SENSE_VOICE, directory, progress, cancel)
