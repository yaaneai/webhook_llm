"""
Simple webhook listener for WhatsApp (or similar) API.
- GET: verification (hub.mode, hub.challenge, hub.verify_token)
- POST: receive events, log body, respond 200
"""
import json
import os
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI(title="Webhook LLM", description="Webhook listener for WhatsApp API", version="1.0.0")

PORT = int(os.environ.get("PORT", 3000))
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")


@app.get("/")
def webhook_verify(request: Request):
    """Handle GET: platform verifies the webhook URL."""
    query = request.query_params
    mode = query.get("hub.mode")
    challenge = query.get("hub.challenge")
    token = query.get("hub.verify_token")

    print(mode, token, VERIFY_TOKEN)

    if mode == "subscribe" and token and token == VERIFY_TOKEN:
        print("WEBHOOK VERIFIED")
        return PlainTextResponse(content=challenge or "")
    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/")
async def webhook_receive(request: Request):
    """Handle POST: receive webhook events (e.g. incoming messages)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n\nWebhook received {timestamp}\n")
    print(json.dumps(body, indent=2))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
