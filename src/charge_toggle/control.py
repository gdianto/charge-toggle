"""Change charge_behaviour, the one thing that needs root.

tee runs as root through pkexec (a password dialog) or sudo (a terminal prompt) and writes the
value, given on standard input, to each battery's charge_behaviour file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence

from charge_toggle.sysfs import AUTO, PAUSE, PowerState

VALUES = (AUTO, PAUSE)


class ControlError(Exception):
    """Charging was not changed; the message says why."""


def targets(state: PowerState) -> list[str]:
    paths = [os.path.join(b.path, "charge_behaviour") for b in state.batteries if b.can_pause]
    if not paths:
        raise ControlError("This laptop can't pause charging.")
    return paths


def elevate(
    interactive: bool,
    env: Mapping[str, str] = os.environ,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """pkexec in a desktop session, sudo in a plain terminal."""
    pkexec, sudo = which("pkexec"), which("sudo")
    desktop = bool(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))
    if pkexec and (desktop or not interactive):
        return [pkexec]
    if sudo and interactive:
        return [sudo]
    if pkexec:
        return [pkexec]
    raise ControlError("This needs root, but neither pkexec nor sudo is installed.")


def command(value: str, paths: Sequence[str], elevation: Sequence[str]) -> list[str]:
    if value not in VALUES:
        raise ControlError(f"Refusing to write {value!r}.")
    for path in paths:
        if not os.path.isabs(path) or os.path.basename(path) != "charge_behaviour":
            raise ControlError(f"Refusing to write to {path!r}.")
    return [*elevation, shutil.which("tee") or "/usr/bin/tee", *paths]


def failure(code: int, err: str) -> str:
    if code == 126:
        return "Cancelled."
    if code == 127:
        return "Not authorized."
    lines = err.strip().splitlines()
    return lines[-1] if lines else f"Failed with exit code {code}."


def write(
    value: str,
    paths: Sequence[str],
    elevation: Sequence[str],
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    args = command(value, paths, elevation)
    try:
        result = run(
            args, input=value, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
    except OSError as e:
        raise ControlError(str(e)) from e
    if result.returncode:
        raise ControlError(failure(result.returncode, result.stderr or ""))
