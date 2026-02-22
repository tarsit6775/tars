#!/bin/bash
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
        echo "Rotated $log_file (was ${size_mb}MB)"
    fi
done
