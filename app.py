from __future__ import annotations

import math
import json
import os
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QUrl, QObject, Slot
from PySide6.QtGui import (QAction, QBitmap, QColor, QDesktopServices, QFont, QIcon,
                           QImage, QPainter, QPainterPath, QPixmap, QRegion)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QAudioBufferOutput, QAudioFormat, QAudioBuffer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMenu,
    QMessageBox, QPushButton, QSlider, QSpinBox, QSystemTrayIcon, QTabWidget,
    QVBoxLayout, QWidget, QScrollArea)

from core import AUDIO_EXTENSIONS, Animation, Pomodoro, Store, cloud_url
from library import LibraryScanner, ImportResult, path_key
from media_bridge import MediaBridge
from audio_motion import AudioFeatures, SystemAudio, MotionEnvelope
from animation_renderer import ContinuousRenderer
from edge_hide import EdgeDock
from action_packs import discover_packs

FROZEN = getattr(sys, 'frozen', False)
ROOT = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
ASSETS = Path(getattr(sys, '_MEIPASS', ROOT)) / 'assets'
BASE_NAMES = {'auto': '自动 · 跟随日常与音乐', 'idle': '校园 · 安静待机',
         'daydream': '校园 · 发呆', 'listen': '轻音乐 · 托腮听歌',
         'spin': '呆唯 · 手臂大回旋',
         'eat': '零食 · 啃玉米', 'quiet': '安静模式'}
ACTION_PACKS, ACTION_ERRORS = discover_packs(ASSETS/'actions',ROOT/'actions')
NAMES = dict(BASE_NAMES,**{key:pack.name for key,pack in ACTION_PACKS.items()})
STYLE = '''
QWidget { font-family: "Microsoft YaHei UI"; font-size: 13px; color: #354946; }
QWidget#panel { background: #f7f6f0; }
QLabel#title { font-size: 27px; font-weight: 700; color: #294e47; }
QLabel#sub { color: #7b8881; font-size: 12px; }
QLabel#clock { font-size: 48px; font-weight: 600; color: #386c60; padding: 10px; }
QLabel#note { color: #62746c; background: #eaf0e6; border-radius: 10px; padding: 12px; }
QTabWidget::pane { border: 1px solid #e2e6dc; background: #ffffff; border-radius: 12px; }
QTabBar::tab { padding: 11px 20px; margin-right: 5px; color: #78877f; border: 0; }
QTabBar::tab:selected { color: #315c50; background: #e4eddf; border-radius: 8px; }
QPushButton { background: #e6eee2; border: 1px solid #d8e3d2; padding: 9px 14px; border-radius: 8px; }
QPushButton:hover { background: #d9e8d2; }
QPushButton:pressed { background: #c8dcc0; }
QPushButton:disabled { color: #a4ada6; background: #f1f2ee; }
QPushButton#primary { background: #386c60; color: white; border: 0; }
QPushButton#primary:hover { background: #28574c; }
QListWidget { background: #fafbf8; border: 1px solid #e2e6dc; border-radius: 9px; padding: 6px; }
QListWidget::item { padding: 9px; border-radius: 5px; }
QListWidget::item:selected { background: #dfeadb; color: #294e47; }
QLineEdit, QSpinBox, QComboBox { background: white; border: 1px solid #dce3d6; border-radius: 6px; padding: 7px; }
QSlider::groove:horizontal { height: 5px; background: #dfe6d9; border-radius: 2px; }
QSlider::handle:horizontal { width: 15px; background: #548675; border-radius: 7px; margin: -5px 0; }
QCheckBox { spacing: 8px; padding: 4px; }
QMenu { background: #fafbf6; border: 1px solid #dce3d6; padding: 7px; }
QMenu::item { padding: 8px 22px; border-radius: 5px; }
QMenu::item:selected { background: #e0ebda; }
'''


