"""Run the config web UI: ``python3 -m server`` (the systemd unit does this).

Host/port can be overridden with ``TRANSPORT_DISPLAY_WEB_HOST`` /
``TRANSPORT_DISPLAY_WEB_PORT``; defaults bind the LAN on :8080.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("TRANSPORT_DISPLAY_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("TRANSPORT_DISPLAY_WEB_PORT", "8080"))
    uvicorn.run("server.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
