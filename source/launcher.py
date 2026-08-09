"""Point-and-click aim trainer used by the 点小球 page.

The runtime bundles this module as a marshal ``.raw`` file.  Keeping the
implementation here makes the coordinate rules easy to audit and rebuild.
"""
import ctypes
import random
import time

from PyQt5.QtCore import QPoint, QRect, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class AimBoard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 360)
        self.target_size = 42
        self.target = QRect()
        self.active = False
        self.started_at = 0.0
        self.targets_hit = 0
        self.targets_missed = 0
        self._last_click = 0.0
        self._color = QColor("#24b47e")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:#f7faf8;border:1px solid #d8e5de;border-radius:14px;")

    def _usable_rect(self):
        # Coordinates are always calculated from the current widget geometry.
        # This avoids the one-frame offset that occurred after a resize/layout pass.
        margin = max(self.target_size + 12, 18)
        return self.rect().adjusted(margin, margin, -margin, -margin)

    def _place_target(self):
        area = self._usable_rect()
        if area.width() < self.target_size or area.height() < self.target_size:
            self.target = QRect()
            self.update()
            return
        x = random.randint(area.left(), area.right() - self.target_size + 1)
        y = random.randint(area.top(), area.bottom() - self.target_size + 1)
        self.target = QRect(x, y, self.target_size, self.target_size)
        self.started_at = time.perf_counter()
        self.update()

    def begin(self):
        self.active = True
        self.targets_hit = 0
        self.targets_missed = 0
        self._place_target()

    def stop(self):
        self.active = False
        self.target = QRect()
        self.update()

    def set_target_size(self, size):
        self.target_size = max(18, int(size))
        if self.active:
            self._place_target()
        else:
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Never keep a target in stale coordinates after the parent layout grows.
        if self.active:
            self._place_target()

    def mousePressEvent(self, event):
        if not self.active or event.button() != Qt.LeftButton:
            return
        point = event.pos()
        if self.target.contains(point):
            now = time.perf_counter()
            self._last_click = now - self.started_at
            self.targets_hit += 1
            self._place_target()
        else:
            self.targets_missed += 1
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        painter.setClipPath(clip)
        painter.fillPath(clip, QColor("#f7faf8"))
        if self.target.isValid() and self.active:
            center = self.target.center()
            painter.setPen(QPen(QColor("#159463"), 2))
            painter.setBrush(self._color)
            painter.drawEllipse(center, self.target.width() // 2, self.target.height() // 2)
            painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
            painter.drawEllipse(center, max(3, self.target.width() // 2 - 7), max(3, self.target.height() // 2 - 7))
        else:
            painter.setPen(QColor("#6f8178"))
            painter.drawText(self.rect(), Qt.AlignCenter, "点击开始后，目标会出现在这里")
        painter.end()


class AimTrainerPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 30
        self._remaining = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(18)

        title = QLabel("点小球")
        title.setObjectName("contentTitle")
        subtitle = QLabel("练习点击速度与准确率，目标位置会随窗口大小实时校正")
        subtitle.setObjectName("contentStatus")
        root.addWidget(title)
        root.addWidget(subtitle)

        settings = QGroupBox("训练设置")
        form = QFormLayout(settings)
        form.setContentsMargins(18, 22, 18, 18)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        self.size_box = QSpinBox()
        self.size_box.setRange(18, 100)
        self.size_box.setValue(42)
        self.size_box.setSuffix(" px")
        form.addRow("目标大小", self.size_box)
        self.duration_box = QComboBox()
        for value in (15, 30, 60, 120):
            self.duration_box.addItem(f"{value} 秒", value)
        self.duration_box.setCurrentIndex(1)
        form.addRow("训练时长", self.duration_box)
        self.sensitivity_box = QSpinBox()
        self.sensitivity_box.setRange(1, 20)
        self.sensitivity_box.setValue(10)
        form.addRow("鼠标灵敏度", self.sensitivity_box)
        self.apply_sensitivity = QCheckBox("训练时应用系统鼠标速度")
        self.apply_sensitivity.setChecked(False)
        form.addRow("", self.apply_sensitivity)
        root.addWidget(settings)

        self.board = AimBoard(self)
        root.addWidget(self.board, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.start_button = QPushButton("开始训练")
        self.start_button.setObjectName("primaryAction")
        self.start_button.clicked.connect(self.toggle)
        actions.addWidget(self.start_button)
        reset = QPushButton("重置统计")
        reset.clicked.connect(self.reset)
        actions.addWidget(reset)
        actions.addStretch(1)
        self.status = QLabel("命中 0  ·  失误 0  ·  平均反应 --")
        actions.addWidget(self.status)
        root.addLayout(actions)

        self.size_box.valueChanged.connect(self.board.set_target_size)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self._reaction_total = 0.0
        self._counted_hits = 0
        self._saved_mouse_speed = None
        current_speed = self._read_mouse_speed()
        if current_speed is not None:
            self.sensitivity_box.setValue(current_speed)

    def toggle(self):
        if self.board.active:
            self.board.stop()
            self.clock.stop()
            self._restore_mouse_speed()
            self.start_button.setText("开始训练")
        else:
            self._duration = int(self.duration_box.currentData())
            self._remaining = self._duration
            self._reaction_total = 0.0
            self._counted_hits = 0
            if self.apply_sensitivity.isChecked():
                self._saved_mouse_speed = self._read_mouse_speed()
                self._set_mouse_speed(self.sensitivity_box.value())
            self.board.begin()
            self.clock.start(1000)
            self.start_button.setText("结束训练")
        self._update_status()

    def reset(self):
        self.clock.stop()
        self.board.stop()
        self._restore_mouse_speed()
        self.board.targets_hit = 0
        self.board.targets_missed = 0
        self._reaction_total = 0.0
        self._counted_hits = 0
        self.start_button.setText("开始训练")
        self._update_status()

    @staticmethod
    def _read_mouse_speed():
        try:
            value = ctypes.c_int()
            ok = ctypes.windll.user32.SystemParametersInfoW(0x0070, 0, ctypes.byref(value), 0)
            return int(value.value) if ok else None
        except (AttributeError, OSError):
            return None

    @staticmethod
    def _set_mouse_speed(value):
        try:
            ctypes.windll.user32.SystemParametersInfoW(0x0071, 0, int(value), 0x02)
        except (AttributeError, OSError):
            pass

    def _restore_mouse_speed(self):
        if self._saved_mouse_speed is not None:
            self._set_mouse_speed(self._saved_mouse_speed)
            self._saved_mouse_speed = None

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self.toggle()
        self._update_status()

    def _update_status(self):
        hit = self.board.targets_hit
        miss = self.board.targets_missed
        if hit > self._counted_hits:
            self._reaction_total += self.board._last_click
            self._counted_hits = hit
        average = "--"
        if hit and self._reaction_total:
            average = f"{self._reaction_total / hit * 1000:.0f} ms"
        suffix = f"  ·  剩余 {self._remaining} 秒" if self.board.active else ""
        self.status.setText(f"命中 {hit}  ·  失误 {miss}  ·  平均反应 {average}{suffix}")
