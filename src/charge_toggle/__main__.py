"""Allow ``python -m charge_toggle``."""

import sys

from charge_toggle.cli import main

if __name__ == "__main__":
    sys.exit(main())
