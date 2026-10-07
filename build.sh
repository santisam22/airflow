#!/bin/zsh
# Builds dist/Airflow.dmg plus the signed self-update files (dist/Airflow-update.zip and
# dist/update.json).  Usage: ./build.sh
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
PY=$ROOT/.venv.nosync/bin/python
REPO=santisam22/airflow
VERSION=$($PY -c "from airflow.config import VERSION; print(VERSION)")
NOTES=$(head -1 WHATS_NEW.txt 2>/dev/null || true)
# Build outside Documents: iCloud Drive adds file metadata (and " 2" duplicates) that
# break code signing. Only the finished results are copied to dist/.
BUILD="$HOME/Library/Caches/AirflowBuild"
DIST=$ROOT/dist
rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD/icon/Airflow.iconset" "$DIST"
echo "→ Building Airflow $VERSION"

echo "→ Running play tests…"
$PY tests/test_flow.py
$PY tests/test_play.py

echo "→ Drawing icon…"
$PY tools/make_icon.py "$BUILD/icon/icon_1024.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BUILD/icon/icon_1024.png" --out "$BUILD/icon/Airflow.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$BUILD/icon/icon_1024.png" --out "$BUILD/icon/Airflow.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$BUILD/icon/Airflow.iconset" -o "$BUILD/icon/Airflow.icns"

echo "→ Bundling the app…"
$PY -m PyInstaller --noconfirm --clean --windowed --log-level WARN \
  --name Airflow \
  --icon "$BUILD/icon/Airflow.icns" \
  --osx-bundle-identifier com.santisam22.airflow \
  --exclude-module tkinter \
  --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
  "$ROOT/main.py"
APP="$BUILD/dist/Airflow.app"
PLIST="$APP/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"
plutil -replace LSMinimumSystemVersion -string "12.0" "$PLIST"
# The "what's new" line, shown in the game after it updates itself.
plutil -replace AirflowWhatsNew -string "$NOTES" "$PLIST"

echo "→ Signing…"
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "→ Creating disk image…"
STAGE="$BUILD/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Airflow" -srcfolder "$STAGE" -ov -format UDZO -quiet "$DIST/Airflow.dmg"

echo "→ Signing update package…"
ditto -c -k --keepParent "$APP" "$DIST/Airflow-update.zip"
if SIG=$(swift macos/sign_tool.swift sign "$DIST/Airflow-update.zip"); then
  $PY - "$VERSION" "https://github.com/$REPO/releases/download/v$VERSION/Airflow-update.zip" "$SIG" "$NOTES" > "$DIST/update.json" <<'PY'
import json, sys
version, url, signature, notes = sys.argv[1:]
print(json.dumps({"version": version, "url": url, "signature": signature, "notes": notes}, indent=2))
PY
else
  echo "  (no signing key in this Keychain: skipped update.json; existing installs won't see this build)"
  rm -f "$DIST/Airflow-update.zip"
fi

echo "✓ Done: Airflow $VERSION → dist/Airflow.dmg ($(du -h "$DIST/Airflow.dmg" | cut -f1))"
