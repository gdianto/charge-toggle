"""Render the README screenshot from the recorded ThinkPad, without a display.

usage: python scripts/screenshots.py
"""

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from charge_toggle import gui
from charge_toggle.sysfs import read_power_state

ROOT = Path(__file__).resolve().parents[1]
PAUSED = {
    "charge_behaviour": "auto [inhibit-charge] force-discharge",
    "status": "Not charging",
    "capacity": "72",
    "power_now": "0",
}

app = QApplication([])
supplies = json.loads((ROOT / "tests/fixtures/thinkpad-t14s-gen4.json").read_text())["supplies"]
supplies["BAT0"].update(PAUSED)
with tempfile.TemporaryDirectory() as tmp:
    for name, attrs in supplies.items():
        (Path(tmp) / name).mkdir()
        for attr, value in attrs.items():
            (Path(tmp) / name / attr).write_text(value + "\n")
    window = gui.Window(read=lambda: read_power_state(tmp), send=lambda *args: None)
    window.show()
    app.processEvents()
    (ROOT / "assets").mkdir(exist_ok=True)
    window.grab().save(str(ROOT / "assets/window.png"))
