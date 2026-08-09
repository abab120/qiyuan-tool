import random
import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PyQt5.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ReactionBoard(QWidget):
    clicked = pyqtSignal(float)
    failed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.Mid)
        self.waiting = False
        self.ready = False
        self.started_at = 0.0
        self.too_early = False
        self.idle = QColor("#6c757d")
        self.wait_color = QColor("#2e7d32")
        self.ready_color = QColor("#dc3545")
        self.color = self.idle

    def start_wait(self):
        self.waiting = True
        self.ready = False
        self.too_early = False
        self.color = self.wait_color
        self.update()

    def show_ready(self):
        if not self.waiting:
            return
        self.waiting = False
        self.ready = True
        self.started_at = time.perf_counter()
        self.color = self.ready_color
        self.update()

    def reset_board(self):
        self.waiting = False
        self.ready = False
        self.too_early = False
        self.color = self.idle
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.color)
        painter.setPen(QPen(Qt.white, 2))
        painter.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        if self.too_early:
            text = "太早了，点击重新开始"
        elif self.waiting:
            text = "等待变红..."
        elif self.ready:
            text = "点击！"
        else:
            text = "点击开始测试"
        painter.drawText(self.rect(), Qt.AlignCenter, text)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.too_early:
            self.reset_board()
        elif self.ready:
            elapsed = (time.perf_counter() - self.started_at) * 1000.0
            self.ready = False
            self.color = self.idle
            self.update()
            self.clicked.emit(elapsed)
        elif self.waiting:
            self.waiting = False
            self.too_early = True
            self.color = QColor("#c62828")
            self.update()
            self.failed.emit()


class ReactionTestPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("reactionTestPanel")
        self.history = []
        self.round_index = 0
        self.best = None
        self.wait_timer = QTimer(self)
        self.wait_timer.setSingleShot(True)
        self.wait_timer.timeout.connect(self._show_ready)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel("反应力测试")
        title.setObjectName("contentTitle")
        layout.addWidget(title)
        hint = QLabel("屏幕变红后尽快点击，测试你的反应速度。")
        hint.setObjectName("hintPanel")
        layout.addWidget(hint)

        self.board = ReactionBoard()
        self.board.setMinimumHeight(220)
        self.board.clicked.connect(self._hit)
        self.board.failed.connect(self._miss)
        layout.addWidget(self.board)

        settings = QGroupBox("测试设置")
        form = QFormLayout(settings)
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 50)
        self.rounds.setValue(10)
        self.rounds.setSuffix(" 次")
        form.addRow("训练轮数", self.rounds)
        layout.addWidget(settings)

        metrics = QFrame()
        metrics.setObjectName("aimMetrics")
        grid = QGridLayout(metrics)
        self.values = []
        for row, name in enumerate(("当前反应", "最佳反应", "平均反应", "测试轮数")):
            n = QLabel(name)
            n.setObjectName("metricName")
            v = QLabel("-")
            v.setObjectName("metricValue")
            self.values.append(v)
            grid.addWidget(n, row, 0)
            grid.addWidget(v, row, 1)
        layout.addWidget(metrics)

        self.history_label = QLabel("暂无记录")
        self.history_label.setObjectName("aimHint")
        layout.addWidget(self.history_label)

        actions = QHBoxLayout()
        self.start_button = QPushButton("开始训练")
        self.start_button.setObjectName("primaryAction")
        self.start_button.clicked.connect(self.start_test)
        actions.addWidget(self.start_button)
        reset = QPushButton("重置")
        reset.clicked.connect(self.reset)
        actions.addWidget(reset)
        layout.addLayout(actions)
        layout.addStretch()

    def start_test(self):
        self.wait_timer.stop()
        self.history.clear()
        self.round_index = 0
        self.best = None
        self.start_button.setEnabled(False)
        self._update_metrics()
        self._next_round()

    def _next_round(self):
        if self.round_index >= self.rounds.value():
            self._finish()
            return
        self.board.start_wait()
        # QTimer requires an integer number of milliseconds.
        self.wait_timer.start(int(random.uniform(1000, 4000)))

    def _show_ready(self):
        self.board.show_ready()

    def _hit(self, elapsed):
        self.round_index += 1
        self.history.append(elapsed)
        self.best = elapsed if self.best is None else min(self.best, elapsed)
        self._update_metrics()
        self._next_round()

    def _miss(self):
        self.round_index += 1
        self._update_metrics()
        self._next_round()

    def _finish(self):
        self.wait_timer.stop()
        self.board.reset_board()
        self.start_button.setEnabled(True)

    def reset(self):
        self.wait_timer.stop()
        self.history.clear()
        self.round_index = 0
        self.best = None
        self.board.reset_board()
        self.start_button.setEnabled(True)
        self._update_metrics()

    def _update_metrics(self):
        current = self.history[-1] if self.history else None
        average = sum(self.history) / len(self.history) if self.history else None
        self.values[0].setText(f"{current:.0f} ms" if current is not None else "-")
        self.values[1].setText(f"{self.best:.0f} ms" if self.best is not None else "-")
        self.values[2].setText(f"{average:.0f} ms" if average is not None else "-")
        self.values[3].setText(f"{self.round_index}/{self.rounds.value()}")
        if self.history:
            self.history_label.setText("最近: " + " | ".join(f"{x:.0f} ms" for x in self.history[-5:]))
        else:
            self.history_label.setText("暂无记录")
