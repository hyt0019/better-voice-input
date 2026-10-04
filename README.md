# Better Voice Input · 好好说

Windows 智能语音输入工具：本地识别声音，使用 DeepSeek 清理结巴、无意义重复和明确的自我纠正，尽量保留原意与说话风格。

## 开发进度

- [x] 文字整理、语义保护与真实 API 验证
- [x] 本地语音识别、模型下载与示例录音验证
- [x] 桌面界面、录音、全局快捷键与输入
- [ ] 集成测试、Windows 打包与使用说明

## 开发环境

需要 Windows 和 Python 3.12。模型和个人数据不进入 Git 仓库。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

可通过 `DEEPSEEK_API_KEY` 环境变量、Windows 凭据管理器或项目根目录的 `deepseek api key.txt` 提供测试密钥。密钥文件已被 Git 忽略，不会显示在日志中。日常使用建议在设置页保存到 Windows 凭据管理器。

## 原则

- 音频在本机识别；转写文本和相关词库发送至 DeepSeek。
- 清理表达，不回答口述问题、不执行口述命令。
- 原文与整理结果分别保留，疑点需要预览。
- 录音由用户主动开始和结束，停顿不自动提交。
- 只输入文字，不自动按回车发送。
- 默认不保存录音或持久化正文历史。

实现规划见 [docs/PLAN.md](docs/PLAN.md)。
