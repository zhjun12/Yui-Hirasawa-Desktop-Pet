"""Verify user GIF timing, visible foreground and interaction restoration."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from app import Controller, NAMES, ROOT

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
with TemporaryDirectory(dir=ROOT) as temp:
    c = Controller(app, Path(temp)/'settings.json')
    try:
        frames = c.sprites.corn_frames
        assert len(frames) == 4
        assert c.sprites.corn_durations == [80]*4
        for index, frame in enumerate(frames):
            assert c.sprites.frame('eat', index*.08+.001).cacheKey() == frame.cacheKey()
            image = frame.toImage()
            assert image.pixelColor(0,0).alpha() == 0
            assert image.pixelColor(270,210).alpha() > 220
        assert c.sprites.frame('eat',.321).cacheKey() == frames[0].cacheKey()
        assert '蛋糕' not in NAMES['eat']
        assert not any('蛋糕' in b.text() for b in c.panel.findChildren(QPushButton))
        c.set_mode('listen')
        c.animation.playing = False
        c.feed()
        c.pet.refresh()
        assert c.animation.state() == 'eat'
        assert c.pet.eat_time < .04
        initial = c.pet.scaled.toImage()
        QTest.qWait(110)
        c.pet.refresh()
        assert initial != c.pet.scaled.toImage(), 'Feeding animates without music'
        c.feed()
        c.pet.refresh()
        assert c.pet.eat_time < .04, 'Repeated interaction restarts the GIF'
        c.pet.grab().save(str(ROOT/'output/corn-widget.png'))
        c.animation.until = time.monotonic()-1
        c.pet.refresh()
        assert c.animation.state() == 'listen'
        c.set_mode('eat')
        assert c.animation.state() == 'eat'
        report = dict(original_frames=4, durations_ms=[80]*4, transparent=True,
                      animates_without_music=True, restarts=True,
                      restores_previous_action=True, old_fixed_mode_compatible=True,
                      cake_buttons_removed=True)
        (ROOT/'output/corn-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        c.quit()
