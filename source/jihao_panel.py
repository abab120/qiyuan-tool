import math
import json
import random
import time
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QFileDialog,
    QMessageBox,
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
    TEMPLATES = [
        ("日常祝福", "嘉豪，愿你每天都开心！"),
        ("表白告白", "遇见你，是我最幸运的事。"),
        ("生日祝福", "生日快乐，愿所有美好如期而至！"),
        ("感谢陪伴", "谢谢你的陪伴，未来也请多多指教！"),
        ("温柔寄语", "愿你一路有光，所遇皆温柔。"),
        ("自定义", ""),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("嘉豪专区")
        title.setObjectName("contentTitle")
        subtitle = QLabel("选择模板或输入文字，生成可分享的爱心祝福")
        subtitle.setObjectName("contentStatus")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QGroupBox("祝福内容")
        controls_layout = QVBoxLayout(controls)
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("模板"))
        self.template_box = QComboBox()
        for name, text in self.TEMPLATES:
            self.template_box.addItem(name, text)
        self.template_box.currentIndexChanged.connect(self._apply_template)
        template_row.addWidget(self.template_box, 1)
        controls_layout.addLayout(template_row)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("文字"))
        self.text_edit = QLineEdit("嘉豪，愿你每天都开心！")
        self.text_edit.setPlaceholderText("输入要显示在爱心下方的文字")
        text_row.addWidget(self.text_edit, 1)
        controls_layout.addLayout(text_row)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("暂停")
        self.start_button.clicked.connect(self.toggle)
        button_row.addWidget(self.start_button)
        reset_button = QPushButton("重新开始")
        reset_button.clicked.connect(self.reset)
        button_row.addWidget(reset_button)
        export_button = QPushButton("导出代码")
        export_button.setObjectName("primaryAction")
        export_button.clicked.connect(self.export_code)
        button_row.addWidget(export_button)
        button_row.addStretch(1)
        controls_layout.addLayout(button_row)
        layout.addWidget(controls)

        self.canvas = HeartCanvas(self)
        self.text_edit.textChanged.connect(self.canvas.set_message)
        layout.addWidget(self.canvas, 1)

    def _apply_template(self, index):
        text = self.template_box.itemData(index)
        if text:
            self.text_edit.setText(text)

    def _export_html(self, message):
        encoded = json.dumps(message, ensure_ascii=False).replace("</", "<\\/")
        return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>嘉豪专区</title>
<style>html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#171b24;color:#ffe1ec;font-family:"Microsoft YaHei",sans-serif}}canvas{{display:block;width:100%;height:100%}}#message{{position:fixed;left:0;right:0;bottom:9%;text-align:center;font-size:clamp(18px,3vw,30px);font-weight:700;text-shadow:0 2px 14px #f2588f}}</style></head>
<body><canvas id="heart"></canvas><div id="message"></div>
<script>
const message={encoded};document.getElementById("message").textContent=message;
const canvas=document.getElementById("heart"),ctx=canvas.getContext("2d"),dots=[];let t0=performance.now();
function resize(){{const d=devicePixelRatio||1;canvas.width=innerWidth*d;canvas.height=innerHeight*d;ctx.setTransform(d,0,0,d,0,0)}}
function heart(t){{return [16*Math.sin(t)**3,13*Math.cos(t)-5*Math.cos(2*t)-2*Math.cos(3*t)-Math.cos(4*t)]}}
for(let i=0;i<900;i++)dots.push([Math.random()*Math.PI*2,.72+Math.random()*.31,Math.random()*6.28,1.2+Math.random()*1.8]);
function draw(now){{const e=(now-t0)/1000,pulse=1+.035*Math.sin(e*3.2),s=Math.min(innerWidth,innerHeight)*.0145,cx=innerWidth/2,cy=innerHeight*.43;ctx.clearRect(0,0,innerWidth,innerHeight);for(const d of dots){{const p=heart(d[0]),drift=Math.sin(e*2+d[2])*.22,x=cx+(p[0]*d[1]+drift)*s*pulse,y=cy-p[1]*d[1]*s*pulse,a=.45+.35*(.5+.5*Math.sin(e*2.8+d[2]));ctx.fillStyle=`rgba(242,88,143,${{a}})`;ctx.beginPath();ctx.arc(x,y,d[3],0,Math.PI*2);ctx.fill()}}requestAnimationFrame(draw)}}
addEventListener("resize",resize);resize();requestAnimationFrame(draw);
</script></body></html>'''

    def export_code(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出爱心代码", "嘉豪专区.html", "HTML 文件 (*.html)")
        if not path:
            return
        try:
            Path(path).write_text(self._export_html(self.text_edit.text()), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"无法写入文件：{exc}")
            return
        QMessageBox.information(self, "导出完成", "爱心代码已导出为 HTML 文件，可直接用浏览器打开或分享。")

    def toggle(self):
        running = not self.canvas.running
        self.canvas.set_running(running)
        self.start_button.setText("暂停" if running else "继续")

    def reset(self):
        self.canvas.set_message(self.text_edit.text())
        self.canvas.reset()
        self.start_button.setText("暂停")
