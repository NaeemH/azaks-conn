"""Entry point for `python -m azaks_conn`."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Console-script + module entry point."""
    # Verbose Azure SDK logs only when AZAKS_CONN_DEBUG=1
    if os.environ.get("AZAKS_CONN_DEBUG") == "1":
        import logging

        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    from azaks_conn.cli import app

    app()


if __name__ == "__main__":
    main()
