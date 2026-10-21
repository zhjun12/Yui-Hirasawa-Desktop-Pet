"""Package the application without user data or diagnostic output."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / 'dist' / 'YuiCompanion'
archive = folder.parent / '平泽唯桌宠-测试版0.8.2.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as out:
    for file in sorted(folder.rglob('*')):
        relative = file.relative_to(folder)
        if file.is_file() and relative.parts[0] not in ('data', 'output', 'actions'):
            out.write(file, Path('YuiCompanion') / relative)
print(archive)
