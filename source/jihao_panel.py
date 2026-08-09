import math
import random
import time

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class HeartCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 430)
        self.message = "嘉豪，愿你每天都开心！"
        self.running = True
        self.started = time.monotonic()
        self.particles = []
        for _ in range(900):
            angle = random.random() * math.tau
            spread = random.uniform(0.72, 1.03)
            self.particles.append((angle, spread, random.random() * math.tau, random.uniform(1.2, 3.0)))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(30)

    def set_message(self, message):
        self.message = message.strip() or "嘉豪，愿你每天都开心！"
        self.update()

    def set_running(self, running):
        self.running = running
        if running:
            self.started = time.monotonic()
        self.update()

    def reset(self):
        self.started = time.monotonic()
        self.set_running(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#171b24"))

        elapsed = time.monotonic() - self.started
        pulse = 1.0 + 0.035 * math.sin(elapsed * 3.2) if self.running else 1.0
        scale = min(self.width(), self.height()) * 0.0145
        center_x = self.width() * 0.5
        center_y = self.height() * 0.43

        for angle, spread, phase, radius in self.particles:
            x = 16 * math.sin(angle) ** 3
            y = 13 * math.cos(angle) - 5 * math.cos(2 * angle) - 2 * math.cos(3 * angle) - math.cos(4 * angle)
            drift = math.sin(elapsed * 2.0 + phase) * 0.22
            px = center_x + (x * spread + drift) * scale * pulse
            py = center_y - (y * spread) * scale * pulse
            alpha = int(125 + 95 * (0.5 + 0.5 * math.sin(elapsed * 2.8 + phase)))
            color = QColor(242, 88, 143, max(80, min(230, alpha)))
            painter.setPen(QPen(color, radius))
            painter.drawPoint(int(px), int(py))

        painter.setPen(QColor(255, 225, 236))
        font = QFont("Microsoft YaHei", 16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(24, int(self.height() * 0.78), -24, -18), Qt.AlignCenter, self.message)
        painter.end()


class JihaoPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("嘉豪专用")
        title.setObjectName("contentTitle")
        subtitle = QLabel("制作一颗会跳动的爱心，输入文字后即可生成专属祝福")
        subtitle.setObjectName("contentStatus")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QGroupBox("自定义文字")
        controls_layout = QHBoxLayout(controls)
        self.text_edit = QLineEdit("嘉豪，愿你每天都开心！")
        self.text_edit.setPlaceholderText("输入要显示在爱心下方的文字")
        controls_layout.addWidget(self.text_edit, 1)
        self.start_button = QPushButton("暂停")
        self.start_button.clicked.connect(self.toggle)
        controls_layout.addWidget(self.start_button)
        reset_button = QPushButton("重新开始")
        reset_button.clicked.connect(self.reset)
        controls_layout.addWidget(reset_button)
        layout.addWidget(controls)

        self.canvas = HeartCanvas(self)
        self.text_edit.textChanged.connect(self.canvas.set_message)
        layout.addWidget(self.canvas, 1)

    def toggle(self):
        running = not self.canvas.running
        self.canvas.set_running(running)
        self.start_button.setText("暂停" if running else "继续")

    def reset(self):
        self.canvas.set_message(self.text_edit.text())
        self.canvas.reset()
        self.start_button.setText("暂停")
