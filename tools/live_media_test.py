"""Read actual SMTC, briefly toggle playback twice and restore initial state."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from media_bridge import MediaBridge

app = QApplication([])
worker = MediaBridge()
started = time.monotonic()
state = {'stage': 0, 'initial': None, 'restored': False, 'connected': False}

def receive(snapshot):
    cloud = next((r for r in snapshot['sessions'] if r['kind'] == 'smtc'
                  and 'cloudmusic' in r['id'].lower()), None)
    if not cloud:
        return
    if state['stage'] == 0:
        state.update(initial=cloud['playing'], connected=True, target=cloud['id'],
                     can_next=cloud['can_next'], can_previous=cloud['can_previous'],
                     can_seek=cloud['can_seek'], duration=cloud['duration'])
        if cloud['playing'] is None or not cloud['can_toggle']:
            state['error'] = 'No confirmed playback state/control'
            finish()
            return
        state['stage'] = 1
        state['requested'] = time.monotonic()
        worker.request(cloud['id'], 'toggle')
    elif state['stage'] == 1 and cloud['playing'] != state['initial']:
        state['first_change_ms'] = round((time.monotonic() - state['requested']) * 1000)
        state['stage'] = 2
        # Restore exactly the previous playback state, without changing songs.
        worker.request(cloud['id'], 'toggle')
    elif state['stage'] == 2 and cloud['playing'] == state['initial']:
        state['restored'] = True
        finish()

def finish():
    worker.stop()
    def wait():
        if worker.isRunning():
            QTimer.singleShot(50, wait)
        else:
            target = Path(__file__).resolve().parents[1] / 'output' / 'live-media-check.json'
            target.write_text(json.dumps(state, indent=2), encoding='utf-8')
            print(json.dumps(state, indent=2), flush=True)
            app.quit()
    wait()

worker.snapshot.connect(receive)
worker.feedback.connect(lambda text: print('CONTROL:', text, flush=True))
worker.start()
QTimer.singleShot(15000, finish)
app.exec()
sys.exit(0 if state['restored'] else 1)
