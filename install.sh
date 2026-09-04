#!/usr/bin/env bash
# Install mumbles into its own virtualenv and put `mumbles` on your PATH.
set -euo pipefail

VENV="${MUMBLES_VENV:-$HOME/.local/share/mumbles/venv}"
BIN_DIR="${MUMBLES_BIN_DIR:-$HOME/.local/bin}"
SRC_DIR="${MUMBLES_SRC:-$HOME/.local/share/mumbles/src}"
REPO_URL="${MUMBLES_REPO:-https://github.com/robertjones-cmyk/mumbles.git}"
REPO_REF="${MUMBLES_REF:-claude/vibrant-einstein-m2e6xf}"

say() { printf '\033[1m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[33m==>\033[0m %s\n' "$1"; }

# Works both ways: run from a checkout, or piped straight from curl, where
# BASH_SOURCE points at nothing and the source has to be fetched first.
_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$_here" && -f "$_here/pyproject.toml" ]]; then
  REPO_DIR="$_here"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required to fetch mumbles. Install Xcode command line tools:" >&2
    echo "  xcode-select --install" >&2
    exit 1
  fi
  say "fetching mumbles into $SRC_DIR"
  if [[ -d "$SRC_DIR/.git" ]]; then
    git -C "$SRC_DIR" fetch --depth 1 origin "$REPO_REF"
    git -C "$SRC_DIR" checkout -q FETCH_HEAD
  else
    mkdir -p "$(dirname "$SRC_DIR")"
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$SRC_DIR"
  fi
  REPO_DIR="$SRC_DIR"
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "mumbles targets macOS. Installing anyway, but paste and sounds won't work."
fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "python3 not found. Install it first (brew install python)." >&2
  exit 1
fi

"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 9):
    sys.exit("mumbles needs Python 3.9 or newer; found %s" % sys.version.split()[0])
PY

# PortAudio backs the microphone capture. Homebrew is the easy route.
if [[ "$(uname -s)" == "Darwin" ]] && ! ls /opt/homebrew/lib/libportaudio* \
     /usr/local/lib/libportaudio* >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    say "installing portaudio"
    brew install portaudio || warn "brew install portaudio failed; continuing"
  else
    warn "portaudio not found and Homebrew is missing."
    warn "If the microphone check fails later: brew install portaudio"
  fi
fi

say "creating virtualenv at $VENV"
mkdir -p "$(dirname "$VENV")"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

# Apple Silicon gets the Metal-accelerated backend; everything else gets CPU.
EXTRAS="cpu"
if [[ "$(uname -s)" == "Darwin" ]]; then
  EXTRAS="ui"
  if [[ "$(uname -m)" == "arm64" ]]; then
    EXTRAS="mlx,ui"
  else
    EXTRAS="cpu,ui"
  fi
fi

say "installing mumbles[$EXTRAS] (this pulls a few hundred MB of ML wheels)"
"$VENV/bin/pip" install --quiet "$REPO_DIR[$EXTRAS]"

say "linking mumbles into $BIN_DIR"
mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/mumbles" "$BIN_DIR/mumbles"

if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
  warn "$BIN_DIR is not on your PATH. Add this to ~/.zshrc:"
  warn "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
say "checking your setup"
"$BIN_DIR/mumbles" doctor || true

cat <<'NEXT'

Next steps
----------
  1. Grant permissions the first time you run it (macOS will prompt, or you can
     pre-approve under System Settings > Privacy & Security):
       - Microphone         -> your terminal, or the mumbles app
       - Accessibility      -> same, so mumbles can paste for you
       - Input Monitoring   -> same, so the global hotkey works
  2. Try one take:      mumbles once
  3. Run it for real:   mumbles run       (menu bar)
                        mumbles listen    (headless, in a terminal)
  4. Start at login:    mumbles autostart enable

NEXT
