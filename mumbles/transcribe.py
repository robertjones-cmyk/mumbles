"""Speech-to-text engines.

Three backends, all local:

  mlx         - mlx-whisper, Metal-accelerated. The fast path on Apple Silicon.
  faster      - faster-whisper (CTranslate2). Works everywhere, CPU friendly.
  whispercpp  - an external whisper.cpp binary, if you already have one.

`auto` picks the best one that is actually importable on this machine.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .audio import write_wav

# Friendly names -> per-engine model identifiers. Anything not listed here is
# passed through to the engine untouched, so custom repos/paths still work.
MODEL_ALIASES = {
    "tiny":      {"mlx": "mlx-community/whisper-tiny-mlx",          "faster": "tiny"},
    "tiny.en":   {"mlx": "mlx-community/whisper-tiny.en-mlx",       "faster": "tiny.en"},
    "base":      {"mlx": "mlx-community/whisper-base-mlx",          "faster": "base"},
    "base.en":   {"mlx": "mlx-community/whisper-base.en-mlx",       "faster": "base.en"},
    "small":     {"mlx": "mlx-community/whisper-small-mlx",         "faster": "small"},
    "small.en":  {"mlx": "mlx-community/whisper-small.en-mlx",      "faster": "small.en"},
    "medium":    {"mlx": "mlx-community/whisper-medium-mlx",        "faster": "medium"},
    "medium.en": {"mlx": "mlx-community/whisper-medium.en-mlx",     "faster": "medium.en"},
    "large":     {"mlx": "mlx-community/whisper-large-v3-mlx",      "faster": "large-v3"},
    "large-v3":  {"mlx": "mlx-community/whisper-large-v3-mlx",      "faster": "large-v3"},
    "turbo":     {"mlx": "mlx-community/whisper-large-v3-turbo",    "faster": "large-v3-turbo"},
}

# Rough guide shown by `mumbles models`.
MODEL_NOTES = {
    "tiny.en":   "~75 MB, instant, sloppy. Fine for short commands.",
    "base.en":   "~150 MB, fast and decent. Good default.",
    "small.en":  "~500 MB, noticeably better punctuation and names.",
    "medium.en": "~1.5 GB, strong accuracy, slower on Intel.",
    "turbo":     "~1.6 GB, large-v3 accuracy at small-model speed. Best on Apple Silicon.",
    "large-v3":  "~3 GB, most accurate, slowest.",
}


class TranscriptionError(RuntimeError):
    pass


@dataclass
class Transcript:
    text: str
    language: Optional[str] = None
    engine: str = ""
    model: str = ""
    duration: float = 0.0


def resolve_model(name: str, engine: str) -> str:
    return MODEL_ALIASES.get(name, {}).get(engine, name)


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")


def _importable(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def available_engines() -> List[str]:
    engines = []
    if _importable("mlx_whisper"):
        engines.append("mlx")
    if _importable("faster_whisper"):
        engines.append("faster")
    if whispercpp_binary():
        engines.append("whispercpp")
    return engines


def whispercpp_binary() -> Optional[str]:
    for candidate in ("whisper-cli", "whisper-cpp", "main"):
        found = shutil.which(candidate)
        if found:
            return found
    env = os.environ.get("WHISPER_CPP_BIN")
    return env if env and Path(env).exists() else None


def pick_engine(preference: str = "auto") -> str:
    engines = available_engines()
    if preference != "auto":
        if preference not in engines:
            raise TranscriptionError(
                f"engine {preference!r} is not installed. Available: "
                f"{', '.join(engines) or 'none'}"
            )
        return preference
    if not engines:
        raise TranscriptionError(
            "no transcription backend installed. Run:\n"
            "  pip install mlx-whisper      # Apple Silicon (recommended)\n"
            "  pip install faster-whisper   # Intel Mac / other platforms"
        )
    if is_apple_silicon() and "mlx" in engines:
        return "mlx"
    for name in ("faster", "mlx", "whispercpp"):
        if name in engines:
            return name
    return engines[0]


# ----------------------------------------------------------------------



def _model_load_error(model: str, exc: Exception) -> TranscriptionError:
    """Turn an opaque download/loading failure into something actionable."""
    detail = str(exc).strip() or exc.__class__.__name__
    hint = ""
    lowered = detail.lower()
    if any(token in lowered for token in
           ("403", "404", "connection", "resolve", "timed out", "network",
            "proxy", "ssl", "offline", "huggingface")):
        hint = (
            "\nModels download from huggingface.co on first use. Check your "
            "network, or point `model` at a model you already have on disk."
        )
    elif "not found" in lowered or "no such" in lowered:
        hint = "\nRun `mumbles models` for the names that are known to work."
    return TranscriptionError(f"could not load model {model!r}: {detail}{hint}")


class Engine:
    """Base class. Subclasses load lazily so startup stays fast."""

    name = "base"

    def __init__(self, model: str, language: Optional[str] = None,
                 compute_type: str = "auto", initial_prompt: str = "") -> None:
        self.model = resolve_model(model, self.name)
        self.requested_model = model
        self.language = language or None
        self.compute_type = compute_type
        self.initial_prompt = initial_prompt or ""
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def transcribe(self, samples, sample_rate: int) -> Transcript:
        raise NotImplementedError


class MLXWhisperEngine(Engine):
    name = "mlx"

    def load(self) -> None:
        # Importing is the whole check: mlx_whisper fetches weights lazily.
        import importlib

        importlib.import_module("mlx_whisper")
        self._loaded = True

    def _guarded(self, call):
        try:
            return call()
        except TranscriptionError:
            raise
        except Exception as exc:
            raise _model_load_error(self.model, exc) from exc

    def transcribe(self, samples, sample_rate: int) -> Transcript:
        import mlx_whisper

        from .audio import resample

        audio = resample(samples, sample_rate, 16000)
        kwargs = {"path_or_hf_repo": self.model, "fp16": True}
        if self.language:
            kwargs["language"] = self.language
        if self.initial_prompt:
            kwargs["initial_prompt"] = self.initial_prompt
        result = self._guarded(lambda: mlx_whisper.transcribe(audio, **kwargs))
        return Transcript(
            text=(result.get("text") or "").strip(),
            language=result.get("language"),
            engine=self.name,
            model=self.model,
        )


class FasterWhisperEngine(Engine):
    name = "faster"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel

        compute = self.compute_type
        if compute == "auto":
            compute = "int8"  # safe and quick on any CPU
        try:
            self._model = WhisperModel(self.model, device="cpu", compute_type=compute)
        except Exception as exc:
            raise _model_load_error(self.model, exc) from exc
        self._loaded = True

    def transcribe(self, samples, sample_rate: int) -> Transcript:
        from .audio import resample

        if self._model is None:
            self.load()
        audio = resample(samples, sample_rate, 16000)
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            initial_prompt=self.initial_prompt or None,
            vad_filter=True,
            beam_size=5,
        )
        text = "".join(segment.text for segment in segments).strip()
        return Transcript(
            text=text,
            language=getattr(info, "language", None),
            engine=self.name,
            model=self.model,
        )


class WhisperCppEngine(Engine):
    name = "whispercpp"

    def load(self) -> None:
        if not whispercpp_binary():
            raise TranscriptionError(
                "no whisper.cpp binary found. Install with: brew install whisper-cpp"
            )
        if not Path(self.model).exists():
            raise TranscriptionError(
                f"whisper.cpp needs a ggml model file path; got {self.model!r}. "
                "Set `model` in the config to something like "
                "~/models/ggml-base.en.bin"
            )
        self._loaded = True

    def transcribe(self, samples, sample_rate: int) -> Transcript:
        binary = whispercpp_binary()
        if binary is None:
            self.load()
        with tempfile.TemporaryDirectory() as tmp:
            wav = write_wav(samples, sample_rate, Path(tmp) / "take.wav")
            cmd = [binary, "-m", str(Path(self.model).expanduser()),
                   "-f", str(wav), "-nt", "-np"]
            if self.language:
                cmd += ["-l", self.language]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            except subprocess.TimeoutExpired as exc:
                raise TranscriptionError("whisper.cpp timed out") from exc
        if proc.returncode != 0:
            raise TranscriptionError(f"whisper.cpp failed: {proc.stderr.strip()}")
        return Transcript(
            text=proc.stdout.strip(),
            language=self.language,
            engine=self.name,
            model=self.model,
        )


ENGINES = {
    "mlx": MLXWhisperEngine,
    "faster": FasterWhisperEngine,
    "whispercpp": WhisperCppEngine,
}


def build_engine(cfg) -> Engine:
    """Create the engine described by a Config."""
    name = pick_engine(cfg.engine)
    return ENGINES[name](
        model=cfg.model,
        language=cfg.language,
        compute_type=cfg.compute_type,
        initial_prompt=cfg.initial_prompt,
    )
