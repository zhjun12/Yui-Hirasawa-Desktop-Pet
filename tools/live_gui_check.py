import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app import Controller, ROOT, STYLE

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setStyleSheet(STYLE)
c = Controller(app, ROOT / 'output/live-gui-settings.json', services=True)
c.set_music_source('cloud')
c.set_mode('listen')
c.panel.system_audio.setChecked(True)
c.panel.show()
start = time.monotonic()
report = {}
done = False

def check():
    global done
    if done:
        return
    info = c.cloud_info
    if info and info['kind'] == 'smtc' and (c.system_features['time'] > start or time.monotonic() - start > 6):
        report.update(connected=True, source=info['id'], state_known=info['playing'] is not None,
                      playing=info['playing'], progress_available=bool(info['duration']),
                      progress_disabled=not c.panel.cloud_seek.isEnabled(),
                      toggle_enabled=c.panel.cloud_play.isEnabled(),
                      system_audio_received=c.system_features['time'] > start,
                      audio_level=round(c.system_features['level'], 3))
        c.panel.tabs.setCurrentIndex(0)
        c.panel.music_pages.setCurrentIndex(1)
        c.panel.grab().save(str(ROOT / 'output/v02-live-cloud.png'))
        c.pet.say('一起听歌吧～', important=True)
        QTimer.singleShot(200, finish)
        done = True
    elif time.monotonic() - start > 12:
        report['error'] = 'No live cloud session'
        done = True
        finish()

def finish():
    r = c.pet.geometry()
    c.pet.screen().grabWindow(0, r.x(), r.y(), r.width(), r.height()).save(str(ROOT / 'output/v02-live-pet.png'))
    (ROOT / 'output/live-gui-check.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    c.quit()

timer = QTimer()
timer.timeout.connect(check)
timer.start(150)
app.exec()
sys.exit(0 if report.get('connected') and report.get('toggle_enabled') else 1)
