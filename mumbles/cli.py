"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import __version__
from . import config as config_module
from . import audio, inject, launchagent, paths, postprocess
from .app import IDLE, RECORDING, TRANSCRIBING, DictationApp
from .history import History
from .hotkey import parse_combo, pretty_combo
from .transcribe import MODEL_NOTES, TranscriptionError, available_engines


def _print_error(message: str) -> None:
    print(f"mumbles: {message}", file=sys.stderr)


# --- commands ----------------------------------------------------------


def cmd_run(args, cfg) -> int:
    """Menu bar app."""
    from . import menubar

    print(f"mumbles {__version__} - menu bar. "
          f"{'Hold' if cfg.activation == 'hold' else 'Tap'} "
          f"{pretty_combo(parse_combo(cfg.hotkey))} to dictate.")
    menubar.run(cfg)
    return 0


def cmd_listen(args, cfg) -> int:
    """Headless daemon: hotkey only, no menu bar."""
    verb = "Hold" if cfg.activation == "hold" else "Tap"
    combo = pretty_combo(parse_combo(cfg.hotkey))

    def on_state(state: str) -> None:
        label = {IDLE: "ready", RECORDING: "recording…",
                 TRANSCRIBING: "transcribing…"}[state]
        print(f"\r\033[K[{datetime.now():%H:%M:%S}] {label}", end="", flush=True)

    def on_result(text: str, transcript) -> None:
        print(f"\r\033[K[{datetime.now():%H:%M:%S}] {text}")

    def on_error(exc: Exception) -> None:
        print(f"\r\033[K[{datetime.now():%H:%M:%S}] error: {exc}", file=sys.stderr)

    app = DictationApp(cfg, on_state=on_state, on_result=on_result, on_error=on_error)
    print(f"mumbles {__version__} - {verb} {combo} to dictate. Ctrl+C to quit.")
    print(f"mode: {cfg.active_mode}   model: {cfg.model}")

    try:
        app.bind_hotkey()
    except Exception as exc:
        _print_error(str(exc))
        return 1

    if not args.lazy:
        print("loading model…", end=" ", flush=True)
        try:
            app.warm_up()
            print("ready.")
        except Exception as exc:
            print()
            _print_error(str(exc))
            return 1

    try:
        while True:
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nbye.")
    finally:
        app.shutdown()
    return 0


def cmd_once(args, cfg) -> int:
    """Record one take from the terminal, no global hotkey needed."""
    app = DictationApp(cfg, on_error=lambda exc: _print_error(str(exc)))
    print("loading model…", end=" ", flush=True)
    try:
        app.warm_up()
    except TranscriptionError as exc:
        print()
        _print_error(str(exc))
        return 1
    print("ready.")

    try:
        app.recorder.start()
    except audio.AudioError as exc:
        _print_error(str(exc))
        return 1

    if args.seconds:
        print(f"recording for {args.seconds}s…")
        time.sleep(args.seconds)
    else:
        print("recording… press Enter to stop.")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            app.recorder.cancel()
            print("cancelled.")
            return 1

    samples = app.recorder.stop()
    seconds = audio.duration_seconds(samples, cfg.sample_rate)
    if seconds < cfg.min_recording_seconds:
        _print_error("recording too short")
        return 1

    print(f"transcribing {seconds:.1f}s…")
    try:
        text, transcript = app.process(samples, seconds)
    except Exception as exc:
        _print_error(str(exc))
        return 1

    if not postprocess.is_meaningful(text):
        _print_error("nothing recognisable in that recording")
        return 1

    print()
    print(text)
    print()

    if not args.print_only:
        outcome = inject.deliver(
            text + (" " if cfg.trailing_space else ""),
            auto_paste=cfg.auto_paste and not args.no_paste,
            restore_clipboard=cfg.restore_clipboard,
        )
        print(f"({outcome})")
        History(limit=cfg.history_limit).add(
            text=text, raw_text=transcript.text, mode=cfg.active_mode,
            engine=transcript.engine, model=transcript.model, audio_secs=seconds,
        )
    return 0


def cmd_transcribe(args, cfg) -> int:
    """Transcribe an existing audio file."""
    path = Path(args.file).expanduser()
    if not path.exists():
        _print_error(f"{path}: no such file")
        return 1

    if path.suffix.lower() != ".wav":
        converted = _convert_to_wav(path, cfg.sample_rate)
        if converted is None:
            _print_error(
                f"{path.suffix} needs ffmpeg to convert. Install it "
                "(brew install ffmpeg) or pass a .wav file."
            )
            return 1
        path = converted

    samples, rate = audio.read_wav(path)
    samples = audio.resample(samples, rate, cfg.sample_rate)
    seconds = audio.duration_seconds(samples, cfg.sample_rate)

    app = DictationApp(cfg, on_error=lambda exc: _print_error(str(exc)))
    try:
        text, _transcript = app.process(samples, seconds)
    except Exception as exc:
        _print_error(str(exc))
        return 1
    print(text)
    return 0


