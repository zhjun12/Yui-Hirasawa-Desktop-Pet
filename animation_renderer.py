"""Continuous regional mesh deformation over a stable pose.

This is a lightweight 2D prototype, not Live2D or newly drawn animation frames.
Head, hair and torso fields are independently weighted; the
bottom remains anchored. Premultiplied alpha avoids colored transparent fringes.
"""
import math
import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt


def smoothstep(a, b, values):
    t = np.clip((values - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


class ContinuousRenderer:
    def __init__(self):
        self.cache = {}
        self.last_state = None
        self.previous = None
        self.transition_time = 0

    def prepare(self, source, size):
        key = (source.cacheKey(), size)
        if key not in self.cache:
            pm = source.scaled(size - 16, size - 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            canvas = QImage(size, size, QImage.Format_RGBA8888_Premultiplied)
            canvas.fill(0)
            from PySide6.QtGui import QPainter
            painter = QPainter(canvas)
            painter.drawPixmap((size - pm.width()) // 2, size - pm.height() - 5, pm)
            painter.end()
            pixels = np.frombuffer(canvas.bits(), np.uint8).reshape(size, size, 4).copy()
            yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
            nx, ny = xx / size, yy / size
            head = 1 - smoothstep(.52, .91, ny)
            hair = np.clip(np.abs(nx - .5) * 3, 0, 1) * (1 - smoothstep(.6, .88, ny))
            anchor = 1 - smoothstep(.9, .99, ny)
            self.cache[key] = pixels, xx, yy, head, hair, anchor
            if len(self.cache) > 30:
                self.cache = {key: self.cache[key]}
        return self.cache[key]

    def render(self, source, size, state, phase, strength, onset, now):
        pixels, xx, yy, head, hair, anchor = self.prepare(source, size)
        if state in ('listen', 'daydream', 'idle', 'happy'):
            weight = head
            amplitude = strength if state == 'listen' else .17
            angle = math.sin(phase) * amplitude * (.085 if state == 'listen' else .022)
            cx, cy = size * .5, size * .67
            dx, dy = xx - cx, yy - cy
            mx = xx + (dx * math.cos(angle) + dy * math.sin(angle) - dx) * weight
            my = yy + (-dx * math.sin(angle) + dy * math.cos(angle) - dy) * weight
            mx += math.sin(phase - .5) * amplitude * size * .009 * hair * anchor
            my += math.sin(now * 1.4) * size * .002 * anchor
            pixels = cv2.remap(pixels, mx.astype(np.float32), my.astype(np.float32),
                               cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        frame = QImage(pixels.data, size, size, size * 4, QImage.Format_RGBA8888_Premultiplied).copy()
        if state != self.last_state:
            self.last_state = state
            self.transition_time = now
            self.transition_from = self.previous
        if getattr(self, 'transition_from', None) and now - self.transition_time < .14:
            from PySide6.QtGui import QPainter
            mixed = QImage(frame.size(), QImage.Format_RGBA8888_Premultiplied)
            mixed.fill(0)
            painter = QPainter(mixed)
            painter.drawImage(0, 0, self.transition_from)
            painter.setOpacity(min(1, (now - self.transition_time) / .14))
            painter.drawImage(0, 0, frame)
            painter.end()
            frame = mixed
        self.previous = frame
        return QPixmap.fromImage(frame)
