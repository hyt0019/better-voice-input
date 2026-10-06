from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import replace

from PySide6.QtCore import QLockFile, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .audio import AudioError, Recorder
from .models import models_ready
from .pipeline import Events, Pipeline
from .session import SessionGate
from .settings import Settings, data_dir, read_key
from .shortcuts import DEFAULT_HOTKEY, HOTKEYS, INSERT_HOTKEY
from .startup import StartupError, save_settings_with_startup, startup_enabled
from .ui import STYLE, RecordingOverlay, SettingsDialog, app_icon, text_column
from .windows import Hotkeys, PasteError, current_target, modifiers_held, paste_text, shortcut_held


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None, native: bool = True):
        super().__init__()
        self.settings = settings or Settings.load()
        self.gate = SessionGate()
        self.events = Events()
        self.pipeline = Pipeline(self.events)
        self.recorder = Recorder(self.events.level.emit)
        self.state = "idle"
        self.target = None
        self.target_changed = False
        self.from_hotkey = False
        self.extra_warnings: list[str] = []
        self.quitting = False
        self.native = native
        self.hotkeys = Hotkeys() if native else None
        self.overlay = RecordingOverlay()
        self.setWindowTitle("好好说 · Better Voice Input")
        self.setWindowIcon(app_icon())
        self.resize(1100, 780)
        self.setMinimumSize(800, 620)
        self._build_ui()
        self.events.stage.connect(self.on_stage)
        self.events.transcript.connect(self.on_transcript)
        self.events.completed.connect(self.on_complete)
        self.events.failed.connect(self.on_error)
        self.events.level.connect(self.on_level)
        self.events.downloaded.connect(self.on_downloaded)
        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.escape = QShortcut(QKeySequence("Escape"), self)
        self.escape.activated.connect(self.cancel)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("好好说 · 语音输入")
        menu = QMenu(self)
        show = QAction("打开好好说", self)
        show.triggered.connect(self.reveal)
        menu.addAction(show)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.reveal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        if native:
            self.tray.show()
            QApplication.instance().installNativeEventFilter(self.hotkeys)
            self.hotkeys.events.triggered.connect(self.on_hotkey)
            self.configure_hotkeys()
        self.refresh_controls()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 24, 30, 20)
        layout.setSpacing(18)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.windowIcon().pixmap(44, 44))
        header.addWidget(logo)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel("好好说")
        title.setObjectName("brand")
        subtitle = QLabel("保留你的意思，整理你的表达。")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.history_button = QPushButton("历史")
        self.history_button.clicked.connect(self.open_history)
        header.addWidget(self.history_button)
        self.import_button = QPushButton("导入录音")
        self.import_button.clicked.connect(self.import_audio)
        self.settings_button = QPushButton("设置")
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.import_button)
        header.addWidget(self.settings_button)
        layout.addLayout(header)

        band = QFrame()
        band.setObjectName("recorder")
        recording = QHBoxLayout(band)
        recording.setContentsMargins(22, 20, 22, 20)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(7)
        self.status = QLabel("准备好，慢慢说")
        self.status.setObjectName("status")
        self.hint = QLabel("按住快捷键说话，松开后自动整理并输入。停顿和改口都没关系。")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.meter = QProgressBar()
        self.meter.setTextVisible(False)
        self.meter.setRange(0, 100)
        self.meter.setValue(0)
        status_layout.addWidget(self.status)
        status_layout.addWidget(self.hint)
        status_layout.addWidget(self.meter)
        recording.addLayout(status_layout, 1)
        self.record_button = QPushButton("开始录音")
        self.record_button.setObjectName("primary")
        self.record_button.setMinimumSize(150, 54)
        self.record_button.clicked.connect(lambda: self.toggle_recording(False))
        recording.addWidget(self.record_button)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel)
        recording.addWidget(self.cancel_button)
        layout.addWidget(band)

        self.notice = QLabel()
        self.notice.setObjectName("notice")
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notice.hide()
        layout.addWidget(self.notice)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(18)
        original_widget, self.original, _ = text_column(
            "原始识别", "录音后，原始识别文字会出现在这里。\n\n也可以粘贴一段文字，直接测试整理效果。"
        )
        result_widget, self.result, _ = text_column(
            "整理结果", "结巴、重复和明确的改口会被整理。\n\n原文保留在左侧，结果可以直接编辑。"
        )
        splitter.addWidget(original_widget)
        splitter.addWidget(result_widget)
        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)
        self.original.textChanged.connect(self.refresh_controls)
        self.result.textChanged.connect(self.result_edited)

        actions = QHBoxLayout()
        self.clean_button = QPushButton("整理文字")
        self.clean_button.clicked.connect(self.clean_text)
        self.copy_original_button = QPushButton("复制原文")
        self.copy_original_button.clicked.connect(lambda: self.copy_text(False))
        self.clear_button = QPushButton("清空")
        self.clear_button.clicked.connect(self.clear)
        actions.addWidget(self.clean_button)
        actions.addWidget(self.copy_original_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.copy_button = QPushButton("复制结果")
        self.copy_button.clicked.connect(lambda: self.copy_text(True))
        self.insert_button = QPushButton("输入到其他窗口")
        self.insert_button.setObjectName("primary")
        self.insert_button.clicked.connect(self.schedule_manual_insert)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.insert_button)
        layout.addLayout(actions)
        self.stats = QLabel("默认仅保留当前会话；可在设置中开启本机加密历史。")
        self.stats.setObjectName("muted")
        layout.addWidget(self.stats)
        bottom = QHBoxLayout()
        self.shortcut_label = QLabel()
        self.shortcut_label.setObjectName("muted")
        bottom.addWidget(self.shortcut_label)
        bottom.addStretch()
        self.download_button = QPushButton("下载语音模型")
        self.download_button.clicked.connect(self.download)
        bottom.addWidget(self.download_button)
        layout.addLayout(bottom)
        privacy = QLabel("音频留在本机，整理时发送文字至 DeepSeek。")
        privacy.setObjectName("muted")
        layout.addWidget(privacy)

    def refresh_controls(self):
        if not hasattr(self, "clean_button"):
            return
        idle = self.state == "idle"
        self.record_button.setEnabled(self.state in ("idle", "recording"))
        self.record_button.setText("结束并整理" if self.state == "recording" else "开始录音")
        self.record_button.setObjectName("recording" if self.state == "recording" else "primary")
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
        self.cancel_button.setVisible(not idle)
        self.import_button.setEnabled(idle)
        self.settings_button.setEnabled(idle)
        self.history_button.setEnabled(idle)
        self.clean_button.setEnabled(idle and bool(self.original.toPlainText().strip()))
        self.copy_original_button.setEnabled(bool(self.original.toPlainText().strip()))
        self.copy_button.setEnabled(bool(self.result.toPlainText().strip()))
        self.insert_button.setEnabled(
            idle and bool(self.result.toPlainText().strip()) and not self.gate.inserted
        )
        self.clear_button.setEnabled(idle)
        self.original.setReadOnly(not idle)
        self.result.setReadOnly(not idle)
        ready = models_ready(self.settings.models)
        self.download_button.setVisible(not ready)
        self.download_button.setEnabled(idle)
        action = "按住说话，松开结束" if self.settings.hold_to_talk else "按一下开始，再按结束"
        self.shortcut_label.setText(f"{self.settings.hotkey}：{action}    {INSERT_HOTKEY}：补输结果")

    def result_edited(self):
        if self.state == "idle":
            self.gate.inserted = False
        self.refresh_controls()

    def set_notice(self, text: str = ""):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def configure_hotkeys(self):
        if not self.hotkeys:
            return
        modifiers, key = HOTKEYS.get(self.settings.hotkey, HOTKEYS[DEFAULT_HOTKEY])
        if not self.hotkeys.register(1, modifiers, key):
            self.set_notice("录音快捷键被其他程序占用，请在设置中更换。仍可点击开始录音。")
        if not self.hotkeys.register(2, 0x0001, ord("V")):
            self.set_notice(f"{INSERT_HOTKEY} 被其他程序占用，请使用复制结果或输入按钮。")

    def on_hotkey(self, identifier: int):
        if identifier == 1:
            if self.state == "recording" and self.settings.hold_to_talk:
                return
            self.toggle_recording(True)
        elif identifier == 2 and self.state == "idle" and self.result.toPlainText().strip():
            target = current_target()
            if target and target.process != os.getpid():
                self.from_hotkey = True
                self.attempt_insert(self.gate.generation, target, explicit=True)
        elif identifier == 3:
            self.cancel()

    def begin(self, kind: str):
        job, cancel = self.gate.begin()
        self.state = kind
        self.set_notice()
        self.extra_warnings = []
        self.target_changed = False
        self.result.clear()
        if self.hotkeys:
            self.hotkeys.register(3, 0, 0x1B)
        self.refresh_controls()
        return job, cancel

    def toggle_recording(self, from_hotkey: bool):
        if self.state == "recording":
            self.stop_recording()
            return
        if self.state != "idle":
            return
        self.from_hotkey = from_hotkey
        if not models_ready(self.settings.models):
            self.set_notice("请先点击“下载语音模型”，首次需要下载约 240 MB。")
            self.feedback("语音模型未就绪", "点击托盘图标，下载语音模型")
            return
        target = current_target() if from_hotkey else None
        self.target = target if target and target.process != os.getpid() else None
        self.begin("recording")
        self.original.clear()
        try:
            self.recorder.start(self.settings.microphone)
        except AudioError as exc:
            self.on_error(self.gate.generation, str(exc))
            return
        self.status.setText("正在听，慢慢说")
        self.hint.setText("最长 2 分钟；停顿不会自动结束。Esc 取消本次录音。")
        self.overlay.hint.setText(
            "松开快捷键结束，Esc 取消"
            if from_hotkey and self.settings.hold_to_talk
            else "再次按快捷键结束，Esc 取消"
        )
        self.overlay.label.setText("正在听  00:00")
        self.overlay.level.setValue(0)
        self.overlay.level.show()
        self.overlay.show_near_bottom()

    def stop_recording(self):
        if self.state != "recording":
            return
        try:
            samples = self.recorder.stop()
        except Exception:
            self.on_error(self.gate.generation, "录音设备已断开，请重新选择麦克风。")
            return
        if self.recorder.overflow:
            self.extra_warnings.append("录音期间设备报告丢帧，请检查原文是否完整。")
        self.state = "busy"
        self.status.setText("正在本地识别…")
        self.hint.setText("原始转写会保留，识别后再整理整段表达。")
        self.overlay.label.setText("正在识别和整理…")
        self.overlay.hint.setText("Esc 取消本次处理")
        self.refresh_controls()
        self.pipeline.start(self.gate.generation, self.gate.cancel_event, self.settings, samples, "audio")

    def tick(self):
        if self.state == "recording":
            seconds = int(time.monotonic() - self.recorder.started)
            self.overlay.label.setText(f"正在听  {seconds // 60:02}:{seconds % 60:02}")
            if self.recorder.limit_reached.is_set():
                self.stop_recording()
                self.set_notice("已达到 2 分钟上限，正在处理刚才的录音。")
            elif self.from_hotkey and self.settings.hold_to_talk and not shortcut_held(self.settings.hotkey):
                self.stop_recording()
        if self.state in ("recording", "busy") and self.target:
            if current_target() != self.target:
                self.target_changed = True

    def on_level(self, level: float):
        if self.state == "recording":
            self.meter.setValue(int(level * 100))
            self.overlay.level.setValue(int(level * 100))

    def on_stage(self, job: int, message: str):
        if self.gate.accepts(job):
            self.status.setText(message)
            self.overlay.label.setText(message)

    def on_transcript(self, job: int, text: str):
        if self.gate.accepts(job):
            self.original.setPlainText(text)

    def finish_ui(self):
        self.state = "idle"
        self.overlay.hide()
        self.meter.setValue(0)
        if self.hotkeys:
            self.hotkeys.unregister(3)
        self.refresh_controls()

    def on_complete(self, job: int, data: dict):
        # A duplicate completion must not reset the insert guard via textChanged.
        if not self.gate.accepts(job) or self.state != "busy":
            return
        result = data["result"]
        self.original.setPlainText(result.original)
        self.result.setPlainText(result.text)
        self.finish_ui()
        warnings = list(result.warnings) + self.extra_warnings
        self.stats.setText(
            f"本地识别 {data['asr_seconds']:.1f} 秒    文字整理 {result.elapsed:.1f} 秒    本次 {result.usage.get('total_tokens', 0)} tokens"
        )
        if self.settings.save_history:
            from .history import HistoryStore

            try:
                HistoryStore().append(result.original, result.text)
            except Exception:
                warnings.append("本次历史记录保存失败，当前结果仍可使用。")
        self.status.setText("整理好了，请核对" if warnings else "整理好了")
        self.hint.setText(f"可以直接编辑结果，或回到输入框按 {INSERT_HOTKEY}。")
        self.set_notice("\n".join(warnings))
        needs_review = bool(warnings) and self.settings.review_warnings
        if self.target and self.settings.auto_insert and not needs_review and not self.target_changed:
            self.attempt_insert(job, self.target)
        else:
            if self.target_changed:
                self.set_notice(
                    "\n".join(warnings + ["输入位置曾发生变化，结果已保留，请选择目标后手动输入。"])
                )
            if self.target_changed:
                self.feedback("输入位置已变化，结果已保留", f"回到输入框按 {INSERT_HOTKEY} 补输")
            elif needs_review:
                self.feedback("结果待核对", "点击托盘图标查看原文和整理结果")
            else:
                self.feedback("整理好了，结果已保留", f"在目标输入框按 {INSERT_HOTKEY} 输入")

    def feedback(self, title: str, hint: str, milliseconds: int = 4500):
        """Global dictation never activates the main window, including failures."""
        if self.from_hotkey:
            self.overlay.show_message(title, hint, milliseconds)
            self.tray.setToolTip(f"好好说 · {title}")
        else:
            self.reveal()

    def attempt_insert(self, job: int, target, explicit: bool = False, tries: int = 0):
        if not self.gate.accepts(job) or self.gate.inserted or self.state != "idle":
            return
        if modifiers_held() and tries < 30:
            QTimer.singleShot(60, lambda: self.attempt_insert(job, target, explicit, tries + 1))
            return
        if not explicit and self.target_changed:
            self.set_notice("输入位置已变化，请核对结果后手动输入。")
            self.feedback("输入位置已变化，结果已保留", f"回到输入框按 {INSERT_HOTKEY} 补输")
            return
        if not self.gate.claim_insert(job):
            return
        try:
            paste_text(self.result.toPlainText(), target, QApplication.clipboard())
            self.status.setText("已提交输入")
            self.hint.setText("请在目标应用查看文字。可继续按录音快捷键输入下一段。")
            self.refresh_controls()
            if self.from_hotkey:
                self.feedback("已输入", "可以继续按住快捷键说下一段", 1200)
        except PasteError as exc:
            self.gate.inserted = False
            self.set_notice(str(exc))
            self.refresh_controls()
            self.feedback("未能自动输入，结果已保留", "点击托盘图标查看原因或复制结果")

    def schedule_manual_insert(self):
        if self.state != "idle" or not self.result.toPlainText().strip() or self.gate.inserted:
            return
        job = self.gate.generation
        self.from_hotkey = False
        self.state = "waiting"
        self.status.setText("请在 3 秒内点击目标输入框")
        self.refresh_controls()

        def insert():
            if not self.gate.accepts(job) or self.state != "waiting":
                return
            self.state = "idle"
            target = current_target()
            if target and target.process != os.getpid():
                self.attempt_insert(job, target, explicit=True)
            else:
                self.set_notice(f"未选中其他窗口，请切换到目标输入框后按 {INSERT_HOTKEY}。")
            self.refresh_controls()

        QTimer.singleShot(3000, insert)

    def clean_text(self):
        text = self.original.toPlainText().strip()
        if self.state != "idle" or not text:
            return
        self.target = None
        self.from_hotkey = False
        job, cancel = self.begin("busy")
        self.pipeline.start(job, cancel, self.settings, text, "text")

    def import_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择录音（最长 2 分钟）",
            "",
            "音频文件 (*.wav *.m4a *.mp3 *.flac *.ogg *.aac);;所有文件 (*)",
        )
        if path:
            self.process_file(path)

    def process_file(self, path: str):
        if self.state != "idle":
            return
        if not models_ready(self.settings.models):
            self.set_notice("请先下载本地语音模型。")
            return
        self.target = None
        self.from_hotkey = False
        job, cancel = self.begin("busy")
        self.original.clear()
        self.pipeline.start(job, cancel, self.settings, path, "file")

    def download(self):
        if self.state != "idle":
            return
        self.target = None
        self.from_hotkey = False
        job, cancel = self.begin("download")
        self.status.setText("正在下载语音模型…")
        self.hint.setText("约 240 MB，仅首次需要。下载后会核对完整性。")
        self.pipeline.start(job, cancel, self.settings, None, "download")

    def on_downloaded(self, job: int):
        if self.gate.accepts(job):
            self.finish_ui()
            self.status.setText("语音模型已就绪")
            self.hint.setText("现在可以开始录音，也可以导入已有录音。")

    def on_error(self, job: int, message: str):
        if self.gate.accepts(job):
            self.finish_ui()
            self.status.setText("本次处理未完成")
            self.hint.setText("原始文字已保留，可以复制或重新整理。")
            self.set_notice(message)
            self.feedback("本次处理未完成", "点击托盘图标查看原因或重试")

    def cancel(self):
        if self.state == "idle":
            return
        self.gate.cancel()
        self.recorder.cancel()
        self.finish_ui()
        self.status.setText("已取消")
        self.hint.setText("本次结果不会输入到其他窗口。")

    def clear(self):
        if self.state != "idle":
            return
        self.gate.begin()
        self.original.clear()
        self.result.clear()
        self.set_notice()
        self.status.setText("准备好，慢慢说")
        self.stats.setText("默认仅保留当前会话；可在设置中开启本机加密历史。")

    def copy_text(self, result: bool):
        text = self.result.toPlainText() if result else self.original.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("已复制结果" if result else "已复制原文")

    def open_settings(self):
        try:
            current = replace(self.settings, start_on_login=startup_enabled())
        except StartupError as exc:
            self.set_notice(str(exc))
            return
        dialog = SettingsDialog(current, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new = dialog.updated
            if self.hotkeys and new.hotkey != self.settings.hotkey:
                modifiers, key = HOTKEYS[new.hotkey]
                if not self.hotkeys.register(1, modifiers, key):
                    self.configure_hotkeys()
                    self.set_notice("所选快捷键已被占用，设置未修改，请选择其他组合。")
                    return
            try:
                save_settings_with_startup(new)
                self.settings = new
                self.configure_hotkeys()
                self.refresh_controls()
                self.status.setText("设置已保存")
            except StartupError as exc:
                self.configure_hotkeys()
                self.set_notice(str(exc))
            except OSError:
                self.configure_hotkeys()
                self.set_notice("无法写入本地设置，请检查用户目录权限。")

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_history(self):
        from .history import HistoryStore

        store = HistoryStore()
        try:
            rows = store.read()
        except OSError:
            self.set_notice("历史记录无法读取，请检查本地目录权限。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("本机历史 · 好好说")
        dialog.resize(650, 440)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("默认不保存。可在设置中开启，加密保留最近 7 天、最多 100 条。"))
        listing = QListWidget()
        for row in rows:
            date = time.strftime("%m-%d %H:%M", time.localtime(row["created"]))
            listing.addItem(f"{date}  {row['text'][:70].replace(chr(10), ' ')}")
        layout.addWidget(listing)
        actions = QHBoxLayout()
        load_button = QPushButton("载入选中记录")
        load_button.setEnabled(bool(rows))
        clear_button = QPushButton("清空全部历史")
        actions.addWidget(load_button)
        actions.addStretch()
        actions.addWidget(clear_button)
        layout.addLayout(actions)

        def load():
            index = listing.currentRow()
            if index < 0:
                return
            self.gate.begin()
            self.target = None
            self.original.setPlainText(rows[index]["original"])
            self.result.setPlainText(rows[index]["text"])
            self.status.setText("已载入历史，请核对后使用")
            self.set_notice("这是一条历史记录，请检查日期、人物和条件是否仍适用。")
            dialog.accept()

        def clear_history():
            try:
                store.clear()
                rows.clear()
                listing.clear()
                load_button.setEnabled(False)
            except OSError:
                QMessageBox.warning(dialog, "无法清空", "请检查本地目录权限。")

        load_button.clicked.connect(load)
        listing.itemDoubleClicked.connect(lambda _: load())
        clear_button.clicked.connect(clear_history)
        dialog.exec()

    def closeEvent(self, event):
        if self.native and not self.quitting and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            self.tray.showMessage(
                "好好说仍在运行",
                f"使用 {self.settings.hotkey} 录音；右键托盘图标可退出。",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            event.ignore()
        else:
            self.shutdown()
            event.accept()

    def shutdown(self):
        self.gate.cancel()
        self.recorder.cancel()
        self.timer.stop()
        self.overlay.dismiss_timer.stop()
        self.overlay.close()
        self.tray.hide()
        if self.hotkeys:
            self.hotkeys.close()
            QApplication.instance().removeNativeEventFilter(self.hotkeys)

    def quit_app(self):
        self.quitting = True
        self.shutdown()
        QApplication.instance().quit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="启动后自动退出，用于打包检查")
    parser.add_argument("--background", action="store_true", help="配置就绪时仅在托盘运行")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("BetterVoiceInput")
    app.setOrganizationName("BetterVoiceInput")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(data_dir() / "application.lock"))
    lock.setStaleLockTime(0)
    if not args.smoke and not lock.tryLock(100):
        QMessageBox.information(None, "好好说", "程序已在运行，请点击系统托盘中的麦克风图标。")
        return 0
    window = MainWindow(native=not args.smoke)
    background_ready = (
        models_ready(window.settings.models)
        and bool(read_key())
        and QSystemTrayIcon.isSystemTrayAvailable()
        and (args.smoke or 1 in window.hotkeys.registered)
    )
    if not args.background or not background_ready:
        window.show()
    if args.smoke:
        QTimer.singleShot(1500, window.quit_app)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