def _convert_to_wav(path: Path, sample_rate: int) -> Optional[Path]:
    if not shutil.which("ffmpeg"):
        return None
    import tempfile

    out = Path(tempfile.mkdtemp()) / "converted.wav"
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", str(path), "-ac", "1",
         "-ar", str(sample_rate), "-sample_fmt", "s16", str(out)],
        capture_output=True,
    )
    return out if proc.returncode == 0 and out.exists() else None


def cmd_mode(args, cfg) -> int:
    modes = cfg.resolved_modes()
    if not args.name:
        for name, mode in sorted(modes.items()):
            marker = "*" if name == cfg.active_mode else " "
            llm = f" [{mode.llm}]" if mode.uses_llm else ""
            print(f" {marker} {name:<9}{llm:<12} {mode.description}")
        return 0
    if args.name not in modes:
        _print_error(f"unknown mode {args.name!r}. Known: {', '.join(sorted(modes))}")
        return 1
    cfg.active_mode = args.name
    cfg.save()
    print(f"mode: {args.name}")
    return 0


def cmd_config(args, cfg) -> int:
    if args.action == "path":
        print(paths.config_file())
        return 0
    if args.action == "show":
        print(json.dumps(cfg.to_dict(), indent=2))
        return 0
    if args.action == "edit":
        path = cfg.save()
        editor = args.editor or None
        if editor:
            subprocess.call([editor, str(path)])
        elif sys.platform == "darwin":
            subprocess.call(["open", "-t", str(path)])
        else:
            subprocess.call([_fallback_editor(), str(path)])
        return 0
    if args.action == "set":
        if not args.key or args.value is None:
            _print_error("usage: mumbles config set KEY VALUE")
            return 1
        try:
            value = config_module.set_key(cfg, args.key, args.value)
        except KeyError:
            _print_error(f"unknown setting {args.key!r}. "
                         f"See: mumbles config show")
            return 1
        except (ValueError, json.JSONDecodeError) as exc:
            _print_error(f"bad value for {args.key}: {exc}")
            return 1
        cfg.save()
        print(f"{args.key} = {value!r}")
        return 0
    if args.action == "reset":
        path = paths.config_file()
        if path.exists():
            backup = path.with_suffix(".json.bak")
            shutil.copy2(path, backup)
            print(f"previous config saved to {backup}")
        config_module.Config().save(path)
        print(f"reset {path}")
        return 0
    return 1


def _fallback_editor() -> str:
    import os

    return os.environ.get("EDITOR", "nano")


def cmd_vocab(args, cfg) -> int:
    if args.action == "list" or args.action is None:
        if not cfg.replacements:
            print("(no custom vocabulary)")
        for source, target in sorted(cfg.replacements.items()):
            print(f"  {source}  ->  {target}")
        return 0
    if args.action == "add":
        if not args.source or not args.target:
            _print_error('usage: mumbles vocab add "spoken form" "written form"')
            return 1
        cfg.replacements[args.source] = args.target
        cfg.save()
        print(f"added: {args.source} -> {args.target}")
        return 0
    if args.action == "remove":
        if args.source in cfg.replacements:
            del cfg.replacements[args.source]
            cfg.save()
            print(f"removed: {args.source}")
            return 0
        _print_error(f"no vocabulary entry for {args.source!r}")
        return 1
    return 1


def cmd_models(args, cfg) -> int:
    engines = available_engines()
    print(f"engines available here: {', '.join(engines) or 'none'}")
    print(f"configured model: {cfg.model}\n")
    for name in ("tiny.en", "base.en", "small.en", "medium.en", "turbo", "large-v3"):
        marker = "*" if name == cfg.model else " "
        print(f" {marker} {name:<11} {MODEL_NOTES.get(name, '')}")
    print("\nSwitch with: mumbles config set model small.en")
    print("Any Hugging Face repo id or local path works too.")
    return 0


def cmd_devices(args, cfg) -> int:
    try:
        devices = audio.list_devices()
    except audio.AudioError as exc:
        _print_error(str(exc))
        return 1
    if not devices:
        print("no input devices found")
        return 1
    for dev in devices:
        marker = "*" if cfg.input_device in (dev["name"], str(dev["index"])) else " "
        print(f" {marker} [{dev['index']}] {dev['name']} ({dev['channels']}ch)")
    print("\nSelect with: mumbles config set input_device \"MacBook Pro Microphone\"")
    return 0


