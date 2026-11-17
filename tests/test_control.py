import subprocess

import pytest

from charge_toggle import control
from charge_toggle.control import ControlError
from charge_toggle.sysfs import read_power_state

BEHAVIOUR = "/sys/class/power_supply/BAT0/charge_behaviour"


def test_targets(tree):
    root = tree("synthetic-dual-battery")
    assert control.targets(read_power_state()) == [
        str(root / "BAT0" / "charge_behaviour"),
        str(root / "BAT1" / "charge_behaviour"),
    ]


def test_no_targets(tree):
    tree("synthetic-limit-only")
    with pytest.raises(ControlError, match="can't pause"):
        control.targets(read_power_state())


@pytest.mark.parametrize("value", ["force-discharge", "auto; rm -rf /", ""])
def test_only_two_values(value):
    with pytest.raises(ControlError, match="Refusing to write"):
        control.command(value, [BEHAVIOUR], [])


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "BAT0/charge_behaviour", "/sys/class/power_supply/BAT0/status"]
)
def test_only_charge_behaviour_files(path):
    with pytest.raises(ControlError, match="Refusing to write to"):
        control.command("auto", [path], [])


def test_command(monkeypatch):
    monkeypatch.setattr(control.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert control.command("inhibit-charge", [BEHAVIOUR], ["/usr/bin/pkexec"]) == [
        "/usr/bin/pkexec",
        "/usr/bin/tee",
        BEHAVIOUR,
    ]


@pytest.mark.parametrize(
    ("env", "interactive", "installed", "expected"),
    [
        ({"DISPLAY": ":0"}, True, ("pkexec", "sudo"), "pkexec"),
        ({"WAYLAND_DISPLAY": "wayland-0"}, False, ("pkexec", "sudo"), "pkexec"),
        ({}, True, ("pkexec", "sudo"), "sudo"),
        ({}, False, ("pkexec", "sudo"), "pkexec"),
        ({"DISPLAY": ":0"}, True, ("sudo",), "sudo"),
    ],
)
def test_elevate(env, interactive, installed, expected):
    which = lambda name: name if name in installed else None  # noqa: E731
    assert control.elevate(interactive, env, which) == [expected]


@pytest.mark.parametrize(("interactive", "installed"), [(False, ("sudo",)), (True, ())])
def test_cannot_elevate(interactive, installed):
    which = lambda name: name if name in installed else None  # noqa: E731
    with pytest.raises(ControlError, match="needs root"):
        control.elevate(interactive, {}, which)


@pytest.mark.parametrize(
    ("code", "err", "message"),
    [
        (126, "", "Cancelled."),
        (127, "", "Not authorized."),
        (1, "tee: x: Invalid argument\n", "tee: x: Invalid argument"),
        (1, "", "Failed with exit code 1."),
    ],
)
def test_failure(code, err, message):
    assert control.failure(code, err) == message


def test_value_goes_through_standard_input():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs["input"]))
        return subprocess.CompletedProcess(args, 0, stderr="")

    control.write("inhibit-charge", [BEHAVIOUR], ["pkexec"], run=run)
    [(args, given)] = calls
    assert "inhibit-charge" not in args
    assert given == "inhibit-charge"


def test_write_reports_failure():
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 126, stderr="")

    with pytest.raises(ControlError, match="Cancelled"):
        control.write("auto", [BEHAVIOUR], ["pkexec"], run=run)


def test_real_tee(tmp_path):
    files = []
    for name in ("BAT0", "BAT1"):
        (tmp_path / name).mkdir()
        files.append(tmp_path / name / "charge_behaviour")
    control.write("inhibit-charge", [str(f) for f in files], elevation=[])  # no root needed here
    assert all(f.read_text() == "inhibit-charge" for f in files)
