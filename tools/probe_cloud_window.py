import json
from pywinauto import Desktop
from pywinauto.timings import Timings
Timings.window_find_timeout = 3
rows = []
for window in Desktop(backend='uia').windows():
    if window.process_id() != 13736:
        continue
    rows.append(dict(title=window.window_text(), class_name=window.class_name()))
    try:
        for item in window.descendants(control_type='Button')[:150]:
            rows.append(dict(button=item.window_text(), automation_id=item.automation_id()))
    except Exception as exc:
        rows.append(dict(error=str(exc)))
print(json.dumps(rows, ensure_ascii=False, indent=2))
