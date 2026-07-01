#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="StockResearcher"
BUNDLE_ID="com.caowei.StockResearcher"
MIN_SYSTEM_VERSION="14.0"
APP_VERSION="${APP_VERSION:-0.1.0}"
BUILD_CONFIGURATION="debug"

if [[ "$MODE" == "--package-only" || "$MODE" == "package" ]]; then
  BUILD_CONFIGURATION="release"
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/macos"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
BACKEND_BUILD_DIR="$ROOT_DIR/build/pyinstaller"
BACKEND_DIST="$BACKEND_BUILD_DIR/dist/research-agent-backend"
UV_BIN="${UV_BIN:-$(command -v uv 2>/dev/null || true)}"

if [[ -z "$UV_BIN" && -x /opt/homebrew/bin/uv ]]; then
  UV_BIN=/opt/homebrew/bin/uv
fi
if [[ -z "$UV_BIN" && -x /usr/local/bin/uv ]]; then
  UV_BIN=/usr/local/bin/uv
fi
if [[ -z "$UV_BIN" ]]; then
  echo "build requires uv; set UV_BIN or install uv" >&2
  exit 127
fi

pkill -x "$APP_NAME" >/dev/null 2>&1 || true
pkill -x "research-agent-backend" >/dev/null 2>&1 || true

"$UV_BIN" sync --group dev
rm -rf "$BACKEND_BUILD_DIR"
mkdir -p "$BACKEND_BUILD_DIR"
"$UV_BIN" run pyinstaller \
  --noconfirm \
  --clean \
  --distpath "$BACKEND_BUILD_DIR/dist" \
  --workpath "$BACKEND_BUILD_DIR/work" \
  "$ROOT_DIR/packaging/backend.spec"

swift build --package-path "$PACKAGE_DIR" -c "$BUILD_CONFIGURATION"
BUILD_BINARY="$(swift build --package-path "$PACKAGE_DIR" -c "$BUILD_CONFIGURATION" --show-bin-path)/$APP_NAME"

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS" "$APP_RESOURCES/backend"
cp "$BUILD_BINARY" "$APP_BINARY"
cp -R "$BACKEND_DIST/." "$APP_RESOURCES/backend/"
chmod +x "$APP_BINARY"
chmod +x "$APP_RESOURCES/backend/research-agent-backend"

cat >"$INFO_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "https://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>股票研报</string>
  <key>CFBundleShortVersionString</key>
  <string>$APP_VERSION</string>
  <key>CFBundleVersion</key>
  <string>$APP_VERSION</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>$MIN_SYSTEM_VERSION</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

open_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

case "$MODE" in
  --package-only|package)
    ;;
  run)
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    open_app
    sleep 2
    pgrep -x "$APP_NAME" >/dev/null
    ;;
  *)
    echo "usage: $0 [run|--package-only|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
