import os

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from charge_toggle import gui, status
from charge_toggle.sysfs import read_power_state

THINKPAD = "thinkpad-t14s-gen4"
HELPING = {"charge_behaviour": "auto [inhibit-charge] force-discharge", "status": "Discharging", "power_now": "8000000"}  # fmt: skip


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def window(notes=None):
    sent = notes if notes is not None else []
    return gui.Window(read=read_power_state, send=lambda summary, body: sent.append(summary))


def test_charging(tree):
    tree(THINKPAD)
    w = window()
    assert (w.level.text(), w.battery.text(), w.charger.text()) == (
        "37%",
        "Charging at 48 W",
        "65 W charger · enough on its own",
    )
    assert w.switch.isChecked()
    assert w.switch.isEnabled()
    assert w.note.isHidden()


def test_paused(tree):
    tree(THINKPAD, {"BAT0": {"charge_behaviour": "auto [inhibit-charge] force-discharge"}})
    assert not window().switch.isChecked()


def test_weak_charger(tree, monkeypatch):
    monkeypatch.setattr(status, "SUSTAIN_S", 0)
    tree(THINKPAD, {"BAT0": HELPING})
    notes = []
    w = window(notes)
    w.refresh()
    assert w.charger.text() == "65 W charger · too weak on its own"
    assert gui.AMBER in w.charger.styleSheet()
    assert notes == ["Charger too weak"]  # once, not on every refresh


def test_no_charger(tree):
    unplugged = {"online": "0"}
    tree(
        THINKPAD,
        {
            "AC": unplugged,
            "ucsi-source-psy-USBC000:001": unplugged,
            "BAT0": {"status": "Discharging"},
        },
    )
    w = window()
    assert not w.switch.isEnabled()
    assert w.switch.toolTip() == "Connect the charger first"


def test_laptop_that_cannot_pause(tree):
    tree("synthetic-limit-only")
    w = window()
    assert not w.switch.isEnabled()
    assert w.note.text() == "This laptop only supports a charge limit"
    assert not w.note.isHidden()


@pytest.mark.parametrize(("script", "message"), [("exit 0", None), ("exit 126", None), ("exit 1", "Failed with exit code 1.")])  # fmt: skip
def test_flipping_the_switch(tree, monkeypatch, script, message):
    root = tree(THINKPAD)
    calls, shown = [], []
    monkeypatch.setattr(gui.control, "elevate", lambda interactive: [])

    def command(value, paths, elevation):
        calls.append((value, paths))
        return ["sh", "-c", f"cat > /dev/null; {script}"]

    monkeypatch.setattr(gui.control, "command", command)
    monkeypatch.setattr(gui.QMessageBox, "warning", lambda parent, title, text: shown.append(text))
    w = window()
    w.switch.click()
    assert not w.switch.isEnabled()  # while the password dialog is open
    assert w.process.waitForFinished(5000)
    assert w.process is None
    assert calls == [("inhibit-charge", [str(root / "BAT0" / "charge_behaviour")])]
    assert shown == ([message] if message else [])
    assert w.switch.isChecked()  # the fake tree didn't change, so the switch shows the truth
