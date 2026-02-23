"""Send Task 2 to TARS."""
import asyncio
import websockets
import json
import os

TASK = (
    "Sign up for (or log into) the OpenAI developer platform and get me an API key. "
    "Try signing in with Google (tarsitsales@gmail.com) first. "
    "If that doesn't work, sign up with email tarsitgroup@outlook.com, password 'Tars.OpenAI2026!'.\n\n"
    "After you're in the platform dashboard:\n"
    "1) Go to API Keys section (usually under Settings or the sidebar)\n"
    "2) Create a new API key:\n"
    "   - Name: 'tars-agent-key'\n"
    "   - Permissions: All (default)\n"
    "   - COPY the key immediately (starts with 'sk-' — only shown once)\n\n"
    "3) Go to Organization settings and note the Organization ID (starts with 'org-')\n\n"
    "4) Check if there's any billing/credits info visible — report the current balance/status\n\n"
    "5) Verify the key works by running this curl command:\n"
    "   curl https://api.openai.com/v1/models \\\n"
    "     -H 'Authorization: Bearer <YOUR_KEY>' \\\n"
    "     -s | head -50\n"
    "   (If it returns a list of models, the key works)\n\n"
    "Report back: API Key, Organization ID, billing status. "
    "Store everything as credentials for 'openai'."
)

async def send():
    token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".dashboard_token")
    with open(token_path) as f:
        token = f.read().strip()
    
    uri = f"ws://localhost:8421?token={token}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "send_task", "task": TASK}))
        print("✅ Task 2 (OpenAI) sent to TARS!")
        
        for _ in range(500):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=600)
                data = json.loads(msg)
                etype = data.get("type", "?")
                
                if etype == "agent_step":
                    d = data.get("data", {})
                    print(f"  🤖 [{d.get('agent','?')}] step {d.get('step','?')}")
                elif etype == "tool_result":
                    d = data.get("data", {})
                    name = d.get("tool_name", d.get("tool", "?"))
                    content = str(d.get("content", ""))[:150]
                    print(f"  🔧 [{name}] {content}")
                elif etype == "tool_use":
                    d = data.get("data", {})
                    print(f"  ⚙️  {d.get('tool_name','?')}({str(d.get('input',''))[:100]})")
                elif etype == "thinking":
                    d = data.get("data", {})
                    text = d.get("text", "")[:200]
                    if text:
                        print(f"  💭 {text}")
                elif etype == "status_change":
                    d = data.get("data", {})
                    status = d.get("status", "?")
                    if status == "online":
                        print(f"\n✅ Task complete!")
                        break
                elif etype == "response":
                    content = data.get("data", {}).get("content", "")
                    print(f"\n{'='*60}")
                    print(f"TARS: {content[:1000]}")
                    print(f"{'='*60}")
            except asyncio.TimeoutError:
                print("⏰ Timeout")
                break

asyncio.run(send())
