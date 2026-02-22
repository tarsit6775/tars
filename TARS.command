#!/bin/bash
# TARS Service — double-click to run, or run from Terminal
# This .command file opens in Terminal.app automatically on macOS
cd /Users/abdullah/Downloads/tars-main
echo ""
echo "  ████████╗ █████╗ ██████╗ ███████╗"
echo "  ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝"
echo "     ██║   ███████║██████╔╝███████╗"
echo "     ██║   ██╔══██║██╔══██╗╚════██║"
echo "     ██║   ██║  ██║██║  ██║███████║"
echo "     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝"
echo ""
echo "  24/7 Service — Auto-restart + Auto-reload"
echo "  Press Ctrl+C to stop"
echo ""
exec .venv/bin/python -u tars_runner.py "$@"
