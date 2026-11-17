"""Read batteries and chargers from /sys/class/power_supply. No root needed.

The interface is documented in the kernel's Documentation/ABI/testing/sysfs-class-power.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ROOT = "/sys/class/power_supply"

AUTO = "auto"
PAUSE = "inhibit-charge"
FORCE = "force-discharge"

CHARGER_TYPES = ("Mains", "USB", "Wireless")
LIMIT_FILES = ("charge_control_end_threshold", "charge_stop_threshold", "charge_types")


@dataclass(frozen=True)
class Battery:
    path: str
    status: str
    level: int | None
    watts: float | None  # size of the power flow; the status gives its direction
    capacity: int | None  # energy_full or charge_full, to weigh several batteries
    behaviours: tuple[str, ...]
    behaviour: str | None
    has_limit: bool

    @property
    def can_pause(self) -> bool:
        return PAUSE in self.behaviours

    @property
    def flow(self) -> float:
        """Watts into the battery (+) or out of it (-)."""
        if self.watts is None:
            return 0.0
        return {"Charging": self.watts, "Discharging": -self.watts}.get(self.status, 0.0)


@dataclass(frozen=True)
class Charger:
    online: bool
    watts: float | None  # the most it advertises, if the driver says


@dataclass(frozen=True)
class PowerState:
    batteries: tuple[Battery, ...] = ()
    chargers: tuple[Charger, ...] = ()


def _text(path: str, name: str) -> str | None:
    try:
        with open(os.path.join(path, name), encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def _number(path: str, name: str) -> int | None:
    try:
        return int(_text(path, name))
    except (TypeError, ValueError):
        return None


def _battery(path: str) -> Battery:
    tokens = (_text(path, "charge_behaviour") or "").split()  # e.g. "[auto] inhibit-charge"
    power = _number(path, "power_now")  # µW
    current, voltage = _number(path, "current_now"), _number(path, "voltage_now")  # µA, µV
    if power is not None:
        watts = abs(power) / 1e6
    elif current is not None and voltage is not None:
        watts = abs(current) * voltage / 1e12
    else:
        watts = None
    return Battery(
        path=path,
        status=_text(path, "status") or "Unknown",
        level=_number(path, "capacity"),
        watts=watts,
        capacity=_number(path, "energy_full") or _number(path, "charge_full"),
        behaviours=tuple(token.strip("[]") for token in tokens),
        behaviour=next((token.strip("[]") for token in tokens if token.startswith("[")), None),
        has_limit=any(os.path.exists(os.path.join(path, name)) for name in LIMIT_FILES),
    )


def _charger(path: str) -> Charger:
    # What a USB-C charger advertises. voltage_now and current_now are not used:
    # some firmware keeps reporting the initial 5 V contract there.
    volts, amps = _number(path, "voltage_max"), _number(path, "current_max")  # µV, µA
    return Charger(
        online=_text(path, "online") == "1",
        watts=volts * amps / 1e12 if volts and amps else None,
    )


def read_power_state(root: str | None = None) -> PowerState:
    """Every system battery and charger. Peripherals, like a mouse, are left out."""
    root = root or ROOT
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    batteries, chargers = [], []
    for name in names:
        path = os.path.join(root, name)
        if _text(path, "scope") == "Device":
            continue
        kind = _text(path, "type")
        if kind == "Battery":
            batteries.append(_battery(path))
        elif kind in CHARGER_TYPES:
            chargers.append(_charger(path))
    return PowerState(tuple(batteries), tuple(chargers))
