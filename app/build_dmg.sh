#!/bin/bash
# ─────────────────────────────────────────────────────
# TARS Control — DMG Installer Builder
# Creates a drag-to-Applications DMG installer
# ─────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARS_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="TARS Control"
DMG_NAME="TARS-Control-Installer"
VERSION="1.0.0"
APP_PATH="$SCRIPT_DIR/dist/$APP_NAME.app"
DMG_DIR="$SCRIPT_DIR/dmg_staging"
DMG_OUT="$SCRIPT_DIR/dist/$DMG_NAME.dmg"

echo "╔══════════════════════════════════════════════╗"
echo "║     TARS Control — DMG Builder               ║"
echo "╚══════════════════════════════════════════════╝"

# Check app exists
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH not found!"
    echo "Run: pyinstaller app/tars_control.spec --distpath app/dist --workpath app/build"
    exit 1
fi

# Clean previous
rm -rf "$DMG_DIR" "$DMG_OUT"

# Create staging directory
echo "→ Creating staging directory..."
mkdir -p "$DMG_DIR"
cp -R "$APP_PATH" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"

# Create a README in the DMG
cat > "$DMG_DIR/README.txt" << 'EOF'
TARS Control — Setup Guide
═══════════════════════════

1. Drag "TARS Control.app" to the Applications folder
2. Open TARS Control from your Applications
3. The app lives in your menu bar (look for the 🤖 icon)

First Launch:
─────────────
• macOS may ask to allow the app — go to System Settings > Privacy & Security
• The app will auto-detect your TARS installation
• If TARS is not found, set TARS_DIR environment variable:
    export TARS_DIR=/path/to/tars

Menu Bar Controls:
──────────────────
  🤖  Default (disconnected)
  🟡  Tunnel connected, TARS idle
  🟢  TARS running
  🟠  Reconnecting...
  🔴  Error

• Start Tunnel — connects your Mac to the Railway cloud relay
• Start TARS — launches TARS automation via the cloud
• Kill Switch — emergency stop for all TARS processes
• Open Dashboard — opens the Railway web dashboard
• View Logs — shows tunnel output
• Settings — edit config.yaml

Requirements:
─────────────
• macOS 10.15 (Catalina) or later
• TARS project with config.yaml and tunnel.py
• Python 3.9+ virtual environment in TARS folder
• Internet connection for Railway cloud relay

Support: https://github.com/tars16775/tars
EOF

# Create the DMG
echo "→ Creating DMG..."
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_DIR" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "$DMG_OUT" 2>&1

# Clean staging
rm -rf "$DMG_DIR"

# Report
DMG_SIZE=$(du -h "$DMG_OUT" | cut -f1)
echo ""
echo "✅ DMG created successfully!"
echo "   Path: $DMG_OUT"
echo "   Size: $DMG_SIZE"
echo ""
echo "To install: Open the DMG and drag TARS Control to Applications"
