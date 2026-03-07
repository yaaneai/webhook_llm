"""
Simple webhook listener for WhatsApp (or similar) API.
- GET: verification (hub.mode, hub.challenge, hub.verify_token)
- POST: receive events, log body, respond 200
"""
import json
import os
import uuid
from datetime import datetime
from datetime import timezone

import httpx
from supabase import Client, create_client
from llm.expense_agent import get_response_text, run_application_agent
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI(title="Webhook LLM", description="Webhook listener for WhatsApp API", version="1.0.0")

PORT = int(os.environ.get("PORT", 3000))
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = VERIFY_TOKEN
GRAPH_API_BASE = "https://graph.facebook.com/v22.0"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client | None = None
SUPABASE_CONNECTED = False

try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        SUPABASE_CONNECTED = True
except Exception as e:
    print(f"Supabase client init failed: {e}")
    supabase = None
    SUPABASE_CONNECTED = False


def _parse_wa_timestamp(ts: str | None) -> str:
    """Convert WhatsApp epoch-seconds timestamp to ISO UTC string."""
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


async def upsert_user_conservation(
    parsed: dict,
    msg: dict,
    user_text: str,
    llm_response: str,
) -> dict:
    """
    Find existing user_conservation by entity/phone IDs; otherwise insert.
    Also updates latest message fields for existing row.
    """
    if not SUPABASE_CONNECTED or not supabase:
        return {}

    entity_id = parsed.get("entity_id") or ""
    phone_number_id = parsed.get("phone_number_id") or ""
    phone_number = msg.get("from") or parsed.get("wa_id") or ""
    profile_name = parsed.get("profile_name") or ""
    initiated_at = _parse_wa_timestamp(msg.get("timestamp"))

    try:
        lookup = (
            supabase.table("user_conservation")
            .select("id,user_id,converstion_id")
            .eq("entity_id", entity_id)
            .eq("phone_number_id", phone_number_id)
            .eq("phone_number", phone_number)
            .limit(1)
            .execute()
        )
        existing = (lookup.data or [None])[0]

        if existing:
            (
                supabase.table("user_conservation")
                .update(
                    {
                        "profile_name": profile_name,
                        "user_msg": user_text,
                        "llm_response": llm_response,
                        "msg_initated_at": initiated_at,
                    }
                )
                .eq("id", existing["id"])
                .execute()
            )
            return existing

        payload = {
            "user_id": str(uuid.uuid4()),
            "converstion_id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "phone_number_id": phone_number_id,
            "phone_number": phone_number,
            "profile_name": profile_name,
            "user_msg": user_text,
            "llm_response": llm_response,
            "msg_initated_at": initiated_at,
        }
        created = supabase.table("user_conservation").insert(payload).execute()
        return (created.data or [None])[0] or {}
    except Exception as e:
        print(f"Supabase upsert_user_conservation failed: {e}")
        return {}


async def insert_conversation_history(
    user_conservation_id: str,
    converstion_id: str,
    user_text: str,
    llm_response: str,
    initiated_at_iso: str,
) -> None:
    """Insert one JSONB conversation history record into conversation table."""
    if not SUPABASE_CONNECTED or not supabase:
        return
    if not user_conservation_id or not converstion_id:
        return
    try:
        conversation_json = {
            initiated_at_iso: {
                "user_msg": user_text,
                "llm_response": llm_response,
            }
        }
        (
            supabase.table("conversation")
            .insert(
                {
                    "user_conversation_id": user_conservation_id,
                    "conversation_id": converstion_id,
                    "conversation": conversation_json,
                }
            )
            .execute()
        )
    except Exception as e:
        print(f"Supabase insert_conversation_history failed: {e}")


async def update_msg_delivered_at(user_conservation_id: str) -> None:
    """Set delivery timestamp after WhatsApp send succeeds."""
    if not SUPABASE_CONNECTED or not supabase:
        return
    if not user_conservation_id:
        return
    try:
        (
            supabase.table("user_conservation")
            .update({"msg_delivered_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", user_conservation_id)
            .execute()
        )
    except Exception as e:
        print(f"Supabase update_msg_delivered_at failed: {e}")


async def claim_message_once(parsed: dict, msg: dict) -> bool:
    """
    Deduplicate webhook retries by WhatsApp message ID.
    Returns True only for the first claim, False for duplicates.
    """
    message_id = (msg.get("id") or "").strip()
    if not message_id:
        return False
    if not SUPABASE_CONNECTED or not supabase:
        return True

    try:
        (
            supabase.table("webhook_message_dedup")
            .insert(
                {
                    "message_id": message_id,
                    "entity_id": parsed.get("entity_id") or "",
                    "phone_number_id": parsed.get("phone_number_id") or "",
                    "phone_number": msg.get("from") or parsed.get("wa_id") or "",
                }
            )
            .execute()
        )
        return True
    except Exception as e:
        # Duplicate key means this webhook message was already processed.
        err = str(e).lower()
        if "duplicate key" in err or "23505" in err:
            print(f"Duplicate webhook skipped for message_id={message_id}")
            return False
        print(f"Supabase claim_message_once failed: {e}")
        return False


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


async def response_to_whatsapp(phone_number_id: str, to_wa_id: str, text: str) -> bool:
    """POST to Graph API: send text message to WhatsApp user. Same URL/headers as mark_read."""
    if not WHATSAPP_ACCESS_TOKEN or not phone_number_id or not to_wa_id or not text:
        return False
    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            data = r.json() if r.content else {}
            return data.get("messages") is not None  # success returns messages array
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


async def process_parsed_messages(parsed: dict) -> None:
    """Background worker to process incoming messages after immediate webhook ACK."""
    phone_number_id = parsed.get("phone_number_id")
    for msg in parsed.get("messages", []) or []:
        should_process = await claim_message_once(parsed, msg)
        if not should_process:
            continue

        message_id = msg.get("id")
        success = await mark_read_and_typing(phone_number_id or "", message_id or "")
        if not success:
            continue

        user_text = (msg.get("text") or "").strip()
        if not user_text:
            continue

        profile_name = parsed.get("profile_name") or ""
        runner = await run_application_agent(user_text, profile_name=profile_name)
        response = get_response_text(runner)
        print("message text:", user_text)
        print("response:", response)
        if not response:
            continue

        to_wa_id = msg.get("from") or parsed.get("wa_id") or ""
        user_row = await upsert_user_conservation(parsed, msg, user_text, response)
        if user_row:
            initiated_at_iso = _parse_wa_timestamp(msg.get("timestamp"))
            await insert_conversation_history(
                user_conservation_id=user_row.get("id", ""),
                converstion_id=user_row.get("converstion_id", ""),
                user_text=user_text,
                llm_response=response,
                initiated_at_iso=initiated_at_iso,
            )

        sent = await response_to_whatsapp(phone_number_id or "", to_wa_id, response)
        if sent and user_row:
            await update_msg_delivered_at(user_row.get("id", ""))


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
        print(f"Supabase DB connection established: {SUPABASE_CONNECTED}")
        return PlainTextResponse(content=challenge or "")
    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks):
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
        background_tasks.add_task(process_parsed_messages, parsed)
    else:
        print(json.dumps(body, indent=2))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    print(f"Supabase DB connection established: {SUPABASE_CONNECTED}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
