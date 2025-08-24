import logging, httpx
from . import env

async def respond_to_client(ai_response: str, wa_id: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": ai_response},
    }
    url = f"https://graph.facebook.com/v22.0/{env.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {env.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",        
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()






def parse_incoming_message(body: dict) -> tuple[str, str, str] | None:
    """
    Parses the incoming WhatsApp webhook payload and extracts the sender ID and message text.

    Supports both regular text messages and interactive button replies. If the payload does not
    contain a valid message (e.g. it's a system event or malformed), returns None.

    Args:
        body (dict): The JSON payload from the WhatsApp webhook.

    Returns:
        tuple [str, str] | None: A tuple containing the sender's WhatsApp ID (`wa_id`) and
        the message text. Returns None if no valid message is found.
    """
    entry_list = body.get("entry", [])
    if not entry_list:
        return None

    entry = entry_list[0]
    changes = entry.get("changes", [])
    if not changes:
        return None

    value = changes[0].get("value", {})
    messages = value.get("messages", [])
    if not messages:
        logging.info("Non-message event received: %s", value)
        # logging.log(value)
        return None

    msg = messages[0]
    wa_id = msg["from"]

    if (
        msg.get("type") == "interactive"
        and msg["interactive"]["type"] == "button_reply"
    ):
        message_text = msg["interactive"]["button_reply"]["title"].strip()
    else:
        message_text = msg.get("text", {}).get("body", "").strip()

    return wa_id, message_text