def button(text, slot, primary=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName('primary')
    b.clicked.connect(slot)
    return b


def note(text):
    label = QLabel(text)
    label.setObjectName('note')
    label.setWordWrap(True)
    return label


def row(*widgets):
    layout = QHBoxLayout()
    for w in widgets:
        layout.addWidget(w)
    return layout


class Sprites:
    def __init__(self):
        sheet = QPixmap(str(ASSETS / 'yui-sheet.png'))
        if sheet.isNull():
            raise RuntimeError('角色素材缺失，请保持 assets 文件夹与程序完整。')
        # Actual row boundaries in the generated sheet; do not rescale source cells.
        bounds = [
            [(30, 0, 300, 275), (370, 0, 300, 275), (700, 0, 300, 275), (1030, 0, 313, 275)],
            [(25, 279, 292, 276), (370, 279, 292, 276), (705, 279, 292, 276), (1040, 279, 303, 276)],
            [(0, 559, 378, 320), (350, 559, 358, 320), (675, 559, 335, 320), (1010, 559, 333, 320)],
            [(30, 882, 290, 289), (370, 882, 290, 289), (705, 882, 290, 289), (1040, 882, 303, 289)],
        ]
        self.frames = [[sheet.copy(*b) for b in line] for line in bounds]
        motion_dir = ASSETS / 'arm-spin'
        manifest = json.loads((motion_dir / 'motion.json').read_text(encoding='utf-8'))
        self.spin_fps = float(manifest['fps'])
        self.spin_frames = [QPixmap(str(motion_dir / f'{i:02d}.png'))
                            for i in range(manifest['frame_count'])]
        if not self.spin_frames or any(pm.isNull() for pm in self.spin_frames):
            raise RuntimeError('手臂大回旋素材缺失，请保持程序文件夹完整。')
        corn_dir = ASSETS / 'corn'
        corn = json.loads((corn_dir / 'motion.json').read_text(encoding='utf-8'))
        self.corn_durations = corn['durations_ms']
        self.corn_frames = [QPixmap(str(corn_dir / f'{i:02d}.png'))
                            for i in range(corn['frame_count'])]
        if (not self.corn_frames or any(pm.isNull() for pm in self.corn_frames)
                or len(self.corn_frames) != len(self.corn_durations)
                or any(ms <= 0 for ms in self.corn_durations)):
            raise RuntimeError('啃玉米素材缺失，请保持程序文件夹完整。')
        self.reload_clips(ACTION_PACKS)

    def reload_clips(self,packs):
        clips={}
        accepted={}
        errors=[]
        for key,pack in packs.items():
            frames=[QPixmap(str(file)) for file in pack.files]
            if any(frame.isNull() for frame in frames):
                fallback,_=discover_packs(ASSETS/'actions')
                base=fallback.get(key)
                if base and base.folder!=pack.folder:
                    frames=[QPixmap(str(file)) for file in base.files]
                    if not any(frame.isNull() for frame in frames):
                        errors.append(f'{pack.name}：外置 PNG 解码失败，已恢复内置版本')
                        pack=base
                    else:
                        errors.append(f'{pack.name}：PNG 解码失败，已跳过')
                        continue
                else:
                    errors.append(f'{pack.name}：PNG 解码失败，已跳过')
                    continue
            clips[key]=(frames,pack.fps)
            accepted[key]=pack
        self.clips,self.packs,self.pack_errors=clips,accepted,errors

    def frame(self, state, now):
        if state in self.clips:
            frames,fps = self.clips[state]
            return frames[self.packs[state].frame_index(now)]
        if state == 'eat':
            elapsed = (now * 1000) % sum(self.corn_durations)
            for pm, duration in zip(self.corn_frames, self.corn_durations):
                if elapsed < duration:
                    return pm
                elapsed -= duration
            return self.corn_frames[-1]
        if state == 'spin':
            return self.spin_frames[int(now * self.spin_fps) % len(self.spin_frames)]
        if state == 'idle':
            cycle = now % 6
            index = 1 if 4.8 < cycle < 4.94 else 2 if 4.94 <= cycle < 5.08 else 0
            return self.frames[0][index]
        if state == 'daydream':
            return self.frames[0][3 if int(now / 2) % 3 else 0]
        if state == 'happy':
            return self.frames[0][1]
        line = {'listen': 1}.get(state, 0)
        # These are drawn frame changes rather than rotation of a static screenshot.
        sequence = [0, 1, 2, 3] if line != 1 else [0, 1, 2, 1, 3, 1]
        interval = .55
        return self.frames[line][sequence[int(now / interval) % len(sequence)]]


class Pet(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setWindowTitle('平泽唯 · 桌宠')
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint |
                            (Qt.WindowStaysOnTopHint if self.c.store.data['topmost'] else Qt.WindowFlags()))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.press_global = None
        self.moved = False
        self.message = ''
        self.message_until = 0
        self.important = False
        self.message_priority = 0
        self.scaled = None
        self.image_rect = QRect()
        self.last_signature = None
        self.renderer = ContinuousRenderer()
        self.envelope = MotionEnvelope()
        self.spin_time = 0.0
        self.eat_time = 0.0
        self.clip_time = 0.0
        self.last_motion_time = time.monotonic()
        self.last_motion_state = None
        self.resize_pet(self.c.store.data['size'])
        pos = self.c.store.data.get('position')
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(QPoint(*pos) if pos else QPoint(screen.right() - self.width() - 45,
                                                 screen.bottom() - self.height() - 20))
        self.keep_visible()
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.refresh)
        self.animation_timer.start(33)
        self.refresh()

    def resize_pet(self, size):
        self.setFixedSize(size + 40, int(size * 1.02) + 100)
        self.last_signature = None
        if hasattr(self, 'animation_timer'):
            self.refresh()
            self.keep_visible()

    def keep_visible(self):
        if hasattr(self.c, 'dock') and self.c.dock.inactive:
            return
        screens = QApplication.screens()
        screen = max(screens, key=lambda s: (s.availableGeometry() & self.geometry()).width() *
                     (s.availableGeometry() & self.geometry()).height())
        area = screen.availableGeometry()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def say(self, text, important=False, seconds=4, priority=None):
        if hasattr(self.c, 'dock') and self.c.dock.inactive:
            return
        priority = (1 if important else 0) if priority is None else priority
        if not important and (not self.c.store.data['bubbles'] or self.c.pomo.phase != 'idle'
                              or self.c.animation.mode == 'quiet'):
            return
        if self.important and time.monotonic() < self.message_until and not important:
            return
        if time.monotonic() < self.message_until and priority < self.message_priority:
            return
        self.message, self.important = text, important
        self.message_priority = priority
        self.message_until = time.monotonic() + seconds
        self.last_signature = None
        self.refresh()

    def refresh(self):
        if hasattr(self.c, 'dock') and self.c.dock.inactive:
            return
        now = time.monotonic()
        state = self.c.animation.state()
        level, onset = self.c.current_audio(now)
        if onset:
            self.envelope.onset = 1
        phase, strength, pulse = self.envelope.update(now, self.c.animation.playing,
            level, self.c.store.data['drive'])
        dt = max(0.0, min(.1, now - self.last_motion_time))
        self.last_motion_time = now
        if state == 'spin':
            if self.last_motion_state != 'spin':
                self.spin_time = 0.0
            speed = min(1.0, strength * 4) if self.c.store.data['drive'] else 1.0
            self.spin_time += dt * speed * (1 + .10 * level)
        if state in self.c.sprites.clips:
            self.clip_time = 0.0 if self.last_motion_state != state else self.clip_time+dt
        if state == 'eat':
            if self.last_motion_state != 'eat':
                self.eat_time = 0.0
            else:
                self.eat_time += dt
        self.last_motion_state = state
        if state == 'listen':
            source = self.c.sprites.frames[1][1]
        elif state == 'spin':
            # Automatic bursts use natural clip timing so they end on complete
            # loops; fixed music-driven spin keeps its pause/decay behavior.
            clip_time = self.c.animation.elapsed() if self.c.animation.mode=='auto' else self.spin_time
            source = self.c.sprites.frame('spin', clip_time)
        elif state in self.c.sprites.clips:
            automatic = self.c.animation.mode=='auto' and self.c.animation.temporary != state
            clip_time = (self.c.animation.elapsed() if automatic else
                         now-self.c.animation.interaction_started if self.c.animation.temporary==state
                         else self.clip_time)
            source = self.c.sprites.frame(state, clip_time)
        elif state == 'eat':
            source = self.c.sprites.frame('eat', self.eat_time)
        else:
            source = self.c.sprites.frame(state, now)
        if now >= self.message_until:
            self.message, self.important = '', False
            self.message_priority = 0
        timer_text = self.c.timer_text() if self.c.pomo.phase != 'idle' else ''
        continuous = state in ('listen', 'idle', 'daydream', 'happy') and self.c.animation.mode != 'quiet'
        signature = (source.cacheKey(), self.width(), self.message, timer_text, int(now * 30) if continuous else 0)
        if signature == self.last_signature:
            return
        self.last_signature = signature
        size = self.c.store.data['size']
        if continuous:
            self.scaled = self.renderer.render(source, size, state, phase, strength, pulse, now)
        else:
            self.scaled = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_rect = QRect((self.width() - self.scaled.width()) // 2,
                                self.height() - self.scaled.height(),
                                self.scaled.width(), self.scaled.height())
        # Include all nonzero-alpha pixels in the input shape to preserve soft edges.
        premultiplied = self.scaled.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        bitmap = QBitmap.fromImage(premultiplied.createMaskFromColor(0, Qt.MaskInColor))
        region = QRegion(bitmap).translated(self.image_rect.topLeft())
        if self.message:
            region = region.united(QRegion(self.bubble_rect()))
        if timer_text:
            region = region.united(QRegion(25, 73, self.width() - 50, 27))
        self.setMask(region)
        self.update()

    def bubble_rect(self):
        return QRect(12, 8, self.width() - 24, 58)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.scaled:
            p.drawPixmap(self.image_rect, self.scaled)
        if self.message:
            p.setPen(QColor('#b9c9aa'))
            p.setBrush(QColor('#fffdf3'))
            p.drawRoundedRect(self.bubble_rect(), 12, 12)
            p.setPen(QColor('#405c4a'))
            p.setFont(QFont('Microsoft YaHei UI', 10))
            p.drawText(self.bubble_rect().adjusted(10, 5, -10, -5), Qt.AlignCenter | Qt.TextWordWrap, self.message)
        if self.c.pomo.phase != 'idle':
            r = QRect(25, 73, self.width() - 50, 27)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#e7efde'))
            p.drawRoundedRect(r, 10, 10)
            p.setPen(QColor('#386354'))
            p.setFont(QFont('Microsoft YaHei UI', 10))
            p.drawText(r, Qt.AlignCenter, self.c.timer_text())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.press_pos = self.pos()
            self.moved = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.press_global is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.press_global
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self.moved = True
            if self.moved:
                self.move(self.press_pos + delta)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.press_global is None:
            return
        self.press_global = None
        self.setCursor(Qt.OpenHandCursor)
        if self.moved:
            if self.c.dock.try_hide(event.globalPosition().toPoint()):
                return
            self.keep_visible()
            self.c.store.data['position'] = [self.x(), self.y()]
            self.c.save()
        elif self.image_rect.contains(event.position().toPoint()):
            if event.position().y() < self.image_rect.top() + self.image_rect.height() * .62:
                self.c.pat()
            else:
                self.c.open_panel()

    def wheelEvent(self, event):
        self.c.set_size(self.c.store.data['size'] + (15 if event.angleDelta().y() > 0 else -15))

    def contextMenuEvent(self, event):
        self.c.menu().exec(event.globalPos())

    def closeEvent(self, event):
        if not self.c.quitting:
            event.ignore()
        else:
            event.accept()


