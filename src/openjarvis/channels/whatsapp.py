"""WhatsAppChannel — WhatsApp Cloud API adapter."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from openjarvis.channels._stubs import (
    BaseChannel,
    ChannelHandler,
    ChannelMessage,
    ChannelStatus,
)
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.registry import ChannelRegistry

logger = logging.getLogger(__name__)


@ChannelRegistry.register("whatsapp")
class WhatsAppChannel(BaseChannel):
    """WhatsApp Cloud API channel adapter (send-only).

    Parameters
    ----------
    access_token:
        WhatsApp Cloud API access token.  Falls back to
        ``WHATSAPP_ACCESS_TOKEN`` env var.
    phone_number_id:
        WhatsApp phone number ID.  Falls back to
        ``WHATSAPP_PHONE_NUMBER_ID`` env var.
    bus:
        Optional event bus for publishing channel events.
    """

    channel_id = "whatsapp"

    def __init__(
        self,
        access_token: str = "",
        *,
        phone_number_id: str = "",
        bus: Optional[EventBus] = None,
    ) -> None:
        self._token = access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        self._phone_number_id = phone_number_id or os.environ.get(
            "WHATSAPP_PHONE_NUMBER_ID",
            "",
        )
        self._bus = bus
        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED

    # -- connection lifecycle ---------------------------------------------------

    def connect(self) -> None:
        """Mark as connected (send-only — no persistent connection)."""
        if not self._token:
            logger.warning("No WhatsApp access token configured")
            self._status = ChannelStatus.ERROR
            return
        self._status = ChannelStatus.CONNECTED

    def disconnect(self) -> None:
        """Mark as disconnected."""
        self._status = ChannelStatus.DISCONNECTED

    # -- send / receive --------------------------------------------------------

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """Send a message via the WhatsApp Cloud API."""
        if not self._token:
            logger.warning("Cannot send: no WhatsApp access token")
            return False

        if metadata and metadata.get("voice_reply"):
            try:
                from openjarvis.speech.voice_channel_bridge import VoiceChannelBridge

                bridge = VoiceChannelBridge()
                voice_data = bridge.synthesize_voice(content)
                if voice_data:
                    return self.send_voice(
                        channel,
                        voice_data,
                        conversation_id=conversation_id,
                    )
            except Exception as exc:
                logger.debug(
                    "WhatsApp voice synthesis failed, falling back to text: %s",
                    exc,
                )

        try:
            import httpx

            url = f"https://graph.facebook.com/v21.0/{self._phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            }
            payload: Dict[str, Any] = {
                "messaging_product": "whatsapp",
                "to": channel,
                "type": "text",
                "text": {"body": content},
            }

            resp = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code < 300:
                self._publish_sent(channel, content, conversation_id)
                return True
            logger.warning(
                "WhatsApp API returned status %d",
                resp.status_code,
            )
            return False
        except Exception:
            logger.debug("WhatsApp send failed", exc_info=True)
            return False

    def send_voice(
        self,
        channel: str,
        voice_bytes: bytes,
        *,
        conversation_id: str = "",
        caption: str = "",
    ) -> bool:
        """Send an audio voice note via WhatsApp Cloud API."""
        if not self._token:
            logger.warning("Cannot send voice: no WhatsApp access token")
            return False
        if not self._phone_number_id:
            logger.warning("Cannot send voice: no WhatsApp phone number ID")
            return False
        if not voice_bytes:
            return False

        try:
            import httpx

            # Step 1: Upload media to WhatsApp Cloud API
            upload_url = (
                f"https://graph.facebook.com/v21.0/{self._phone_number_id}/media"
            )
            headers = {"Authorization": f"Bearer {self._token}"}
            files = {"file": ("voice.mp3", voice_bytes, "audio/mpeg")}
            data = {"messaging_product": "whatsapp", "type": "audio/mpeg"}

            upload_resp = httpx.post(
                upload_url,
                data=data,
                files=files,
                headers=headers,
                timeout=30.0,
            )
            if upload_resp.status_code >= 300:
                logger.warning(
                    "WhatsApp media upload failed: %d %s",
                    upload_resp.status_code,
                    upload_resp.text,
                )
                return False

            media_id = upload_resp.json().get("id")
            if not media_id:
                logger.warning("WhatsApp media upload returned no media ID")
                return False

            # Step 2: Send audio message referencing uploaded media
            send_url = (
                f"https://graph.facebook.com/v21.0/{self._phone_number_id}/messages"
            )
            payload = {
                "messaging_product": "whatsapp",
                "to": channel,
                "type": "audio",
                "audio": {"id": media_id},
            }
            send_resp = httpx.post(
                send_url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if send_resp.status_code < 300:
                self._publish_sent(channel, "[Voice Note]", conversation_id)
                return True

            logger.warning(
                "WhatsApp send audio message failed: %d %s",
                send_resp.status_code,
                send_resp.text,
            )
            return False
        except Exception:
            logger.debug("WhatsApp send_voice failed", exc_info=True)
            return False

    def process_webhook_payload(
        self,
        payload: Dict[str, Any],
    ) -> List[ChannelMessage]:
        """Process incoming webhook JSON from WhatsApp Cloud API.

        Parses text and voice/audio messages, transcribes voice notes,
        dispatches to registered handlers, and publishes events.
        """
        from openjarvis.speech.voice_channel_bridge import VoiceChannelBridge

        messages: List[ChannelMessage] = []
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                raw_messages = value.get("messages", [])
                for raw_msg in raw_messages:
                    msg_type = raw_msg.get("type", "")
                    sender = raw_msg.get("from", "")
                    msg_id = raw_msg.get("id", "")
                    content = ""
                    metadata: Dict[str, Any] = {}

                    if msg_type == "text":
                        content = raw_msg.get("text", {}).get("body", "")
                    elif msg_type in ("audio", "voice"):
                        audio_info = raw_msg.get(msg_type, {})
                        media_id = audio_info.get("id", "")
                        if media_id and self._token:
                            try:
                                import httpx

                                meta_url = (
                                    f"https://graph.facebook.com/v21.0/{media_id}"
                                )
                                meta_resp = httpx.get(
                                    meta_url,
                                    headers={"Authorization": f"Bearer {self._token}"},
                                    timeout=10.0,
                                )
                                if meta_resp.status_code < 300:
                                    download_url = meta_resp.json().get("url")
                                    if download_url:
                                        dl_resp = httpx.get(
                                            download_url,
                                            headers={
                                                "Authorization": (
                                                    f"Bearer {self._token}"
                                                )
                                            },
                                            timeout=30.0,
                                        )
                                        if dl_resp.status_code < 300:
                                            bridge = VoiceChannelBridge()
                                            suffix = (
                                                ".ogg"
                                                if msg_type == "voice"
                                                else ".mp3"
                                            )
                                            content = bridge.transcribe_audio(
                                                dl_resp.content,
                                                suffix=suffix,
                                            )
                                            metadata["is_voice"] = True
                                            metadata["transcribed"] = True
                                            metadata["voice_reply"] = True
                            except Exception as exc:
                                logger.warning(
                                    "WhatsApp voice transcription failed: %s",
                                    exc,
                                )
                                content = "[Voice Note received: transcription failed]"
                        else:
                            content = "[Voice Note received]"

                    if content:
                        cm = ChannelMessage(
                            channel="whatsapp",
                            sender=sender,
                            content=content,
                            message_id=msg_id,
                            conversation_id=sender,
                            metadata=metadata,
                        )
                        messages.append(cm)
                        for handler in self._handlers:
                            try:
                                handler(cm)
                            except Exception:
                                logger.exception("WhatsApp handler error")
                        if self._bus is not None:
                            self._bus.publish(
                                EventType.CHANNEL_MESSAGE_RECEIVED,
                                {
                                    "channel": cm.channel,
                                    "sender": cm.sender,
                                    "content": cm.content,
                                    "message_id": cm.message_id,
                                },
                            )
        return messages

    def status(self) -> ChannelStatus:
        """Return the current connection status."""
        return self._status

    def list_channels(self) -> List[str]:
        """Return available channel identifiers."""
        return ["whatsapp"]

    def on_message(self, handler: ChannelHandler) -> None:
        """Register a callback for incoming messages."""
        self._handlers.append(handler)

    # -- internal helpers -------------------------------------------------------

    def _publish_sent(self, channel: str, content: str, conversation_id: str) -> None:
        """Publish a CHANNEL_MESSAGE_SENT event on the bus."""
        if self._bus is not None:
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_SENT,
                {
                    "channel": channel,
                    "content": content,
                    "conversation_id": conversation_id,
                },
            )


__all__ = ["WhatsAppChannel"]
