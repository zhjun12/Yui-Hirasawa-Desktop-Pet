"""Offline demonstration of the implemented renderer, not a music sync claim."""
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtCore import Qt
from app import Sprites, ROOT
from animation_renderer import ContinuousRenderer

app = QApplication([])
sprites = Sprites()
renderers = {'listen': ContinuousRenderer()}
output = ROOT / 'output/motion-demo.mp4'
video = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*'mp4v'), 30, (760, 420))
times = []
assert video.isOpened()
for index in range(180):
    now = index / 30
    frame = QImage(760, 420, QImage.Format_RGBA8888)
    frame.fill(QColor('#f7f6f0'))
    painter = QPainter(frame)
    painter.setFont(QFont('Microsoft YaHei UI', 14))
    painter.setPen(QColor('#315c50'))
    painter.drawText(0, 10, 760, 40, Qt.AlignCenter, '托腮为局部动作原型 · 大回旋为用户视频原始动作')
    for column, state in enumerate(['listen', 'spin']):
        start = time.perf_counter()
        if state == 'listen':
            pm = renderers[state].render(sprites.frames[1][1], 320, state, now * 2.0, .75, 0, now)
        else:
            pm = sprites.frame('spin', now).scaled(320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        times.append((time.perf_counter() - start) * 1000)
        painter.drawPixmap(column * 380 + 30, 390 - pm.height(), pm)
        painter.drawText(column * 380, 390, 380, 30, Qt.AlignCenter, '托腮听歌' if state == 'listen' else '手臂大回旋')
    painter.end()
    rgba = np.frombuffer(frame.bits(), np.uint8).reshape(420, 760, 4)
    video.write(cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR))
    if index == 55:
        frame.save(str(ROOT / 'output/motion-preview.png'))
video.release()
report = dict(frames=180, fps=30, seconds=6, render_mean_ms=round(float(np.mean(times)), 2),
              render_p95_ms=round(float(np.percentile(times, 95)), 2),
              type='procedural listening pose and original video arm-windmill cycle')
(ROOT / 'output/motion-performance.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
