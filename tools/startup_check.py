"""Exercise the real entrypoint, including local single-instance server."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as target
from PySide6.QtCore import QTimer

Original = target.Controller


class CheckedController(Original):
    def __init__(self, application):
        output = target.ROOT / 'output'
        output.mkdir(exist_ok=True)
        super().__init__(application, output / 'startup-check-settings.json')
        def record():
            report = dict(entrypoint=True, local_server=True, visible=self.pet.isVisible(),
                          panel=self.panel.isVisible())
            (output / 'startup-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            self.quit()
        QTimer.singleShot(1000, record)


target.Controller = CheckedController
sys.exit(target.main())
