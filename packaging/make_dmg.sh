#!/usr/bin/env bash
# Build mumbles.app and wrap it in a drag-to-Applications disk image.
# Runs on macOS only (py2app, sips, iconutil and hdiutil are all Apple tools).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c 'import sys; sys.path.insert(0, "."); from mumbles import __version__; print(__version__)')"
ARCH="$(uname -m)"
DMG_NAME="mumbles-${VERSION}-macos-${ARCH}"
STAGE="build/dmg"

say() { printf '\033[1m==>\033[0m %s\n' "$1"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "this script builds a macOS app and must run on macOS" >&2
  exit 1
fi

say "generating the app icon"
python3 packaging/make_icon.py build/mumbles.png
rm -rf build/mumbles.iconset
mkdir -p build/mumbles.iconset
for size in 16 32 128 256 512; do
  sips -z $size $size build/mumbles.png \
       --out "build/mumbles.iconset/icon_${size}x${size}.png" >/dev/null
  sips -z $((size * 2)) $((size * 2)) build/mumbles.png \
       --out "build/mumbles.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns build/mumbles.iconset -o packaging/mumbles.icns
say "icon: packaging/mumbles.icns"

if ! PYTHONPATH="$ROOT" python3 -c "import mumbles" 2>/dev/null; then
  echo "cannot import mumbles; run 'pip install .' in $ROOT first" >&2
  exit 1
fi

say "building mumbles.app (this takes a few minutes)"
# Build from a staging directory. setuptools reads pyproject.toml from the
# working directory and turns [project].dependencies into install_requires,
# which py2app then refuses to build against.
STAGE_BUILD="build/appbuild"
rm -rf "$STAGE_BUILD" dist/mumbles.app
mkdir -p "$STAGE_BUILD"
cp packaging/setup_app.py packaging/app_main.py "$STAGE_BUILD/"

(
  cd "$STAGE_BUILD"
  MUMBLES_SOURCE_ROOT="$ROOT" PYTHONPATH="$ROOT" python3 setup_app.py py2app
)

# py2app names the bundle after the entry script, so find whatever it built
# rather than assuming. Renaming the directory is safe: a bundle's identity
# comes from Info.plist, not from its folder name.
BUILT="$(find "$STAGE_BUILD/dist" -maxdepth 1 -name '*.app' -print -quit)"
if [[ -z "$BUILT" ]]; then
  echo "py2app did not produce an .app bundle" >&2
  ls -la "$STAGE_BUILD/dist" 2>/dev/null || true
  exit 1
fi
say "py2app built $(basename "$BUILT")"

mkdir -p dist
rm -rf dist/mumbles.app
cp -R "$BUILT" dist/mumbles.app

# py2app writes a bundle whose signature is stale by the time we finish
# touching it. An ad-hoc signature is what lets macOS run it at all; it is
# not a Developer ID signature and does not clear Gatekeeper on its own.
say "ad-hoc signing the bundle"
codesign --force --deep --sign - dist/mumbles.app || \
  echo "warning: ad-hoc signing failed; the app may not launch" >&2

say "staging the disk image"
rm -rf "$STAGE" "dist/${DMG_NAME}.dmg"
mkdir -p "$STAGE"
cp -R dist/mumbles.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"

cat > "$STAGE/READ ME FIRST.txt" <<'NOTE'
mumbles - local voice dictation
===============================

1. Drag mumbles.app onto the Applications folder shown here.

2. THE FIRST LAUNCH IS DIFFERENT. This app is not signed with a paid Apple
   Developer certificate, so macOS will refuse to open it normally and may
   say it is "damaged". It is not. To get past this:

       Right-click mumbles.app in Applications, choose Open,
       then click Open in the dialog.

   If macOS still refuses, open Terminal and run:

       xattr -dr com.apple.quarantine /Applications/mumbles.app

   You only have to do this once.

3. mumbles lives in the menu bar - look for the microphone icon. There is no
   Dock icon and no window.

4. macOS will ask for permissions the first time you use it. Grant all three,
   under System Settings > Privacy & Security:

       Microphone        - to hear you
       Input Monitoring  - to see the global hotkey
       Accessibility     - to paste the text for you

   If the hotkey does nothing, Input Monitoring is the one to check.

5. Hold Command-Shift-Space, talk, and let go. The text is pasted wherever
   your cursor is. The first dictation downloads a speech model (about
   150 MB) and so takes a moment; after that it is fast and works offline.

Everything runs on this Mac. No account, no subscription, no audio uploaded.
NOTE

say "creating ${DMG_NAME}.dmg"
hdiutil create -volname "mumbles" -srcfolder "$STAGE" -ov -format ULFO \
  "dist/${DMG_NAME}.dmg"

say "done: dist/${DMG_NAME}.dmg"
du -h "dist/${DMG_NAME}.dmg" | cut -f1
