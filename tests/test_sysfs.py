import pytest

from charge_toggle.sysfs import PowerState, read_power_state


def test_thinkpad(tree):
    tree("thinkpad-t14s-gen4")
    state = read_power_state()
    [battery] = state.batteries
    assert battery.path.endswith("BAT0")
    assert battery.behaviours == ("auto", "inhibit-charge", "force-discharge")
    assert battery.behaviour == "auto"
    assert battery.can_pause
    assert battery.has_limit
    assert battery.watts == pytest.approx(47.748)
    assert battery.flow == pytest.approx(47.748)
    # AC, then the two USB-C ports. The rating is voltage_max x current_max,
    # not the stale 5 V x 3 A in voltage_now and current_now.
    assert [(c.online, c.watts) for c in state.chargers] == [
        (True, None),
        (True, 65.0),
        (False, None),
    ]


def test_power_from_current_and_voltage(tree):
    tree("synthetic-framework-style")
    [battery] = read_power_state().batteries
    assert battery.watts == pytest.approx(34.0)  # 2 A x 17 V


def test_peripherals_are_left_out(tree):
    tree("synthetic-peripheral")
    assert [b.path.rsplit("/", 1)[1] for b in read_power_state().batteries] == ["BAT0"]


def test_charge_limit_only(tree):
    tree("synthetic-limit-only")
    [battery] = read_power_state().batteries
    assert not battery.can_pause
    assert battery.has_limit


def test_unreadable_values(tree):
    tree("synthetic-no-control", {"BAT0": {"capacity": "?", "power_now": ""}})
    [battery] = read_power_state().batteries
    assert battery.level is None
    assert battery.watts is None
    assert battery.flow == 0.0


def test_no_power_supplies(tmp_path):
    assert read_power_state(str(tmp_path / "missing")) == PowerState()
