import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QThread, QTimer
from app import Controller, ROOT

app = QApplication([])
with TemporaryDirectory(dir=ROOT) as folder:
    root = Path(folder)
    (root / '中文 日文').mkdir()
    (root / '中文 日文' / 'ふわふわ #1.mp3').write_bytes(b'not-audio')
    c = Controller(app, root / 'settings.json')
    original = c.add_tracks
    def inspect(paths):
        print('SCAN_CALLBACK_MAIN_THREAD:', QThread.currentThread() == app.thread(), flush=True)
        original(paths)
        print('IMPORTED:', len(c.store.data['tracks']), flush=True)
        QTimer.singleShot(200, c.quit)
    c.add_tracks = inspect
    QFileDialog.getExistingDirectory = lambda *args: str(root)
    c.import_folder()
    QTimer.singleShot(5000, c.quit)
    app.exec()
