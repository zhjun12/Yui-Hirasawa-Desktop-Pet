"""Transparent music companion matching the approved desktop-pet preview."""
import math
import time
from PySide6.QtCore import Qt,QPoint,QPointF,QRect,QRectF,QEvent,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QColor,QFont,QPainter,QPen,QRegion,QBitmap,QImage,QRadialGradient
from PySide6.QtWidgets import (QWidget,QLabel,QPushButton,QApplication,QDialog,QVBoxLayout,
    QHBoxLayout,QListWidget,QSpinBox,QFileDialog,QGraphicsDropShadowEffect)
from edge_hide import clamp_position
from lyrics import LyricsLibrary,lyric_index


class DragLabel(QLabel):
    def __init__(self,view,pat=False):
        super().__init__(view)
        self.view=view;self.pat=pat
        self.setCursor(Qt.OpenHandCursor)
        self.setTextFormat(Qt.PlainText)
        self.setStyleSheet('background:transparent;border:0;')

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton: self.view.start_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.LeftButton: self.view.move_drag(event.globalPosition().toPoint())

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton: self.view.end_drag(event.globalPosition().toPoint(),self.pat)

    def mouseDoubleClickEvent(self,event):
        if self.view.lyrics_enabled and not self.pat and event.button()==Qt.LeftButton: self.view.open_lyrics()


class ListeningStatus(QWidget):
    def __init__(self,view):
        super().__init__(view)
        self.view=view;self.text='等待播放'
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        font=QFont('Microsoft YaHei UI');font.setPixelSize(11);font.setWeight(QFont.DemiBold)
        painter.setFont(font);painter.setPen(QColor('#795133'))
        width=painter.fontMetrics().horizontalAdvance(self.text)
        x=(self.width()-width)/2
        painter.drawText(QRectF(x,0,width,self.height()),Qt.AlignCenter,self.text)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor('#b18446'))
        for index in range(3):
            height=3+7*(.5+.5*math.sin(self.view.effect_time*5.7-index*1.8))
            for side in (-1,1):
                center=(x-8-index*4) if side<0 else (x+width+8+index*4)
                painter.drawRoundedRect(QRectF(center-1,(self.height()-height)/2,2,height),1,1)


class BubbleButton(QPushButton):
    def __init__(self,view,command,color,ink,diameter):
        super().__init__(view)
        self.view=view;self.command=command;self.color=color;self.ink=ink
        self.press=None;self.moved=False;self.held=False
        self.setFixedSize(diameter,diameter)
        self.setStyleSheet('background:transparent;border:0;padding:0;')
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName({'previous':'上一首','toggle':'播放 / 暂停','next':'下一首'}[command])
        self.clicked.connect(self.control)

    def control(self):
        if self.command=='toggle': self.view.c.toggle_active()
        else: self.view.c.music_step(-1 if self.command=='previous' else 1)

    def enterEvent(self,event):
        self.view.hovered.add(self.command);super().enterEvent(event)

    def leaveEvent(self,event):
        self.view.hovered.discard(self.command);super().leaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.press=event.globalPosition().toPoint();self.origin=self.pos()
            self.moved=False;self.held=True
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.press is not None and event.buttons()&Qt.LeftButton:
            delta=event.globalPosition().toPoint()-self.press
            self.moved|=delta.manhattanLength()>=QApplication.startDragDistance()
            if self.moved:
                point=self.origin+delta
                point.setX(max(0,min(point.x(),self.view.width()-self.width())))
                point.setY(max(0,min(point.y(),self.view.height()-self.height())))
                self.move(point);self.view.update_mask()
        if not self.moved: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.press is not None:
            self.press=None;self.held=False
            if self.moved:
                self.setDown(False)
                self.view.save_bubble(self)
                event.accept();return
        super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        rectangle=QRectF(1,1,self.width()-2,self.height()-2)
        gradient=QRadialGradient(QPointF(self.width()*.28,self.height()*.23),self.width()*.9)
        gradient.setColorAt(0,QColor('#fffef9'));gradient.setColorAt(.3,QColor('#fffdf0df'))
        gradient.setColorAt(1,QColor(self.color))
        painter.setPen(QPen(QColor('#ddffffff'),.7));painter.setBrush(gradient)
        painter.setOpacity(1 if self.isEnabled() else .45);painter.drawEllipse(rectangle)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor('#c0ffffff'))
        painter.drawEllipse(QRectF(6,5,8,4))
        painter.setBrush(QColor(self.ink));center=QPointF(self.width()/2,self.height()/2)
        if self.command=='toggle' and self.view.song.get('playing') is True:
            painter.drawRoundedRect(QRectF(center.x()-4,center.y()-5,2.5,10),.6,.6)
            painter.drawRoundedRect(QRectF(center.x()+1.5,center.y()-5,2.5,10),.6,.6)
        else:
            from PySide6.QtGui import QPolygonF
            sign=-1 if self.command=='previous' else 1
            painter.drawPolygon(QPolygonF([QPointF(center.x()-sign*3,center.y()-5),QPointF(center.x()+sign*4,center.y()),QPointF(center.x()-sign*3,center.y()+5)]))
            if self.command!='toggle': painter.drawRect(QRectF(center.x()+sign*5-1,center.y()-5,1.5,10))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush);painter.setPen(QPen(QColor('#a4864e'),1))
            painter.drawEllipse(rectangle.adjusted(3,3,-3,-3))


