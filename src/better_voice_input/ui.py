from __future__ import annotations

import math
import os
import shutil
from collections import deque
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .api_config import chat_completion_url
from .models import CATALOG, SENSE_VOICE, AsrModel, models_ready
from .settings import Settings, read_key, save_key
from .shortcuts import RECORDING_CHOICES

INK = "#17211F"
MUTED = "#6B7673"
ACCENT = "#0E7C86"
ACCENT_SOFT = "#E3F1F0"
RECORD = "#EF5F57"
HERO_TEXT = "#EAF6F4"

STYLE = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 14px; color: #17211F; }
QMainWindow, QDialog { background: #F5F4F0; }
QLabel { background: transparent; }
QLabel#brand { font-size: 22px; font-weight: 700; }
QLabel#title { font-size: 22px; font-weight: 700; }
QLabel#muted { color: #6B7673; font-size: 13px; }
QLabel#caption { color: #8A938F; font-size: 12px; }
QLabel#section { font-size: 15px; font-weight: 700; }
QLabel#cardTitle { font-size: 16px; font-weight: 700; }
QLabel#fieldLabel { color: #4F5A57; font-size: 13px; }
QLabel#count { background: #F1EFEA; color: #6B7673; border-radius: 10px; padding: 2px 9px; font-size: 12px; }
QLabel#tag { background: #E3F1F0; color: #0A646C; border-radius: 10px; padding: 2px 9px;
             font-size: 12px; font-weight: 700; }
QLabel#tagActive { background: #0E7C86; color: #FFFFFF; border-radius: 10px; padding: 2px 9px;
                   font-size: 12px; font-weight: 700; }
QLabel#strength { color: #2E3A37; font-size: 13px; }
QLabel#notice { background: #FFF5E1; color: #6E4E12; border: 1px solid #F3DFB4; border-radius: 12px;
                padding: 10px 14px; font-size: 13px; }

QFrame#hero QLabel { color: #EAF6F4; }
QLabel#status { font-size: 25px; font-weight: 700; color: #FFFFFF; }
QLabel#heroHint { color: #A9C9C6; font-size: 14px; }
QLabel#pill { border-radius: 11px; padding: 3px 11px; font-size: 12px; font-weight: 700;
              background: rgba(255, 255, 255, 0.12); color: #BFEAE4; }
QLabel#pill[tone="rec"] { background: rgba(239, 95, 87, 0.25); color: #FFC2BC; }
QLabel#pill[tone="busy"] { background: rgba(255, 207, 102, 0.20); color: #FFE3A3; }
QLabel#pill[tone="done"] { background: rgba(110, 231, 183, 0.20); color: #A6F2D2; }
QLabel#heroChip, QPushButton#heroChip { background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 14px; padding: 5px 12px;
    color: #CFE6E3; font-size: 12px; font-weight: 400; }
QPushButton#heroChip:hover { background: rgba(255, 255, 255, 0.16); border-color: rgba(255, 255, 255, 0.28); }
QPushButton#heroGhost { background: rgba(255, 255, 255, 0.10); color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.22); border-radius: 13px; padding: 5px 18px; font-size: 13px;
    min-height: 16px; }
QPushButton#heroGhost:hover { background: rgba(255, 255, 255, 0.18); }

QFrame#card { background: #FFFFFF; border: 1px solid #E6E2DA; border-radius: 18px; }
QFrame#card[accent="true"] { border: 1px solid #B9DCDA; }
QFrame#card QPlainTextEdit { background: transparent; border: none; padding: 2px 12px 12px 12px;
                             font-size: 16px; selection-background-color: #C5E6E6; }
QFrame#sectionCard { background: #FFFFFF; border: 1px solid #E6E2DA; border-radius: 16px; }
QFrame#modelCard { background: #FFFFFF; border: 1px solid #E6E2DA; border-radius: 16px; }
QFrame#modelCard[active="true"] { border: 2px solid #0E7C86; background: #FBFEFD; }
QFrame#locationBar { background: #FFFFFF; border: 1px solid #E6E2DA; border-radius: 14px; }
QFrame#footerBar { background: #FFFFFF; border-top: 1px solid #E6E2DA; }
QFrame#divider { background: #EEEAE3; max-height: 1px; min-height: 1px; border: none; }

