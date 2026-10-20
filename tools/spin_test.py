import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from app import Controller, ROOT, NAMES
from core import Store

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
temp = TemporaryDirectory(dir=ROOT)
settings = Path(temp.name) / 'settings.json'
settings.write_text(json.dumps({'mode': 'guitar'}))
c = Controller(app, settings)
report = {}
errors = []
def check():
    try:
        assert 'guitar' not in NAMES and c.animation.mode == 'spin'
        assert Store(settings).data['mode'] == 'spin'
        assert len(c.sprites.spin_frames) == 21
        for pm in c.sprites.spin_frames:
            im = pm.toImage()
            assert im.hasAlphaChannel()
            assert im.pixelColor(0, 0).alpha() == 0
        c.animation.playing = True
        c.pet.refresh()
        before = c.spin_time if hasattr(c, 'spin_time') else c.pet.spin_time
        first = c.pet.scaled.toImage()
        QTest.qWait(400)
        assert c.pet.spin_time > before
        assert first != c.pet.scaled.toImage()
        c.animation.playing = False
        QTest.qWait(3000)
        frame = c.pet.scaled.toImage()
        clock = c.pet.spin_time
        QTest.qWait(350)
        assert c.pet.spin_time - clock < .002
        assert frame == c.pet.scaled.toImage()
        c.store.data['drive'] = False
        QTest.qWait(300)
        assert c.pet.spin_time > clock + .1
        c.pet.grab().save(str(ROOT / 'output/spin-widget.png'))
        c.panel.tabs.setCurrentIndex(2)
        c.panel.show()
        c.panel.grab().save(str(ROOT / 'output/v03-panel.png'))
        report.update(migrated=True, old_action_absent=True, source_frames=21,
                      frame_fps=30, duration=.7, transparent=True,
                      advances_when_playing=True, stops_when_paused=True,
                      standalone_loop=True)
        print(json.dumps(report, indent=2), flush=True)
        (ROOT / 'output/spin-check.json').write_text(json.dumps(report, indent=2))
    except Exception:
        import traceback
        errors.append(traceback.format_exc())
        print(errors[-1], flush=True)
    finally:
        c.quit()
QTimer.singleShot(100, check)
app.exec()
assert Path(temp.name).resolve().is_relative_to(ROOT)
temp.cleanup()
sys.exit(bool(errors))
