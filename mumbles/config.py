"""User configuration: a single JSON file, hot-reloadable."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from . import paths
from .modes import Mode, default_modes_dict, load_modes

# Sensible starting vocabulary fixes. Whisper mangles these constantly.
DEFAULT_REPLACEMENTS: Dict[str, str] = {
    "get hub": "GitHub",
    "guitar hub": "GitHub",
    "pie thon": "Python",
    "java script": "JavaScript",
    "type script": "TypeScript",
    "kubernets": "Kubernetes",
    "post gres": "Postgres",
}


@dataclass
class Config:
    # --- capture -------------------------------------------------------
    hotkey: str = "<cmd>+<shift>+space"
    # "toggle": tap to start, tap to stop. "hold": push-to-talk.
    activation: str = "hold"
    input_device: Optional[str] = None
    sample_rate: int = 16000
    max_recording_seconds: int = 300
    min_recording_seconds: float = 0.35

    # --- transcription -------------------------------------------------
    # "auto" picks mlx on Apple Silicon, faster-whisper elsewhere.
    engine: str = "auto"
    model: str = "base.en"
    language: Optional[str] = "en"
    initial_prompt: str = ""
    compute_type: str = "auto"

    # --- output --------------------------------------------------------
    # Paste into the focused app. Off means "clipboard only".
    auto_paste: bool = True
    restore_clipboard: bool = True
    trailing_space: bool = True
    sounds: bool = True

    # --- text handling -------------------------------------------------
    active_mode: str = "clean"
    replacements: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REPLACEMENTS))
    modes: Dict[str, Any] = field(default_factory=default_modes_dict)

    # --- llm -----------------------------------------------------------
    anthropic_model: str = "claude-haiku-4-5-20251001"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    llm_timeout: float = 30.0

    # --- misc ----------------------------------------------------------
    keep_recordings: bool = False
    history_limit: int = 1000

    # ------------------------------------------------------------------
    def resolved_modes(self) -> Dict[str, Mode]:
        return load_modes(self.modes)

    def mode(self, name: Optional[str] = None) -> Mode:
        modes = self.resolved_modes()
        wanted = name or self.active_mode
        if wanted in modes:
            return modes[wanted]
        # Never blow up on a stale mode name in the config file.
        return modes.get("clean") or next(iter(modes.values()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        known = set(cls.__dataclass_fields__)
        unknown = [k for k in data if k not in known]
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg._unknown_keys = unknown  # type: ignore[attr-defined]
        return cfg

    def save(self, path: Optional[Path] = None) -> Path:
        path = path or paths.config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        tmp.replace(path)
        return path


def load(path: Optional[Path] = None) -> Config:
    """Load config, writing a default file the first time."""
    path = path or paths.config_file()
    if not path.exists():
        cfg = Config()
        cfg.save(path)
        return cfg
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config file {path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"config file {path} must contain a JSON object")
    return Config.from_dict(data)


def set_key(cfg: Config, key: str, raw_value: str) -> Any:
    """Apply a `key=value` edit from the CLI, coercing to the field's type."""
    if key not in Config.__dataclass_fields__:
        raise KeyError(key)
    current = getattr(cfg, key)
    if isinstance(current, bool):
        value: Any = raw_value.strip().lower() in ("1", "true", "yes", "on")
    elif isinstance(current, int) and not isinstance(current, bool):
        value = int(raw_value)
    elif isinstance(current, float):
        value = float(raw_value)
    elif isinstance(current, (dict, list)):
        value = json.loads(raw_value)
    elif raw_value == "" and current is None:
        value = None
    else:
        value = raw_value
    setattr(cfg, key, value)
    return value