class LyricsDialog(QDialog):
    def __init__(self,view):
        super().__init__(view)
        self.view=view;self.setWindowTitle('当前歌曲 · 歌词设置');self.resize(440,390)
        self.setStyleSheet('QDialog{background:#fff9ec;} QLabel,QPushButton,QListWidget,QSpinBox{font-family:"Microsoft YaHei UI";font-size:12px;}')
        layout=QVBoxLayout(self)
        self.title=QLabel();self.title.setTextFormat(Qt.PlainText);self.title.setWordWrap(True);layout.addWidget(self.title)
        self.hint=QLabel();self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.lines=QListWidget();self.lines.setWordWrap(True);layout.addWidget(self.lines,1)
        self.lines.currentRowChanged.connect(self.manual_line)
        row=QHBoxLayout();import_button=QPushButton('导入 LRC / TXT');import_button.clicked.connect(view.import_lyrics);row.addWidget(import_button)
        row.addWidget(QLabel('歌词提前 / 毫秒'))
        self.offset=QSpinBox();self.offset.setRange(-60000,60000);self.offset.setSingleStep(250)
        self.offset.valueChanged.connect(view.offset_changed);row.addWidget(self.offset);layout.addLayout(row)
        done=QPushButton('完成');done.clicked.connect(self.hide);layout.addWidget(done)

    def manual_line(self,index):
        if (self.view.song.get('position') is None or not (self.view.document or {}).get('lines')) and index>=0:
            self.view.manual_index=index;self.view.refresh()


