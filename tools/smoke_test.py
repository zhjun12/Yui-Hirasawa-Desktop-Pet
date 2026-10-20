"""Real Qt integration checks; also saves review screenshots."""
import os
import sys
from pathlib import Path
import tempfile
import wave
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QPoint
from app import Controller, ROOT, STYLE

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setStyleSheet(STYLE)
temp = tempfile.TemporaryDirectory(dir=ROOT)
output = ROOT / 'output'
output.mkdir(exist_ok=True)
c = Controller(app, Path(temp.name) / 'settings.json')
c.panel.show()
c.pet.show()
errors = []


def check():
    try:
        assert not c.pet.mask().isEmpty(), 'Transparent character must have an input region'
        assert not c.pet.mask().contains(QPoint(0, c.pet.height() - 1)), 'Empty corner must pass through'
        # A nonempty mask can still be inverted. Check opaque AND transparent image pixels.
        image = c.pet.scaled.toImage()
        solid = empty = 0
        for y in range(0, image.height(), 7):
            for x in range(0, image.width(), 7):
                point = c.pet.image_rect.topLeft() + QPoint(x, y)
                alpha = image.pixelColor(x, y).alpha()
                if alpha > 220:
                    assert c.pet.mask().contains(point), 'Opaque character pixels must remain visible'
                    solid += 1
                elif alpha == 0:
                    assert not c.pet.mask().contains(point), 'Transparent sprite pixels must pass through'
                    empty += 1
        assert solid > 100 and empty > 10
        c.set_mode('listen')
        c.feed()
        assert c.animation.state() == 'eat'
        c.animation.until = 0
        assert c.animation.state() == 'listen', 'Feeding must restore fixed action'
        for index, key in enumerate(['idle', 'daydream', 'listen', 'spin', 'eat']):
            c.set_mode(key)
            c.pet.refresh()
            c.pet.grab().save(str(output / f'pet-{key}.png'))
        c.set_mode('auto')
        c.start_timer('focus')
        c.pause_timer()
        remaining = c.pomo.remaining()
        QTest.qWait(230)
        assert c.pomo.remaining() == remaining
        c.pause_timer()
        c.pomo.deadline -= c.store.data['focus'] * 60 + 1
        c.tick()
        assert c.pomo.phase == 'idle', 'Timer must finish without auto-starting next phase'
        c.panel.link_name.setText('测试歌单')
        c.panel.link_url.setText('https://music.163.com/#/playlist?id=123')
        c.panel.add_link()
        assert len(c.store.data['links']) == 1
        # A real, non-copyrighted synthetic silent WAV exercises the actual decoder.
        wav = Path(temp.name) / '音乐测试.wav'
        with wave.open(str(wav), 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(22050)
            f.writeframes(b'\x00\x00' * 22050 * 3)
        c.add_tracks([wav, wav])
        assert len(c.store.data['tracks']) == 1, 'Duplicate imports should be ignored'
        c.play(0)
        QTest.qWait(800)
        assert c.player.error() == QMediaPlayer.NoError, c.player.errorString()
        assert c.player.duration() >= 2900, 'Decoder must load actual WAV duration'
        assert c.player.playbackState() == QMediaPlayer.PlayingState, 'Actual playback should start'
        assert c.animation.playing
        c.toggle_play()
        assert c.player.playbackState() == QMediaPlayer.PausedState
        assert not c.animation.playing
        if shutil.which('ffmpeg'):
            for extension in ['mp3', 'flac', 'ogg', 'm4a', 'aac', 'wma']:
                target = wav.with_suffix('.' + extension)
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), str(target)],
                               check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                c.add_tracks([target])
                c.play(len(c.store.data['tracks']) - 1)
                QTest.qWait(600)
                assert c.player.error() == QMediaPlayer.NoError, (extension, c.player.errorString())
                assert c.player.playbackState() == QMediaPlayer.PlayingState, extension
                assert c.player.duration() >= 2500, extension
                print('PASS audio:', extension)
                c.player.pause()
        c.set_size(320)
        assert c.pet.width() == 360
        c.set_size(280)
        c.pet.move(-10000, -10000)
        c.pet.keep_visible()
        assert any(screen.availableGeometry().intersects(c.pet.geometry()) for screen in app.screens())
        c.panel.tabs.setCurrentIndex(0)
        c.panel.grab().save(str(output / 'panel-music.png'))
        c.panel.tabs.setCurrentIndex(1)
        c.panel.grab().save(str(output / 'panel-study.png'))
        c.panel.tabs.setCurrentIndex(2)
        c.panel.grab().save(str(output / 'panel-pet.png'))
        # Mouse movement must not accidentally trigger a head pat.
        c.set_mode('listen')
        c.animation.temporary = None
        c.pet.refresh()
        hit = c.pet.image_rect.center()
        start = c.pet.pos()
        QTest.mousePress(c.pet, Qt.LeftButton, pos=hit)
        QTest.mouseMove(c.pet, hit + QPoint(35, 20), delay=20)
        QTest.mouseRelease(c.pet, Qt.LeftButton, pos=hit + QPoint(35, 20))
        assert c.animation.temporary is None, 'Dragging must not trigger interaction'
        print('PASS: transparent input mask, action restoration, timer pause/completion, cloud link storage, '
              'WAV decoder/playback/pause, duplicate import, scaling, screen recovery, screenshots')
    except Exception:
        import traceback
        errors.append(traceback.format_exc())
        print(errors[-1])
    finally:
        c.quit()


QTimer.singleShot(500, check)
app.exec()
c.player.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
assert Path(temp.name).resolve().is_relative_to(ROOT)
temp.cleanup()
sys.exit(1 if errors else 0)
