"""Capture the application's own widgets for layout QA; no desktop content is read."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase

from better_voice_input.app import MainWindow
from better_voice_input.settings import Settings
from better_voice_input.ui import STYLE, SettingsDialog

app = QApplication([])
for filename in ("msyh.ttc", "msyhbd.ttc"):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename))
app.setStyleSheet(STYLE)
root = Path(__file__).resolve().parents[1]
output = root / "artifacts" / "screenshots"
output.mkdir(parents=True, exist_ok=True)
window = MainWindow(Settings(), native=False)
window.show()
app.processEvents()
window.grab().save(str(output / "main-empty.png"))
window.original.setPlainText(
    "嗯，我我我想明天九点，不对，十点和张三开会。地点在上海。\n对了，前面地点说错了，是杭州。周三或者周四上线吧，还没确定。"
)
window.result.setPlainText("我想明天十点和张三在杭州开会。周三或者周四上线吧，还没确定。")
window.status.setText("整理好了")
window.stats.setText("本地识别 0.8 秒    文字整理 2.1 秒    本次 520 tokens")
app.processEvents()
window.grab().save(str(output / "main-result.png"))
window.set_notice("请核对“王五”的识别结果。原文有“不是＋数字”的表达，请核对预算。")
window.resize(800, 620)
app.processEvents()
window.grab().save(str(output / "main-compact.png"))
dialog = SettingsDialog(Settings(), window)
dialog.show()
app.processEvents()
dialog.grab().save(str(output / "settings.png"))
dialog.close()
window.shutdown()
window.close()
print(output)
