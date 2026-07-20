"""
cheapwine: A lightweight, project-based Wine prefix and application manager.
"""

try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("cheapwine")
except Exception:
    __version__ = "0.1.8"
