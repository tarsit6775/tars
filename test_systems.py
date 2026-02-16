#!/usr/bin/env python3
"""Quick test to verify all TARS modules work."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml

with open("config.yaml") as f:
    config = yaml.safe_load(f)
print("✅ Config loads")

from brain.tools import TARS_TOOLS
print(f"✅ {len(TARS_TOOLS)} tools defined")

from brain.prompts import TARS_SYSTEM_PROMPT
print(f"✅ System prompt loaded ({len(TARS_SYSTEM_PROMPT)} chars)")

from hands.terminal import run_terminal
r = run_terminal("echo TARS is alive")
print(f"✅ Terminal: {r['content']}")

from hands.mac_control import get_frontmost_app
r = get_frontmost_app()
print(f"✅ Mac control: frontmost app = {r['content']}")

from hands.file_manager import list_directory
r = list_directory(".")
print(f"✅ File manager works")

from memory.memory_manager import MemoryManager
mm = MemoryManager(config, ".")
print(f"✅ Memory manager: active project = {mm.get_active_project()}")

from voice.imessage_read import IMessageReader
ir = IMessageReader(config)
print(f"✅ iMessage reader: connected to chat.db")

from utils.safety import is_destructive
print(f"✅ Safety: 'rm -rf /' is destructive = {is_destructive('rm -rf /')}")

print()
print("🟢 ALL SYSTEMS GO — TARS is ready")
