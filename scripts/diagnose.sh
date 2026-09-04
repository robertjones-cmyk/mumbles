#!/usr/bin/env bash
# Collect everything needed to work out why mumbles will not start.
# Prints a report to the terminal. Nothing is uploaded anywhere.
#
#   bash scripts/diagnose.sh
#
# Written for macOS's stock bash 3.2, so no modern shell features.

APP="${MUMBLES_APP:-/Applications/mumbles.app}"
SUPPORT="$HOME/Library/Application Support/mumbles"

hr() { printf '\n===== %s =====\n' "$1"; }

hr "system"
sw_vers 2>/dev/null || echo "sw_vers unavailable"
echo "arch: $(uname -m)"

hr "app bundle"
if [ -d "$APP" ]; then
  echo "found: $APP"
  /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
    "$APP/Contents/Info.plist" 2>/dev/null | sed 's/^/version: /'
  EXE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' \
        "$APP/Contents/Info.plist" 2>/dev/null)"
  echo "executable: $EXE"
  echo "quarantine attribute:"
  xattr -p com.apple.quarantine "$APP" 2>&1 | sed 's/^/  /'
  echo "signature:"
  codesign -dv "$APP" 2>&1 | sed 's/^/  /' | head -5
else
  echo "NOT FOUND at $APP"
  echo "apps that look related:"
  ls -d /Applications/*umbles* 2>/dev/null | sed 's/^/  /' || echo "  none"
fi

hr "import selftest (does the bundle contain what it needs?)"
if [ -d "$APP" ]; then
  BIN="$APP/Contents/MacOS/$EXE"
  if [ -x "$BIN" ]; then
    MUMBLES_SELFTEST=1 "$BIN" > /tmp/mumbles-selftest.out 2>&1
    echo "  (exit $?)"
    sed 's/^/  /' /tmp/mumbles-selftest.out
  else
    echo "  no executable at $BIN"
    ls -la "$APP/Contents/MacOS" 2>&1 | sed 's/^/  /'
  fi
fi

hr "actually launching it (10 second timeout)"
if [ -d "$APP" ]; then
  BIN="$APP/Contents/MacOS/$EXE"
  # Run it in the foreground so a startup traceback lands on stderr where we
  # can see it, rather than vanishing into the window server.
  ( "$BIN" > /tmp/mumbles-launch.out 2>&1 & echo $! > /tmp/mumbles-launch.pid ) 
  sleep 10
  PID="$(cat /tmp/mumbles-launch.pid 2>/dev/null)"
  if kill -0 "$PID" 2>/dev/null; then
    echo "  still running after 10s - it started. Look for 🎙 in the menu bar."
    kill "$PID" 2>/dev/null
  else
    echo "  exited within 10s. Output:"
  fi
  sed 's/^/  /' /tmp/mumbles-launch.out 2>/dev/null | head -60
fi

hr "application log"
if [ -f "$SUPPORT/mumbles.log" ]; then
  tail -60 "$SUPPORT/mumbles.log" | sed 's/^/  /'
else
  echo "  no log at $SUPPORT/mumbles.log"
fi

hr "crash reports"
ls -t "$HOME/Library/Logs/DiagnosticReports"/mumbles* 2>/dev/null | head -3 | \
  while read -r f; do
    echo "  --- $f"
    head -40 "$f" | sed 's/^/    /'
  done
[ -z "$(ls "$HOME/Library/Logs/DiagnosticReports"/mumbles* 2>/dev/null)" ] && \
  echo "  none"

hr "config"
if [ -f "$SUPPORT/config.json" ]; then
  sed 's/^/  /' "$SUPPORT/config.json" | head -30
else
  echo "  no config yet (the app has never got far enough to write one)"
fi

hr "end of report"
echo "Copy everything from '===== system =====' down and paste it back."
