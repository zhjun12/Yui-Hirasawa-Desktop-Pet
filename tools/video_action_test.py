import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app import Controller,ROOT,NAMES

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
report={}
with TemporaryDirectory(dir=ROOT) as temp:
    c=Controller(app,Path(temp)/'settings.json')
    try:
        c.animation.playing=False
        assert 'expect' not in NAMES and 'expect' not in c.sprites.clips
        for key,pack in c.sprites.packs.items():
            count=len(pack.files)
            frames,fps=c.sprites.clips[key]
            assert len(frames)==count and fps>0
            assert all(pm.toImage().hasAlphaChannel() for pm in frames)
            assert any(pm.toImage()!=frames[0].toImage() for pm in frames[1:])
            assert c.sprites.frame(key,pack.duration+.001).cacheKey()==frames[0].cacheKey()
            if key=='stretch':
                from PIL import Image
                qa=json.loads((pack.folder/'qa.json').read_text(encoding='utf-8'))
                assert qa['source_head_top_min']>=8 and qa['head_checked']
                for file in pack.files:
                    image=Image.open(file)
                    x,y,right,bottom=image.getchannel('A').getbbox()
                    assert min(x,y,image.width-right,image.height-bottom)>=8
            c.set_mode(key)
            c.pet.refresh()
            assert c.animation.state()==key
            assert not c.pet.mask().isEmpty()
            c.pet.grab().save(str(ROOT/f'output/{key}-widget.png'))
            c.set_mode('listen')
            c.play_gesture(key)
            assert c.animation.state()==key
            assert abs(c.animation.until-c.animation.interaction_started-pack.manual_cycles*pack.duration)<.0001
            QTest.qWait(180)
            assert c.animation.state()==key
            c.animation.until=time.monotonic()-1
            assert c.animation.state()=='listen'
            report[key]=dict(frames=count,fps=fps,transparent=True,real_pixels_change=True,
                             loops=True,manual_interaction_restores=True)
        (ROOT/'output/video-action-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    finally:
        c.quit()
