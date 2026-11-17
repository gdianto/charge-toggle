"""The application-menu entry, installed for the current user."""

from __future__ import annotations

import os
import sys
from importlib import resources


def paths() -> tuple[str, str]:
    """Where the menu entry and its icon go."""
    home = os.environ.get("XDG_DATA_HOME", "")
    if not os.path.isabs(home):
        home = os.path.expanduser("~/.local/share")
    return (
        os.path.join(home, "applications", "charge-toggle.desktop"),
        os.path.join(home, "icons", "hicolor", "scalable", "apps", "charge-toggle.svg"),
    )


def launcher(argv0: str | None = None) -> str:
    """The Exec line: the installed script, or python -m charge_toggle."""
    argv0 = sys.argv[0] if argv0 is None else argv0
    if os.path.basename(argv0) == "charge-toggle" and os.path.isfile(argv0):
        args = [os.path.abspath(argv0)]
    else:
        args = [sys.executable, "-m", "charge_toggle"]
    return " ".join(f'"{arg}"' if " " in arg else arg for arg in args)


def install(argv0: str | None = None) -> None:
    entry, icon = paths()
    data = resources.files("charge_toggle") / "data"
    for path in (entry, icon):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(icon, "wb") as f:
        f.write((data / "charge-toggle.svg").read_bytes())
    template = (data / "charge-toggle.desktop.in").read_text(encoding="utf-8")
    with open(entry, "w", encoding="utf-8") as f:
        f.write(template.format(exec=launcher(argv0), icon=icon))


def uninstall() -> bool:
    removed = False
    for path in paths():
        if os.path.exists(path):
            os.remove(path)
            removed = True
    return removed
