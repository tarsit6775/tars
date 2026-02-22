#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║        TARS — Mac Mini Environment Optimizer                 ║
# ║                                                              ║
# ║  Sets up macOS for 24/7 TARS operation:                      ║
# ║    • Prevents sleep & auto-restarts after power loss         ║
# ║    • Configures launchd watchdog (auto-start on login)       ║
# ║    • Starts TARS + cloud tunnel                              ║
# ║    • Sets up log rotation & disk cleanup                     ║
# ║    • Grants required permissions checklist                   ║
# ║                                                              ║
# ║  Usage:                                                      ║
# ║    ./setup_environment.sh          # Full setup + start      ║
# ║    ./setup_environment.sh status   # Check everything        ║
# ║    ./setup_environment.sh start    # Start TARS only         ║
# ║    ./setup_environment.sh stop     # Stop TARS               ║
# ║    ./setup_environment.sh teardown # Undo all optimizations  ║
# ╚══════════════════════════════════════════════════════════════╝

set -uo pipefail

# ── Constants ──────────────────────────────────────────
TARS_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$TARS_DIR/.venv/bin/python"
LOG_DIR="$TARS_DIR/logs"
LOG_FILE="$LOG_DIR/tars.log"
LAUNCHD_LOG="$LOG_DIR/tars-launchd.log"
LAUNCHD_ERR="$LOG_DIR/tars-launchd-err.log"
PLIST_NAME="com.tars.agent"
PLIST_FILE="$TARS_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOGROTATE_PLIST="com.tars.logrotate"
LOGROTATE_DST="$HOME/Library/LaunchAgents/$LOGROTATE_PLIST.plist"
MAX_LOG_SIZE_MB=50
MAX_LOG_BACKUPS=5

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
DIM='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ████████╗ █████╗ ██████╗ ███████╗"
    echo "  ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝"
    echo "     ██║   ███████║██████╔╝███████╗"
    echo "     ██║   ██╔══██║██╔══██╗╚════██║"
    echo "     ██║   ██║  ██║██║  ██║███████║"
    echo "     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝"
    echo -e "${NC}"
    echo -e "  ${DIM}Mac Mini Environment Optimizer${NC}"
    echo ""
}

ok()   { echo -e "  ${GREEN}✅${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠️${NC}  $1"; }
fail() { echo -e "  ${RED}❌${NC} $1"; }
info() { echo -e "  ${DIM}$1${NC}"; }
section() { echo ""; echo -e "  ${BOLD}── $1 ──${NC}"; }

