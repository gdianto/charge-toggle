import json
from pathlib import Path

import pytest

from charge_toggle import sysfs

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """tree("fixture", {"BAT0": {"status": "..."}}) builds a fake power_supply tree and reads it."""

    def build(name: str, changes: dict | None = None) -> Path:
        supplies = json.loads((FIXTURES / f"{name}.json").read_text())["supplies"]
        for supply, attrs in (changes or {}).items():
            supplies[supply].update(attrs)
        root = tmp_path / "power_supply"
        for supply, attrs in supplies.items():
            (root / supply).mkdir(parents=True)
            for attr, value in attrs.items():
                (root / supply / attr).write_text(value + "\n")
        monkeypatch.setattr(sysfs, "ROOT", str(root))
        return root

    return build
