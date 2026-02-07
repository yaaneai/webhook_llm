"""
Simple webhook listener for WhatsApp (or similar) API.
- GET: verification (hub.mode, hub.challenge, hub.verify_token)
- POST: receive events, log body, respond 200
"""
import json
import os
from datetime import datetime

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI(title="Webhook LLM", description="Webhook listener for WhatsApp API", version="1.0.0")

PORT = int(os.environ.get("PORT", 3000))
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = VERIFY_TOKEN
GRAPH_API_BASE = "https://graph.facebook.com/v22.0"


async def mark_read_and_typing(phone_number_id: str, message_id: str) -> bool:
    """POST to Graph API: mark message as read and send typing indicator. Returns True if success."""
    if not WHATSAPP_ACCESS_TOKEN or not phone_number_id or not message_id:
        return False
    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            data = r.json() if r.content else {}
            return data.get("success") is True
    except Exception:
        return False


def parse_webhook_payload(data: dict) -> dict:
    """
    Extract needed fields from WhatsApp webhook body into a simple flat structure.
    No nested access needed: one call gives object, entity_id, metadata, contact, messages.
    """
    if not data or data.get("object") != "whatsapp_business_account":
        return {}
    entry = (data.get("entry") or [{}])[0]
    entry_id = entry.get("id")
    changes = entry.get("changes") or [{}]
    value = (changes[0] if changes else {}).get("value") or {}
    metadata = value.get("metadata") or {}
    contacts = value.get("contacts") or [{}]
    contact = contacts[0] if contacts else {}
    profile = contact.get("profile") or {}
    messages_raw = value.get("messages") or []
    messages = []
    for m in messages_raw:
        text_obj = m.get("text") or {}
        messages.append({
            "from": m.get("from"),
            "id": m.get("id"),
            "timestamp": m.get("timestamp"),
            "text": text_obj.get("body", ""),
            "type": m.get("type"),
        })
    return {
        "object": data.get("object"),
        "entity_id": entry_id,
        "display_phone_number": metadata.get("display_phone_number"),
        "phone_number_id": metadata.get("phone_number_id"),
        "profile_name": profile.get("name"),
        "wa_id": contact.get("wa_id"),
        "messages": messages,
    }


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
    parsed = parse_webhook_payload(body)
    if parsed:
        print("Parsed:", json.dumps(parsed, indent=2))
        phone_number_id = parsed.get("phone_number_id")
        for msg in parsed.get("messages") or []:
            message_id = msg.get("id")
            success = await mark_read_and_typing(phone_number_id or "", message_id or "")
            if success:
                print("message text:", msg.get("text"))
                print("message type:", msg.get("type"))
    else:
        print(json.dumps(body, indent=2))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