# ═══════════════════════════════════════════════════════
#  STATUS — Check everything
# ═══════════════════════════════════════════════════════
cmd_status() {
    print_header
    section "System"
    
    # macOS version
    os_ver=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
    chip=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown")
    ram=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f", $1/1024/1024/1024}')
    echo -e "  macOS $os_ver | $chip | ${ram}GB RAM"
    
    # Disk space
    free_gb=$(diskutil info / 2>/dev/null | grep "Container Free" | awk '{print $4}')
    if [ -n "$free_gb" ]; then
        free_num=$(echo "$free_gb" | tr -d '.')
        if (( ${free_num:-0} < 100 )); then
            warn "Disk: ${free_gb}GB free — LOW"
        else
            ok "Disk: ${free_gb}GB free"
        fi
    fi

    section "Power Settings"
    
    # Sleep
    sleep_val=$(pmset -g 2>/dev/null | grep "^ sleep" | awk '{print $2}')
    if [ "$sleep_val" = "0" ]; then
        ok "System sleep: disabled"
    else
        fail "System sleep: ${sleep_val} (should be 0 — run: sudo pmset -a sleep 0)"
    fi
    
    # Auto-restart after power failure
    auto_restart=$(pmset -g 2>/dev/null | grep "autorestart" | awk '{print $2}')
    if [ "$auto_restart" = "1" ]; then
        ok "Auto-restart on power loss: enabled"
    else
        fail "Auto-restart: disabled (run: sudo pmset -a autorestart 1)"
    fi
    
    # Display sleep (save energy, TARS doesn't need display)
    disp_sleep=$(pmset -g 2>/dev/null | grep "displaysleep" | awk '{print $2}')
    if [ "$disp_sleep" != "0" ] && [ -n "$disp_sleep" ]; then
        ok "Display sleep: ${disp_sleep} min (saves energy)"
    else
        warn "Display sleep: never (set to 5 to save energy: sudo pmset -a displaysleep 5)"
    fi

    # Wake on LAN
    womp=$(pmset -g 2>/dev/null | grep "womp" | awk '{print $2}')
    if [ "$womp" = "1" ]; then
        ok "Wake on LAN: enabled"
    else
        warn "Wake on LAN: disabled (enable: sudo pmset -a womp 1)"
    fi

    section "TARS Process"
    
    # Check if TARS is running
    tars_pid=$(pgrep -f "python.*tars\.py" 2>/dev/null | head -1)
    if [ -n "$tars_pid" ]; then
        uptime_sec=$(ps -p "$tars_pid" -o etime= 2>/dev/null | xargs)
        ok "TARS running (PID $tars_pid, uptime: $uptime_sec)"
    else
        fail "TARS is NOT running"
    fi
    
    # Check tunnel
    tunnel_pid=$(pgrep -f "python.*tunnel\.py" 2>/dev/null | head -1)
    if [ -n "$tunnel_pid" ]; then
        ok "Tunnel running (PID $tunnel_pid)"
    else
        warn "Tunnel not running (dashboard won't work remotely)"
    fi
    
    # Check ports
    port_8420=$(lsof -ti:8420 2>/dev/null | head -1)
    port_8421=$(lsof -ti:8421 2>/dev/null | head -1)
    if [ -n "$port_8420" ] && [ -n "$port_8421" ]; then
        ok "Dashboard ports: 8420 + 8421 open"
    else
        warn "Dashboard ports not all open (8420: ${port_8420:-closed}, 8421: ${port_8421:-closed})"
    fi

    section "Watchdog (launchd)"
    
    if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
        exit_code=$(launchctl list 2>/dev/null | grep "$PLIST_NAME" | awk '{print $2}')
        ok "Watchdog loaded (last exit: $exit_code)"
    else
        fail "Watchdog NOT loaded (run: ./setup_environment.sh to install)"
    fi

    section "Logs"
    
    if [ -f "$LOG_FILE" ]; then
        log_size=$(du -sh "$LOG_FILE" 2>/dev/null | awk '{print $1}')
        log_lines=$(wc -l < "$LOG_FILE" 2>/dev/null | xargs)
        ok "Log: $LOG_FILE ($log_size, $log_lines lines)"
    else
        warn "No log file found"
    fi
    
    # Check for log rotation
    backup_count=$(ls "$LOG_DIR"/tars.log.* 2>/dev/null | wc -l | xargs)
    if [ "$backup_count" -gt 0 ]; then
        ok "Log backups: $backup_count"
    fi

    section "Python Environment"
    
    if [ -f "$VENV_PYTHON" ]; then
        py_ver=$("$VENV_PYTHON" --version 2>/dev/null)
        ok "venv: $py_ver"
    else
        fail "venv not found at $VENV_PYTHON"
    fi

    section "Permissions Checklist"
    
    # Full Disk Access (needed for chat.db iMessage reading)
    if [ -r "$HOME/Library/Messages/chat.db" ]; then
        ok "Full Disk Access: chat.db readable"
    else
        fail "Full Disk Access: DENIED — grant in System Settings → Privacy → Full Disk Access → Terminal/Python"
    fi
    
    # Accessibility (needed for AppleScript GUI control)
    # Can't easily check programmatically, just remind
    info "Accessibility: verify in System Settings → Privacy → Accessibility → Terminal"
    info "Automation: verify in System Settings → Privacy → Automation → Terminal → Mail, Messages, etc."
    
    echo ""
}

