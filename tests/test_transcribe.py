import pytest

from mumbles import transcribe
from mumbles.config import Config
from mumbles.transcribe import TranscriptionError, pick_engine, resolve_model


def test_aliases_map_to_each_backend():
    assert resolve_model("base.en", "mlx") == "mlx-community/whisper-base.en-mlx"
    assert resolve_model("base.en", "faster") == "base.en"
    assert resolve_model("turbo", "faster") == "large-v3-turbo"


def test_unknown_models_pass_through_untouched():
    assert resolve_model("myorg/whisper-custom", "mlx") == "myorg/whisper-custom"
    assert resolve_model("/models/ggml-base.bin", "whispercpp") == "/models/ggml-base.bin"


def test_auto_prefers_mlx_on_apple_silicon(monkeypatch):
    monkeypatch.setattr(transcribe, "available_engines", lambda: ["mlx", "faster"])
    monkeypatch.setattr(transcribe, "is_apple_silicon", lambda: True)
    assert pick_engine("auto") == "mlx"


def test_auto_falls_back_to_faster_elsewhere(monkeypatch):
    monkeypatch.setattr(transcribe, "available_engines", lambda: ["mlx", "faster"])
    monkeypatch.setattr(transcribe, "is_apple_silicon", lambda: False)
    assert pick_engine("auto") == "faster"


def test_explicit_engine_must_be_installed(monkeypatch):
    monkeypatch.setattr(transcribe, "available_engines", lambda: ["faster"])
    assert pick_engine("faster") == "faster"
    with pytest.raises(TranscriptionError, match="not installed"):
        pick_engine("mlx")


def test_no_backend_gives_install_instructions(monkeypatch):
    monkeypatch.setattr(transcribe, "available_engines", lambda: [])
    with pytest.raises(TranscriptionError, match="pip install"):
        pick_engine("auto")


def test_build_engine_wires_config_through(monkeypatch):
    monkeypatch.setattr(transcribe, "available_engines", lambda: ["faster"])
    monkeypatch.setattr(transcribe, "is_apple_silicon", lambda: False)
    engine = transcribe.build_engine(
        Config(model="small.en", language="fr", initial_prompt="jargon"))
    assert engine.name == "faster"
    assert engine.model == "small.en"
    assert engine.language == "fr"
    assert engine.initial_prompt == "jargon"


def test_empty_language_becomes_none(monkeypatch):
    monkeypatch.setattr(transcribe, "available_engines", lambda: ["faster"])
    monkeypatch.setattr(transcribe, "is_apple_silicon", lambda: False)
    assert transcribe.build_engine(Config(language="")).language is None