class MusicWindow(QWidget):
    # Keep the lyrics adapter available for a future player connection.
    lyrics_enabled=False

    def __init__(self,c):
        super().__init__()
        self.c=c;self.key=None;self.document=None;self.last_lyric=None;self.manual_index=0
        self.song={};self.reveal=None;self.hovered=set();self.effect_time=0.;self.bubble_time=0.
        self.last_frame=time.monotonic();self.drag=None;self.bases={};self.mask_signature=None
        self.feedback_text='';self.feedback_until=0.
        self.library=LyricsLibrary(c.store.path.parent/'lyrics')
        self.setWindowTitle('平泽唯 · 音乐桌宠')
        self.setWindowFlags(Qt.Tool|Qt.FramelessWindowHint|
            (Qt.WindowStaysOnTopHint if c.store.data['topmost'] else Qt.WindowFlags()))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet('background:transparent;')
        self.actor=DragLabel(self,pat=True);self.actor.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)
        self.head=ListeningStatus(self)
        self.current=DragLabel(self);self.current.setAlignment(Qt.AlignCenter);self.current.setWordWrap(True)
        self.following=DragLabel(self);self.following.setAlignment(Qt.AlignCenter)
        self.title=DragLabel(self);self.title.setAlignment(Qt.AlignCenter)
        self.timer_label=QLabel(self);self.timer_label.hide()
        for widget,pixels in ((self.current,13),(self.following,10)):
            font=QFont('SimSun');font.setPixelSize(pixels);font.setWeight(QFont.DemiBold if pixels==13 else QFont.Normal)
            widget.setFont(font);widget.setStyleSheet(f'font-family:"SimSun";font-size:{pixels}px;font-weight:{600 if pixels==13 else 400};color:#edf0e6;background:transparent;border:0;')
            shadow=QGraphicsDropShadowEffect(widget);shadow.setOffset(0,1);shadow.setBlurRadius(2)
            shadow.setColor(QColor('#aa4f593d'));widget.setGraphicsEffect(shadow)
        font=QFont('Microsoft YaHei UI');font.setPixelSize(10);self.title.setFont(font)
        self.title.setStyleSheet('font-family:"Microsoft YaHei UI";font-size:10px;color:#72816a;background:transparent;border:0;')
        self.previous=BubbleButton(self,'previous','#fff0c8','#a4864e',34)
        self.play=BubbleButton(self,'toggle','#f6dcd1','#b75d4b',37)
        self.next=BubbleButton(self,'next','#e5ebd7','#829368',34)
        self.buttons=(self.previous,self.play,self.next)
        self.dialog=LyricsDialog(self)
        self.offset=self.dialog.offset
        self.rescale()
        saved=c.store.data['music_positions'].get('companion')
        self.move(QPoint(*saved) if saved else c.pet.pos());self.keep_visible()
        c.pet.animation_timer.timeout.connect(self.refresh_avatar)

    @property
    def image_rect(self):
        return self.actor.geometry()

    @property
    def bubbles_frozen(self):
        return bool(self.hovered) or any(button.held or button.hasFocus() for button in self.buttons)

    def rescale(self):
        size=self.c.store.data['size'];self.setFixedSize(size+100,size+118)
        self.actor.setGeometry(64,20,size,size)
        self.head.setGeometry(64,0,size,18)
        self.current.setGeometry(34,size+26,size+62,38)
        self.following.setGeometry(34,size+65,size+62,17)
        self.title.setGeometry(34,size+88,size+62,20)
        saved=self.c.store.data['music_bubbles']
        for index,button in enumerate(self.buttons):
            default=QPoint(8,70+index*51)
            point=QPoint(*saved[button.command]) if button.command in saved else default
            point.setX(max(1,min(point.x(),self.width()-button.width()-1)))
            point.setY(max(1,min(point.y(),self.height()-button.height()-1)))
            self.bases[button.command]=point;button.move(point)
        self.keep_visible();self.mask_signature=None

    def keep_visible(self):
        screen=QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        self.move(clamp_position(self.pos(),self.size(),screen.availableGeometry()))

    def persist_position(self,point):
        self.c.store.data['music_positions']['companion']=[point.x(),point.y()];self.c.save()

    def save_bubble(self,button):
        self.bases[button.command]=QPoint(button.pos())
        self.c.store.data['music_bubbles'][button.command]=[button.x(),button.y()]
        self.c.save();self.update_mask()

    def reset_bubbles(self):
        self.c.store.data['music_bubbles']={};self.bubble_time=0.;self.rescale();self.c.save();self.update_mask()

    def enter(self):
        self.hovered.clear()
        self.rescale();self.refresh();self.refresh_avatar()

    def reveal_smoothly(self):
        if self.reveal: self.reveal.stop();self.reveal.deleteLater()
        self.setWindowOpacity(0)
        self.reveal=QPropertyAnimation(self,b'windowOpacity',self)
        self.reveal.setStartValue(0.);self.reveal.setEndValue(1.)
        self.reveal.setDuration(220);self.reveal.setEasingCurve(QEasingCurve.OutCubic);self.reveal.start()

    def prepare_dock(self):
        if self.reveal: self.reveal.stop()
        self.dialog.hide()
        self.hovered.clear()
        self.setWindowOpacity(1)

    def start_drag(self,point):
        self.drag=dict(point=point,origin=self.pos(),moved=False)

    def move_drag(self,point):
        if self.drag:
            delta=point-self.drag['point']
            self.drag['moved']|=delta.manhattanLength()>=QApplication.startDragDistance()
            if self.drag['moved']: self.move(self.drag['origin']+delta)

    def end_drag(self,point,pat=False):
        if not self.drag: return
        moved=self.drag['moved'];self.drag=None
        if moved:
            if not self.c.dock.try_hide(point): self.keep_visible();self.persist_position(self.pos())
        elif pat:
            self.c.pat();self.show_feedback('嘿嘿，一起听歌吧 ♡')

    def refresh_avatar(self):
        if not self.c.music_state.active or self.c.dock.inactive: return
        now=time.monotonic();delta=max(0,min(.1,now-self.last_frame));self.last_frame=now
        if self.song.get('playing') is True: self.effect_time+=delta
        if not self.bubbles_frozen:
            self.bubble_time+=delta
            for index,button in enumerate(self.buttons):
                phase=self.bubble_time*2*math.pi/4.8-index*1.7
                base=self.bases[button.command]
                button.move(base+QPoint(round(-1.5+1.5*math.cos(phase)),round(-1+4*math.cos(phase))))
        if self.c.pet.scaled:
            pixmap=self.c.pet.scaled.scaled(self.actor.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation)
            self.actor.setPixmap(pixmap)
            bounds=QRegion(pixmap.mask()).boundingRect()
            y=self.actor.y()+self.actor.height()-pixmap.height()+bounds.top()-self.head.height()-3
            self.head.move(self.head.x(),max(0,y))
        self.head.update()
        for button in self.buttons: button.update()
        self.update_mask()

    def update_mask(self):
        pixmap=self.actor.pixmap()
        if pixmap is None or pixmap.isNull(): return
        origin=self.actor.pos()+QPoint((self.actor.width()-pixmap.width())//2,self.actor.height()-pixmap.height())
        signature=(pixmap.cacheKey(),tuple((b.x(),b.y()) for b in self.buttons),self.head.y(),self.current.text(),self.following.text(),self.title.text())
        if signature==self.mask_signature:return
        self.mask_signature=signature
        image=pixmap.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        region=QRegion(QBitmap.fromImage(image.createMaskFromColor(0,Qt.MaskInColor))).translated(origin)
        for button in self.buttons: region|=QRegion(button.geometry(),QRegion.Ellipse)
        center=self.head.geometry().center()
        region|=QRegion(QRect(center.x()-85,self.head.y(),170,self.head.height()))
        for label in (self.current,self.following,self.title):
            if label.text(): region|=QRegion(label.geometry())
        self.setMask(region)

    def populate_lyrics(self):
        self.last_lyric=None;self.manual_index=0
        self.dialog.lines.blockSignals(True);self.dialog.lines.clear()
        if self.document: self.dialog.lines.addItems([row[1] or '♪' for row in self.document['lines']] or self.document['plain'])
        self.dialog.lines.blockSignals(False)
        self.offset.blockSignals(True);self.offset.setValue(self.document.get('offset_ms',0) if self.document else 0);self.offset.blockSignals(False)
        self.offset.setEnabled(bool(self.document and self.document['lines']))

    def refresh(self):
        song=self.c.music_song();self.song=song
        if song['key']!=self.key:
            self.key=song['key'];self.document=self.library.load(self.key) if self.key else None
            self.populate_lyrics()
        self.c.music_state.cloud_owned=song['source']=='cloud'
        self.previous.setEnabled(song['can_previous']);self.play.setEnabled(song['can_toggle']);self.next.setEnabled(song['can_next'])
        self.head.text='正在听歌' if song['playing'] is True else '已暂停' if song['playing'] is False and self.key else '等待播放' if song['source']=='local' else '等待连接'
        self.play.setToolTip('暂停 · 拖动移位' if song['playing'] is True else '播放 / 暂停 · 拖动移位')
        self.previous.setToolTip('上一首 · 拖动移位');self.next.setToolTip('下一首 · 拖动移位')
        if not self.lyrics_enabled:
            self.refresh_song_info(song)
            return
        self.current.setText('暂无歌词 · 双击导入');self.following.clear();self.last_lyric=-1
        hint='导入 LRC / TXT，为当前歌曲保存歌词。'
        if self.document:
            lines=[row[1] for row in self.document['lines']] or self.document['plain']
            if self.document['lines'] and song['position'] is not None:
                index=lyric_index(self.document,song['position']);self.last_lyric=index
                hint='按播放器真实进度同步。正数让歌词提前，负数让歌词延后。'
                if index<0:
                    self.current.setText('前奏');self.following.setText(lines[0] if lines else '')
            else:
                index=min(self.manual_index,max(0,len(lines)-1))
                hint='播放器未提供进度，点击下面的歌词手动选择；不自动模拟计时。' if self.document['lines'] else '纯文本歌词，点击下面的行手动选择。'
            if 0<=index<len(lines):
                self.current.setText(lines[index] or '♪');self.following.setText(lines[index+1] if index+1<len(lines) else '')
                if self.dialog.isVisible():
                    self.dialog.lines.blockSignals(True);self.dialog.lines.setCurrentRow(index);self.dialog.lines.blockSignals(False)
        if not self.key: self.current.setText('选择一首歌，和唯一起听')
        self.current.setToolTip(hint+' 双击打开歌词设置。');self.following.setToolTip(self.current.toolTip())
        self.timer_label.setText(self.c.timer_text() if self.c.pomo.phase!='idle' else '')
        text=song['title'] or ('本地唱片架' if song['source']=='local' else '网易云音乐')
        if self.timer_label.text():text+=' · '+self.timer_label.text()
        if time.monotonic()<self.feedback_until:text=self.feedback_text
        self.title.setText(self.title.fontMetrics().elidedText(text,Qt.ElideRight,self.title.width()))
        self.title.setToolTip(song['status']+' · 右键打开音乐与歌词设置')
        self.dialog.title.setText(song['title'] or '请先选择歌曲');self.dialog.hint.setText(hint)
        self.head.update();self.update_mask()

    def refresh_song_info(self,song):
        title=song['title'].strip() or '等待播放歌曲'
        artist=song.get('artist','').strip()
        self.last_lyric=None
        for label,text in ((self.current,title),(self.following,artist)):
            label.setText(label.fontMetrics().elidedText(text,Qt.ElideRight,label.width()))
            label.setToolTip(text)
        self.timer_label.setText(self.c.timer_text() if self.c.pomo.phase!='idle' else '')
        text=self.feedback_text if time.monotonic()<self.feedback_until else self.timer_label.text()
        self.title.setText(self.title.fontMetrics().elidedText(text,Qt.ElideRight,self.title.width()))
        self.title.setToolTip(text or song['status'])
        self.dialog.hide()
        self.head.update();self.update_mask()

    def show_feedback(self,text):
        self.feedback_text=text;self.feedback_until=time.monotonic()+5
        self.refresh();self.title.setToolTip(text)

    def open_lyrics(self):
        if not self.lyrics_enabled:return
        self.refresh();self.dialog.show();self.dialog.raise_();self.dialog.activateWindow()

    def import_lyrics(self):
        self.refresh()
        if not self.key: self.c.tell('请先播放或选择一首歌曲，再导入歌词。');return
        key=self.key
        path,_=QFileDialog.getOpenFileName(self.dialog,'给当前歌曲导入歌词','','歌词 (*.lrc *.txt)')
        if not path:return
        try:
            document=self.library.import_file(key,path)
            if key==self.key:self.document=document;self.populate_lyrics();self.refresh()
        except (OSError,ValueError) as exc:self.c.tell('歌词导入失败：'+str(exc))

    def offset_changed(self,value):
        if self.document and self.key:
            self.document['offset_ms']=value
            try:self.library.save(self.key,self.document)
            except OSError:self.c.tell('无法保存歌词偏移')
            self.refresh()

    def closeEvent(self,event):
        if self.c.quitting:event.accept()
        else:self.c.leave_music_mode();event.ignore()

    def contextMenuEvent(self,event):
        menu=self.c.menu();menu.addSeparator()
        if self.lyrics_enabled:
            menu.addAction('导入当前歌曲歌词…',self.import_lyrics)
            menu.addAction('歌词与同步设置…',self.open_lyrics)
        menu.addAction('复位左侧控制气泡',self.reset_bubbles)
        menu.exec(event.globalPos())