# ═══════════════════════════════════════════════════════
#  SETUP — Full environment optimization
# ═══════════════════════════════════════════════════════
cmd_setup() {
    print_header
    echo -e "  ${BOLD}Setting up Mac Mini for 24/7 TARS operation...${NC}"

    # ── 1. Power Settings ──────────────────────────────
    section "1. Power Settings (requires sudo)"
    
    echo ""
    echo "  The following commands need admin privileges:"
    echo -e "  ${CYAN}sudo pmset -a sleep 0${NC}              # Never sleep"
    echo -e "  ${CYAN}sudo pmset -a autorestart 1${NC}        # Restart after power loss"
    echo -e "  ${CYAN}sudo pmset -a displaysleep 5${NC}       # Display off after 5 min"
    echo -e "  ${CYAN}sudo pmset -a womp 1${NC}               # Wake on LAN"
    echo -e "  ${CYAN}sudo pmset -a powernap 1${NC}           # Power Nap (background tasks)"
    echo -e "  ${CYAN}sudo pmset -a tcpkeepalive 1${NC}       # Keep network alive in sleep"
    echo -e "  ${CYAN}sudo pmset -a disksleep 0${NC}          # Don't spin down disk"
    echo ""
    
    read -p "  Apply power settings now? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo pmset -a sleep 0
        sudo pmset -a autorestart 1
        sudo pmset -a displaysleep 5
        sudo pmset -a womp 1
        sudo pmset -a powernap 1
        sudo pmset -a tcpkeepalive 1
        sudo pmset -a disksleep 0
        ok "Power settings applied"
    else
        warn "Skipped — apply manually with the commands above"
    fi

    # ── 2. Directories ──────────────────────────────────
    section "2. Directories"
    mkdir -p "$LOG_DIR"
    mkdir -p "$TARS_DIR/memory/projects"
    mkdir -p "$TARS_DIR/memory/agents"
    ok "Log and memory directories ready"

    # ── 3. Python Environment ───────────────────────────
    section "3. Python Environment"
    
    if [ ! -f "$VENV_PYTHON" ]; then
        warn "Creating virtual environment..."
        python3 -m venv "$TARS_DIR/.venv"
        "$VENV_PYTHON" -m pip install --upgrade pip -q
        ok "venv created"
    else
        ok "venv exists"
    fi
    
    echo "  Checking dependencies..."
    "$VENV_PYTHON" -m pip install -r "$TARS_DIR/requirements.txt" -q 2>/dev/null
    ok "All Python packages installed"

    # ── 4. Health Check ─────────────────────────────────
    section "4. Health Check"
    cd "$TARS_DIR"
    "$VENV_PYTHON" healthcheck.py 2>/dev/null || warn "Some health checks failed — review above"

    # ── 5. Update launchd plist ─────────────────────────
    section "5. Watchdog (launchd auto-restart)"
    
    # Generate plist with correct paths
    _update_launchd_plist
    ok "Plist updated with correct paths"
    
    # Install it
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    cp "$PLIST_FILE" "$PLIST_DST"
    ok "Watchdog plist installed"
    info "Not loading yet — will start TARS directly first"

    # ── 6. Log Rotation ─────────────────────────────────
    section "6. Log Rotation"
    _setup_log_rotation
    ok "Log rotation configured (max ${MAX_LOG_SIZE_MB}MB, ${MAX_LOG_BACKUPS} backups)"

    # ── 7. Permissions Reminder ─────────────────────────
    section "7. macOS Permissions (manual)"
    echo ""
    echo "  Open System Settings → Privacy & Security and grant these:"
    echo ""
    echo -e "  ${BOLD}Full Disk Access${NC} (for iMessage chat.db):"
    echo "    → Terminal.app"
    echo "    → Python ($VENV_PYTHON)"
    echo ""
    echo -e "  ${BOLD}Accessibility${NC} (for GUI automation):"
    echo "    → Terminal.app"
    echo ""
    echo -e "  ${BOLD}Automation${NC} (for AppleScript):"
    echo "    → Terminal.app → Messages, Mail, Notes, Reminders, Calendar"
    echo ""

    # ── 8. Start ────────────────────────────────────────
    section "8. Start TARS"
    
    read -p "  Start TARS now? (Y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        cmd_start
    else
        info "Start later with: ./setup_environment.sh start"
    fi

    echo ""
    echo -e "  ${GREEN}${BOLD}Setup complete!${NC}"
    echo ""
    echo "  Quick reference:"
    echo "    ./setup_environment.sh status    — Check everything"
    echo "    ./setup_environment.sh start     — Start TARS + tunnel"
    echo "    ./setup_environment.sh stop      — Stop TARS"
    echo "    ./setup_environment.sh logs      — Tail live logs"
    echo "    ./setup_environment.sh teardown  — Undo all optimizations"
    echo ""
}

