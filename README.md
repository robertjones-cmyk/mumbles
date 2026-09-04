# mumbles

Local voice dictation for macOS. Hold a key, talk, and the text lands in
whatever app has focus — editor, browser, Slack, terminal, anything.

Speech recognition runs on your machine with Whisper. No account, no
subscription, no audio leaving the laptop. The only time anything touches the
network is if you deliberately switch to a mode that asks an LLM to reformat
the transcript, and even that can point at a local Ollama instead.

```
   ⌘⇧Space ──▶ 🎙 record ──▶ whisper (local) ──▶ cleanup ──▶ paste into the front app
```

## Install

### Download the app

Grab the disk image for your Mac from the
[latest release](https://github.com/robertjones-cmyk/mumbles/releases/latest):

| Mac | File |
|---|---|
| Apple Silicon (M1 and later) | `mumbles-*-macos-arm64.dmg` |
| Intel | `mumbles-*-macos-x86_64.dmg` |

Open it, drag **mumbles.app** to Applications, and look for the microphone in
your menu bar. There is no Dock icon and no window — it is a menu bar app.

> **The first launch is different.** These builds are not notarized by Apple
> — that needs a paid Developer account — so macOS blocks them with "could
> not verify this app is free of malware". Apple never inspected it, rather
> than inspected it and objected. The fix, once:
>
> ```bash
> xattr -dr com.apple.quarantine /Applications/mumbles.app
> ```
>
> Or: **System Settings → Privacy & Security → Security → Open Anyway**.
>
> Right-clicking and choosing Open used to work and no longer does — Apple
> removed that bypass in macOS 15 Sequoia. If you would rather not bypass
> Gatekeeper at all, use the one-line install below instead: a Python
> package is not a signed app bundle, so none of this applies to it.

### Or install with one command

No disk image, no Gatekeeper prompt, no right-click dance:

```bash
curl -fsSL https://raw.githubusercontent.com/robertjones-cmyk/mumbles/main/install.sh | bash
```

This is the simplest route, and it also gives you the `mumbles` command line
alongside the menu bar app. From a clone it is the same script:

```bash
git clone https://github.com/robertjones-cmyk/mumbles.git
cd mumbles
./install.sh
```

The installer creates a virtualenv, picks the right Whisper backend for your
Mac (Metal-accelerated `mlx-whisper` on Apple Silicon, `faster-whisper` on
Intel), links `mumbles` into `~/.local/bin`, and runs the setup check. This is
the route if you want the `mumbles` command line as well as the menu bar.

### Or build the app yourself

```bash
./packaging/make_dmg.sh    # macOS only; produces dist/mumbles-*.dmg
```

### Permissions

macOS gates everything mumbles needs. Grant these to whichever app launches it
(your terminal if you run it from a shell), under
**System Settings → Privacy & Security**:

| Permission | Why |
|---|---|
| Microphone | recording you |
| Input Monitoring | seeing the global hotkey |
| Accessibility | sending Cmd+V to paste |

`mumbles doctor` tells you which ones are still missing.

## Use it

```bash
mumbles run        # menu bar app - the normal way to use it
mumbles listen     # headless, prints transcripts to the terminal
mumbles once       # record a single take, no hotkey needed
```

Default hotkey is **⌘⇧Space**, push-to-talk: hold it, talk, let go. The text is
pasted where your cursor is. Tap **Esc** mid-take to throw a recording away.

While you are recording, the menu bar shows a live level meter, so you can see
that the mic is actually picking you up before you find out from an empty
transcript:

```
🎙              idle
🔴 ▁▁▁▁▁▁       recording, hearing nothing - check your input device
🔴 ███▆▁▁       recording, normal speaking level
🔴 ██████       too loud, back off the mic
```

Prefer tap-to-start/tap-to-stop?

```bash
mumbles config set activation toggle
```

## Modes

A mode decides what happens to the transcript before it gets inserted.

| Mode | What it does | Network |
|---|---|---|
| `raw` | exactly what you said | never |
| `clean` | drops "um"/"uh" and stutters, fixes punctuation (**default**) | never |
| `polish` | LLM tidy-up of grammar and punctuation | yes |
| `email` | reshapes a ramble into a short email body | yes |
| `message` | casual chat-message tone | yes |
| `notes` | turns spoken thoughts into bullets | yes |
| `code` | "open paren" → `(`, "snake case foo bar" → `foo_bar` | yes |

```bash
mumbles mode           # list them, * marks the active one
mumbles mode email     # switch
```

The LLM modes need either `ANTHROPIC_API_KEY` in your environment, or a mode
switched to Ollama:

```bash
mumbles config set ollama_model llama3.1:8b
# then in ~/Library/Application Support/mumbles/config.json set the mode's
# "llm" to "ollama"
```

If an LLM call fails, mumbles pastes the locally cleaned transcript instead —
a dropped network connection never costs you what you just said.

Write your own mode by adding an entry to `modes` in the config file: give it a
`prompt`, set `llm` to `anthropic`, `ollama` or `none`, and it shows up in the
menu.

## Models

```bash
mumbles models
mumbles config set model small.en
```

| Model | Size | Notes |
|---|---|---|
| `tiny.en` | ~75 MB | instant, sloppy |
| `base.en` | ~150 MB | fast and decent — the default |
| `small.en` | ~500 MB | noticeably better with names and punctuation |
| `medium.en` | ~1.5 GB | strong, slower on Intel |
| `turbo` | ~1.6 GB | large-v3 accuracy at small-model speed; best on Apple Silicon |
| `large-v3` | ~3 GB | most accurate, slowest |

On an M-series Mac, `turbo` is usually the sweet spot. Any Hugging Face repo id
or local model path works too. Models download once, on first use.

## Custom vocabulary

Whisper mangles jargon. Teach it:

```bash
mumbles vocab add "get hub" "GitHub"
mumbles vocab add "cube cuddle" "kubectl"
mumbles vocab list
```

Replacements are whole-phrase, case-insensitive, and applied before any LLM
step. They cost nothing at runtime.

## Everything else

```bash
mumbles history            # what you've dictated
mumbles history --stats    # how much you've talked
mumbles history -s invoice # search it
mumbles devices            # pick a different microphone
mumbles transcribe memo.m4a
mumbles doctor             # diagnose a broken setup
mumbles autostart enable   # launch at login
mumbles config show
```

Config lives at `~/Library/Application Support/mumbles/config.json`
(`mumbles config path` will tell you). Editable by hand; the menu bar has a
"Reload configuration" item.

Useful settings:

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `<cmd>+<shift>+space` | pynput notation, e.g. `<ctrl>+<alt>+d`, `<f5>` |
| `activation` | `hold` | `hold` (push-to-talk) or `toggle` |
| `auto_paste` | `true` | off means "copy to clipboard, don't paste" |
| `restore_clipboard` | `true` | put your old clipboard back after pasting |
| `trailing_space` | `true` | append a space so dictations chain naturally |
| `language` | `en` | set `null` to auto-detect |
| `initial_prompt` | `""` | bias the model toward your jargon |
| `max_recording_seconds` | `300` | safety cap on a single take |
| `keep_recordings` | `false` | save the WAVs for debugging |
| `sounds` | `true` | start/stop chimes |

## When it doesn't work

**Hotkey does nothing.** Input Monitoring isn't granted to the app that
launched mumbles. Toggle it off and on again in System Settings — macOS caches
the old answer after an upgrade.

**Text goes to the clipboard but never pastes.** Accessibility permission. Same
fix. mumbles falls back to typing character-by-character, so if you see slow
typing that's the tell.

**"could not open the microphone".** Microphone permission, or another app has
an exclusive grab on the device. `mumbles devices` shows what it can see.

**First dictation is slow.** The model loads on first use. `mumbles listen`
preloads it at startup; the menu bar app warms up in the background.

**Transcripts are wrong.** Move up a model size, set `language` explicitly, and
add jargon to `initial_prompt` and `vocab`.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The test suite runs anywhere, macOS or not — every OS-specific import is lazy,
and `rumps` is stubbed so the menu bar pump is exercised too.

CI runs the tests on every push and builds both architectures on a tag, so a
release is `git tag v0.1.1 && git push --tags`.

Layout:

| File | Role |
|---|---|
| `app.py` | the state machine everything else drives |
| `audio.py` | microphone capture |
| `transcribe.py` | Whisper backends (mlx / faster-whisper / whisper.cpp) |
| `postprocess.py` | local text cleanup — pure functions |
| `meter.py` | the menu bar level meter — pure functions |
| `llm.py` | optional Anthropic / Ollama rewriting |
| `inject.py` | clipboard and keystroke delivery |
| `hotkey.py` | global hotkey state machine |
| `menubar.py` | the rumps menu bar UI |
| `cli.py` | command line |
| `packaging/` | icon, py2app bundle and `.dmg` build |

## What this isn't

mumbles is written from scratch and is not affiliated with, derived from, or a
copy of any commercial dictation app. It contains no third-party proprietary
code or assets, and it isn't a way to unlock paid software — it's an
independent tool that happens to do a similar job. If a paid app suits you
better, buy it; the people who make those are worth paying.

MIT licensed.
