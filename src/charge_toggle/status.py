"""What to show: the battery level, a battery line, a charger line and, rarely, a note."""

from __future__ import annotations

from dataclasses import dataclass

from charge_toggle.sysfs import FORCE, PAUSE, Battery, PowerState

NOISE_W = 0.5  # battery discharge on AC below this is measurement noise
SUSTAIN_S = 10  # a shortfall must last this long; CPU boost peaks are shorter


@dataclass(frozen=True)
class Status:
    """The laptop as a whole, across all its batteries and chargers."""

    has_battery: bool
    can_pause: bool
    has_limit: bool
    paused: bool
    forced: bool  # force-discharge was set by another tool
    ac: bool
    battery: str
    level: int | None
    flow: float | None  # watts into the batteries (+) or out of them (-)
    charger_w: float | None

    @classmethod
    def of(cls, state: PowerState) -> Status:
        batteries = state.batteries
        pausable = [b for b in batteries if b.can_pause]
        measured = [b for b in batteries if b.watts is not None]
        statuses = [b.status for b in batteries]
        ratings = [c.watts for c in state.chargers if c.online and c.watts]
        return cls(
            has_battery=bool(batteries),
            can_pause=bool(pausable),
            has_limit=any(b.has_limit for b in batteries),
            paused=bool(pausable) and all(b.behaviour == PAUSE for b in pausable),
            forced=any(b.behaviour == FORCE for b in batteries),
            ac=any(c.online for c in state.chargers) or "Charging" in statuses,
            battery=_combined(statuses),
            level=_level(batteries),
            flow=sum(b.flow for b in measured) if measured else None,
            charger_w=max(ratings, default=None),
        )


def _combined(statuses: list[str]) -> str:
    for status in ("Charging", "Discharging"):
        if status in statuses:
            return status
    if statuses and all(s == "Full" for s in statuses):
        return "Full"
    if "Not charging" in statuses:
        return "Not charging"
    return statuses[0] if statuses else "Unknown"


def _level(batteries: tuple[Battery, ...]) -> int | None:
    known = [b for b in batteries if b.level is not None]
    if not known:
        return None
    if all(b.capacity for b in known):
        return round(sum(b.level * b.capacity for b in known) / sum(b.capacity for b in known))
    return round(sum(b.level for b in known) / len(known))


@dataclass(frozen=True)
class View:
    level: str
    battery: str
    charger: str
    note: str | None
    weak: bool  # the charger can't power the laptop on its own
    shortfall: float  # watts the battery supplies while plugged in


def shortfall(s: Status) -> float:
    """Watts the battery supplies while the charger is connected, if any."""
    if s.ac and not s.forced and s.flow is not None and -s.flow >= NOISE_W:
        return -s.flow
    return 0.0


def describe(s: Status, shortfall_s: float | None = None) -> View:
    """shortfall_s is how long the battery has been helping; None means a single snapshot."""
    deficit = shortfall(s)
    weak = bool(deficit) and (shortfall_s is None or shortfall_s >= SUSTAIN_S)
    watts = abs(s.flow) if s.flow else 0.0

    if not s.has_battery:
        battery = "No battery"
    elif not s.ac:
        battery = f"On battery · {watts:.0f} W" if watts else "On battery"
    elif s.battery == "Discharging" and watts >= NOISE_W:
        battery = f"Discharging at {watts:.0f} W"
    elif s.battery == "Charging":
        battery = "Pausing…" if s.paused else f"Charging at {watts:.0f} W" if watts else "Charging"
    elif s.paused:
        battery = "Paused · running on the charger"
    elif s.battery == "Full":
        battery = "Full · running on the charger"
    else:
        battery = "Not charging · running on the charger"

    name = f"{s.charger_w:.0f} W charger" if s.charger_w else "Charger"
    if not s.ac:
        charger = "No charger"
    elif weak:
        charger = f"{name} · too weak on its own"
    elif deficit:
        charger = name
    else:
        charger = f"{name} · enough on its own"

    if not s.has_battery or s.can_pause:
        note = None
    elif s.has_limit:
        note = "This laptop only supports a charge limit"
    else:
        note = "This laptop can't pause charging"

    level = f"{s.level}%" if s.level is not None else "—"
    return View(level, battery, charger, note, weak, deficit)
