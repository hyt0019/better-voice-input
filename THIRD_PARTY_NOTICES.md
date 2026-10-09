# 第三方组件

本项目使用以下主要开源组件。分发程序时保留随包许可证，模型另行下载。

| 组件 | 用途 | 上游 |
|---|---|---|
| Python | 运行时 | https://www.python.org/ |
| Segoe Fluent Icons | 界面图标，使用 Windows 系统字体，不随程序分发 | https://learn.microsoft.com/windows/apps/design/style/segoe-fluent-icons-font |
| Qt / PySide6 Essentials | 桌面界面 | https://www.qt.io/qt-for-python |
| sherpa-onnx / ONNX Runtime | 本地语音推理 | https://github.com/k2-fsa/sherpa-onnx |
| SenseVoice | 语音识别模型（默认） | https://github.com/FunAudioLLM/SenseVoice |
| X-ASR zh-en | 可选语音识别模型，Apache-2.0 | https://huggingface.co/GilgameshWind/X-ASR-zh-en |
| NVIDIA Canary-180M-Flash | 可选英文语音识别模型，CC-BY-4.0 | https://huggingface.co/nvidia/canary-180m-flash |
| Silero VAD | 语音检测模型 | https://github.com/snakers4/silero-vad |
| PyAV / FFmpeg | 音频解码与重采样 | https://github.com/PyAV-Org/PyAV |
| sounddevice / PortAudio | 麦克风采集 | https://github.com/spatialaudio/python-sounddevice |
| NumPy | 音频数组处理 | https://numpy.org/ |
| HTTPX / Pydantic | HTTP 与输出校验 | https://www.python-httpx.org/ ; https://docs.pydantic.dev/ |
| keyring / pywin32 | Windows 凭据与系统接口 | https://github.com/jaraco/keyring ; https://github.com/mhammond/pywin32 |
| PyInstaller | 应用打包 | https://pyinstaller.org/ |

精确依赖版本见 requirements-lock.txt。应用采用目录式打包以保留独立动态库；模型权重不嵌入可执行文件。DeepSeek 是需要用户自备密钥的外部 API 服务。
