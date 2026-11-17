from dataclasses import replace

import pytest

from charge_toggle.status import Status, describe
from charge_toggle.sysfs import read_power_state

CHARGING = Status(
    has_battery=True,
    can_pause=True,
    has_limit=True,
    paused=False,
    forced=False,
    ac=True,
    battery="Charging",
    level=72,
    flow=41.3,
    charger_w=65.0,
)
PAUSED = replace(CHARGING, paused=True, battery="Not charging", flow=0.0)
HELPING = replace(PAUSED, battery="Discharging", flow=-8.0)

ENOUGH = "65 W charger · enough on its own"

# (status, seconds the battery has been helping, battery line, charger line, note)
CASES = {
    "charging": (CHARGING, 0, "Charging at 41 W", ENOUGH, None),
    "charging, power unknown": (replace(CHARGING, flow=None), 0, "Charging", ENOUGH, None),
    "paused": (PAUSED, 0, "Paused · running on the charger", ENOUGH, None),
    "pausing": (replace(CHARGING, paused=True), 0, "Pausing…", ENOUGH, None),
    "full": (replace(CHARGING, battery="Full", flow=0.0), 0, "Full · running on the charger", ENOUGH, None),
    "firmware not charging": (replace(PAUSED, paused=False), 0, "Not charging · running on the charger", ENOUGH, None),
    "on battery": (replace(HELPING, ac=False, flow=-9.0), 0, "On battery · 9 W", "No charger", None),
    "short peak": (HELPING, 4, "Discharging at 8 W", "65 W charger", None),
    "too weak": (HELPING, 12, "Discharging at 8 W", "65 W charger · too weak on its own", None),
    "snapshot": (HELPING, None, "Discharging at 8 W", "65 W charger · too weak on its own", None),
    "noise": (replace(HELPING, flow=-0.3), 30, "Paused · running on the charger", ENOUGH, None),
    "forced discharge": (replace(HELPING, forced=True, paused=False), 30, "Discharging at 8 W", ENOUGH, None),
    "unknown rating": (replace(CHARGING, charger_w=None), 0, "Charging at 41 W", "Charger · enough on its own", None),
    "charge limit only": (replace(CHARGING, can_pause=False), 0, "Charging at 41 W", ENOUGH, "This laptop only supports a charge limit"),
    "no control": (replace(CHARGING, can_pause=False, has_limit=False), 0, "Charging at 41 W", ENOUGH, "This laptop can't pause charging"),
}  # fmt: skip


@pytest.mark.parametrize(("s", "seconds", "battery", "charger", "note"), CASES.values(), ids=CASES)
def test_describe(s, seconds, battery, charger, note):
    view = describe(s, seconds)
    assert (view.battery, view.charger, view.note) == (battery, charger, note)
    assert view.weak == charger.endswith("too weak on its own")


def test_level():
    assert describe(CHARGING).level == "72%"
    assert describe(replace(CHARGING, level=None)).level == "—"


def test_no_battery():
    view = describe(replace(CHARGING, has_battery=False, can_pause=False, level=None, flow=None))
    assert (view.level, view.battery, view.note) == ("—", "No battery", None)


def test_shortfall_is_reported():
    assert describe(HELPING, 12).shortfall == 8.0
    assert describe(PAUSED, 12).shortfall == 0.0


@pytest.mark.parametrize(
    ("fixture", "changes", "expected"),
    [
        ("thinkpad-t14s-gen4", None, dict(paused=False, ac=True, battery="Charging", level=37, charger_w=65.0)),
        ("thinkpad-t14s-gen4", {"BAT0": {"charge_behaviour": "auto [inhibit-charge] force-discharge"}}, dict(paused=True)),
        ("thinkpad-t14s-gen4", {"BAT0": {"charge_behaviour": "auto inhibit-charge [force-discharge]"}}, dict(forced=True)),
        ("synthetic-framework-style", None, dict(can_pause=True, flow=34.0, charger_w=60.0)),
        # Levels are weighted by capacity: (50 x 23 + 100 x 69) / 92 = 87.5.
        ("synthetic-dual-battery", None, dict(level=88, flow=15.0, battery="Charging")),
        ("synthetic-dual-battery", {"BAT1": {"charge_behaviour": "auto [inhibit-charge] force-discharge"}}, dict(paused=False)),
        ("synthetic-limit-only", None, dict(can_pause=False, has_limit=True)),
        ("synthetic-no-control", None, dict(can_pause=False, has_limit=False, ac=False, flow=-9.0)),
        ("synthetic-peripheral", None, dict(level=80, battery="Charging")),
    ],
)  # fmt: skip
def test_status_of(tree, fixture, changes, expected):
    tree(fixture, changes)
    s = Status.of(read_power_state())
    for field, value in expected.items():
        assert getattr(s, field) == pytest.approx(value), field
