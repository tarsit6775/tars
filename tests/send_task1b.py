"""Send a focused task to TARS via WebSocket."""
import asyncio
import websockets
import json
import sys
import os

TASK = """The GitHub repo 'tars-automation-hub' already exists at https://github.com/tarsit6775/tars-automation-hub (private, with README).

Now do these 2 remaining things:

1) GENERATE A FINE-GRAINED PERSONAL ACCESS TOKEN:
   - Already logged into GitHub on Chrome as tarsit6775
   - Go to Settings > Developer settings > Personal access tokens > Fine-grained tokens
   - Click 'Generate new token'
   - GitHub may ask for sudo verification — if it asks to "Verify via email", click it, then check Gmail (tarsitsales@gmail.com) for the verification code and enter it
   - Token name: 'tars-agent-token'
   - Expiration: 90 days
   - Repository access: 'Only select repositories' → select 'tars-automation-hub'
   - Permissions: Contents (Read and write), Metadata (Read-only), Webhooks (Read and write)
   - Generate and COPY the token value

2) SET UP A WEBHOOK on tars-automation-hub:
   - Go to https://github.com/tarsit6775/tars-automation-hub/settings/hooks/new
   - Payload URL: https://tars-production-58a6.up.railway.app/webhook/github
   - Content type: application/json
   - Secret: 'tars-webhook-secret-2026'
   - Events: 'Send me everything'
   - Click 'Add webhook'

Report back the Personal Access Token value."""

async def send():
    # Read token from .dashboard_token file
    token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".dashboard_token")
    try:
        with open(token_path) as f:
            token = f.read().strip()
    except FileNotFoundError:
        print("❌ No .dashboard_token file found. Is TARS running?")
        return
    
    uri = f"ws://localhost:8421?token={token}"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "send_task",
                "task": TASK
            }))
            print("✅ Task sent to TARS!")
            
            # Listen for events
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=600)
                    data = json.loads(msg)
                    etype = data.get("type", "?")
                    
                    if etype in ("thinking", "tool_use", "tool_result", "agent_step", "status_change", "task_received"):
                        detail = str(data.get("data", ""))[:200]
                        print(f"  [{etype}] {detail}")
                    elif etype == "response":
                        print(f"\n{'='*60}")
                        print(f"TARS RESPONSE: {data.get('data', {}).get('content', '')[:500]}")
                        print(f"{'='*60}")
                        break
                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for response")
                    break
    except Exception as e:
        print(f"❌ Connection error: {e}")

asyncio.run(send())
