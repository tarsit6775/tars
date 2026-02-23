#!/usr/bin/env python3
"""Send Task 2 (OpenAI) - smarter version that accounts for existing session."""
import json
import time
import hashlib
import websocket

TOKEN_FILE = "/Users/abdullah/Downloads/tars-main/.dashboard_token"
with open(TOKEN_FILE) as f:
    token = f.read().strip()

ws_url = f"ws://localhost:8421?token={token}"

task = """Go to platform.openai.com in Chrome. The browser may already be logged in.

Step 1: Navigate to https://platform.openai.com/api-keys
- If you land on the API keys page, you're logged in. Skip to Step 3.
- If you land on a login page, do Step 2.

Step 2 (only if not logged in): Sign up or log in
- Use email: tarsitgroup@outlook.com, password: Tars.OpenAI2026!
- Or try Continue with Google using tarsitsales@gmail.com

Step 3: Create an API key
- Click "Create new secret key"
- Name it "tars-agent-key"
- Copy the full key (starts with sk-)

Step 4: Get Organization ID
- Go to Settings > Organization or https://platform.openai.com/settings/organization
- Copy the Organization ID (starts with org-)

Step 5: Report everything - API key, Org ID, billing status."""

ws = websocket.create_connection(ws_url, timeout=10)
msg = json.dumps({
    "type": "send_task",
    "task": task,
    "id": hashlib.md5(f"task2b-{time.time()}".encode()).hexdigest()[:8]
})
ws.send(msg)
print("✅ Task 2b sent!")

# Wait for result
while True:
    try:
        data = json.loads(ws.recv())
        if data.get("type") == "task_complete":
            print(f"✅ Task complete: {data.get('result', '')[:200]}")
            break
        elif data.get("type") == "error":
            print(f"❌ Error: {data.get('message', '')}")
            break
    except websocket.WebSocketTimeoutException:
        continue
    except KeyboardInterrupt:
        break

ws.close()