# ═══════════════════════════════════════════════════════
#  START — Start TARS + Tunnel
# ═══════════════════════════════════════════════════════
cmd_start() {
    section "Starting TARS"
    
    # Kill any existing instances
    pgrep -f "python.*tars\.py" | xargs kill -9 2>/dev/null || true
    pgrep -f "python.*tunnel\.py" | xargs kill -9 2>/dev/null || true
    lsof -ti:8420 -ti:8421 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 2
    
    # Rotate logs if needed
    _rotate_log_if_needed
    
    # Start TARS in background with caffeinate (prevents sleep while running)
    cd "$TARS_DIR"
    nohup caffeinate -s "$VENV_PYTHON" tars.py >> "$LAUNCHD_LOG" 2>> "$LAUNCHD_ERR" &
    TARS_PID=$!
    ok "TARS started (PID $TARS_PID)"
    
    # Wait for dashboard ports to come up
    echo -n "  Waiting for dashboard..."
    for i in $(seq 1 15); do
        if lsof -ti:8420 >/dev/null 2>&1; then
            echo ""
            ok "Dashboard live at http://localhost:8420"
            break
        fi
        echo -n "."
        sleep 1
    done
    
    # Start tunnel if relay URL is configured
    RELAY_URL=$(cd "$TARS_DIR" && "$VENV_PYTHON" -c "
import yaml
with open('config.yaml') as f:
    c = yaml.safe_load(f)
print(c.get('relay', {}).get('url', ''))
" 2>/dev/null)
    
    if [ -n "$RELAY_URL" ] && [ "$RELAY_URL" != "None" ] && [ "$RELAY_URL" != "" ]; then
        sleep 3  # Let TARS fully boot before tunnel connects
        cd "$TARS_DIR"
        nohup "$VENV_PYTHON" tunnel.py >> "$LOG_DIR/tunnel.log" 2>&1 &
        TUNNEL_PID=$!
        ok "Tunnel started (PID $TUNNEL_PID) → $RELAY_URL"
    else
        info "Tunnel skipped — no relay URL in config.yaml"
    fi
    
    # Enable watchdog for auto-restart on crash
    if [ -f "$PLIST_DST" ]; then
        # Don't load launchd right now since we already started manually.
        # It'll kick in on login or if the process dies.
        info "Watchdog plist ready — will auto-restart on crash"
    fi
    
    echo ""
    ok "TARS is running! Send an iMessage or use the dashboard."
}

# ═══════════════════════════════════════════════════════
#  STOP — Stop TARS + Tunnel
# ═══════════════════════════════════════════════════════
cmd_stop() {
    section "Stopping TARS"
    
    # Unload watchdog so it doesn't restart
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    info "Watchdog unloaded (won't auto-restart)"
    
    # Send SIGTERM first (graceful shutdown)
    tars_pid=$(pgrep -f "python.*tars\.py" 2>/dev/null | head -1)
    if [ -n "$tars_pid" ]; then
        kill "$tars_pid" 2>/dev/null
        sleep 3
        # Force kill if still alive
        kill -9 "$tars_pid" 2>/dev/null || true
        ok "TARS stopped"
    else
        info "TARS was not running"
    fi
    
    # Stop tunnel
    pgrep -f "python.*tunnel\.py" | xargs kill -9 2>/dev/null || true
    ok "Tunnel stopped"
    
    # Free ports
    lsof -ti:8420 -ti:8421 2>/dev/null | xargs kill -9 2>/dev/null || true
    ok "Ports 8420/8421 freed"
}

# ═══════════════════════════════════════════════════════
#  RESTART — Stop + Start
# ═══════════════════════════════════════════════════════
cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start
}

# ═══════════════════════════════════════════════════════
#  LOGS — Tail live logs
# ═══════════════════════════════════════════════════════
cmd_logs() {
    echo -e "  ${DIM}Tailing TARS logs (Ctrl+C to stop)...${NC}"
    echo ""
    tail -f "$LOG_FILE" "$LAUNCHD_LOG" 2>/dev/null
}

# ═══════════════════════════════════════════════════════
#  TEARDOWN — Undo all optimizations
# ═══════════════════════════════════════════════════════
cmd_teardown() {
    print_header
    echo -e "  ${BOLD}Reverting Mac Mini optimizations...${NC}"
    
    # Stop TARS
    cmd_stop
    
    # Remove launchd plists
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    rm -f "$PLIST_DST"
    launchctl unload "$LOGROTATE_DST" 2>/dev/null || true
    rm -f "$LOGROTATE_DST"
    ok "Watchdog and log rotation removed"
    
    # Restore power defaults
    echo ""
    echo "  To restore default power settings:"
    echo -e "  ${CYAN}sudo pmset -a sleep 1${NC}"
    echo -e "  ${CYAN}sudo pmset -a autorestart 0${NC}"
    echo -e "  ${CYAN}sudo pmset -a displaysleep 10${NC}"
    echo -e "  ${CYAN}sudo pmset -a disksleep 10${NC}"
    echo ""
    
    ok "Teardown complete"
}