class Panel(QWidget):
    def __init__(self, c):
        super().__init__()
        self.c = c
        self.setObjectName('panel')
        self.setWindowTitle('放课后 · 平泽唯桌宠测试版')
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(620, area.width() - 30), min(720, area.height() - 40))
        self.setMinimumSize(520, 480)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(25, 23, 25, 20)
        outer.setSpacing(12)
        title = QLabel('放课后，和唯一起。')
        title.setObjectName('title')
        outer.addWidget(title)
        sub = QLabel('YUI COMPANION   /   测试版 0.7.1')
        sub.setObjectName('sub')
        outer.addWidget(sub)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.music_tab(), '音乐')
        self.tabs.addTab(self.study_tab(), '学习')
        self.tabs.addTab(self.pet_tab(), '陪伴')
        outer.addWidget(self.tabs, 1)
        self.status = QLabel('准备好啦。右键桌宠也可以打开菜单。')
        self.status.setWordWrap(True)
        self.status.setObjectName('sub')
        self.status.setMinimumHeight(36)
        outer.addWidget(self.status)
        self.setWindowIcon(c.icon)

    def page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        return w, layout

    def scrolled(self, widget):
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll

    def music_tab(self):
        self.music_pages = QTabWidget()
        w, layout = self.page()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索本地歌曲或歌手文件名')
        self.search.textChanged.connect(self.filter_tracks)
        layout.addWidget(self.search)
        self.add_files_button = button('添加歌曲', self.c.import_files)
        self.add_folder_button = button('添加文件夹', self.c.import_folder)
        self.cancel_scan = button('取消扫描', self.c.cancel_scan)
        self.cancel_scan.setEnabled(False)
        layout.addLayout(row(self.add_files_button, self.add_folder_button, self.cancel_scan))
        self.scan_status = QLabel('尚未扫描')
        self.scan_status.setWordWrap(True)
        self.scan_status.setObjectName('sub')
        self.library_count = QLabel()
        layout.addWidget(self.scan_status)
        layout.addWidget(self.library_count)
        self.tracks = QListWidget()
        self.tracks.setMinimumHeight(135)
        self.tracks.itemDoubleClicked.connect(lambda _: self.c.play(self.tracks.currentRow()))
        layout.addWidget(self.tracks, 1)
        layout.addLayout(row(button('移除选中', self.remove_track),
                             button('重新定位文件', self.c.relocate_track),
                             button('导入详情', self.c.import_details)))
        self.now = QLabel('还没有播放歌曲')
        self.now.setWordWrap(True)
        layout.addWidget(self.now)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderReleased.connect(lambda: self.c.player.setPosition(self.seek.value()))
        self.elapsed = QLabel('00:00 / 00:00')
        self.elapsed.setObjectName('sub')
        layout.addWidget(self.seek)
        layout.addWidget(self.elapsed)
        self.play_button = button('播放 / 暂停', self.c.toggle_play, True)
        self.loop = QComboBox()
        self.loop.addItems(['列表顺序', '单曲循环', '列表循环'])
        self.loop.setCurrentIndex(self.c.store.data['loop'])
        self.loop.currentIndexChanged.connect(lambda v: self.c.setting('loop', v))
        layout.addLayout(row(button('上一首', lambda: self.c.step(-1)), self.play_button,
                             button('下一首', lambda: self.c.step(1)), self.loop))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(self.c.store.data['volume'])
        self.volume.valueChanged.connect(self.c.set_volume)
        self.volume_label = QLabel(f"音量 {self.c.store.data['volume']}%")
        layout.addLayout(row(self.volume_label, self.volume))
        self.refresh_tracks()
        self.music_pages.addTab(self.scrolled(w), '本地唱片架')
        w, layout = self.page()
        self.cloud_sessions = QComboBox()
        self.cloud_sessions.addItem('正在查找网易云…', '')
        self.cloud_sessions.currentIndexChanged.connect(self.c.select_cloud)
        layout.addLayout(row(self.cloud_sessions, button('重新连接', self.c.refresh_media)))
        self.cloud_status = QLabel('连接中…')
        self.cloud_status.setObjectName('note')
        self.cloud_status.setWordWrap(True)
        layout.addWidget(self.cloud_status)
        self.cloud_now = QLabel('等待播放器提供曲名')
        self.cloud_now.setWordWrap(True)
        layout.addWidget(self.cloud_now)
        self.cloud_previous = button('上一首', lambda: self.c.cloud_command('previous'))
        self.cloud_play = button('播放 / 暂停', lambda: self.c.cloud_command('toggle'), True)
        self.cloud_next = button('下一首', lambda: self.c.cloud_command('next'))
        for control in (self.cloud_previous, self.cloud_play, self.cloud_next):
            control.setEnabled(False)
        layout.addLayout(row(self.cloud_previous, self.cloud_play, self.cloud_next))
        self.cloud_seek = QSlider(Qt.Horizontal)
        self.cloud_seek.setRange(0, 0)
        self.cloud_seek.setEnabled(False)
        self.cloud_seek.sliderReleased.connect(lambda: self.c.cloud_command('seek', self.cloud_seek.value()))
        self.cloud_elapsed = QLabel('尚未获得播放进度')
        self.cloud_elapsed.setObjectName('sub')
        layout.addWidget(self.cloud_seek)
        layout.addWidget(self.cloud_elapsed)
        self.system_audio = QCheckBox('允许分析系统声音，让角色随声音强弱动作')
        self.system_audio.setChecked(self.c.store.data['system_audio'])
        self.system_audio.toggled.connect(self.c.set_system_audio)
        layout.addWidget(self.system_audio)
        self.audio_status = QLabel('系统声音分析已关闭。本地音乐使用自身解码音频。')
        self.audio_status.setObjectName('sub')
        self.audio_status.setWordWrap(True)
        layout.addWidget(self.audio_status)
        layout.addWidget(note('声音只在本地实时分析，不保存、不上传、不使用麦克风。\n系统声音包含其他应用，当前不是网易云专属节拍。'))
        layout.addWidget(QLabel('歌曲与歌单入口'))
        self.links = QListWidget()
        self.links.setMaximumHeight(100)
        self.links.itemDoubleClicked.connect(lambda _: self.open_link())
        layout.addWidget(self.links)
        self.link_name = QLineEdit()
        self.link_name.setPlaceholderText('歌单名称')
        self.link_url = QLineEdit()
        self.link_url.setPlaceholderText('粘贴网易云歌曲 / 歌单链接')
        layout.addLayout(row(self.link_name, self.link_url))
        layout.addLayout(row(button('保存链接', self.add_link), button('打开选中', self.open_link),
                             button('删除链接', self.remove_link)))
        hint = QLabel('连接不到时：在网易云设置开启系统媒体控制（SMTC），完全退出后重启并播放。\n歌单仍在网易云打开；此处不读取完整歌单，也不接管账号。')
        hint.setWordWrap(True)
        hint.setObjectName('sub')
        layout.addWidget(hint)
        self.refresh_links()
        self.music_pages.addTab(self.scrolled(w), '网易云联动')
        self.music_pages.setCurrentIndex(0 if self.c.store.data['music_source'] == 'local' else 1)
        self.music_pages.currentChanged.connect(lambda i: self.c.set_music_source('local' if i == 0 else 'cloud'))
        return self.music_pages

    def study_tab(self):
        w, layout = self.page()
        layout.addWidget(note('一起认真一小会儿，再去喝茶吧。\n计时期间减少随机气泡，音乐仍可继续播放。'))
        self.phase = QLabel('准备专注')
        self.phase.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.phase)
        self.clock = QLabel('25:00')
        self.clock.setObjectName('clock')
        self.clock.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.clock)
        form = QFormLayout()
        self.focus = QSpinBox()
        self.focus.setRange(1, 180)
        self.focus.setSuffix(' 分钟')
        self.focus.setValue(self.c.store.data['focus'])
        self.focus.valueChanged.connect(lambda v: self.c.setting('focus', v))
        self.rest = QSpinBox()
        self.rest.setRange(1, 60)
        self.rest.setSuffix(' 分钟')
        self.rest.setValue(self.c.store.data['rest'])
        self.rest.valueChanged.connect(lambda v: self.c.setting('rest', v))
        form.addRow('专注时长', self.focus)
        form.addRow('休息时长', self.rest)
        layout.addLayout(form)
        self.start_focus = button('开始专注', lambda: self.c.start_timer('focus'), True)
        self.start_rest = button('开始休息', lambda: self.c.start_timer('rest'))
        layout.addLayout(row(self.start_focus, self.start_rest))
        self.pause = button('暂停', self.c.pause_timer)
        self.stop = button('结束计时', self.c.stop_timer)
        layout.addLayout(row(self.pause, self.stop))
        self.reminders = QCheckBox('定时提醒我学习')
        self.reminders.setChecked(self.c.store.data['reminders'])
        self.reminders.toggled.connect(self.c.set_reminders)
        layout.addWidget(self.reminders)
        self.interval = QSpinBox()
        self.interval.setRange(1, 240)
        self.interval.setValue(self.c.store.data['interval'])
        self.interval.setSuffix(' 分钟提醒一次')
        self.interval.valueChanged.connect(self.c.set_interval)
        layout.addWidget(self.interval)
        layout.addWidget(note('每个阶段结束后由你决定下一步，不自动开始下一轮。\n番茄钟运行时，普通学习提醒暂缓；重启不续跑计时。'))
        layout.addStretch()
        return self.scrolled(w)

    def pet_tab(self):
        w, layout = self.page()
        layout.addWidget(note('点击头部摸摸头，点击身体打开面板。\n拖动调整位置，滚轮调整大小，右键打开菜单。'))
        self.mode = QComboBox()
        for key, name in NAMES.items():
            self.mode.addItem(name, key)
        self.mode.setCurrentIndex(list(NAMES).index(self.c.animation.mode))
        self.mode.currentIndexChanged.connect(lambda i: self.c.set_mode(self.mode.itemData(i)))
        layout.addWidget(QLabel('选择情境与动作'))
        layout.addWidget(self.mode)
        self.action_label = QLabel()
        self.action_label.setObjectName('sub')
        layout.addWidget(self.action_label)
        self.drive = QCheckBox('根据所选播放器的状态与声音驱动动作')
        self.drive.setChecked(self.c.store.data['drive'])
        self.drive.toggled.connect(self.c.set_drive)
        layout.addWidget(self.drive)
        layout.addWidget(note('自动：日常等待 30～60 秒后偶尔做小动作；\n听歌以托腮为主，45～90 秒后偶尔大回旋。\n短动作按完整循环播放；专注时减少动作，互动结束后重新等待。'))
        layout.addLayout(row(button('摸摸头', self.c.pat), button('喂玉米', self.c.feed)))
        pack_buttons=[button(pack.button_label,lambda checked=False,key=key:self.c.play_gesture(key))
                      for key,pack in self.c.sprites.packs.items()]
        for start in range(0,len(pack_buttons),3):
            layout.addLayout(row(*pack_buttons[start:start+3]))
        layout.addWidget(button('重新载入动作包',self.c.reload_action_packs))
        if self.c.action_errors:
            layout.addWidget(note('部分动作未载入：'+'；'.join(self.c.action_errors)))
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(180, 480)
        self.size.setValue(self.c.store.data['size'])
        self.size.valueChanged.connect(self.c.set_size)
        layout.addWidget(QLabel('角色大小'))
        layout.addWidget(self.size)
        self.topmost = QCheckBox('桌宠始终置顶')
        self.topmost.setChecked(self.c.store.data['topmost'])
        self.topmost.toggled.connect(self.c.set_topmost)
        self.sound = QCheckBox('计时结束与学习提醒声音')
        self.sound.setChecked(self.c.store.data['sound'])
        self.sound.toggled.connect(lambda v: self.c.setting('sound', v))
        self.bubbles = QCheckBox('普通互动文字气泡')
        self.bubbles.setChecked(self.c.store.data['bubbles'])
        self.bubbles.toggled.connect(lambda v: self.c.setting('bubbles', v))
        layout.addWidget(self.topmost)
        layout.addWidget(self.sound)
        layout.addWidget(self.bubbles)
        self.edge_hide = QCheckBox('拖到屏幕边缘时隐藏')
        self.edge_hide.setChecked(self.c.store.data['edge_hide'])
        self.edge_hide.toggled.connect(self.c.set_edge_hide)
        layout.addWidget(self.edge_hide)
        layout.addWidget(note('拖到上下左右边缘并松开，可收成轻音标志。\n点击标志展开，向屏幕内拖动可恢复并继续移动。'))
        layout.addWidget(note('大回旋：使用你提供视频的原始动作帧，半身透明构图。\n旧拨弦动作已移除；视频中的吉他道具保留。\n音乐暂停后逐渐收住，不宣称精准跟拍。'))
        layout.addLayout(row(button('找回桌宠', self.c.find_pet), button('退出桌宠', self.c.quit)))
        layout.addStretch()
        return self.scrolled(w)

    def refresh_tracks(self):
        selected = self.tracks.currentRow()
        self.tracks.setUpdatesEnabled(False)
        self.tracks.clear()
        for path in self.c.store.data['tracks']:
            self.tracks.addItem(Path(path).stem)
            self.tracks.item(self.tracks.count() - 1).setToolTip(path)
        if self.tracks.count():
            self.tracks.setCurrentRow(min(max(0, selected), self.tracks.count() - 1))
        self.tracks.setUpdatesEnabled(True)
        self.filter_tracks(self.search.text())

    def filter_tracks(self, text):
        visible = 0
        for index in range(self.tracks.count()):
            item = self.tracks.item(index)
            show = text.casefold() in item.text().casefold()
            item.setHidden(not show)
            visible += show
        self.library_count.setText(f'唱片架共 {self.tracks.count()} 首 · 当前显示 {visible} 首')

    def remove_track(self):
        index = self.tracks.currentRow()
        tracks = self.c.store.data['tracks']
        if not 0 <= index < len(tracks):
            return
        if index == self.c.track_index:
            self.c.player.stop()
            self.c.player.setSource(QUrl())
            self.c.track_index = -1
            self.now.setText('已移除当前歌曲')
        elif index < self.c.track_index:
            self.c.track_index -= 1
        tracks.pop(index)
        self.refresh_tracks()
        self.c.save()

    def refresh_links(self):
        self.links.clear()
        for item in self.c.store.data['links']:
            self.links.addItem(item['name'])
            self.links.item(self.links.count() - 1).setToolTip(item['url'])
        if self.links.count():
            self.links.setCurrentRow(0)

    def add_link(self):
        try:
            url = cloud_url(self.link_url.text())
        except ValueError as e:
            self.c.tell(str(e))
            return
        name = self.link_name.text().strip()[:100] or '我的网易云歌单'
        links = self.c.store.data['links']
        for item in links:
            if item['url'] == url:
                item['name'] = name
                break
        else:
            links.append({'name': name, 'url': url})
        self.refresh_links()
        self.c.save()
        self.link_name.clear()
        self.link_url.clear()
        self.c.tell('已保存。打开链接后，请在网易云页面中播放。')

    def open_link(self):
        index = self.links.currentRow()
        if index < 0:
            self.c.tell('请先添加或选择一条网易云链接。')
            return
        url = cloud_url(self.c.store.data['links'][index]['url'])
        if not QDesktopServices.openUrl(QUrl(url)):
            self.c.tell('未能打开链接，请检查默认浏览器设置。')

    def remove_link(self):
        index = self.links.currentRow()
        if index >= 0:
            self.c.store.data['links'].pop(index)
            self.refresh_links()
            self.c.save()

    def closeEvent(self, event):
        if self.c.quitting:
            event.accept()
        else:
            self.hide()
            event.ignore()


