"""Quick health check — verify all TARS imports and subsystems."""
import sys, os

checks = []

# 1. Core imports
try:
    from brain.llm_client import LLMClient
    from brain.planner import TARSBrain
    from executor import ToolExecutor
    checks.append("✅ Brain + Executor")
except Exception as e:
    checks.append(f"❌ Brain/Executor: {e}")

# 2. Agents
try:
    from agents.base_agent import BaseAgent
    from hands.browser_agent import BrowserAgent, BROWSER_TOOLS
    checks.append(f"✅ Agents (Browser: {len(BROWSER_TOOLS)} tools)")
except Exception as e:
    checks.append(f"❌ Agents: {e}")

# 3. Browser
try:
    from hands.browser import act_goto, act_inspect_page, act_solve_captcha
    checks.append("✅ Browser + CAPTCHA solver")
except Exception as e:
    checks.append(f"❌ Browser: {e}")

# 4. iMessage
try:
    from voice.imessage_read import IMessageReader
    from voice.imessage_send import IMessageSender
    checks.append("✅ iMessage read/send")
except Exception as e:
    checks.append(f"❌ iMessage: {e}")

# 5. Config
try:
    import yaml
    with open('config.yaml') as f:
        cfg = yaml.safe_load(f)
    provider = list(cfg.keys())[0]
    model = cfg.get('anthropic', cfg.get('groq', {})).get('heavy_model', '?')
    phone = cfg.get('owner_phone', '?')
    checks.append(f"✅ Config (provider={provider}, model={model}, phone={phone})")
except Exception as e:
    checks.append(f"❌ Config: {e}")

# 6. Tunnel
try:
    import tunnel
    checks.append("✅ Tunnel module")
except Exception as e:
    checks.append(f"❌ Tunnel: {e}")

print("=" * 50)
print("  TARS HEALTH CHECK")
print("=" * 50)
for c in checks:
    print(f"  {c}")
print("=" * 50)
all_ok = all(c.startswith("✅") for c in checks)
print(f"  {'ALL SYSTEMS GO' if all_ok else 'ISSUES FOUND'}")
print("=" * 50)
