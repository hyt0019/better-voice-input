# 开发说明

## 环境

需要 Windows 和 Python 3.12。模型、密钥、用户录音和本地打包产物不进入 Git 仓库。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m better_voice_input.app
```

精确依赖版本保存在 `requirements-lock.txt`。运行 `scripts/build.ps1` 会先跑测试，再用 PyInstaller 构建目录式便携程序 `dist/BetterVoiceInput/`。本地构建可双击 `启动好好说.cmd` 在托盘启动。

## API 与密钥

API 地址支持 Base URL（如 `https://api.example.com/v1`）或完整 `/chat/completions` 地址；模型名称使用服务商提供的 ID。DeepSeek 只是默认值。密钥按 API 地址分别保存在 Windows 凭据管理器，切换地址时需要该服务的密钥。

开发测试可将 `BVI_API_KEY` 与匹配的 `BVI_API_BASE_URL` 环境变量一起使用。旧 `DEEPSEEK_API_KEY` 和根目录 `deepseek api key.txt` 仅供 DeepSeek 官方接口使用。提交前可运行 `scripts/verify_private_files.py` 检查已跟踪文件中没有密钥和私有素材。

## 命令行与脚本

```powershell
.\.venv\Scripts\python.exe -m better_voice_input.cli download-models --asr-model canary
.\.venv\Scripts\python.exe -m better_voice_input.cli transcribe '录音.m4a' --asr-model xasr --clean --output private/result.json
.\.venv\Scripts\python.exe scripts/evaluate_text.py   # 调用真实 API，会计费
.\.venv\Scripts\python.exe scripts/capture_ui.py      # 离屏渲染界面截图到 artifacts/screenshots
```

普通 pytest 不访问网络，也不读取测试 Key。

## 设计原则

- 音频在本机识别；转写文本和相关词库发送至设置中选定的 API。
- 清理表达，不回答口述问题、不执行口述命令。
- 快捷键录音直接输入整理结果，疑点不阻断；API 整理失败时输入识别原文。原文和结果可在主窗口查看。
- 录音由用户主动开始和结束，停顿不自动提交。
- 只输入文字，不自动按回车发送。
- 录音仅在内存中，本地识别后释放；默认不保存文字历史，开启后最多保留最近 5 条（最长 7 天）。
- 语音模型只收录识别耗时与 SenseVoice 同一量级的模型，保证实时听写；模型文件固定版本并校验摘要。

## 文档

- [实现规划与界面设计](PLAN.md)
- [使用指南](USER_GUIDE.md)
- [验证记录](VALIDATION.md)
- [第三方组件](../THIRD_PARTY_NOTICES.md)
