"""Four-edge docking without interrupting playback or study timers."""
import time
from PySide6.QtCore import (QObject, QPoint, Qt, QTimer, QPropertyAnimation,
                            QParallelAnimationGroup, QEasingCurve)
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


def clamp_position(position, size, area):
    return QPoint(max(area.left(), min(position.x(), area.right()-size.width()+1)),
                  max(area.top(), min(position.y(), area.bottom()-size.height()+1)))


def nearest_edge(rect, area, threshold=20):
    # Stable ordering makes left/right win corner ties.
    distances = [('left', rect.left()-area.left()), ('right', area.right()-rect.right()),
                 ('top', rect.top()-area.top()), ('bottom', area.bottom()-rect.bottom())]
    edge, distance = min(distances, key=lambda pair: pair[1])
    return edge if distance <= threshold else None


class EdgeLabel(QWidget):
    def __init__(self, dock, image):
        super().__init__()
        self.dock = dock
        self.image = QPixmap(str(image))
        if self.image.isNull():
            raise RuntimeError('贴边标签素材缺失，请保持程序文件夹完整。')
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint |
                            (Qt.WindowStaysOnTopHint if dock.c.store.data['topmost'] else Qt.WindowFlags()))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(116,38)
        self.setWindowTitle('平泽唯 · 贴边标签')
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip('点击展开；向屏幕内拖动恢复桌宠')
        self.press = None
        self.dragging = False

    def paintEvent(self, event):
        painter = QPainter(self)
        # Nonzero alpha keeps the enlarged padding clickable on Windows layered
        # windows while remaining visually transparent.
        painter.fillRect(self.rect(),QColor(255,255,255,1))
        painter.drawPixmap(4,4,self.image)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dock.stop_transition()
            self.setWindowOpacity(1)
            self.press = event.globalPosition().toPoint()
            self.origin = self.pos()
            self.dragging = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.press is None or not event.buttons() & Qt.LeftButton:
            return
        delta = event.globalPosition().toPoint()-self.press
        if delta.manhattanLength() >= QApplication.startDragDistance():
            self.dragging = True
            inward = {'left':delta.x(), 'right':-delta.x(),
                      'top':delta.y(), 'bottom':-delta.y()}[self.dock.edge]
            if self.dock.hidden and inward >= QApplication.startDragDistance():
                self.dock.restore_at_cursor(event.globalPosition().toPoint())
            elif self.dock.hidden:
                self.dock.place_label(self.origin+delta)
            else:
                pet = self.dock.pet
                pet.move(event.globalPosition().toPoint()-self.dock.drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.press is None:
            return
        self.press = None
        self.setCursor(Qt.OpenHandCursor)
        if self.dragging:
            if self.dock.hidden:
                self.dock.place_label(self.pos())
            else:
                self.dock.pet.keep_visible()
                self.dock.persist()
                self.hide()
        else:
            self.dock.restore()

    def contextMenuEvent(self, event):
        self.dock.c.menu().exec(event.globalPos())


class EdgeDock(QObject):
    def __init__(self, controller, image):
        super().__init__(controller)
        self.c = controller
        self.pet = controller.pet
        self.hidden = False
        self.transitioning = False
        self.group = None
        self.edge = None
        self.target_screen = None
        self.restore_position = self.pet.pos()
        self.label = EdgeLabel(self,image)
        for screen in QApplication.screens():
            self.watch_screen(screen)
        controller.app.screenAdded.connect(self.screen_added)
        controller.app.screenRemoved.connect(self.screen_removed)

    @property
    def inactive(self):
        return self.hidden or self.transitioning

    def screen_added(self, screen):
        self.watch_screen(screen)
        self.reconcile()

    def watch_screen(self, screen):
        screen.availableGeometryChanged.connect(self.reconcile)

    def screen_removed(self, screen):
        self.target_screen = None
        QTimer.singleShot(50,self.reconcile)

    def area(self):
        screens = QApplication.screens()
        if self.target_screen not in screens:
            self.target_screen = QApplication.primaryScreen()
        return self.target_screen.availableGeometry()

    def persist(self):
        position = self.restore_position if self.inactive else self.pet.pos()
        self.c.store.data['position'] = [position.x(),position.y()]
        self.c.save()

    def try_hide(self, cursor):
        if not self.c.store.data['edge_hide'] or self.inactive:
            return False
        self.target_screen = QApplication.screenAt(cursor) or self.pet.screen()
        visual = self.pet.image_rect.translated(self.pet.pos())
        edge = nearest_edge(visual,self.area())
        if not edge:
            return False
        self.collapse(edge)
        return True

    def animate(self, start, end, opacity_start, opacity_end, finish):
        self.stop_transition()
        self.transitioning = True
        self.group = QParallelAnimationGroup(self)
        for prop, first, last in ((b'pos',start,end),
                                  (b'windowOpacity',opacity_start,opacity_end)):
            animation = QPropertyAnimation(self.pet,prop,self.group)
            animation.setStartValue(first)
            animation.setEndValue(last)
            animation.setDuration(220)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            self.group.addAnimation(animation)
        self.group.finished.connect(finish)
        self.group.start()

    def stop_transition(self):
        if self.group:
            self.group.stop()
            self.group.deleteLater()
            self.group = None
        self.transitioning = False

    def offscreen(self, position):
        area = self.area()
        end = QPoint(position)
        if self.edge == 'left': end.setX(area.left()-self.pet.width()+16)
        elif self.edge == 'right': end.setX(area.right()-16)
        elif self.edge == 'top': end.setY(area.top()-self.pet.height()+16)
        else: end.setY(area.bottom()-16)
        return end

    def collapse(self, edge):
        self.edge = edge
        self.restore_position = clamp_position(self.pet.pos(),self.pet.size(),self.area())
        self.hidden = True
        self.c.animation.set_suspended(True)
        self.pet.animation_timer.stop()
        self.pet.message = ''
        self.pet.last_signature = None
        self.pet.update()
        self.place_label(self.pet.geometry().center()-QPoint(58,19))
        self.show_label()
        self.persist()
        def finish():
            self.transitioning = False
            self.pet.hide()
            self.pet.setWindowOpacity(1)
            self.show_label()
        self.animate(self.pet.pos(),self.offscreen(self.pet.pos()),1.,0.,finish)

    def show_label(self):
        # Drag restoration temporarily fades the mouse-grab owner. Always reset
        # that native window opacity before reusing it for another collapse.
        self.label.setWindowOpacity(1)
        self.place_label(self.label.pos())
        self.label.show()
        self.label.raise_()
        self.label.update()

    def place_label(self, point):
        area = self.area()
        position = clamp_position(point,self.label.size(),area)
        if self.edge == 'left': position.setX(area.left())
        elif self.edge == 'right': position.setX(area.right()-self.label.width()+1)
        elif self.edge == 'top': position.setY(area.top())
        else: position.setY(area.bottom()-self.label.height()+1)
        self.label.move(position)

    def resume(self):
        self.c.animation.set_suspended(False)
        self.pet.last_motion_time = time.monotonic()
        self.pet.last_signature = None
        self.pet.refresh()
        self.pet.animation_timer.start(33)

    def restore(self, animated=True):
        if not self.inactive:
            self.pet.show()
            return
        self.stop_transition()
        self.hidden = False
        self.label.hide()
        target = clamp_position(self.restore_position,self.pet.size(),self.area())
        self.pet.move(target)
        self.pet.setWindowOpacity(1)
        self.pet.show()
        self.resume()
        if animated:
            start = self.offscreen(target)
            self.pet.move(start)
            def finish():
                self.transitioning = False
                self.resume()
                self.persist()
            self.animate(start,target,0.,1.,finish)
        else:
            self.persist()

    def restore_at_cursor(self, cursor):
        # Keep the label as the mouse-grab owner until release, so dragging is
        # continuous and does not deliver an accidental pet click.
        self.stop_transition()
        self.hidden = False
        self.drag_offset = QPoint(self.pet.width()//2,self.pet.height()//2)
        self.pet.move(cursor-self.drag_offset)
        self.pet.setWindowOpacity(1)
        self.pet.show()
        self.resume()
        self.label.setWindowOpacity(.01)

    def reconcile(self, *args):
        if self.c.quitting:
            return
        self.stop_transition()
        if self.hidden:
            self.pet.hide()
            self.place_label(self.label.pos())
            self.show_label()
            self.restore_position = clamp_position(self.restore_position,self.pet.size(),self.area())
        else:
            self.label.hide()
            self.pet.setWindowOpacity(1)
            self.pet.keep_visible()
            self.resume()

    def shutdown(self):
        self.stop_transition()
        self.label.hide()
        self.label.close()
