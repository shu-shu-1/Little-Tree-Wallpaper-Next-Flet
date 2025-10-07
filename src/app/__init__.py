"""Application package for Little Tree Wallpaper Next."""

from .application import Application
from .logging_config import setup_logging

setup_logging()

__all__ = ["Application", "setup_logging"]
