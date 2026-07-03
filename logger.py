"""
Structured logging for the research agent.

Provides a single "research_agent" logger with:
- Console handler at INFO level (overridable via LOG_LEVEL env var)
- Rotating file handler at DEBUG level → ~/Documents/AI-search/logs/agent.log
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.cwd() /"logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "agent.log"

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s.%(funcName)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger("research_agent")
_logger.setLevel(logging.DEBUG)  # root level — handlers control granularity

# --- Console handler (INFO by default, overridable via LOG_LEVEL) ---
_console = logging.StreamHandler()
_console.setLevel(
    getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
)
_console.setFormatter(_fmt)
_logger.addHandler(_console)

# --- Rotating file handler (always DEBUG) ---
_file = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
_file.setLevel(logging.DEBUG)
_file.setFormatter(_fmt)
_logger.addHandler(_file)


def get_logger():
    """Return the research_agent logger instance."""
    return _logger
