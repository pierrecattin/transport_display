"""Config web UI backend (FastAPI). Runs on the Pi as its own service.

Serves the built React app (``web/dist``) and a small JSON API to read/validate/
write ``config.json`` and restart the display service. Imports ``src.config`` and
``src.layout`` (both hardware-free) for validation and the live PNG preview; it
must never import ``src.renderer`` (that's the only ``rgbmatrix`` consumer).
"""
