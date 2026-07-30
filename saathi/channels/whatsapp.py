"""WhatsApp Cloud API as a Transport.

Thin adapter over `saathi.wa`, which keeps the existing, tested window guard and
client as the implementation rather than rewriting them behind an abstraction.
"""
from __future__ import annotations

from ..wa import client as wa
from ..wa.format import to_whatsapp_text
from .base import Capabilities, Transport


class WhatsAppTransport(Transport):
    channel = "whatsapp"
    capabilities = Capabilities(
        has_session_window=True,
        session_window_hours=24,
        requires_templates=True,
        max_quick_replies=3,      # PRD §11
        quick_reply_label_len=20,
        supports_voice_notes=True,
        supports_cta_url_button=True,
        max_text_len=4096,
        markup="whatsapp",        # *bold*, not **bold**
        supports_payments=True,   # WhatsApp Pay via Razorpay (India)
    )

    async def send_text(self, conn, user_id, handle, text):
        return await wa.send_text(conn, user_id, handle, text)

    async def send_voice(self, conn, user_id, handle, text, lang, *, wa_message_id=None):
        return await wa.send_voice_note(conn, user_id, handle, text, lang,
                                        wa_message_id=wa_message_id)

    async def send_buttons(self, conn, user_id, handle, body, buttons):
        return await wa.send_buttons(conn, user_id, handle, body, buttons)

    async def send_list(self, conn, user_id, handle, body, button, rows):
        return await wa.send_list(conn, user_id, handle, body, button, rows)

    async def send_template(self, conn, user_id, handle, name, lang="en", variables=None,
                            payloads=None):
        return await wa.send_template(conn, user_id, handle, name, lang, variables or [],
                                      payloads=payloads or [])

    async def send_order_details(self, conn, user_id, handle, payload):
        return await wa.send_order_details(conn, user_id, handle, payload)

    async def fetch_media(self, media_id, max_bytes):
        return await wa.fetch_media(media_id, max_bytes)

    def format_text(self, text: str) -> str:
        return to_whatsapp_text(text)