def cmd_history(args, cfg) -> int:
    history = History(limit=cfg.history_limit)
    if args.clear:
        removed = history.clear()
        print(f"cleared {removed} entries")
        return 0
    if args.stats:
        stats = history.stats()
        minutes = stats["audio_seconds"] / 60.0
        print(f"entries: {stats['entries']}")
        print(f"words:   {stats['words']}")
        print(f"audio:   {minutes:.1f} min")
        return 0
    entries = history.search(args.search, args.count) if args.search \
        else history.recent(args.count)
    if not entries:
        print("(no history yet)")
        return 0
    for entry in reversed(entries):
        stamp = datetime.fromtimestamp(entry.created_at).strftime("%Y-%m-%d %H:%M")
        print(f"\033[2m{stamp}  [{entry.mode}]\033[0m\n{entry.text}\n")
    return 0


def cmd_doctor(args, cfg) -> int:
    from .doctor import run_checks

    checks = run_checks()
    failures = 0
    for check in checks:
        if check.ok:
            print(f"  \033[32m✓\033[0m {check.name}: {check.detail}")
        else:
            failures += 1
            print(f"  \033[31m✗\033[0m {check.name}: {check.detail}")
            if check.fix:
                print(f"      → {check.fix}")
    print()
    if failures:
        print(f"{failures} check(s) need attention.")
        return 1
    print("all good - run `mumbles run` to start dictating.")
    return 0


def cmd_autostart(args, cfg) -> int:
    if args.action == "status":
        print("enabled" if launchagent.installed() else "not enabled")
        return 0
    if args.action == "enable":
        paths.ensure_dirs()
        target = launchagent.install(paths.log_file())
        print(f"installed {target}\nmumbles will start at login.")
        return 0
    if args.action == "disable":
        if launchagent.uninstall():
            print("autostart disabled")
        else:
            print("autostart was not enabled")
        return 0
    return 1


# --- parser ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mumbles",
        description="Local, offline voice dictation. Hold a key, talk, get text.",
    )
    parser.add_argument("--version", action="version", version=f"mumbles {__version__}")
    parser.add_argument("--config", type=Path, default=None,
                        help="use an alternate config file")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="run the menu bar app (default)")

    listen = sub.add_parser("listen", help="run headless with just the hotkey")
    listen.add_argument("--lazy", action="store_true",
                        help="skip model preload; first dictation will be slower")

    once = sub.add_parser("once", help="record a single take from the terminal")
    once.add_argument("-s", "--seconds", type=float, default=None,
                      help="record for a fixed duration instead of until Enter")
    once.add_argument("--print-only", action="store_true",
                      help="print the text without touching the clipboard")
    once.add_argument("--no-paste", action="store_true",
                      help="copy to the clipboard but do not paste")

    transcribe = sub.add_parser("transcribe", help="transcribe an audio file")
    transcribe.add_argument("file")

    mode = sub.add_parser("mode", help="show or switch the active mode")
    mode.add_argument("name", nargs="?")

    config_parser = sub.add_parser("config", help="inspect or change settings")
    config_parser.add_argument(
        "action", choices=["show", "path", "edit", "set", "reset"], nargs="?",
        default="show")
    config_parser.add_argument("key", nargs="?")
    config_parser.add_argument("value", nargs="?")
    config_parser.add_argument("--editor", default=None)

    vocab = sub.add_parser("vocab", help="custom word replacements")
    vocab.add_argument("action", choices=["list", "add", "remove"], nargs="?",
                       default="list")
    vocab.add_argument("source", nargs="?")
    vocab.add_argument("target", nargs="?")

    sub.add_parser("models", help="list Whisper models and their trade-offs")
    sub.add_parser("devices", help="list microphones")

    history = sub.add_parser("history", help="browse past transcripts")
    history.add_argument("-n", "--count", type=int, default=10)
    history.add_argument("-s", "--search", default=None)
    history.add_argument("--stats", action="store_true")
    history.add_argument("--clear", action="store_true")

    sub.add_parser("doctor", help="check permissions and dependencies")

    autostart = sub.add_parser("autostart", help="start mumbles at login")
    autostart.add_argument("action", choices=["enable", "disable", "status"],
                           nargs="?", default="status")

    return parser


HANDLERS = {
    "run": cmd_run,
    "listen": cmd_listen,
    "once": cmd_once,
    "transcribe": cmd_transcribe,
    "mode": cmd_mode,
    "config": cmd_config,
    "vocab": cmd_vocab,
    "models": cmd_models,
    "devices": cmd_devices,
    "history": cmd_history,
    "doctor": cmd_doctor,
    "autostart": cmd_autostart,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths.ensure_dirs()

    try:
        cfg = config_module.load(args.config)
    except SystemExit as exc:
        _print_error(str(exc))
        return 1

    handler = HANDLERS.get(args.command or "run")
    try:
        return handler(args, cfg)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
