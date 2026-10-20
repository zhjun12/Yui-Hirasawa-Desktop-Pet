import json
from pathlib import Path
import sys
import tempfile
import time
import wave
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer, QThread, QEvent, QCoreApplication
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app import Controller, ROOT, STYLE
from core import Store

app = QApplication([])
app.setStyleSheet(STYLE)
app.setQuitOnLastWindowClosed(False)
temp = tempfile.TemporaryDirectory(dir=ROOT)
folder = Path(temp.name)
library = folder / '中文 日本語 # 音乐'
(library / '子目录').mkdir(parents=True)
for i in range(720):
    path = (library if i % 2 else library / '子目录') / f'{i:04d} 放课后.MP3'
    path.write_bytes(b'nonempty-import-fixture')
(library / 'empty.wav').touch()
(library / '加密歌曲.ncm').write_bytes(b'ncm')
(library / 'readme.txt').write_text('skip')
c = Controller(app, folder / 'settings.json')
c.audio.setMuted(True)
c.panel.show()
errors = []
report = {}

def wait_until(test, seconds=15):
    deadline = time.monotonic() + seconds
    while not test() and time.monotonic() < deadline:
        QTest.qWait(20)
        # Yield Python's GIL as well as processing Qt events for Python workers.
        time.sleep(.005)
    assert test(), 'Operation timed out'

def check():
    try:
        beats = [0]
        heartbeat = QTimer()
        heartbeat.timeout.connect(lambda: beats.__setitem__(0, beats[0] + 1))
        heartbeat.start(10)
        c.panel.search.setText('no matches')
        assert c.start_import([library])
        assert not c.start_import([library])
        wait_until(lambda: c.last_import is not None)
        wait_until(lambda: not c.scanner.isRunning())
        assert len(c.store.data['tracks']) == 720
        assert c.panel.tracks.count() == 720, 'Worker result must enter actual widget'
        assert c.panel.search.text() == '', 'New tracks should not remain hidden by old search'
        assert '720' in c.panel.library_count.text()
        assert len(Store(folder / 'settings.json').data['tracks']) == 720
        assert QThread.currentThread() == app.thread()
        report['imported_widget_and_disk'] = 720
        report['empty_files_rejected'] = c.last_import.failed == 1
        report['encrypted_reported'] = c.last_import.encrypted == 1
        first = c.last_import
        c.start_import([library])
        wait_until(lambda: c.last_import is not first)
        assert c.last_import.duplicates == 720
        assert len(c.store.data['tracks']) == 720
        report['repeat_import_duplicates'] = 720
        c.panel.filter_tracks('0001')
        assert sum(not c.panel.tracks.item(i).isHidden() for i in range(720)) == 1
        c.panel.filter_tracks('')
        report['search'] = True
        # Synthetic PCM is decoded while muted; received features must be nonzero.
        sample = folder / '波形测试.wav'
        pcm = (.2 * np.sin(np.arange(22050 * 3) * (2 * np.pi * 440 / 22050)) * 32767).astype(np.int16)
        with wave.open(str(sample), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(pcm.tobytes())
        c.add_tracks([sample])
        c.play(720)
        wait_until(lambda: c.local_features['level'] > .1)
        report['decoded_audio_feature_level'] = round(c.local_features['level'], 3)
        c.set_mode('listen')
        c.pet.refresh()
        frame1 = c.pet.scaled.toImage()
        QTest.qWait(350)
        frame2 = c.pet.scaled.toImage()
        assert frame1 != frame2, 'Continuous movement must change real pixels'
        report['continuous_pixels_change'] = True
        c.set_mode('quiet')
        assert c.animation.state() == 'idle'
        c.set_mode('listen')
        c.feed()
        c.animation.until = 0
        assert c.animation.state() == 'listen'
        c.panel.music_pages.setCurrentIndex(0)
        c.panel.grab().save(str(ROOT / 'output/v02-local.png'))
        c.panel.music_pages.setCurrentIndex(1)
        c.panel.grab().save(str(ROOT / 'output/v02-cloud.png'))
        c.panel.tabs.setCurrentIndex(2)
        c.panel.grab().save(str(ROOT / 'output/v02-pet.png'))
        report['gui_heartbeat_events'] = beats[0]
        assert beats[0] > 0
        heartbeat.stop()
        print(json.dumps(report, indent=2), flush=True)
        (ROOT / 'output/v02-integration.json').write_text(json.dumps(report, indent=2))
    except Exception:
        import traceback
        errors.append(traceback.format_exc())
        print(errors[-1], flush=True)
    finally:
        c.quit()

QTimer.singleShot(500, check)
app.exec()
c.player.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
assert folder.resolve().is_relative_to(ROOT)
temp.cleanup()
sys.exit(bool(errors))
