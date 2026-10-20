"""Verify actual desktop pixels and native hit targets, not QWidget flags alone."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from app import Controller,ROOT

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
user32=ctypes.windll.user32
user32.WindowFromPoint.argtypes=[wintypes.POINT]
user32.WindowFromPoint.restype=wintypes.HWND

def array(image):
    from PySide6.QtGui import QImage
    image=image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.width(),4).copy()[:,:,:3]

with TemporaryDirectory(dir=ROOT) as temp:
    c=Controller(app,Path(temp)/'settings.json')
    report=[]
    try:
        c.panel.hide()
        c.set_topmost(True)
        for repeat in range(2):
            for edge in ('left','right','top','bottom'):
                c.dock.target_screen=QApplication.primaryScreen()
                c.dock.collapse(edge)
                QTest.qWait(350)
                label=c.dock.label
                screen=c.dock.target_screen
                rect=label.geometry().adjusted(4,4,-4,-4)
                actual=screen.grabWindow(0,rect.x(),rect.y(),rect.width(),rect.height())
                assert not actual.isNull()
                actual=actual.toImage().scaled(108,30,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                expected=label.image.toImage()
                difference=float(np.abs(array(actual).astype(float)-array(expected)).mean())
                actual.save(str(ROOT/f'output/edge-desktop-{repeat}-{edge}.png'))
                native=wintypes.RECT()
                user32.GetWindowRect(int(label.winId()),ctypes.byref(native))
                hit=user32.WindowFromPoint(wintypes.POINT((native.left+native.right)//2,
                                                         (native.top+native.bottom)//2))
                print(dict(edge=edge,geometry=label.geometry().getRect(),dpr=screen.devicePixelRatio(),
                           native_rect=(native.left,native.top,native.right,native.bottom),
                           difference=difference,hit=hit,label=int(label.winId())),flush=True)
                assert hit==int(label.winId()), (edge,'Native hit target differs',hit,int(label.winId()))
                assert difference < 20,(edge,'Label absent from desktop',difference)
                actual.save(str(ROOT/f'output/edge-desktop-{repeat}-{edge}.png'))
                report.append(dict(repeat=repeat,edge=edge,pixel_difference=round(difference,3),
                                   opacity=label.windowOpacity(),native_click_target=True))
                c.dock.restore_at_cursor(screen.availableGeometry().center())
                label.hide()
                c.pet.keep_visible()
        (ROOT/'output/edge-desktop-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    finally:
        c.quit()
