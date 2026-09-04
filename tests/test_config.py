import json

import pytest

from mumbles import config as config_module
from mumbles import paths
from mumbles.config import Config, set_key


def test_first_load_writes_a_default_file(sandbox):
    assert not paths.config_file().exists()
    cfg = config_module.load()
    assert paths.config_file().exists()
    assert cfg.active_mode == "clean"
    assert json.loads(paths.config_file().read_text())["hotkey"] == cfg.hotkey


def test_round_trips_through_disk(sandbox):
    cfg = Config(hotkey="<ctrl>+<alt>+d", model="small.en", auto_paste=False)
    cfg.replacements["kubectl"] = "kubectl"
    cfg.save()
    loaded = config_module.load()
    assert loaded.hotkey == "<ctrl>+<alt>+d"
    assert loaded.model == "small.en"
    assert loaded.auto_paste is False
    assert loaded.replacements["kubectl"] == "kubectl"


def test_unknown_keys_in_the_file_do_not_break_loading(sandbox):
    paths.ensure_dirs()
    paths.config_file().write_text(json.dumps({"hotkey": "<f5>", "from_v9": True}))
    cfg = config_module.load()
    assert cfg.hotkey == "<f5>"
    assert cfg.model == Config().model


def test_invalid_json_fails_loudly(sandbox):
    paths.ensure_dirs()
    paths.config_file().write_text("{not json")
    with pytest.raises(SystemExit):
        config_module.load()


def test_mode_lookup_falls_back_when_the_name_is_stale():
    cfg = Config(active_mode="deleted-mode")
    assert cfg.mode().name == "clean"
    assert cfg.mode("email").llm == "anthropic"


def test_custom_modes_override_builtins():
    cfg = Config()
    cfg.modes["email"] = {"name": "email", "llm": "ollama", "prompt": "hi"}
    cfg.modes["shouty"] = {"name": "shouty", "llm": "none"}
    modes = cfg.resolved_modes()
    assert modes["email"].llm == "ollama"
    assert "shouty" in modes
    assert "raw" in modes  # built-ins survive


def test_set_key_coerces_to_the_field_type():
    cfg = Config()
    assert set_key(cfg, "auto_paste", "false") is False
    assert set_key(cfg, "sounds", "yes") is True
    assert set_key(cfg, "sample_rate", "48000") == 48000
    assert set_key(cfg, "llm_timeout", "12.5") == 12.5
    assert set_key(cfg, "model", "turbo") == "turbo"
    assert set_key(cfg, "replacements", '{"a": "b"}') == {"a": "b"}
    with pytest.raises(KeyError):
        set_key(cfg, "not_a_setting", "x")
    with pytest.raises(ValueError):
        set_key(cfg, "sample_rate", "banana")