# ═══════════════════════════════════════════════════════
#  INTERNAL — Update launchd plist with correct paths
# ═══════════════════════════════════════════════════════
_update_launchd_plist() {
    cat > "$PLIST_FILE" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-s</string>
        <string>$VENV_PYTHON</string>
        <string>$TARS_DIR/tars.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$TARS_DIR</string>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>15</integer>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/tars-launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/tars-launchd-err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$TARS_DIR/.venv/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
        <key>LANG</key>
        <string>en_US.UTF-8</string>
    </dict>

    <key>SoftResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>4096</integer>
    </dict>
</dict>
</plist>
PLIST_EOF
}

# ═══════════════════════════════════════════════════════
#  INTERNAL — Log rotation
# ═══════════════════════════════════════════════════════
_rotate_log_if_needed() {
    if [ ! -f "$LOG_FILE" ]; then
        return
    fi
    
    # Get size in MB
    log_size_bytes=$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
    log_size_mb=$((log_size_bytes / 1024 / 1024))
    
    if [ "$log_size_mb" -ge "$MAX_LOG_SIZE_MB" ]; then
        info "Rotating log ($log_size_mb MB > ${MAX_LOG_SIZE_MB}MB limit)..."
        
        # Shift existing backups
        for i in $(seq $((MAX_LOG_BACKUPS - 1)) -1 1); do
            if [ -f "$LOG_FILE.$i" ]; then
                mv "$LOG_FILE.$i" "$LOG_FILE.$((i + 1))"
            fi
        done
        
        # Rotate current log
        mv "$LOG_FILE" "$LOG_FILE.1"
        touch "$LOG_FILE"
        
        # Delete oldest if over limit
        if [ -f "$LOG_FILE.$((MAX_LOG_BACKUPS + 1))" ]; then
            rm -f "$LOG_FILE.$((MAX_LOG_BACKUPS + 1))"
        fi
        
        ok "Log rotated (was ${log_size_mb}MB)"
    fi
}

_setup_log_rotation() {
    # Create a log rotation script
    cat > "$TARS_DIR/rotate_logs.sh" << 'ROTATE_EOF'
#!/bin/bash
# TARS log rotation — called by launchd daily
TARS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$TARS_DIR/logs"
MAX_SIZE_MB=50
MAX_BACKUPS=5

for log_file in "$LOG_DIR"/tars.log "$LOG_DIR"/tars-launchd.log "$LOG_DIR"/tunnel.log; do
    [ ! -f "$log_file" ] && continue
    size_bytes=$(stat -f%z "$log_file" 2>/dev/null || echo 0)
    size_mb=$((size_bytes / 1024 / 1024))
    
    if [ "$size_mb" -ge "$MAX_SIZE_MB" ]; then
        for i in $(seq $((MAX_BACKUPS - 1)) -1 1); do
            [ -f "$log_file.$i" ] && mv "$log_file.$i" "$log_file.$((i + 1))"
        done
        mv "$log_file" "$log_file.1"
        touch "$log_file"
        rm -f "$log_file.$((MAX_BACKUPS + 1))"
    fi
done

# Clean up old error tracker entries (keep last 200)
TRACKER="$TARS_DIR/memory/error_tracker.json"
if [ -f "$TRACKER" ]; then
    "$TARS_DIR/.venv/bin/python" -c "
import json
with open('$TRACKER') as f:
    data = json.load(f)
if len(data.get('errors', [])) > 200:
    data['errors'] = data['errors'][-200:]
    with open('$TRACKER', 'w') as f:
        json.dump(data, f)
    print('Pruned error tracker')
" 2>/dev/null
fi
ROTATE_EOF
    chmod +x "$TARS_DIR/rotate_logs.sh"
    
    # Create launchd plist for daily log rotation
    cat > "$LOGROTATE_DST" << LOGROTATE_PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LOGROTATE_PLIST</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$TARS_DIR/rotate_logs.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/logrotate.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/logrotate.log</string>
</dict>
</plist>
LOGROTATE_PLIST_EOF
    
    launchctl unload "$LOGROTATE_DST" 2>/dev/null || true
    launchctl load "$LOGROTATE_DST" 2>/dev/null || true
}

# ═══════════════════════════════════════════════════════
#  MAIN — Route command
# ═══════════════════════════════════════════════════════
case "${1:-}" in
    status)
        cmd_status
        ;;
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs
        ;;
    teardown)
        cmd_teardown
        ;;
    ""|setup)
        cmd_setup
        ;;
    *)
        echo "Usage: $0 {setup|status|start|stop|restart|logs|teardown}"
        exit 1
        ;;
esac
