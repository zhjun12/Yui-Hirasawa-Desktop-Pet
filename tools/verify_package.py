"""Check archive integrity and exclude private state from distribution."""
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
archive = root / 'dist/平泽唯桌宠-测试版0.8.2.zip'
with zipfile.ZipFile(archive) as package:
    names = package.namelist()
    assert package.testzip() is None, 'Archive checksum failure'
    assert not any(name.startswith(('YuiCompanion/data/', 'YuiCompanion/output/','YuiCompanion/actions/'))
                   or name.endswith('/settings.json') for name in names)
    assert not any(name.endswith('/yui-guitar.png') for name in names)
    frames = [name for name in names
              if '/assets/arm-spin/' in name and name.endswith('.png')]
    assert len(frames) == 21
    assert len([name for name in names if '/assets/corn/' in name and name.endswith('.png')]) == 4
    assert 'YuiCompanion/_internal/assets/edge-label.png' in names
    assert not any('/assets/actions/expect/' in name for name in names)
    for action,count in [('roll',32),('stretch',55),('sing_guitar',67)]:
        assert len([name for name in names if f'/assets/actions/{action}/' in name
                    and Path(name).suffix=='.png' and Path(name).stem.isdigit()])==count
        manifest=json.loads(package.read(f'YuiCompanion/_internal/assets/actions/{action}/motion.json'))
        assert manifest['playback']['weights']['music']==1
    assert json.loads(package.read('YuiCompanion/_internal/assets/actions/roll/motion.json'))['source']=='154818931-1-208.mp4'
    policy=json.loads(package.read('YuiCompanion/_internal/assets/music-policy.json'))
    assert {key:rule['share'] for key,rule in policy['actions'].items()}==dict(
        sing_guitar=45,spin=45,listen=8,roll=1,stretch=1)
    assert policy['weak']['actions']['listen']['share']==80
report = dict(archive_valid=True, user_data_excluded=True, old_guitar_excluded=True,
              source_frames=len(frames), archive_bytes=archive.stat().st_size)
(root / 'output/v082-package-check.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
