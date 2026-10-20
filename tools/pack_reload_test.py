"""Prove a new ID adds UI, timing and persistence without application edits."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from PIL import Image,ImageDraw
import app as pet_app
from app import Controller,ROOT,NAMES

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
with TemporaryDirectory(dir=ROOT) as temp:
    root=Path(temp)
    c=Controller(app,root/'settings.json')
    try:
        with patch.object(pet_app,'ROOT',root):
            folder=root/'actions/wave_demo'
            folder.mkdir(parents=True)
            for i in range(2):
                im=Image.new('RGBA',(96,96),(0,0,0,0))
                ImageDraw.Draw(im).ellipse((20+i*5,20,70+i*5,80),fill='#926a40')
                im.save(folder/f'{i:03d}.png')
            manifest=dict(id='wave_demo',name='热加载测试',button_label='测试挥手',frame_count=2,
                          fps=10,durations_ms=[80,140],playback=dict(weights=dict(daily=10),
                          cycles=[1,2],cooldown_seconds=30,manual_cycles=2))
            (folder/'motion.json').write_text(json.dumps(manifest),encoding='utf-8')
            c.reload_action_packs()
            assert 'wave_demo' in c.sprites.clips and 'wave_demo' in NAMES
            assert any(button.text()=='测试挥手' for button in c.panel.findChildren(QPushButton))
            assert abs(c.animation.loop_seconds['wave_demo']-.22)<.0001
            c.set_mode('wave_demo')
            c.pet.refresh()
            assert c.animation.state()=='wave_demo' and not c.pet.mask().isEmpty()
            c.play_gesture('wave_demo')
            assert abs(c.animation.until-c.animation.interaction_started-.44)<.0001
            QTest.qWait(50)
            broken=root/'actions/roll'
            broken.mkdir()
            original=pet_app.ASSETS/'actions/roll/000.png'
            (broken/'000.png').write_bytes(original.read_bytes()[:24])
            (broken/'motion.json').write_text(json.dumps(dict(id='roll',name='损坏的覆盖包',
                frame_count=1,fps=10)),encoding='utf-8')
            c.reload_action_packs()
            assert c.sprites.packs['roll'].folder==(pet_app.ASSETS/'actions/roll').resolve()
            assert c.action_errors
            folder.rename(root/'actions/.wave_removed')
            c.reload_action_packs()
            assert 'wave_demo' not in c.sprites.clips and 'wave_demo' not in NAMES
            assert c.animation.mode=='auto'
            QTest.qWait(50)
        report=dict(new_id_loaded=True,button_created=True,frame_timing_loaded=True,
                    automatic_rule_loaded=True,removed_pack_falls_back=True)
        (ROOT/'output/pack-reload-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    finally:
        c.quit()
