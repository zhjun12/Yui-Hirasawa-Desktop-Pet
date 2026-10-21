"""Read-only live check: never send a command to the user's music client."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from media_bridge import MediaBridge

root=Path(__file__).resolve().parents[1]
app=QApplication([])
bridge=MediaBridge()
result={}
def receive(snapshot):
    rows=[row for row in snapshot['sessions'] if 'cloudmusic' in row['id'].lower() or 'netease' in row['id'].lower()]
    if rows:
        row=rows[0];art=row.get('artwork')
        result.update(client_detected=snapshot.get('cloud_running'),session_kind=row['kind'],
            metadata_received=bool(row.get('title')),state_known=row.get('playing') is not None,
            timeline_available=row.get('duration',0)>0,artwork_received=bool(art),
            artwork_decodes=not QImage.fromData(art).isNull() if art else False,
            controls_enabled={key:row[key] for key in ('can_toggle','can_next','can_previous','can_seek')})
        bridge.stop()
def finish():
    bridge.stop()
    if bridge.isRunning(): QTimer.singleShot(100,finish)
    else: app.quit()
bridge.snapshot.connect(receive)
bridge.finished.connect(app.quit)
bridge.start();QTimer.singleShot(7000,finish)
app.exec()
if not result: result=dict(client_detected=False,metadata_received=False)
(root/'output/music-live-metadata-check.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
