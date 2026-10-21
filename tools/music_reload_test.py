"""Check policy reload and bundled singing with isolated UI settings."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
import app as pet_app

application=QApplication([])
application.setQuitOnLastWindowClosed(False)
with TemporaryDirectory(dir=pet_app.ROOT) as temp:
    root=Path(temp)
    with patch.object(pet_app,'ROOT',root):
        c=pet_app.Controller(application,root/'settings.json',services=False)
        try:
            assert not c.action_errors,c.action_errors
            assert len(c.sprites.clips['sing_guitar'][0])==67
            assert c.animation.music_policy['actions']['sing_guitar']['share']==45
            c.reload_action_packs()
            assert not c.action_errors,c.action_errors
            c.set_mode('sing_guitar')
            c.pet.refresh()
            assert c.animation.state()=='sing_guitar' and not c.pet.mask().isEmpty()
            policy=json.loads((pet_app.ASSETS/'music-policy.json').read_text())
            policy['actions']['sing_guitar']['share']=40
            override=root/'music-policy.json'
            override.write_text(json.dumps(policy),encoding='utf-8')
            c.reload_action_packs()
            assert c.animation.music_policy['actions']['sing_guitar']['share']==40
            override.write_text('{broken',encoding='utf-8')
            c.reload_action_packs()
            assert c.action_errors and c.animation.music_policy is None
            override.unlink()
            c.reload_action_packs()
            assert not c.action_errors and c.animation.music_policy['actions']['sing_guitar']['share']==45
            assert c.animation.music_policy['weak']['actions']['listen']['share']==80
            report=dict(singing_frames=67,singing_visible=True,reload_ok=True,
                        policy_override_ok=True,invalid_policy_reported=True,recovery_ok=True)
            (pet_app.ASSETS.parent/'output/music-reload-check.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report),flush=True)
        finally:
            c.quit()
