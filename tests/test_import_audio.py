import math
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QCoreApplication

from library import LibraryScanner, path_key
from audio_motion import AudioFeatures, MotionEnvelope

ROOT = Path(__file__).resolve().parents[1]
_application = QCoreApplication.instance() or QCoreApplication([])


class ImportTests(unittest.TestCase):
    def test_nested_unicode_duplicates_encrypted_empty_and_error(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            sub = root / '中文 日本語 # 专辑'
            sub.mkdir()
            bad = root / 'cannot-read'
            bad.mkdir()
            music = sub / 'ふわふわ時間.MP3'
            music.write_bytes(b'mock-audio')
            (sub / 'second.flac').write_bytes(b'mock-audio')
            (sub / 'encrypted.ncm').write_bytes(b'ncm')
            (sub / 'empty.wav').write_bytes(b'')
            (sub / 'readme.txt').write_text('not music')
            native = os.scandir
            def fail_one(path):
                if Path(path) == bad:
                    raise PermissionError('simulated denied')
                return native(path)
            worker = LibraryScanner([root], [music], scan_dir=fail_one)
            results = []
            worker.result_ready.connect(results.append)
            worker.run()
            result = results[0]
            self.assertEqual(result.duplicates, 1)
            self.assertEqual(result.encrypted, 1)
            self.assertEqual(result.failed, 2)
            self.assertEqual(result.paths, [str(sub / 'second.flac')])
            self.assertEqual(len(result.errors), 2)

    def test_cancellation_stops_and_keeps_partial_results(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            for index in range(150):
                (root / f'{index:04d}.mp3').write_bytes(b'mock')
            worker = LibraryScanner([root])
            results = []
            worker.result_ready.connect(results.append)
            original = LibraryScanner._file
            def cancel_at(path, seen, result):
                original(path, seen, result)
                if len(result.paths) == 10:
                    worker.requestInterruption()
            # Interruption requests apply only while a QThread is running.
            worker._file = cancel_at
            worker.start()
            deadline = time.monotonic() + 3
            while not results and time.monotonic() < deadline:
                _application.processEvents()
                time.sleep(.005)
            worker.wait(1000)
            _application.processEvents()
            self.assertTrue(results[0].cancelled)
            self.assertEqual(len(results[0].paths), 10)

    def test_normalization(self):
        self.assertEqual(path_key('E:/Music/a/../Song.MP3'), path_key('e:/music/song.mp3'))


class AudioTests(unittest.TestCase):
    def test_silence_tone_decay_and_nonfinite(self):
        now = [1.0]
        features = AudioFeatures(lambda: now[0])
        self.assertEqual(features.feed(np.zeros(1024))['level'], 0)
        sine = .4 * np.sin(np.arange(1024) * .1)
        for _ in range(20):
            now[0] += .025
            value = features.feed(sine)
        self.assertGreater(value['level'], .5)
        for _ in range(90):
            now[0] += .025
            value = features.feed(np.zeros(1024))
        self.assertLess(value['level'], .02)
        now[0] += .025
        self.assertTrue(math.isfinite(features.feed([np.nan, np.inf, -np.inf])['level']))

    def test_pause_motion_decays_without_phase_jump(self):
        envelope = MotionEnvelope()
        now = envelope.last
        for _ in range(60):
            now += 1 / 30
            envelope.update(now, True, .7)
        before = envelope.phase
        self.assertGreater(envelope.level, .6)
        for _ in range(90):
            now += 1 / 30
            envelope.update(now, False, 0)
        self.assertLess(envelope.level, .005)
        self.assertGreaterEqual(envelope.phase, before)


if __name__ == '__main__':
    unittest.main()
