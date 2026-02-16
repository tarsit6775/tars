#!/bin/bash
# ─────────────────────────────────────────────────────
# TARS Control — Full Build Script
# Builds the .app and DMG in one command
# Usage: ./app/build.sh
# ─────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARS_DIR="$(dirname "$SCRIPT_DIR")"
cd "$TARS_DIR"

echo "╔══════════════════════════════════════════════╗"
echo "║     TARS Control — Full Build Pipeline       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 1. Ensure venv and dependencies
echo "→ [1/4] Checking dependencies..."
if [ ! -f "venv/bin/python" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q rumps pyinstaller pyyaml 2>/dev/null

# 2. Generate icon
echo "→ [2/4] Generating icon..."
python app/generate_icon.py

# Convert to .icns
mkdir -p app/icon.iconset
for SIZE in 16 32 64 128 256 512; do
    sips -z $SIZE $SIZE app/icon.png --out "app/icon.iconset/icon_${SIZE}x${SIZE}.png" >/dev/null 2>&1 || true
done
cp app/icon.png app/icon.iconset/icon_16x16@2x.png 2>/dev/null || true
sips -z 32 32 app/icon.png --out app/icon.iconset/icon_16x16@2x.png >/dev/null 2>&1 || true
sips -z 64 64 app/icon.png --out app/icon.iconset/icon_32x32@2x.png >/dev/null 2>&1 || true
sips -z 256 256 app/icon.png --out app/icon.iconset/icon_128x128@2x.png >/dev/null 2>&1 || true
sips -z 512 512 app/icon.png --out app/icon.iconset/icon_256x256@2x.png >/dev/null 2>&1 || true
cp app/icon.png app/icon.iconset/icon_512x512.png 2>/dev/null || true
cp app/icon.png app/icon.iconset/icon_512x512@2x.png 2>/dev/null || true
iconutil -c icns app/icon.iconset -o app/icon.icns 2>/dev/null || true
rm -rf app/icon.iconset
echo "  Icon ready ✓"

# 3. Build .app
echo "→ [3/4] Building TARS Control.app..."
pyinstaller app/tars_control.spec \
    --distpath app/dist \
    --workpath app/build \
    --clean \
    --noconfirm 2>&1 | grep -E "(INFO|ERROR|WARNING)" | tail -5

echo "  App built ✓  ($(du -sh app/dist/'TARS Control.app' | cut -f1))"

# 4. Build DMG
echo "→ [4/4] Creating DMG installer..."
bash app/build_dmg.sh 2>&1 | tail -3

echo ""
echo "════════════════════════════════════════════════"
echo "  Build complete!"
echo "  App:  app/dist/TARS Control.app"
echo "  DMG:  app/dist/TARS-Control-Installer.dmg"
echo "════════════════════════════════════════════════"
