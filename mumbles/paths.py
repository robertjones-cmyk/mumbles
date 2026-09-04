"""Where mumbles keeps its config, models and history."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _mac() -> bool:
    return sys.platform == "darwin"


def config_dir() -> Path:
    if env := os.environ.get("MUMBLES_HOME"):
        return Path(env).expanduser()
    if _mac():
        return Path.home() / "Library" / "Application Support" / "mumbles"
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "mumbles"


def data_dir() -> Path:
    if os.environ.get("MUMBLES_HOME"):
        return config_dir()
    if _mac():
        return config_dir()
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "mumbles"


def config_file() -> Path:
    return config_dir() / "config.json"


def history_file() -> Path:
    return data_dir() / "history.db"


def log_file() -> Path:
    return data_dir() / "mumbles.log"


def recordings_dir() -> Path:
    return data_dir() / "recordings"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)
