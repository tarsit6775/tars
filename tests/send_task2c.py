#!/usr/bin/env python3
"""Send Task 2 — OpenAI API key creation (simplified for autopilot)."""
import asyncio
import websockets
import json

TOKEN = "D6smbqYh0ioclLOSqRwKeviGA2X5Fnja"

async def send():
    uri = f"ws://localhost:8421?token={TOKEN}"
    async with websockets.connect(uri) as ws:
        # Simplified task — browser is already on platform.openai.com/api-keys
        task = {
            "type": "send_task",
            "task": (
                "Go to https://platform.openai.com/api-keys in Chrome. "
                "You are already logged in. "
                "Click the 'Create new secret key' button. "
                "In the dialog, name it 'tars-agent-key' and click Create. "
                "Copy the generated API key and report it back."
            )
        }
        await ws.send(json.dumps(task))
        print(f"✅ Task sent")
        # Wait for ack
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"Response: {resp}")
        except asyncio.TimeoutError:
            print("No ack (timeout)")

asyncio.run(send())
