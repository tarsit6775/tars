"""Send a reply message to TARS."""
import asyncio
import websockets
import json
import os

MESSAGE = "The password is Tars.Dev2026!"

async def send():
    token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".dashboard_token")
    with open(token_path) as f:
        token = f.read().strip()
    
    uri = f"ws://localhost:8421?token={token}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "send_message",
            "message": MESSAGE
        }))
        print(f"✅ Sent: {MESSAGE}")
        
        # Listen for events
        for _ in range(200):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=600)
                data = json.loads(msg)
                etype = data.get("type", "?")
                
                if etype in ("thinking", "tool_use", "tool_result", "agent_step", "status_change"):
                    detail = str(data.get("data", ""))[:200]
                    print(f"  [{etype}] {detail}")
                elif etype == "response":
                    content = data.get("data", {}).get("content", "")
                    print(f"\n{'='*60}")
                    print(f"TARS: {content[:800]}")
                    print(f"{'='*60}")
                    break
            except asyncio.TimeoutError:
                print("⏰ Timeout")
                break

asyncio.run(send())