class Controller(QObject):
    def __init__(self, app, data_path=None, services=None):
        super().__init__(app)
        self.app = app
        self.quitting = False
        self.services = data_path is None if services is None else services
        self.store = Store(data_path or ROOT / 'data' / 'settings.json',modes=NAMES)
        self.scanner = None
        self.last_import = None
        self.cloud_rows = []
        self.cloud_info = None
        self.media = None
        self.system_worker = None
        self.feature_extractor = AudioFeatures()
        self.local_features = {'level': 0, 'onset': False, 'time': 0}
        self.system_features = {'level': 0, 'onset': False, 'time': 0}
        self.consumed_onset = 0
        self.pomo = Pomodoro()
        self.animation = Animation()
        self.animation.mode = self.store.data['mode']
        self.animation.follow_music = self.store.data['drive']
        self.sprites = Sprites()
        NAMES.clear()
        NAMES.update(BASE_NAMES)
        NAMES.update({key:pack.name for key,pack in self.sprites.packs.items()})
        if self.animation.mode not in NAMES:
            self.animation.mode=self.store.data['mode']='auto'
        self.animation.configure_actions(self.sprites.packs)
        self.action_errors=ACTION_ERRORS+self.sprites.pack_errors
        self.icon = QIcon(self.sprites.frames[0][0])
        self.app.setWindowIcon(self.icon)
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.audio.setVolume(self.store.data['volume'] / 100)
        self.player.setAudioOutput(self.audio)
        self.buffer_output = QAudioBufferOutput()
        self.player.setAudioBufferOutput(self.buffer_output)
        self.buffer_output.audioBufferReceived.connect(self.local_audio)
        self.track_index = -1
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.media_error)
        self.next_reminder = time.monotonic() + self.store.data['interval'] * 60
        self.next_random = time.monotonic() + 60
        self.panel = Panel(self)
        self.player.positionChanged.connect(self.local_position)
        self.player.durationChanged.connect(self.local_duration)
        self.pet = Pet(self)
        self.dock = EdgeDock(self, ASSETS / 'edge-label.png')
        self.panel.setWindowIcon(self.icon)
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip('平泽唯 · 放课后桌宠')
        self.tray_menu = self.menu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.tick_timer = QTimer()
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(200)
        self.tick()
        self.pet.show()
        self.pet.say('放课后，一起听歌吧！', seconds=5)
        if self.store.warning:
            self.tell(self.store.warning)
        if self.services:
            self.media = MediaBridge(self)
            self.media.snapshot.connect(self.media_snapshot, Qt.QueuedConnection)
            self.media.feedback.connect(self.tell, Qt.QueuedConnection)
            self.media.start()
            self.update_capture()
        else:
            self.panel.cloud_status.setText('测试会话：未连接外部播放器')

    def save(self):
        try:
            self.store.save()
        except OSError:
            self.tell('无法保存设置，请将程序放在可写的普通文件夹中。')

    def setting(self, key, value):
        self.store.data[key] = value
        self.save()

    def tell(self, text):
        self.panel.status.setText(text)
        self.panel.status.setToolTip(text)
        if hasattr(self, 'pet'):
            self.pet.say(text[:100], important=True, seconds=7)

    def open_panel(self):
        self.panel.showNormal()
        self.panel.raise_()
        self.panel.activateWindow()

    def find_pet(self):
        self.dock.restore(animated=False)
        area = QApplication.primaryScreen().availableGeometry()
        self.pet.move(area.right() - self.pet.width() - 25, area.bottom() - self.pet.height() - 20)
        self.pet.keep_visible()
        self.pet.show()
        self.pet.raise_()
        self.store.data['position'] = [self.pet.x(), self.pet.y()]
        self.save()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_panel()

    def menu(self):
        menu = QMenu()
        menu.setStyleSheet(STYLE)
        menu.addAction('打开控制面板', self.open_panel)
        menu.addAction('播放 / 暂停所选播放器', self.toggle_active)
        actions = menu.addMenu('情境与动作')
        for key, label in NAMES.items():
            a = actions.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.animation.mode == key)
            a.triggered.connect(lambda checked=False, k=key: self.set_mode(k))
        menu.addSeparator()
        menu.addAction('摸摸头', self.pat)
        menu.addAction('喂玉米', self.feed)
        menu.addAction('开始专注 / 查看计时', self.focus_from_menu)
        menu.addAction('显示桌宠', lambda: self.dock.restore())
        menu.addAction('找回桌宠', self.find_pet)
        menu.addSeparator()
        menu.addAction('退出', self.quit)
        menu.aboutToShow.connect(lambda: self.sync_menu(actions))
        return menu

    def sync_menu(self, actions):
        for a, key in zip(actions.actions(), NAMES):
            a.setChecked(key == self.animation.mode)

    def focus_from_menu(self):
        if self.pomo.phase == 'idle':
            self.start_timer('focus')
        self.panel.tabs.setCurrentIndex(1)
        self.open_panel()

    def set_mode(self, mode):
        if mode not in NAMES:
            return
        self.animation.mode = mode
        self.animation.temporary = None
        self.pet.last_motion_state = None
        self.panel.mode.blockSignals(True)
        self.panel.mode.setCurrentIndex(list(NAMES).index(mode))
        self.panel.mode.blockSignals(False)
        self.setting('mode', mode)
        self.update_capture()

    def pat(self):
        self.animation.interact('happy', 2.5)
        self.pet.say(random.choice(['嘿嘿，好开心～', '今天也一起加油！', '再摸一下也可以哦。']))

    def feed(self):
        self.animation.interact('eat', 4.4)
        self.pet.eat_time = 0.0
        self.pet.last_motion_state = None
        self.pet.say('玉米好香！啊呜～')

    def play_gesture(self, state):
        if state not in self.sprites.clips:
            return
        pack=self.sprites.packs[state]
        self.animation.interact(state,pack.duration*pack.manual_cycles)
        self.pet.clip_time = 0.0
        self.pet.last_motion_state = None
        self.pet.say(pack.info.get('bubble',pack.name+'～'))
        self.pet.refresh()

    def reload_action_packs(self):
        packs,errors=discover_packs(ASSETS/'actions',ROOT/'actions')
        self.sprites.reload_clips(packs)
        self.action_errors=errors+self.sprites.pack_errors
        NAMES.clear()
        NAMES.update(BASE_NAMES)
        NAMES.update({key:pack.name for key,pack in self.sprites.packs.items()})
        self.animation.configure_actions(self.sprites.packs)
        if self.animation.mode not in NAMES:
            self.animation.mode=self.store.data['mode']='auto'
        if self.animation.temporary not in set(NAMES)|{'happy'}:
            self.animation.temporary=None
        previous=self.panel.tabs.currentIndex()
        old=self.panel.tabs.widget(2)
        self.panel.tabs.removeTab(2)
        self.panel.tabs.insertTab(2,self.panel.pet_tab(),'陪伴')
        self.panel.tabs.setCurrentIndex(previous)
        old.deleteLater()
        old_menu=self.tray_menu
        self.tray_menu=self.menu()
        self.tray.setContextMenu(self.tray_menu)
        old_menu.deleteLater()
        self.pet.last_motion_state=None
        self.pet.last_signature=None
        self.pet.refresh()
        self.save()
        issues=errors+self.sprites.pack_errors
        self.tell(f'已载入 {len(self.sprites.packs)} 个动作包。'+('部分素材已跳过：'+'；'.join(issues) if issues else ''))

    def set_size(self, value):
        value = max(180, min(480, value))
        self.store.data['size'] = value
        self.panel.size.blockSignals(True)
        self.panel.size.setValue(value)
        self.panel.size.blockSignals(False)
        self.pet.resize_pet(value)
        self.dock.persist()

    def set_edge_hide(self, value):
        self.setting('edge_hide', value)
        if not value:
            self.dock.restore(animated=False)

    def set_topmost(self, value):
        self.pet.setWindowFlag(Qt.WindowStaysOnTopHint, value)
        self.dock.label.setWindowFlag(Qt.WindowStaysOnTopHint, value)
        if self.dock.hidden:
            self.dock.label.show()
        else:
            self.pet.show()
        self.setting('topmost', value)

    def set_volume(self, value):
        self.audio.setVolume(value / 100)
        self.panel.volume_label.setText(f'音量 {value}%')
        self.setting('volume', value)

    def set_drive(self, value):
        self.animation.follow_music = value
        self.setting('drive', value)
        self.sync_playing()
        self.update_capture()

    def set_music_source(self, source):
        self.setting('music_source', source)
        self.panel.music_pages.blockSignals(True)
        self.panel.music_pages.setCurrentIndex(0 if source == 'local' else 1)
        self.panel.music_pages.blockSignals(False)
        self.sync_playing()
        self.update_capture()

    def set_system_audio(self, value):
        self.setting('system_audio', value)
        self.update_capture()

    def update_capture(self):
        wanted = (self.services and self.store.data['system_audio'] and self.store.data['drive']
                  and self.store.data['music_source'] == 'cloud' and self.animation.mode != 'quiet'
                  and self.cloud_info and self.cloud_info.get('playing') is True)
        if self.system_worker and self.system_worker.isRunning():
            if not wanted:
                self.system_worker.requestInterruption()
            return
        if wanted:
            self.system_worker = SystemAudio(self)
            self.system_worker.features.connect(self.system_audio_features, Qt.QueuedConnection)
            self.system_worker.status.connect(self.panel.audio_status.setText, Qt.QueuedConnection)
            self.system_worker.finished.connect(self.capture_finished)
            self.system_worker.start()
        elif hasattr(self, 'panel'):
            self.panel.audio_status.setText('系统声音分析已关闭；本地音乐使用自身解码音频。')

    @Slot()
    def capture_finished(self):
        self.system_features = {'level': 0, 'onset': False, 'time': 0}
        if not self.quitting:
            QTimer.singleShot(0, self.update_capture)

    @Slot(object)
    def system_audio_features(self, features):
        self.system_features = features

    @Slot(QAudioBuffer)
    def local_audio(self, buffer):
        if not buffer.isValid() or not buffer.byteCount():
            return
        import numpy as np
        try:
            raw = buffer.constData()
            raw = raw.asstring(buffer.byteCount()) if hasattr(raw, 'asstring') else bytes(raw)
            fmt = buffer.format().sampleFormat()
            types = {QAudioFormat.Float: (np.float32, 1.0), QAudioFormat.Int16: (np.int16, 32768.0),
                     QAudioFormat.Int32: (np.int32, 2147483648.0), QAudioFormat.UInt8: (np.uint8, 128.0)}
            if fmt not in types:
                return
            dtype, divisor = types[fmt]
            data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            if fmt == QAudioFormat.UInt8:
                data -= 128
            self.local_features = self.feature_extractor.feed(data / divisor, buffer.format().sampleRate())
        except (TypeError, ValueError, BufferError):
            return

    def current_audio(self, now):
        if not self.store.data['drive'] or not self.animation.playing:
            return 0.0, False
        features = self.local_features if self.store.data['music_source'] == 'local' else self.system_features
        if now - features['time'] > .4:
            return 0.0, False
        onset = features['onset'] and features['time'] != self.consumed_onset
        if onset:
            self.consumed_onset = features['time']
        return features['level'], onset

    def sync_playing(self):
        local = self.store.data['music_source'] == 'local'
        self.animation.playing = (self.player.playbackState() == QMediaPlayer.PlayingState if local
                                  else bool(self.cloud_info and self.cloud_info.get('playing')))

    def toggle_active(self):
        self.toggle_play() if self.store.data['music_source'] == 'local' else self.cloud_command('toggle')

    def refresh_media(self):
        if self.media:
            self.media.refresh()
        else:
            self.tell('当前测试会话没有连接外部播放器。')

    @Slot(object)
    def media_snapshot(self, snapshot):
        if self.quitting:
            return
        self.cloud_rows = snapshot['sessions']
        wanted = self.store.data['cloud_target']
        if not wanted:
            cloud = next((r for r in self.cloud_rows if any(x in r['id'].lower()
                         for x in ('cloudmusic', 'netease'))), None)
            wanted = cloud['id'] if cloud else ''
            if wanted:
                self.store.data['cloud_target'] = wanted
                self.save()
        combo = self.panel.cloud_sessions
        current_items = [combo.itemData(i) for i in range(combo.count())]
        ids = [''] + [r['id'] for r in self.cloud_rows]
        if current_items != ids:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem('选择目标播放器', '')
            for item in self.cloud_rows:
                label = '网易云音乐' if 'cloudmusic' in item['id'].lower() else item['label']
                combo.addItem(label, item['id'])
            combo.setCurrentIndex(ids.index(wanted) if wanted in ids else 0)
            combo.blockSignals(False)
        self.cloud_info = next((r for r in self.cloud_rows if r['id'] == wanted), None)
        self.render_cloud(snapshot.get('error', ''))
        self.sync_playing()
        self.update_capture()

    @Slot(int)
    def select_cloud(self, index):
        if not hasattr(self.panel, 'cloud_sessions'):
            return
        target = self.panel.cloud_sessions.itemData(index) or ''
        self.setting('cloud_target', target)
        self.cloud_info = next((r for r in self.cloud_rows if r['id'] == target), None)
        self.render_cloud()
        self.sync_playing()

    def render_cloud(self, error=''):
        info = self.cloud_info
        if not info:
            self.panel.cloud_status.setText(error or '未连接：开启网易云系统媒体控制并重启，然后点击重新连接。')
            self.panel.cloud_now.setText('未获得曲名')
            self.panel.cloud_elapsed.setText('未获得播放进度')
        else:
            kind = info['kind']
            state = '正在播放' if info['playing'] is True else '已暂停 / 停止' if info['playing'] is False else '播放状态未知'
            self.panel.cloud_status.setText(('系统媒体已连接 · ' if kind == 'smtc' else '兼容窗口控制 · ') + state)
            self.panel.cloud_now.setText(info['title'] + ('\n' + info['artist'] if info['artist'] else ''))
            self.panel.cloud_play.setText('暂停' if info['playing'] is True else '播放' if info['playing'] is False else '播放 / 暂停')
            duration, position = max(0, info['duration']), max(0, info['position'])
            self.panel.cloud_seek.setRange(0, int(duration))
            if not self.panel.cloud_seek.isSliderDown():
                self.panel.cloud_seek.setValue(int(position))
            self.panel.cloud_elapsed.setText(f'{self.minutes(position)} / {self.minutes(duration)}'
                if duration else '当前客户端未提供播放进度')
        for widget, key in ((self.panel.cloud_play, 'can_toggle'), (self.panel.cloud_next, 'can_next'),
                            (self.panel.cloud_previous, 'can_previous')):
            widget.setEnabled(bool(info and info[key]))
        self.panel.cloud_seek.setEnabled(bool(info and info['can_seek'] and info['duration'] > 0))

    def cloud_command(self, command, position=None):
        if not self.media or not self.cloud_info:
            self.tell('请先连接并选择网易云会话。')
            return
        self.set_music_source('cloud')
        self.media.request(self.cloud_info['id'], command, position)

    @staticmethod
    def minutes(seconds):
        seconds = max(0, int(seconds))
        return f'{seconds // 60:02d}:{seconds % 60:02d}'

    @Slot(int)
    def local_position(self, position):
        if not self.panel.seek.isSliderDown():
            self.panel.seek.setValue(position)
        self.panel.elapsed.setText(f'{self.minutes(position / 1000)} / {self.minutes(self.player.duration() / 1000)}')

    @Slot(int)
    def local_duration(self, duration):
        self.panel.seek.setRange(0, max(0, duration))
        self.panel.seek.setEnabled(duration > 0)

    def add_tracks(self, paths):
        result = ImportResult()
        seen = {path_key(x) for x in self.store.data['tracks']}
        for path in paths:
            LibraryScanner._file(str(path), seen, result)
        self.merge_import(result)

    def import_files(self):
        if self.scanner and self.scanner.isRunning():
            self.tell('已有扫描正在进行，可先取消后再添加。')
            return
        self.open_panel()
        paths, _ = QFileDialog.getOpenFileNames(self.panel, '选择本地歌曲', '',
            '音乐文件 (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma);;所有文件 (*)')
        if paths:
            self.start_import(paths)

    def import_folder(self):
        if self.scanner and self.scanner.isRunning():
            self.tell('已有扫描正在进行，可先取消后再添加。')
            return
        self.open_panel()
        path = QFileDialog.getExistingDirectory(self.panel, '选择音乐文件夹（包含子文件夹）')
        if path:
            self.start_import([path])

    def start_import(self, roots):
        if self.scanner and self.scanner.isRunning():
            self.tell('已有扫描正在进行。')
            return False
        self.scanner = LibraryScanner(roots, self.store.data['tracks'], self)
        self.scanner.progress.connect(self.scan_progress, Qt.QueuedConnection)
        self.scanner.result_ready.connect(self.merge_import, Qt.QueuedConnection)
        self.scanner.finished.connect(self.scan_finished, Qt.QueuedConnection)
        self.panel.cancel_scan.setEnabled(True)
        self.panel.add_folder_button.setEnabled(False)
        self.panel.add_files_button.setEnabled(False)
        self.panel.scan_status.setText('正在扫描…可以取消，已发现内容会保留。')
        self.scanner.start()
        return True

    @Slot(int, int)
    def scan_progress(self, examined, found):
        self.panel.scan_status.setText(f'扫描中：检查 {examined} 项，发现 {found} 首新歌曲…')

    @Slot(object)
    def merge_import(self, result):
        # This QObject slot is explicitly queued from the worker to the GUI thread.
        self.last_import = result
        previous_count = len(self.store.data['tracks'])
        self.store.data['tracks'].extend(result.paths)
        if result.paths:
            self.panel.search.clear()
            self.panel.refresh_tracks()
            self.panel.tracks.setCurrentRow(previous_count)
            self.panel.tracks.scrollToItem(self.panel.tracks.item(previous_count))
            self.panel.music_pages.setCurrentIndex(0)
        else:
            self.panel.filter_tracks(self.panel.search.text())
        self.panel.scan_status.setText(result.summary())
        self.panel.scan_status.setToolTip('\n'.join(result.errors) or result.summary())
        self.save()
        self.tell(result.summary())

    @Slot()
    def scan_finished(self):
        self.panel.cancel_scan.setEnabled(False)
        self.panel.add_folder_button.setEnabled(True)
        self.panel.add_files_button.setEnabled(True)

    def cancel_scan(self):
        if self.scanner and self.scanner.isRunning():
            self.scanner.requestInterruption()
            self.panel.cancel_scan.setEnabled(False)
            self.panel.scan_status.setText('正在停止扫描，保留已发现的歌曲…')

    def import_details(self):
        report = self.last_import
        if not report:
            self.tell('本次启动尚无导入记录。')
            return
        box = QMessageBox(self.panel)
        box.setWindowTitle('歌曲导入结果')
        box.setText(report.summary())
        box.setInformativeText('加密音频无法直接播放；目录链接会跳过，避免重复遍历。导入不复制或删除原文件。')
        if report.errors:
            box.setDetailedText('\n'.join(report.errors))
        box.exec()

    def relocate_track(self):
        index = self.panel.tracks.currentRow()
        if not 0 <= index < len(self.store.data['tracks']):
            self.tell('请先选择要重新定位的歌曲。')
            return
        path, _ = QFileDialog.getOpenFileName(self.panel, '重新定位歌曲文件', '',
            '音乐文件 (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma)')
        if not path:
            return
        if any(path_key(path) == path_key(p) for i, p in enumerate(self.store.data['tracks']) if i != index):
            self.tell('这个文件已经在列表中。')
            return
        if self.track_index == index:
            self.player.stop()
            self.player.setSource(QUrl())
            self.track_index = -1
        self.store.data['tracks'][index] = os.path.abspath(path)
        self.panel.refresh_tracks()
        self.save()
        self.tell('已更新文件位置。')

    def play(self, index):
        tracks = self.store.data['tracks']
        if not 0 <= index < len(tracks):
            self.tell('请先添加并选择本地歌曲。')
            return
        path = Path(tracks[index])
        if not path.is_file():
            self.panel.tracks.item(index).setText('（文件缺失）' + path.stem)
            self.tell('找不到歌曲文件，请重新导入或移除此项。')
            return
        self.set_music_source('local')
        self.track_index = index
        self.panel.tracks.setCurrentRow(index)
        self.panel.now.setText('正在载入：' + path.stem)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.player.source().isValid() and self.track_index >= 0 and self.player.error() == QMediaPlayer.NoError:
            self.player.play()
        else:
            self.play(self.panel.tracks.currentRow())

    def step(self, delta):
        tracks = self.store.data['tracks']
        if not tracks:
            self.tell('请先添加本地歌曲。')
            return
        start = self.track_index if self.track_index >= 0 else self.panel.tracks.currentRow()
        for n in range(1, len(tracks) + 1):
            index = (start + delta * n) % len(tracks)
            if Path(tracks[index]).is_file():
                self.play(index)
                return
        self.tell('列表中的文件都已缺失，请重新导入。')

    def playback_changed(self, state):
        self.sync_playing()
        if hasattr(self, 'panel'):
            playing = state == QMediaPlayer.PlayingState
            self.panel.play_button.setText('暂停' if playing else '播放')
            if 0 <= self.track_index < len(self.store.data['tracks']):
                prefix = '正在播放：' if playing else '已暂停 / 停止：'
                self.panel.now.setText(prefix + Path(self.store.data['tracks'][self.track_index]).stem)

    def media_status(self, status):
        if status != QMediaPlayer.EndOfMedia:
            return
        loop = self.store.data['loop']
        tracks = self.store.data['tracks']
        if loop == 1:
            self.player.setPosition(0)
            self.player.play()
        elif loop == 2:
            self.step(1)
        else:
            for index in range(self.track_index + 1, len(tracks)):
                if Path(tracks[index]).is_file():
                    self.play(index)
                    break

    def media_error(self, error, description):
        if error != QMediaPlayer.NoError:
            self.player.stop()
            self.tell('这首歌无法播放，请换一首。' + description[:80])

    def start_timer(self, phase):
        if self.pomo.phase != 'idle':
            self.tell('已有计时正在进行，请先结束本轮。')
            return
        self.pomo.start(phase, self.store.data[phase] * 60)
        self.animation.focus = phase == 'focus'
        self.pet.message_until = 0
        self.panel.status.setText('专注开始，一起加油。' if phase == 'focus' else '休息一下，喝口水吧。')
        self.tick()

    def pause_timer(self):
        self.pomo.toggle_pause()
        self.tick()

    def stop_timer(self):
        self.pomo.stop()
        self.animation.focus = False
        self.next_reminder = time.monotonic() + self.store.data['interval'] * 60
        self.tick()

    def timer_text(self):
        n = self.pomo.remaining()
        phase = {'focus': '专注', 'rest': '休息', 'idle': '待开始'}[self.pomo.phase]
        return f'{phase} {n // 60:02d}:{n % 60:02d}' + (' · 已暂停' if self.pomo.paused else '')

    def notify(self, text):
        self.tell(text)
        self.pet.say(text, important=True, seconds=18, priority=2)
        self.tray.showMessage('平泽唯 · 学习伙伴', text, QSystemTrayIcon.NoIcon, 10000)
        if self.store.data['sound']:
            QApplication.beep()

    def set_reminders(self, value):
        self.next_reminder = time.monotonic() + self.store.data['interval'] * 60
        self.setting('reminders', value)

    def set_interval(self, value):
        self.next_reminder = time.monotonic() + value * 60
        self.setting('interval', value)

    def tick(self):
        now = time.monotonic()
        finished = self.pomo.poll()
        if finished:
            self.animation.focus = False
            self.next_reminder = now + self.store.data['interval'] * 60
            self.notify('专注完成！休息一下吧，去「学习」开始休息。' if finished == 'focus'
                        else '休息结束啦，准备好后再开始学习吧！')
        running = self.pomo.phase != 'idle'
        self.panel.start_focus.setEnabled(not running)
        self.panel.start_rest.setEnabled(not running)
        self.panel.pause.setEnabled(running)
        self.panel.stop.setEnabled(running)
        self.panel.focus.setEnabled(not running)
        self.panel.rest.setEnabled(not running)
        self.panel.pause.setText('继续' if self.pomo.paused else '暂停')
        n = self.pomo.remaining() if running else self.store.data['focus'] * 60
        self.panel.clock.setText(f'{n // 60:02d}:{n % 60:02d}')
        self.panel.phase.setText({'idle': '准备专注', 'focus': '专注时间', 'rest': '休息时间'}[self.pomo.phase]
                                 + (' · 已暂停' if self.pomo.paused else ''))
        self.panel.action_label.setText('当前动作：' + NAMES.get(self.animation.state(), '摸头 · 开心'))
        if running:
            self.next_reminder = now + self.store.data['interval'] * 60
        elif self.store.data['reminders'] and now >= self.next_reminder:
            self.next_reminder = now + self.store.data['interval'] * 60
            self.notify('要不要一起学习一小会儿？去「学习」开启番茄钟吧。')
        if now >= self.next_random:
            self.next_random = now + random.randint(90, 180)
            if not running:
                self.pet.say(random.choice(['今天想听哪首歌？', '玉米和音乐，都很喜欢～', '累了就伸个懒腰吧。']))

    def quit(self):
        if not self.quitting:
            self.quitting = True
            self.dock.persist()
            self.dock.shutdown()
            self.tick_timer.stop()
            self.pet.animation_timer.stop()
            self.player.stop()
            self.player.setSource(QUrl())
            self.cancel_scan()
            if self.media:
                self.media.stop()
            if self.system_worker:
                self.system_worker.requestInterruption()
            self.tray.hide()
            self.panel.hide()
            self.pet.hide()
        if any(worker and worker.isRunning() for worker in (self.scanner, self.media, self.system_worker)):
            QTimer.singleShot(100, self.quit)
            return
        self.pet.close()
        self.panel.close()
        self.app.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('YuiCompanion')
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    if '--self-check' in sys.argv:
        # Exercise the frozen binary without touching ordinary user settings.
        import json
        output = ROOT / 'output'
        output.mkdir(exist_ok=True)
        live_check = '--live-check' in sys.argv
        c = Controller(app, output / 'self-check-settings.json', services=live_check)
        c.audio.setMuted(True)
        c.panel.show()
        import wave
        sample = output / 'self-check.wav'
        with wave.open(str(sample), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(b'\x00\x00' * 22050 * 3)
        c.add_tracks([sample])
        c.play(len(c.store.data['tracks']) - 1)
        edge_result = {}
        video_result = {}
        if '--video-check' in sys.argv:
            def capture_video_action(key):
                c.pet.refresh()
                image = c.pet.scaled.toImage()
                points = [QPoint(x,y) for y in range(0,image.height(),7)
                          for x in range(0,image.width(),7) if image.pixelColor(x,y).alpha()>220]
                video_result[key] = dict(frames=len(c.sprites.clips[key][0]),
                    visible=c.pet.isVisible() and bool(points) and all(c.pet.mask().contains(
                        c.pet.image_rect.topLeft()+point) for point in points))
                c.pet.grab().save(str(output / f'build-{key}.png'))
            for index,key in enumerate(c.sprites.clips):
                QTimer.singleShot(100+index*200, lambda key=key: c.set_mode(key))
                QTimer.singleShot(250+index*200, lambda key=key: capture_video_action(key))
            QTimer.singleShot(150+len(c.sprites.clips)*200, lambda: c.set_mode('listen'))
        if '--edge-check' in sys.argv:
            def collapse_test():
                c.dock.target_screen = c.pet.screen()
                c.dock.collapse('right')
            def inspect_edge():
                edge_result.update(edge_hidden=c.dock.hidden and not c.pet.isVisible(),
                                   label_visible=c.dock.label.isVisible(),
                                   label_in_screen=c.dock.area().contains(c.dock.label.geometry()),
                                   animation_stopped=not c.pet.animation_timer.isActive(),
                                   music_continues=c.player.playbackState() == QMediaPlayer.PlayingState)
                c.dock.label.grab().save(str(output / 'build-edge-label.png'))
                c.dock.restore()
            QTimer.singleShot(100, collapse_test)
            QTimer.singleShot(500, inspect_edge)
        if live_check:
            def select_cloud_test():
                c.set_music_source('cloud')
                c.set_system_audio(True)
                c.set_mode('listen')
            QTimer.singleShot(450, select_cloud_test)
        def record():
            c.pet.refresh()
            image = c.pet.scaled.toImage()
            opaque = [QPoint(x, y) for y in range(0, image.height(), 7)
                      for x in range(0, image.width(), 7) if image.pixelColor(x, y).alpha() > 220]
            result = dict(started=True, frozen=FROZEN, transparent_mask=not c.pet.mask().isEmpty(),
                          sprite_rows=len(c.sprites.frames), multimedia=bool(c.player),
                          tabs=c.panel.tabs.count(), audio_duration=c.player.duration(),
                          audio_playing=c.player.playbackState() == QMediaPlayer.PlayingState,
                          audio_error=c.player.errorString(),
                          character_visible=bool(opaque) and all(c.pet.mask().contains(
                              c.pet.image_rect.topLeft() + point) for point in opaque))
            if live_check:
                info = c.cloud_info
                result.update(cloud_connected=bool(info and info['kind'] == 'smtc'),
                              cloud_state_known=bool(info and info['playing'] is not None),
                              cloud_toggle_enabled=c.panel.cloud_play.isEnabled(),
                              system_audio_received=c.system_features['time'] > 0,
                              capture_required=bool(info and info['playing']),
                              cloud_progress_enabled=c.panel.cloud_seek.isEnabled())
                c.panel.music_pages.setCurrentIndex(1)
            if edge_result:
                result.update(edge_result, edge_restored=not c.dock.inactive and c.pet.isVisible())
            if video_result:
                result['video_actions'] = video_result
            (output / 'build-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            c.panel.grab().save(str(output / 'build-panel.png'))
            r = c.pet.geometry()
            c.pet.screen().grabWindow(0, r.x(), r.y(), r.width(), r.height()).save(
                str(output / 'build-desktop.png'))
            c.quit()
        delay=2300 if live_check else 1200
        if '--video-check' in sys.argv:
            delay=max(delay,600+len(c.sprites.clips)*200)
        QTimer.singleShot(delay, record)
        return app.exec()
    # An independent server name per installation, no global process termination.
    import hashlib
    server_name = 'yui-companion-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(400):
        socket.write(b'open')
        socket.waitForBytesWritten(400)
        return 0
    server = QLocalServer()
    if not server.listen(server_name):
        QMessageBox.warning(None, '平泽唯桌宠', '无法建立本地程序会话，请稍后重试。')
        return 1
    try:
        c = Controller(app)
    except Exception as e:
        QMessageBox.critical(None, '启动失败', str(e))
        return 1
    def incoming():
        peer = server.nextPendingConnection()
        if peer:
            c.open_panel()
            peer.disconnectFromServer()
            peer.deleteLater()
    server.newConnection.connect(incoming)
    c.open_panel()
    app.aboutToQuit.connect(c.save)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
