import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QTimer
from audio_motion import SystemAudio

app = QCoreApplication([])
worker = SystemAudio()
stats = {'buffers': 0, 'max_level': 0.0, 'onsets': 0, 'source': 'system-output-loopback'}
def receive(data):
    stats['buffers'] += 1
    stats['max_level'] = max(stats['max_level'], data['level'])
    stats['onsets'] += int(data['onset'])
    if stats['buffers'] >= 80:
        worker.requestInterruption()
worker.features.connect(receive)
worker.status.connect(lambda text: print(text, flush=True))
def done():
    print(json.dumps(stats, indent=2), flush=True)
    (Path(__file__).resolve().parents[1] / 'output/live-audio-check.json').write_text(json.dumps(stats, indent=2))
    app.quit()
worker.finished.connect(done)
worker.start()
QTimer.singleShot(8000, worker.requestInterruption)
app.exec()
sys.exit(0 if stats['buffers'] > 0 else 1)
