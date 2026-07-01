#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT_DIR/dist/StockResearcher.app"
ARCHIVE="$ROOT_DIR/dist/StockResearcher-macOS.zip"
DMG="$ROOT_DIR/dist/StockResearcher-macOS.dmg"
DMG_ROOT="$ROOT_DIR/build/dmg-root"
IDENTITY="${CODESIGN_IDENTITY:--}"

"$ROOT_DIR/script/build_and_run.sh" --package-only

SIGN_ARGS=(--force --deep --sign "$IDENTITY")
if [[ "$IDENTITY" != "-" ]]; then
  SIGN_ARGS+=(--options runtime --timestamp)
fi
codesign "${SIGN_ARGS[@]}" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
spctl --assess --type execute --verbose=2 "$APP" || {
  if [[ "$IDENTITY" != "-" ]]; then exit 1; fi
}

rm -f "$ARCHIVE"
ditto -c -k --keepParent "$APP" "$ARCHIVE"

rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
ditto "$APP" "$DMG_ROOT/StockResearcher.app"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$DMG"
hdiutil create \
  -volname "Stock Researcher" \
  -srcfolder "$DMG_ROOT" \
  -ov \
  -format UDZO \
  "$DMG"

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  if [[ "$IDENTITY" == "-" ]]; then
    echo "NOTARY_PROFILE requires a Developer ID Application identity" >&2
    exit 2
  fi
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  rm -f "$ARCHIVE"
  ditto -c -k --keepParent "$APP" "$ARCHIVE"
fi

echo "$ARCHIVE"
echo "$DMG"
