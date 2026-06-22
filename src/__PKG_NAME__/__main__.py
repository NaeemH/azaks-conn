"""Entry point for `python -m __PKG_NAME__`."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Console-script + module entry point."""
    # Verbose Azure SDK logs only when __PKG_NAME_UPPER___DEBUG=1
    if os.environ.get("__PKG_NAME_UPPER___DEBUG") == "1":
        import logging

        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    from __PKG_NAME__.cli import app

    app()


if __name__ == "__main__":
    main()
