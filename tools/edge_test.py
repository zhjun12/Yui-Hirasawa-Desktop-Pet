"""Exercise docking widgets, mouse events, reminder delivery and geometry."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QPoint,QPointF,QRect,QSize,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app import Controller,ROOT
from edge_hide import nearest_edge,clamp_position

app=QApplication([])
app.setQuitOnLastWindowClosed(False)

def mouse(widget, kind, global_point, button, buttons):
    local=widget.mapFromGlobal(global_point)
    event=QMouseEvent(kind,QPointF(local),QPointF(global_point),button,buttons,Qt.NoModifier)
    QApplication.sendEvent(widget,event)

def click(widget):
    point=widget.geometry().center()
    mouse(widget,QEvent.MouseButtonPress,point,Qt.LeftButton,Qt.LeftButton)
    mouse(widget,QEvent.MouseButtonRelease,point,Qt.LeftButton,Qt.NoButton)

with TemporaryDirectory(dir=ROOT) as temp:
    c=Controller(app,Path(temp)/'settings.json')
    try:
        dock=c.dock
        screen=QApplication.primaryScreen()
        dock.target_screen=screen
        area=screen.availableGeometry()
        results=[]
        for size in (180,280,480):
            c.set_size(size)
            for edge in ('left','right','top','bottom'):
                pet=c.pet
                pet.move(clamp_position(area.center()-QPoint(pet.width()//2,pet.height()//2),pet.size(),area))
                pet.refresh()
                rect=pet.image_rect.translated(pet.pos())
                shift={'left':QPoint(area.left()-rect.left(),0),
                       'right':QPoint(area.right()-rect.right(),0),
                       'top':QPoint(0,area.top()-rect.top()),
                       'bottom':QPoint(0,area.bottom()-rect.bottom())}[edge]
                start=rect.center()
                mouse(pet,QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton)
                mouse(pet,QEvent.MouseMove,start+shift,Qt.NoButton,Qt.LeftButton)
                mouse(pet,QEvent.MouseButtonRelease,start+shift,Qt.LeftButton,Qt.NoButton)
                QTest.qWait(300)
                assert dock.hidden and dock.edge==edge,(size,edge,dock.edge)
                assert not pet.isVisible() and dock.label.isVisible()
                assert dock.label.windowOpacity() > .99
                assert area.contains(dock.label.geometry())
                assert not pet.animation_timer.isActive()
                cached=pet.scaled.cacheKey()
                pet.say('hidden message')
                QTest.qWait(50)
                assert pet.scaled.cacheKey()==cached and not pet.message
                click(dock.label)
                QTest.qWait(300)
                assert not dock.inactive and pet.isVisible() and not dock.label.isVisible()
                assert area.contains(pet.geometry())
                assert c.animation.temporary is None,'Restore click must not pat the pet'
                results.append(f'{size}:{edge}')
        # Release after an inward drag is still received by the label, and does
        # not immediately collapse or activate a head-pat at its final position.
        c.set_size(280)
        for edge in ('left','right','top','bottom'):
            dock.target_screen=screen
            dock.collapse(edge)
            QTest.qWait(260)
            label=dock.label
            assert label.windowOpacity() > .99, 'A new collapse must reset drag transparency'
            start=label.geometry().center()
            delta={'left':QPoint(180,0),'right':QPoint(-180,0),
                   'top':QPoint(0,180),'bottom':QPoint(0,-180)}[edge]
            mouse(label,QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton)
            mouse(label,QEvent.MouseMove,start+delta,Qt.NoButton,Qt.LeftButton)
            mouse(label,QEvent.MouseMove,start+delta*2,Qt.NoButton,Qt.LeftButton)
            mouse(label,QEvent.MouseButtonRelease,start+delta*2,Qt.LeftButton,Qt.NoButton)
            assert not dock.hidden and not label.isVisible()
            assert area.contains(c.pet.geometry())
            assert c.animation.temporary is None
        dock.collapse('left')
        QTest.qWait(260)
        c.start_timer('focus')
        c.pomo.deadline=time.monotonic()-.1
        c.tick()
        assert c.pomo.phase=='idle' and dock.hidden
        assert '专注完成' in c.panel.status.text()
        c.set_topmost(False)
        assert dock.label.isVisible() and not c.pet.isVisible()
        c.set_topmost(True)
        c.set_size(180)
        assert dock.hidden
        c.set_edge_hide(False)
        assert not dock.inactive and c.pet.isVisible()
        assert not dock.try_hide(area.topLeft())
        c.set_edge_hide(True)
        dock.collapse('right')
        QTest.qWait(260)
        dock.label.move(-50000,-50000)
        dock.target_screen=None
        dock.reconcile()
        assert area.contains(dock.label.geometry())
        c.find_pet()
        assert not dock.hidden and area.contains(c.pet.geometry())
        # Geometry-only cases cover a secondary monitor left of the primary.
        other=QRect(-1920,0,1920,1040)
        assert nearest_edge(QRect(-1920,0,280,280),other)=='left'
        assert nearest_edge(QRect(-280,0,280,280),other)=='right'
        assert nearest_edge(QRect(-1920,760,280,280),other)=='left'
        assert nearest_edge(QRect(-280,760,280,280),other)=='right'
        assert nearest_edge(QRect(-1800,100,280,280),other) is None
        assert other.contains(QRect(clamp_position(QPoint(-9000,9000),QSize(320,400),other),QSize(320,400)))
        dock.target_screen=screen
        dock.collapse('left')
        QTest.qWait(260)
        dock.label.grab().save(str(ROOT/'output/edge-label-widget.png'))
        report=dict(four_edges_and_scales=results, inward_drags=4, click_restores=True,
                    no_accidental_interaction=True, rendering_stops=True,
                    hidden_timer_completes=True, topmost_and_size_safe=True,
                    disable_restores=True, lost_screen_recovery=True,
                    synthetic_negative_monitor_geometry=True,
                    physical_multi_monitor_hotplug='not tested')
        (ROOT/'output/edge-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        c.quit()
    restored=Controller(app,Path(temp)/'settings.json')
    try:
        assert not restored.dock.hidden and restored.pet.isVisible()
        assert not restored.dock.label.isVisible()
        assert area.contains(restored.pet.geometry())
        report['restart_visible']=True
        (ROOT/'output/edge-check.json').write_text(json.dumps(report,indent=2))
    finally:
        restored.quit()
