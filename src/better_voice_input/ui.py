from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .api_config import chat_completion_url
from .settings import Settings, read_key, save_key
from .shortcuts import RECORDING_CHOICES

STYLE = """
QWidget { font-family: 'DengXian', 'Microsoft YaHei UI'; font-size: 15px; color: #192C3A; }
QMainWindow, QDialog { background: #F3F6FA; }
QLabel { background: transparent; }
QLabel#brand { font-family: 'Microsoft YaHei UI'; font-size: 26px; font-weight: 700; }
QLabel#muted { color: #596F7F; font-size: 13px; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#status { font-size: 20px; font-weight: 600; }
QFrame#recorder { background: #E6EFF4; border: 1px solid #D2E1E9; border-radius: 14px; }
QPlainTextEdit { background: #FFFFFF; border: 1px solid #D5E0E7; border-radius: 8px; padding: 14px;
                selection-background-color: #C7E2EC; font-size: 16px; }
QPlainTextEdit:focus { border: 2px solid #176B87; padding: 13px; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #CDD9E2; border-radius: 5px;
                     padding: 8px; min-height: 20px; }
QPushButton { background: #FFFFFF; border: 1px solid #CDD9E2; border-radius: 7px; padding: 9px 16px; }
QPushButton:hover { background: #E9F2F7; border-color: #7EA8B9; }
QPushButton:focus { border: 2px solid #176B87; }
QPushButton:disabled { color: #9AA9B4; background: #EDF1F5; }
QPushButton#primary { background: #176B87; color: #FFFFFF; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #125A73; }
QPushButton#recording { background: #B84B52; color: #FFFFFF; border: none; font-weight: 600; }
QPushButton#primary:disabled { background: #A2BAC5; }
QProgressBar { background: #CFDEE7; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #176B87; border-radius: 3px; }
QLabel#notice { background: #FFF2D9; color: #795514; padding: 10px; border-radius: 6px; }
QCheckBox { spacing: 8px; }
QToolTip { background: #FFFFFF; border: 1px solid #B9CCD8; padding: 5px; }
"""


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#176B87"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 16, 16)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(25, 12, 14, 27, 7, 7)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#FFFFFF"), 3))
    painter.drawArc(18, 21, 28, 26, 180 * 16, 180 * 16)
    painter.drawLine(32, 47, 32, 53)
    painter.drawLine(25, 53, 39, 53)
    painter.end()
    return QIcon(pixmap)


class RecordingOverlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.hide)
        self.setStyleSheet(
            "QWidget { background: #E6EFF4; color: #192C3A; border-radius: 10px; } QLabel { border: none; }"
        )
        self.setFixedSize(300, 85)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        self.label = QLabel("正在听  00:00")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.hint = QLabel("松开快捷键结束，Esc 取消")
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setStyleSheet("font-size: 12px; color: #596F7F;")
        self.level = QProgressBar()
        self.level.setTextVisible(False)
        self.level.setRange(0, 100)
        layout.addWidget(self.label)
        layout.addWidget(self.hint)
        layout.addWidget(self.level)

    def show_near_bottom(self):
        self.dismiss_timer.stop()
        area = self.screen().availableGeometry()
        self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 35)
        self.show()

    def show_message(self, title: str, hint: str, milliseconds: int = 4500):
        self.label.setText(title)
        self.hint.setText(hint)
        self.level.hide()
        self.show_near_bottom()
        self.dismiss_timer.start(milliseconds)


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.updated = settings
        self.setWindowTitle("设置 · 好好说")
        self.resize(580, 740)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        form = QFormLayout()
        form.setSpacing(12)
        self.base_url = QLineEdit(settings.api_base_url)
        self.base_url.setPlaceholderText("例如 https://api.example.com/v1")
        self.base_url.setToolTip("填写兼容 Chat Completions 的 API 地址，支持 Base URL 或完整请求地址。")
        form.addRow("API 地址", self.base_url)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.update_key_hint()
        self.base_url.textChanged.connect(self.api_address_changed)
        form.addRow("API Key", self.key)
        self.model = QLineEdit(settings.model)
        self.model.setPlaceholderText("填写服务商提供的模型名称")
        form.addRow("模型名称", self.model)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(int(settings.api_timeout))
        form.addRow("请求超时", self.timeout)
        self.mic = QComboBox()
        self.mic.addItem("系统默认麦克风", None)
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            for index, device in enumerate(devices):
                if device["max_input_channels"] > 0 and (
                    device["hostapi"] == 0 or index == settings.microphone
                ):
                    self.mic.addItem(device["name"], index)
            self.mic.setCurrentIndex(max(0, self.mic.findData(settings.microphone)))
        except Exception:
            self.mic.setToolTip("未能列出麦克风，请检查音频设备。")
        form.addRow("麦克风", self.mic)
        self.hotkey = QComboBox()
        self.hotkey.addItems(RECORDING_CHOICES)
        if settings.hotkey not in RECORDING_CHOICES:
            self.hotkey.addItem(settings.hotkey)
        self.hotkey.setCurrentText(settings.hotkey)
        form.addRow("录音快捷键", self.hotkey)
        self.hold = QCheckBox("按住快捷键说话，松开结束")
        self.hold.setChecked(settings.hold_to_talk)
        form.addRow("录音方式", self.hold)
        form.addRow("输入方式", QLabel("快捷键录音后直接输入，疑点不暂停"))
        self.history = QCheckBox("在本机加密保留最近 7 天文字，最多 100 条")
        self.history.setChecked(settings.save_history)
        form.addRow("历史记录", self.history)
        self.startup = QCheckBox("开机自启动，登录 Windows 后在托盘运行")
        self.startup.setChecked(settings.start_on_login)
        form.addRow("启动方式", self.startup)
        layout.addLayout(form)
        label = QLabel("个人词库")
        label.setObjectName("section")
        layout.addWidget(label)
        description = QLabel("每行一个常用人名、项目名或英文术语，最多 100 个。")
        description.setObjectName("muted")
        layout.addWidget(description)
        self.glossary = QPlainTextEdit("\n".join(settings.glossary))
        self.glossary.setMaximumHeight(160)
        layout.addWidget(self.glossary)
        model_label = QLabel(f"本地模型位置：{settings.models}")
        model_label.setWordWrap(True)
        model_label.setObjectName("muted")
        layout.addWidget(model_label)
        privacy = QLabel(
            "音频在本机识别。整理时，文字和词库发送至所选 API。\n密钥按 API 地址分别保存在 Windows 凭据管理器。"
        )
        privacy.setWordWrap(True)
        privacy.setObjectName("muted")
        layout.addWidget(privacy)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_key_hint(self):
        found = bool(read_key(api_base_url=self.base_url.text()))
        self.key.setPlaceholderText("该地址已有密钥；留空保留" if found else "填写此 API 地址对应的密钥")

    def api_address_changed(self):
        self.key.clear()
        self.update_key_hint()

    def save(self):
        words = list(dict.fromkeys(x.strip() for x in self.glossary.toPlainText().splitlines() if x.strip()))
        if len(words) > 100 or any(len(word) > 80 for word in words):
            QMessageBox.warning(self, "检查词库", "最多添加 100 个词，每个词不超过 80 字。")
            return
        if not self.model.text().strip():
            QMessageBox.warning(self, "检查模型", "请填写 API 服务商提供的模型名称。")
            return
        base_url = self.base_url.text().strip().rstrip("/")
        try:
            endpoint = chat_completion_url(base_url)
        except ValueError as exc:
            QMessageBox.warning(self, "检查 API 地址", str(exc))
            return
        try:
            previous_endpoint = chat_completion_url(self.settings.api_base_url)
        except ValueError:
            previous_endpoint = ""
        if (
            endpoint != previous_endpoint
            and not self.key.text().strip()
            and not read_key(api_base_url=base_url)
        ):
            QMessageBox.warning(self, "检查 API Key", "已更换 API 地址，请填写该服务对应的密钥。")
            return
        try:
            if self.key.text().strip():
                save_key(self.key.text(), api_base_url=base_url)
            self.updated = replace(
                self.settings,
                model=self.model.text().strip(),
                api_base_url=base_url,
                api_timeout=float(self.timeout.value()),
                microphone=self.mic.currentData(),
                hotkey=self.hotkey.currentText(),
                hold_to_talk=self.hold.isChecked(),
                save_history=self.history.isChecked(),
                start_on_login=self.startup.isChecked(),
                glossary=words,
            )
            self.accept()
        except Exception:
            QMessageBox.warning(self, "保存失败", "无法保存密钥到 Windows 凭据管理器，请检查系统权限。")


def text_column(title: str, hint: str) -> tuple[QWidget, QPlainTextEdit, QLabel]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    row = QHBoxLayout()
    label = QLabel(title)
    label.setObjectName("section")
    count = QLabel("0 字")
    count.setObjectName("muted")
    row.addWidget(label)
    row.addStretch()
    row.addWidget(count)
    layout.addLayout(row)
    editor = QPlainTextEdit()
    editor.setPlaceholderText(hint)
    editor.textChanged.connect(lambda: count.setText(f"{len(editor.toPlainText())} 字"))
    layout.addWidget(editor)
    return widget, editor, count