QPlainTextEdit { background: #FFFFFF; border: 1px solid #DDD9D0; border-radius: 12px; padding: 10px;
                 selection-background-color: #C5E6E6; }
QPlainTextEdit:focus { border-color: #0E7C86; }
QLineEdit, QComboBox, QSpinBox { background: #FFFFFF; border: 1px solid #DDD9D0; border-radius: 10px;
    padding: 7px 11px; min-height: 22px; selection-background-color: #C5E6E6; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #0E7C86; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: #C6C0B4; }
QComboBox { padding-right: 32px; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView { background: #FFFFFF; border: 1px solid #DDD9D0; border-radius: 8px;
    selection-background-color: #E3F1F0; selection-color: #17211F; outline: none; padding: 4px; }

QPushButton { background: #FFFFFF; border: 1px solid #DFDBD2; border-radius: 11px; padding: 8px 16px;
              color: #24302D; }
QPushButton:hover { background: #F8F7F3; border-color: #CBC5B9; }
QPushButton:pressed { background: #EFEDE7; }
QPushButton:focus { border-color: #0E7C86; }
QPushButton:disabled { color: #ADB4B1; background: #F7F6F2; border-color: #ECE8E0; }
QPushButton#primary { background: #0E7C86; color: #FFFFFF; border: 1px solid #0E7C86; font-weight: 700; }
QPushButton#primary:hover { background: #0B6C75; border-color: #0B6C75; }
QPushButton#primary:pressed { background: #095A61; }
QPushButton#primary:disabled { background: #A9CFD2; border-color: #A9CFD2; color: #F3FAFA; }
QPushButton#toolbar { border-radius: 17px; padding: 7px 15px; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; color: #3C4744; }
QPushButton#ghost:hover { background: #ECE9E3; }
QPushButton#ghost:disabled { color: #B5BBB8; background: transparent; }
QPushButton#danger { background: transparent; border: 1px solid transparent; color: #B4443C; }
QPushButton#danger:hover { background: #FBECEA; }

QProgressBar { background: #E7E4DD; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #0E7C86; border-radius: 3px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #D3CEC4; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #B9B3A7; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: transparent; }
QListWidget { background: #FFFFFF; border: 1px solid #E6E2DA; border-radius: 14px; padding: 6px; outline: none; }
QListWidget::item { padding: 10px 12px; border-radius: 9px; color: #24302D; }
QListWidget::item:hover { background: #F5F4F0; }
QListWidget::item:selected { background: #E3F1F0; color: #17211F; }
QMenu { background: #FFFFFF; border: 1px solid #E0DCD3; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 26px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: #E3F1F0; color: #17211F; }
QToolTip { background: #17211F; color: #FFFFFF; border: none; padding: 6px 9px; border-radius: 6px; }
"""


class Glyph:
    MIC = ""
    SETTINGS = ""
    HISTORY = ""
    IMPORT = ""
    MODEL = ""
    DOWNLOAD = ""
    COPY = ""
    DELETE = ""
    CLEAR = ""
    CHECK = ""
    CHEVRON_DOWN = ""
    INFO = ""
    FOLDER = ""
    LOCK = ""
    EDIT = ""
    SEND = ""
    KEYBOARD = ""
    GLOBE = ""


def icon_font(pixel_size: int) -> QFont:
    families = set(QFontDatabase.families())
    name = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), "Segoe Fluent Icons")
    font = QFont(name)
    font.setPixelSize(pixel_size)
    return font


def glyph_pixmap(glyph: str, color: str, size: int = 16) -> QPixmap:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(icon_font(size))
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return pixmap


def glyph_icon(glyph: str, color: str = INK, size: int = 16, disabled: str = "#B5BBB8") -> QIcon:
    icon = QIcon(glyph_pixmap(glyph, color, size))
    icon.addPixmap(glyph_pixmap(glyph, disabled, size), QIcon.Mode.Disabled)
    return icon


def icon_text(text: str) -> str:
    """Leading space so the label does not touch its icon."""
    return f" {text}"


def make_button(text: str, glyph: str | None = None, kind: str | None = None, icon_color: str | None = None):
    widget = QPushButton(icon_text(text) if glyph and text else text)
    if kind:
        widget.setObjectName(kind)
    if glyph:
        color = icon_color or ("#FFFFFF" if kind == "primary" else "#3C4744")
        widget.setIcon(glyph_icon(glyph, color, 16, "#F3FAFA" if kind == "primary" else "#B5BBB8"))
        widget.setIconSize(QSize(16, 16))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return widget


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class ElidedLabel(QLabel):
    """Single-line label that shortens long paths in the middle instead of widening the window."""

    def __init__(self, text: str = "", name: str | None = None):
        super().__init__()
        self.full = ""
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(60)
        self.setText(text)

    def setText(self, text: str):
        self.full = text
        super().setText(text)
        self.setToolTip(text if self.fontMetrics().horizontalAdvance(text) > self.width() else "")

    def text(self) -> str:
        return self.full

    def resizeEvent(self, event):
        self.setToolTip(self.full if self.fontMetrics().horizontalAdvance(self.full) > self.width() else "")
        super().resizeEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideMiddle, rect.width())
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


def glyph_label(glyph: str, color: str, size: int = 16) -> QLabel:
    widget = QLabel()
    widget.setPixmap(glyph_pixmap(glyph, color, size))
    widget.setFixedSize(size + 4, size + 4)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def repolish(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        gradient = QLinearGradient(0, 0, 64, 64)
        gradient.setColorAt(0, QColor("#16A3A0"))
        gradient.setColorAt(1, QColor("#0B4F5C"))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 17, 17)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(25, 12, 14, 26), 7, 7)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor("#FFFFFF"), 3.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(18, 19, 28, 27), 200 * 16, 140 * 16)
        painter.drawLine(32, 46, 32, 52)
        pen = QPen(QColor(255, 255, 255, 150), 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(10, 15, 44, 36), 165 * 16, 30 * 16)
        painter.drawArc(QRectF(10, 15, 44, 36), -15 * 16, 30 * 16)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class LevelBars(QWidget):
    """A scrolling voice-level visualizer with a QProgressBar-like setValue API."""

    def __init__(self, bars: int = 36, color: str = "#7FE3D2", parent=None):
        super().__init__(parent)
        self.levels = deque([0.0] * bars, maxlen=bars)
        self.color = QColor(color)
        self.target = 0.0
        self._value = 0
        self.timer = QTimer(self)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self._advance)
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setValue(self, value: int):
        self._value = max(0, min(100, int(value)))
        if self._value == 0:
            self.target = 0.0
            if not any(self.levels):
                return
        # Speech RMS is compressed; a square root keeps quiet talkers visible.
        self.target = max(self.target, math.sqrt(self._value / 100))
        if not self.timer.isActive():
            self.timer.start()

    def value(self) -> int:
        return self._value

    def _advance(self):
        self.levels.append(self.target)
        self.target *= 0.55
        if self.target < 0.02:
            self.target = 0.0
            if not any(level > 0.01 for level in self.levels):
                self.levels.extend([0.0] * self.levels.maxlen)
                self.timer.stop()
        self.update()

    def hideEvent(self, event):
        self.timer.stop()
        self.target = 0.0
        self.levels.extend([0.0] * self.levels.maxlen)
        super().hideEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        count = self.levels.maxlen
        gap = 4
        width = max(2.0, (self.width() - gap * (count - 1)) / count)
        width = min(width, 6.0)
        x = 0.0
        middle = self.height() / 2
        for index, level in enumerate(self.levels):
            height = max(width, level * (self.height() - 2))
            color = QColor(self.color)
            color.setAlphaF(0.28 + 0.72 * (index + 1) / count if level > 0.01 else 0.22)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, middle - height / 2, width, height), width / 2, width / 2)
            x += width + gap


class MicButton(QPushButton):
    """Round record button. objectName "recording" switches it to the stop state."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.busy = False
        self.phase = 0.0
        self.hover = False
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(1500)
        self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self._tick)
        self.keyboard_focus = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedSize(150, 146)

    def focusInEvent(self, event):
        self.keyboard_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
        )
        super().focusInEvent(event)

    def _tick(self, value):
        self.phase = float(value)
        self.update()

    def set_busy(self, busy: bool):
        self.busy = busy
        self._sync_animation()

    def _sync_animation(self):
        animate = self.busy or self.objectName() == "recording"
        if animate and self.animation.state() != QVariantAnimation.State.Running:
            self.animation.start()
        elif not animate and self.animation.state() == QVariantAnimation.State.Running:
            self.animation.stop()
            self.phase = 0.0
        self.update()

    def setObjectName(self, name: str):
        super().setObjectName(name)
        self._sync_animation()

    def enterEvent(self, event):
        self.hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        recording = self.objectName() == "recording"
        diameter = 88.0
        center_x, center_y = self.width() / 2, 4 + 10 + diameter / 2
        if not self.isEnabled() and not self.busy:
            painter.setOpacity(0.5)
        if recording:
            for offset in (0.0, 0.5):
                progress = (self.phase + offset) % 1.0
                radius = diameter / 2 + 4 + progress * 14
                color = QColor(RECORD)
                color.setAlphaF(0.45 * (1 - progress))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))
        else:
            halo = QColor(255, 255, 255, 44 if self.hover else 26)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            radius = diameter / 2 + 9
            painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))
        circle = QRectF(center_x - diameter / 2, center_y - diameter / 2, diameter, diameter)
        if recording:
            fill = QColor("#F26A62") if self.hover else QColor(RECORD)
        else:
            fill = QColor("#FFFFFF") if self.hover or self.busy else QColor("#F4FBFA")
        if self.isDown():
            fill = fill.darker(108)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(circle)
        if self.hasFocus() and self.keyboard_focus:
            painter.setPen(QPen(QColor(255, 255, 255, 170), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle.adjusted(-5, -5, 5, 5))
        if recording:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRoundedRect(QRectF(center_x - 13, center_y - 13, 26, 26), 6, 6)
        elif self.busy:
            pen = QPen(QColor(ACCENT), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(circle.adjusted(24, 24, -24, -24), int(-self.phase * 360 * 16), 100 * 16)
        else:
            painter.setFont(icon_font(34))
            painter.setPen(QColor(ACCENT))
            painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, Glyph.MIC)
        painter.setOpacity(1.0 if self.isEnabled() or self.busy else 0.5)
        font = QFont(self.font())
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        text_rect = QRectF(0, circle.bottom() + 12, self.width(), 24)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())


class ComboBox(QComboBox):
    """QComboBox with a drawn chevron, so no image files are needed for the arrow."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setFont(icon_font(12))
        painter.setPen(QColor(MUTED if self.isEnabled() else "#B5BBB8"))
        painter.drawText(
            QRectF(self.width() - 32, 0, 22, self.height()), Qt.AlignmentFlag.AlignCenter, Glyph.CHEVRON_DOWN
        )


class HeroCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hero")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 24, 24)
        painter.setClipPath(path)
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0, QColor("#0C2A30"))
        base.setColorAt(0.55, QColor("#0F3D45"))
        base.setColorAt(1, QColor("#12545C"))
        painter.fillPath(path, base)
        glow = QRadialGradient(rect.right() - 150, rect.top() + 40, 260)
        glow.setColorAt(0, QColor(70, 214, 190, 70))
        glow.setColorAt(1, QColor(70, 214, 190, 0))
        painter.fillRect(rect, glow)
        glow = QRadialGradient(rect.left() + 60, rect.bottom() + 40, 240)
        glow.setColorAt(0, QColor(120, 160, 255, 34))
        glow.setColorAt(1, QColor(120, 160, 255, 0))
        painter.fillRect(rect, glow)
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 24, 24)


class Switch(QCheckBox):
    """A toggle switch that keeps the QCheckBox API."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        metrics = self.fontMetrics()
        return QSize(46 + 12 + metrics.horizontalAdvance(self.text()), max(26, metrics.height() + 6))

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, (self.height() - 24) / 2, 44, 24)
        on = self.isChecked()
        if not self.isEnabled():
            painter.setOpacity(0.5)
        painter.setPen(Qt.PenStyle.NoPen if on else QPen(QColor("#CFC9BE"), 1))
        painter.setBrush(QColor(ACCENT) if on else QColor("#ECE9E3"))
        painter.drawRoundedRect(track, 12, 12)
        knob = QRectF(track.right() - 21 if on else track.left() + 3, track.top() + 3, 18, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob)
        if self.hasFocus():
            painter.setPen(QPen(QColor(ACCENT), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(-2.5, -2.5, 2.5, 2.5), 14, 14)
        painter.setPen(QColor(INK))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(track.right() + 12, 0, self.width() - track.right() - 12, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )


class RecordingOverlay(QWidget):
    TONES = {"rec": RECORD, "busy": "#F4B740", "done": "#3CCB9C", "warn": "#F4B740"}

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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tone = "rec"
        self.phase = 0.0
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.hide)
        self.pulse = QVariantAnimation(self)
        self.pulse.setStartValue(0.0)
        self.pulse.setEndValue(1.0)
        self.pulse.setDuration(1200)
        self.pulse.setLoopCount(-1)
        self.pulse.valueChanged.connect(self._pulse)
        self.setFixedSize(380, 104)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(52, 22, 26, 22)
        layout.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.label = QLabel("正在听  00:00")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 700; background: transparent;")
        self.hint = QLabel("松开快捷键结束，Esc 取消")
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.setStyleSheet("color: #9DBDB9; font-size: 12px; background: transparent;")
        text.addWidget(self.label)
        text.addWidget(self.hint)
        layout.addLayout(text, 1)
        self.level = LevelBars(14, "#7FE3D2")
        self.level.setFixedWidth(104)
        layout.addWidget(self.level)

    def _pulse(self, value):
        self.phase = float(value)
        self.update()

    def set_tone(self, tone: str):
        self.tone = tone if tone in self.TONES else "rec"
        if self.tone in ("rec", "busy"):
            if self.pulse.state() != QVariantAnimation.State.Running:
                self.pulse.start()
        else:
            self.pulse.stop()
            self.phase = 0.0
        self.update()

    def show_near_bottom(self):
        self.dismiss_timer.stop()
        area = self.screen().availableGeometry()
        self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 28)
        self.show()

    def show_message(self, title: str, hint: str, milliseconds: int = 4500, tone: str = "done"):
        self.label.setText(title)
        self.hint.setText(hint)
        self.level.hide()
        self.set_tone(tone)
        self.show_near_bottom()
        self.dismiss_timer.start(milliseconds)

    def hideEvent(self, event):
        self.pulse.stop()
        super().hideEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(12, 10, -12, -14)
        for step in range(8):
            shadow = QColor(0, 0, 0, 10 - step)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow)
            painter.drawRoundedRect(body.adjusted(-step, -step + 3, step, step + 3), 22 + step, 22 + step)
        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        gradient.setColorAt(0, QColor(14, 38, 43, 246))
        gradient.setColorAt(1, QColor(17, 60, 67, 246))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawRoundedRect(body, 22, 22)
        color = QColor(self.TONES.get(self.tone, RECORD))
        center = body.left() + 22, body.center().y()
        if self.tone in ("rec", "busy"):
            ring = 6 + self.phase * 9
            halo = QColor(color)
            halo.setAlphaF(0.5 * (1 - self.phase))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QRectF(center[0] - ring, center[1] - ring, ring * 2, ring * 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(center[0] - 6, center[1] - 6, 12, 12))


def card(accent: bool = False) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    if accent:
        frame.setProperty("accent", True)
    return frame


def text_column(title: str, hint: str, accent: bool = False) -> tuple[QWidget, QPlainTextEdit, QLabel]:
    widget = card(accent)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(8, 16, 8, 6)
    layout.setSpacing(8)
    row = QHBoxLayout()
    row.setContentsMargins(14, 0, 12, 0)
    row.setSpacing(9)
    dot = QLabel()
    dot.setFixedSize(9, 9)
    dot.setStyleSheet(f"background: {ACCENT if accent else '#C5BFB3'}; border-radius: 4px;")
    row.addWidget(dot)
    row.addWidget(label(title, "cardTitle"))
    row.addStretch()
    count = label("0 字", "count")
    row.addWidget(count)
    layout.addLayout(row)
    editor = QPlainTextEdit()
    editor.setPlaceholderText(hint)
    editor.textChanged.connect(lambda: count.setText(f"{len(editor.toPlainText())} 字"))
    layout.addWidget(editor, 1)
    return widget, editor, count


class Section(QFrame):
    def __init__(self, title: str, description: str, glyph: str):
        super().__init__()
        self.setObjectName("sectionCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(12)
        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(glyph_pixmap(glyph, ACCENT, 16))
        badge.setStyleSheet(f"background: {ACCENT_SOFT}; border-radius: 10px;")
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "section"))
        text.addWidget(label(description, "muted", wrap=True))
        head.addLayout(text, 1)
        layout.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        layout.addLayout(self.body)

    def form(self) -> QFormLayout:
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.body.addLayout(form)
        return form


def field_label(text: str) -> QLabel:
    widget = label(text, "fieldLabel")
    widget.setMinimumWidth(76)
    return widget


def dialog_header(title: str, subtitle: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(30, 26, 30, 10)
    layout.setSpacing(4)
    layout.addWidget(label(title, "title"))
    layout.addWidget(label(subtitle, "muted", wrap=True))
    return widget


def scroll_body(spacing: int = 14) -> tuple[QScrollArea, QVBoxLayout]:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(30, 8, 26, 22)
    layout.setSpacing(spacing)
    area.setWidget(content)
    return area, layout


def footer_bar() -> tuple[QFrame, QHBoxLayout]:
    frame = QFrame()
    frame.setObjectName("footerBar")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(30, 14, 30, 14)
    layout.setSpacing(10)
    return frame, layout


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.updated = settings
        self.setWindowTitle("设置 · 好好说")
        self.resize(640, 780)
        self.setMinimumSize(560, 560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(dialog_header("设置", "调整文字整理服务、录音方式和个人词库。保存后立即生效。"))
        area, layout = scroll_body()
        outer.addWidget(area, 1)

        api = Section("文字整理服务", "录音在本机识别后，只把文字发送到这里填写的 API 进行整理。", Glyph.GLOBE)
        form = api.form()
        self.base_url = QLineEdit(settings.api_base_url)
        self.base_url.setPlaceholderText("例如 https://api.example.com/v1")
        self.base_url.setToolTip("填写兼容 Chat Completions 的 API 地址，支持 Base URL 或完整请求地址。")
        form.addRow(field_label("API 地址"), self.base_url)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.update_key_hint()
        self.base_url.textChanged.connect(self.api_address_changed)
        form.addRow(field_label("API Key"), self.key)
        self.model = QLineEdit(settings.model)
        self.model.setPlaceholderText("填写服务商提供的模型名称")
        form.addRow(field_label("模型名称"), self.model)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(int(settings.api_timeout))
        self.timeout.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.timeout.setMaximumWidth(140)
        form.addRow(field_label("请求超时"), self.timeout)
        layout.addWidget(api)

        recording = Section("录音与输入", "全局快捷键随时可用，结果直接输入到原来的光标处。", Glyph.MIC)
        form = recording.form()
        self.mic = ComboBox()
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
        form.addRow(field_label("麦克风"), self.mic)
        self.hotkey = ComboBox()
        self.hotkey.addItems(RECORDING_CHOICES)
        if settings.hotkey not in RECORDING_CHOICES:
            self.hotkey.addItem(settings.hotkey)
        self.hotkey.setCurrentText(settings.hotkey)
        self.hotkey.setMaximumWidth(200)
        form.addRow(field_label("录音快捷键"), self.hotkey)
        self.hold = Switch("按住快捷键说话，松开结束")
        self.hold.setChecked(settings.hold_to_talk)
        form.addRow(field_label("录音方式"), self.hold)
        form.addRow(field_label("输入方式"), label("直接输入单行文字，支持终端，不自动回车", "muted", wrap=True))
        layout.addWidget(recording)

        privacy = Section("隐私与启动", "录音只在内存中处理，识别后立即释放，不保存录音文件。", Glyph.LOCK)
        self.history = Switch("保留最近 5 条文字（本机加密，最长 7 天）")
        self.history.setChecked(settings.save_history)
        privacy.body.addWidget(self.history)
        self.startup = Switch("开机自启动，登录 Windows 后在托盘运行")
        self.startup.setChecked(settings.start_on_login)
        privacy.body.addWidget(self.startup)
        layout.addWidget(privacy)

        words = Section(
            "个人词库",
            "每行一个常用人名、项目名或英文术语，最多 100 个，整理时用于纠正拼写。",
            Glyph.EDIT,
        )
        self.glossary = QPlainTextEdit("\n".join(settings.glossary))
        self.glossary.setMinimumHeight(130)
        self.glossary.setMaximumHeight(180)
        words.body.addWidget(self.glossary)
        layout.addWidget(words)
        layout.addStretch()

        footer, actions = footer_bar()
        actions.addWidget(glyph_label(Glyph.LOCK, MUTED, 14))
        actions.addWidget(label("密钥按 API 地址分别保存在 Windows 凭据管理器", "caption"))
        actions.addStretch()
        cancel = make_button("取消")
        cancel.clicked.connect(self.reject)
        save = make_button("保存设置", Glyph.CHECK, "primary")
        save.setDefault(True)
        save.clicked.connect(self.save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        outer.addWidget(footer)

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


def free_space(path: Path) -> int | None:
    for candidate in (path, *path.parents):
        try:
            if candidate.exists():
                return shutil.disk_usage(candidate).free
        except OSError:
            return None
    return None


def format_bytes(size: int) -> str:
    return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"


def delete_model_files(model: AsrModel, directory: Path) -> None:
    for spec in model.files:
        (directory / spec.name).unlink(missing_ok=True)
    folders = sorted({(directory / spec.name).parent for spec in model.files}, key=lambda p: len(p.parts))
    for folder in reversed(folders):
        if folder != directory or model.folder:
            try:
                folder.rmdir()  # Only removes folders that are now empty.
            except OSError:
                pass


class ModelCard(QFrame):
    def __init__(self, model: AsrModel):
        super().__init__()
        self.model = model
        self.setObjectName("modelCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 14)
        layout.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(label(model.name, "cardTitle"))
        self.tag = label(model.tagline, "tag")
        head.addWidget(self.tag)
        self.active_tag = label("使用中", "tagActive")
        head.addWidget(self.active_tag)
        head.addStretch()
        head.addWidget(label(f"{model.languages}    {model.size_label}", "muted"))
        layout.addLayout(head)
        strengths = QVBoxLayout()
        strengths.setSpacing(5)
        for text in model.strengths:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(glyph_label(Glyph.CHECK, ACCENT, 13))
            row.addWidget(label(text, "strength"), 1)
            strengths.addLayout(row)
        layout.addLayout(strengths)
        caveat = QHBoxLayout()
        caveat.setSpacing(8)
        caveat.addWidget(glyph_label(Glyph.INFO, "#9AA19E", 13), 0, Qt.AlignmentFlag.AlignTop)
        caveat.addWidget(label(model.caveat, "caption", wrap=True), 1)
        layout.addLayout(caveat)
        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.state = ElidedLabel("", "muted")
        bottom.addWidget(self.state, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(160)
        bottom.addWidget(self.progress)
        self.delete_button = make_button("删除", Glyph.DELETE, "danger", "#B4443C")
        bottom.addWidget(self.delete_button)
        self.cancel_button = make_button("取消下载")
        bottom.addWidget(self.cancel_button)
        self.action = make_button("", None, "primary")
        self.action.setMinimumWidth(128)
        bottom.addWidget(self.action)
        layout.addLayout(bottom)

    def update_state(self, *, active: bool, ready: bool, directory: Path, downloading: str | None, percent: int):
        mine = downloading == self.model.id
        self.setProperty("active", active and ready)
        repolish(self)
        self.active_tag.setVisible(active and ready)
        self.progress.setVisible(mine)
        self.progress.setValue(percent if mine else 0)
        self.cancel_button.setVisible(mine)
        self.delete_button.setVisible(ready and not active and not mine and self.model.id != SENSE_VOICE.id)
        self.action.setVisible(not mine)
        self.action.setIcon(QIcon())
        if mine:
            self.state.setText(f"正在下载 {percent}%  ·  下载后自动校验完整性")
        elif ready:
            self.state.setText(f"已下载  ·  {directory}")
        else:
            self.state.setText("未下载" + ("  ·  当前选择，需下载后才能识别" if active else ""))
        if ready and active:
            self.action.setText("正在使用")
            self.action.setEnabled(False)
        elif ready:
            self.action.setText("使用此模型")
            self.action.setEnabled(True)
        else:
            self.action.setText(icon_text(f"下载 · {self.model.size_label.removeprefix('约 ')}"))
            self.action.setIcon(glyph_icon(Glyph.DOWNLOAD, "#FFFFFF", 16, "#F3FAFA"))
            self.action.setEnabled(downloading is None)
            self.action.setToolTip("请等待当前下载完成" if downloading else "")


class ModelDialog(QDialog):
    """Choose, download and switch local speech models."""

    changed = Signal(object)

    def __init__(self, settings: Settings, downloads, apply, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.downloads = downloads
        self.apply = apply
        self.setWindowTitle("语音模型 · 好好说")
        available = self.screen().availableGeometry().height() if self.screen() else 900
        self.resize(720, max(560, min(860, available - 60)))
        self.setMinimumSize(600, 520)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(
            dialog_header("语音模型", "全部在本机识别，录音不会上传。按需下载，随时切换；当前模型保持不变，直到你选择其他模型。")
        )
        area, layout = scroll_body(12)
        outer.addWidget(area, 1)

        location = QFrame()
        location.setObjectName("locationBar")
        row = QHBoxLayout(location)
        row.setContentsMargins(16, 12, 12, 12)
        row.setSpacing(12)
        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(glyph_pixmap(Glyph.FOLDER, ACCENT, 16))
        badge.setStyleSheet(f"background: {ACCENT_SOFT}; border-radius: 10px;")
        row.addWidget(badge)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label("下载位置", "fieldLabel"))
        self.location = ElidedLabel("", "strength")
        text.addWidget(self.location)
        row.addLayout(text, 1)
        self.space = label("", "caption")
        row.addWidget(self.space)
        self.change_location = make_button("更改…", None, "toolbar")
        self.change_location.clicked.connect(self.choose_location)
        row.addWidget(self.change_location)
        self.open_location = make_button("打开", Glyph.FOLDER, "toolbar")
        self.open_location.clicked.connect(self.open_folder)
        row.addWidget(self.open_location)
        layout.addWidget(location)

        self.cards: dict[str, ModelCard] = {}
        for model in CATALOG:
            item = ModelCard(model)
            item.action.clicked.connect(lambda _=False, m=model: self.primary_action(m))
            item.cancel_button.clicked.connect(lambda _=False: self.downloads.cancel())
            item.delete_button.clicked.connect(lambda _=False, m=model: self.delete_model(m))
            self.cards[model.id] = item
            layout.addWidget(item)
        note = label(
            "准确率来自各模型公开测试和本机示例录音，实际效果因口音、麦克风和环境而异。"
            "切换后首次识别需要几秒加载模型。",
            "caption",
            wrap=True,
        )
        layout.addWidget(note)
        layout.addStretch()

        footer, actions = footer_bar()
        self.message = label("", "muted")
        actions.addWidget(self.message, 1)
        close = make_button("完成", None, "primary")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        outer.addWidget(footer)

        downloads.progress.connect(self.on_progress)
        downloads.finished.connect(self.on_finished)
        downloads.failed.connect(self.on_failed)
        self.refresh()

    def done(self, result):
        for signal, slot in (
            (self.downloads.progress, self.on_progress),
            (self.downloads.finished, self.on_finished),
            (self.downloads.failed, self.on_failed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(result)

    def refresh(self):
        root = self.settings.download_root
        space = free_space(root)
        self.location.setText(str(root))
        self.space.setText(f"剩余 {format_bytes(space)}" if space is not None else "")
        busy = self.downloads.active
        self.change_location.setEnabled(busy is None)
        self.change_location.setToolTip("下载进行中，完成后再更改位置" if busy else "")
        for model in CATALOG:
            directory = self.settings.model_path(model.id)
            self.cards[model.id].update_state(
                active=model.id == self.settings.asr_model,
                ready=models_ready(directory, model=model),
                directory=directory,
                downloading=busy,
                percent=self.downloads.percent,
            )

    def commit(self, settings: Settings) -> bool:
        if not self.apply(settings):
            QMessageBox.warning(self, "无法保存", "无法写入本地设置，请检查用户目录权限。")
            return False
        self.settings = settings
        self.changed.emit(settings)
        self.refresh()
        return True

    def primary_action(self, model: AsrModel):
        directory = self.settings.model_path(model.id)
        if models_ready(directory, model=model):
            if self.commit(replace(self.settings, asr_model=model.id)):
                self.message.setText(f"已切换到 {model.name}，下次录音生效。")
            return
        space = free_space(directory)
        if space is not None and space < model.size * 1.05:
            QMessageBox.warning(
                self,
                "磁盘空间不足",
                f"{model.name} 需要约 {format_bytes(model.size)}，所选位置只剩 {format_bytes(space)}。\n请更改下载位置后重试。",
            )
            return
        if self.downloads.start(model.id, directory):
            self.message.setText(f"开始下载 {model.name}，可以关闭此窗口，下载会在后台继续。")
        self.refresh()

    def delete_model(self, model: AsrModel):
        directory = self.settings.model_path(model.id)
        answer = QMessageBox.question(
            self,
            "删除模型",
            f"删除 {model.name} 的模型文件（{model.size_label}）？\n{directory}\n\n之后需要时可以重新下载。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_model_files(model, directory)
        except OSError:
            QMessageBox.warning(self, "未能删除", "模型文件正在使用或没有权限，请稍后重试。")
        paths = {key: value for key, value in self.settings.model_paths.items() if key != model.id}
        if paths != self.settings.model_paths:
            self.commit(replace(self.settings, model_paths=paths))
        self.message.setText(f"已删除 {model.name}。")
        self.refresh()

    def choose_location(self):
        if self.downloads.active:
            return
        chosen = QFileDialog.getExistingDirectory(self, "选择模型下载位置", str(self.settings.download_root))
        if not chosen:
            return
        directory = Path(chosen)
        try:
            probe = directory / f".write-test-{os.getpid()}"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            QMessageBox.warning(self, "无法使用此位置", "没有写入权限，请选择其他文件夹。")
            return
        if self.commit(self.settings.with_download_root(directory)):
            self.message.setText("新下载将保存到此位置，已下载的模型保留在原处。")

    def open_folder(self):
        root = self.settings.download_root
        try:
            root.mkdir(parents=True, exist_ok=True)
            os.startfile(root)  # type: ignore[attr-defined]
        except OSError:
            self.message.setText("无法打开文件夹，请检查路径是否存在。")

    def on_progress(self, model_id: str, percent: int):
        item = self.cards.get(model_id)
        if item:
            item.progress.setValue(percent)
            item.state.setText(f"正在下载 {percent}%  ·  下载后自动校验完整性")

    def on_finished(self, model_id: str):
        self.message.setText("下载完成，点击“使用此模型”即可切换。")
        self.refresh()

    def on_failed(self, model_id: str, message: str):
        self.message.setText(message or "已取消下载。")
        self.refresh()
