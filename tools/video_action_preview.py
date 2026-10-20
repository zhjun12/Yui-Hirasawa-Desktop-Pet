"""Visual preview of source-video gesture loops, without music sync claims."""
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from PySide6.QtCore import Qt
from app import Sprites,ROOT

app=QApplication([])
sprites=Sprites()
writer=cv2.VideoWriter(str(ROOT/'output/new-actions-demo.mp4'),
                       cv2.VideoWriter_fourcc(*'mp4v'),30,(800,420))
assert writer.isOpened()
for index in range(180):
    image=QImage(800,420,QImage.Format_RGBA8888)
    image.fill(QColor('#f7f6f0'))
    painter=QPainter(image)
    painter.setFont(QFont('Microsoft YaHei UI',14))
    painter.setPen(QColor('#315c50'))
    for column,(key,title) in enumerate([('roll','趴地打滚 · 原片近景'),
                                        ('stretch','举手伸展 · 头顶完整')]):
        pm=sprites.frame(key,index/30).scaled(380,330,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        painter.drawPixmap(column*400+(400-pm.width())//2,360-pm.height(),pm)
        painter.drawText(column*400,370,400,35,Qt.AlignCenter,title)
    painter.end()
    if index==20: image.save(str(ROOT/'output/new-actions-preview.png'))
    pixels=np.frombuffer(image.bits(),np.uint8).reshape(420,800,4)
    writer.write(cv2.cvtColor(pixels,cv2.COLOR_RGBA2BGR))
writer.release()
print('output/new-actions-demo.mp4')
