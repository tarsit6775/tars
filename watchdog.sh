#!/bin/bash
# ╔══════════════════════════════════════════╗
# ║  TARS — Watchdog Install/Uninstall       ║
# ╚══════════════════════════════════════════╝
#
# Usage:
#   ./watchdog.sh install    — Install and start watchdog
#   ./watchdog.sh uninstall  — Stop and remove watchdog
#   ./watchdog.sh status     — Check if watchdog is running

PLIST_NAME="com.tars.agent.plist"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

case "${1:-status}" in
    install)
        echo "📦 Installing TARS watchdog..."
        
        # Unload first if already loaded
        launchctl unload "$PLIST_DST" 2>/dev/null
        
        # Copy plist
        cp "$PLIST_SRC" "$PLIST_DST"
        
        # Load it
        launchctl load "$PLIST_DST"
        
        echo "✅ Watchdog installed and started."
        echo "   TARS will auto-restart on crash and start on login."
        echo ""
        echo "   Check status: $0 status"
        echo "   Uninstall:    $0 uninstall"
        ;;
        
    uninstall)
        echo "🗑️  Removing TARS watchdog..."
        launchctl unload "$PLIST_DST" 2>/dev/null
        rm -f "$PLIST_DST"
        echo "✅ Watchdog removed. TARS will no longer auto-restart."
        ;;
        
    status)
        if launchctl list 2>/dev/null | grep -q "com.tars.agent"; then
            echo "✅ TARS watchdog is RUNNING"
            launchctl list | grep "com.tars.agent"
        else
            echo "❌ TARS watchdog is NOT running"
            echo "   Install with: $0 install"
        fi
        ;;
        
    *)
        echo "Usage: $0 {install|uninstall|status}"
        exit 1
        ;;
esac
