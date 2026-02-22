#!/bin/bash
TARS_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMAND_FILE="$TARS_DIR/TARS.command"

_kill_tars() {
    pkill -f "tars_runner" 2>/dev/null || true
    pkill -f "caffeinate.*tars" 2>/dev/null || true
    pkill -f "python.*tars.py" 2>/dev/null || true
    lsof -ti:8420 -ti:8421 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 1
}

_is_running() {
    pgrep -f "tars_runner" > /dev/null 2>&1
}

case "${1:-status}" in
    start)
        echo ""
        if _is_running; then
            echo "  TARS is already running! Use ./watchdog.sh restart"
        else
            echo "  Starting TARS in Terminal.app..."
            _kill_tars
            chmod +x "$COMMAND_FILE"
            open -a Terminal "$COMMAND_FILE"
            sleep 3
            if _is_running; then
                PID=$(pgrep -f "tars_runner" | head -1)
                echo "  TARS started! (PID: $PID)"
                echo "  Dashboard: http://localhost:8420"
            else
                echo "  Failed to start. Check /tmp/tars-logs/tars-service.log"
            fi
        fi
        echo ""
        ;;
    stop)
        echo "  Stopping TARS..."
        _kill_tars
        echo "  Stopped."
        ;;
    restart)
        echo "  Restarting TARS..."
        _kill_tars
        sleep 2
        chmod +x "$COMMAND_FILE"
        open -a Terminal "$COMMAND_FILE"
        sleep 5
        if _is_running; then
            PID=$(pgrep -f "tars_runner" | head -1)
            echo "  TARS restarted! (PID: $PID)"
        else
            echo "  Failed to restart."
        fi
        ;;
    status)
        echo ""
        if _is_running; then
            RUNNER_PID=$(pgrep -f "tars_runner" | head -1)
            TARS_PID=$(pgrep -f "caffeinate.*tars" | head -1 2>/dev/null)
            [ -n "$RUNNER_PID" ] && ELAPSED=$(ps -o etime= -p "$RUNNER_PID" 2>/dev/null | xargs)
            echo "  TARS is RUNNING"
            echo "  Runner PID:  $RUNNER_PID"
            [ -n "$TARS_PID" ] && echo "  TARS PID:    $TARS_PID"
            [ -n "$ELAPSED" ] && echo "  Uptime:      $ELAPSED"
            echo "  Dashboard:   http://localhost:8420"
            if lsof -i :8420 > /dev/null 2>&1; then
                echo "  Port 8420:   Listening"
            else
                echo "  Port 8420:   Starting up..."
            fi
        else
            echo "  TARS is NOT running"
            echo "  Run ./watchdog.sh start"
        fi
        echo ""
        ;;
    install)
        echo "  Setting up TARS auto-start..."
        chmod +x "$COMMAND_FILE"
        osascript -e 'tell application "System Events" to delete login item "TARS.command"' 2>/dev/null || true
        osascript -e 'tell application "System Events" to delete login item "TARS Agent"' 2>/dev/null || true
        osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$COMMAND_FILE\", hidden:false, name:\"TARS Agent\"}"
        launchctl unload "$HOME/Library/LaunchAgents/com.tars.agent.plist" 2>/dev/null
        rm -f "$HOME/Library/LaunchAgents/com.tars.agent.plist" 2>/dev/null
        echo "  TARS auto-start installed!"
        echo "  TARS will start in Terminal.app when you log in."
        ;;
    uninstall)
        echo "  Removing TARS auto-start..."
        osascript -e 'tell application "System Events" to delete login item "TARS.command"' 2>/dev/null || true
        osascript -e 'tell application "System Events" to delete login item "TARS Agent"' 2>/dev/null || true
        _kill_tars
        echo "  Auto-start removed."
        ;;
    logs)
        echo "  TARS Live Logs (Ctrl+C to stop)"
        tail -f /tmp/tars-logs/tars-service.log /tmp/tars-logs/tars-stdout.log /tmp/tars-logs/tars-stderr.log 2>/dev/null
        ;;
    *)
        echo "Usage: ./watchdog.sh {start|stop|restart|status|install|uninstall|logs}"
        ;;
esac
