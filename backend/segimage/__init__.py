"""Installable package name for `python -m segimage` / console script.

The cutout engine lives in `app.*` (shared with the FastAPI service).
The thin HTTP client SDK is a separate file at sdk/python/segimage.py and is
not this package.
"""
from app.version import __version__ as __version__  # noqa: F401
