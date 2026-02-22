#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  TARS Service — Opens in Terminal.app for 24/7 operation      ║
# ╠══════════════════════════════════════════════════════════════╣
# ║  This script is opened by launchd via `open -a Terminal`.     ║
# ║  It runs tars_runner.py which handles:                        ║
# ║   • Auto-restart on crash                                    ║
# ║   • Auto-reload on code changes                              ║
# ║   • Prevents Mac sleep (caffeinate)                          ║
# ║                                                              ║
# ║  You can also run this directly:                              ║
# ║    ./tars_service.sh                                         ║
# ╚══════════════════════════════════════════════════════════════╝

cd /Users/abdullah/Downloads/tars-main
exec .venv/bin/python -u tars_runner.py "$@"
