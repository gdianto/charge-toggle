"""The charge-toggle command."""

from __future__ import annotations

import argparse
import sys
import time

from charge_toggle import __version__, control, desktop
from charge_toggle.status import Status, describe
from charge_toggle.sysfs import AUTO, PAUSE, read_power_state


def current() -> Status:
    return Status.of(read_power_state())


def show(s: Status) -> None:
    view = describe(s)
    print(f"{view.level} · {view.battery}")
    print(view.charger)
    if view.note:
        print(view.note)


def status() -> int:
    show(current())
    return 0


def set_charging(pause: bool) -> int:
    state = read_power_state()
    s = Status.of(state)
    if not s.can_pause:
        print(describe(s).note or "No battery found.", file=sys.stderr)
        return 1
    if s.paused == pause:
        show(s)
        return 0
    if pause and not s.ac:
        print("No charger connected.", file=sys.stderr)
        return 1
    try:
        elevation = control.elevate(interactive=sys.stdin.isatty())
        control.write(PAUSE if pause else AUTO, control.targets(state), elevation)
    except control.ControlError as e:
        print(e, file=sys.stderr)
        return 1
    # The firmware takes a moment to follow.
    deadline = time.monotonic() + 15
    s = current()
    while time.monotonic() < deadline and not settled(s, pause):
        time.sleep(1)
        s = current()
    show(s)
    return 0


def settled(s: Status, pause: bool) -> bool:
    return s.paused == pause and s.battery != ("Charging" if pause else "Not charging")


def window() -> int:
    try:
        from charge_toggle import gui
    except ModuleNotFoundError as e:
        if not (e.name or "").startswith("PySide6"):
            raise
        print(
            'The window needs PySide6: pipx inject charge-toggle PySide6, or pip install "charge-toggle[gui]".',
            file=sys.stderr,
        )
        return 2
    return gui.run()


def install_desktop() -> int:
    desktop.install()
    print("Added Charge Toggle to the application menu.")
    print("If it doesn't show up, log out and back in.")
    return 0


def uninstall_desktop() -> int:
    print("Removed it from the application menu." if desktop.uninstall() else "Nothing to remove.")
    return 0


COMMANDS = {
    None: window,
    "status": status,
    "pause": lambda: set_charging(pause=True),
    "resume": lambda: set_charging(pause=False),
    "install-desktop": install_desktop,
    "uninstall-desktop": uninstall_desktop,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="charge-toggle",
        description="Pause battery charging while the laptop runs on its charger. "
        "Without a command, opens the window.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.add_parser("status", help="show the battery and the charger")
    commands.add_parser("pause", help="stop charging (asks for your password)")
    commands.add_parser("resume", help="charge normally again (asks for your password)")
    commands.add_parser("install-desktop", help="add Charge Toggle to the application menu")
    commands.add_parser("uninstall-desktop", help="remove it from the application menu")
    try:
        return COMMANDS[parser.parse_args(argv).command]()
    except KeyboardInterrupt:
        return 130
