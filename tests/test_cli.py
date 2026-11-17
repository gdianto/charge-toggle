import sys

import pytest

import charge_toggle
from charge_toggle import cli, control
from charge_toggle.control import ControlError

PAUSED = {
    "charge_behaviour": "auto [inhibit-charge] force-discharge",
    "status": "Not charging",
    "power_now": "0",
}
CHARGING = {"charge_behaviour": "[auto] inhibit-charge force-discharge", "status": "Charging"}
NO_CHARGER = {"AC": {"online": "0"}, "ucsi-source-psy-USBC000:001": {"online": "0"}, "BAT0": {"status": "Discharging"}}  # fmt: skip


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(control, "elevate", lambda interactive: ["pkexec"])


def run(capsys, *args):
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out.splitlines(), err.strip()


def firmware(root, calls, **after):
    """A stand-in for control.write that answers the way the firmware does."""

    def write(value, paths, elevation):
        calls.append(value)
        for attr, text in after.items():
            (root / "BAT0" / attr).write_text(text + "\n")

    return write


def test_status(tree, capsys):
    tree("thinkpad-t14s-gen4")
    assert run(capsys, "status") == (
        0,
        ["37% · Charging at 48 W", "65 W charger · enough on its own"],
        "",
    )


def test_status_explains_a_limit_only_laptop(tree, capsys):
    tree("synthetic-limit-only")
    _, out, _ = run(capsys, "status")
    assert out[-1] == "This laptop only supports a charge limit"


def test_pause(tree, capsys, monkeypatch):
    root, calls = tree("thinkpad-t14s-gen4"), []
    monkeypatch.setattr(control, "write", firmware(root, calls, **PAUSED))
    assert run(capsys, "pause") == (
        0,
        ["37% · Paused · running on the charger", "65 W charger · enough on its own"],
        "",
    )
    assert calls == ["inhibit-charge"]


def test_resume(tree, capsys, monkeypatch):
    root, calls = tree("thinkpad-t14s-gen4", {"BAT0": PAUSED}), []
    monkeypatch.setattr(control, "write", firmware(root, calls, **CHARGING, power_now="40000000"))
    code, out, _ = run(capsys, "resume")
    assert (code, out[0], calls) == (0, "37% · Charging at 40 W", ["auto"])


def test_already_paused(tree, capsys, monkeypatch):
    tree("thinkpad-t14s-gen4", {"BAT0": PAUSED})
    monkeypatch.setattr(control, "write", lambda *args: pytest.fail("nothing to change"))
    code, out, _ = run(capsys, "pause")
    assert (code, out[0]) == (0, "37% · Paused · running on the charger")


def test_pause_needs_a_charger(tree, capsys):
    tree("thinkpad-t14s-gen4", NO_CHARGER)
    assert run(capsys, "pause") == (1, [], "No charger connected.")


def test_pause_on_a_laptop_that_cannot(tree, capsys):
    tree("synthetic-limit-only")
    assert run(capsys, "pause") == (1, [], "This laptop only supports a charge limit")


def test_cancelled(tree, capsys, monkeypatch):
    tree("thinkpad-t14s-gen4")

    def cancelled(*args):
        raise ControlError("Cancelled.")

    monkeypatch.setattr(control, "write", cancelled)
    assert run(capsys, "pause") == (1, [], "Cancelled.")


def test_menu_entry(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert run(capsys, "install-desktop")[1][0] == "Added Charge Toggle to the application menu."
    assert run(capsys, "uninstall-desktop")[1] == ["Removed it from the application menu."]
    assert run(capsys, "uninstall-desktop")[1] == ["Nothing to remove."]


def test_window_without_pyside6(capsys, monkeypatch):
    # Block PySide6, including submodules other tests may already have imported.
    for name in [n for n in sys.modules if n.split(".")[0] == "PySide6"] + ["PySide6"]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, "charge_toggle.gui", raising=False)
    monkeypatch.delattr(charge_toggle, "gui", raising=False)
    code, _, err = run(capsys)
    assert code == 2
    assert err.startswith("The window needs PySide6")


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"charge-toggle {charge_toggle.__version__}"
