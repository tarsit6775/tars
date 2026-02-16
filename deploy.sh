#!/bin/bash
# ╔══════════════════════════════════════════╗
# ║   TARS Dashboard — Build & Deploy        ║
# ╚══════════════════════════════════════════╝
#
# Usage:
#   ./deploy.sh          # Build only (local)
#   ./deploy.sh railway   # Build + deploy to Railway

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"
RELAY_DIR="$SCRIPT_DIR/relay"

echo ""
echo "  TARS DASHBOARD BUILD"
echo "  ===================="
echo ""

# ── 1. Build React dashboard ───────────────
echo "  [1/3] Building dashboard..."
cd "$DASHBOARD_DIR"

if [ ! -d "node_modules" ]; then
    echo "        Installing dependencies..."
    npm install
fi

npm run build

echo "        Built to dashboard/dist/"

# ── 2. Copy dist to relay/static ───────────
echo "  [2/3] Copying build to relay/static..."
rm -rf "$RELAY_DIR/static"
cp -r "$DASHBOARD_DIR/dist" "$RELAY_DIR/static"
echo "        Done"

# ── 3. Deploy if requested ─────────────────
if [ "$1" = "railway" ]; then
    echo "  [3/3] Deploying to Railway..."
    cd "$SCRIPT_DIR"

    # Check for Railway CLI
    if ! command -v railway &> /dev/null; then
        echo ""
        echo "  [!] Railway CLI not found. Install it:"
        echo "      brew install railway"
        echo "      railway login"
        exit 1
    fi

    railway up
    echo ""
    echo "  Deployed! Set these Railway env vars:"
    echo "    TARS_RELAY_TOKEN   — shared secret for tunnel auth"
    echo "    TARS_PASSPHRASE    — dashboard login passphrase"
    echo "    TARS_JWT_SECRET    — JWT signing key (optional)"
    echo ""
    echo "  Then update config.yaml relay.url with your Railway URL"
    echo "  and run: python tunnel.py"
else
    echo "  [3/3] Skipping deploy (pass 'railway' to deploy)"
fi

echo ""
echo "  Done. Run locally with:"
echo "    python tars.py"
echo "    open http://localhost:8420"
echo ""
