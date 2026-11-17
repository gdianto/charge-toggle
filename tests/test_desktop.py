import shutil
import subprocess
from pathlib import Path

import pytest

from charge_toggle import desktop


def test_launcher(tmp_path):
    script = tmp_path / "charge-toggle"
    script.write_text("#!/bin/sh\n")
    assert desktop.launcher(str(script)) == str(script)


def test_launcher_quotes_spaces(tmp_path):
    script = tmp_path / "my apps" / "charge-toggle"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\n")
    assert desktop.launcher(str(script)) == f'"{script}"'


def test_launcher_falls_back_to_the_module(monkeypatch):
    monkeypatch.setattr(desktop.sys, "executable", "/usr/bin/python3")
    assert desktop.launcher("/x/__main__.py") == "/usr/bin/python3 -m charge_toggle"


def test_install_and_uninstall(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    script = tmp_path / "charge-toggle"
    script.write_text("#!/bin/sh\n")
    desktop.install(str(script))
    entry, icon = desktop.paths()
    text = Path(entry).read_text()
    assert f"Exec={script}\n" in text
    assert f"Icon={icon}\n" in text
    assert Path(icon).read_text().startswith("<svg")
    if shutil.which("desktop-file-validate"):
        result = subprocess.run(["desktop-file-validate", entry], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout
    assert desktop.uninstall()
    assert not desktop.uninstall()


@pytest.mark.parametrize("home", ["", "relative/path"])
def test_paths_default_to_local_share(monkeypatch, home):
    monkeypatch.setenv("XDG_DATA_HOME", home)
    entry, _ = desktop.paths()
    assert entry.endswith("/.local/share/applications/charge-toggle.desktop")
