"""opencow - A lightweight personal AI agent framework."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("opencow")
except PackageNotFoundError:
    __version__ = "0.1.0"

from opencow.app import OpenCow

__all__ = ["OpenCow"]
