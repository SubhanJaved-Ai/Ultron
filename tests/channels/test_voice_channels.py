"""Tests for voice integration across Telegram, WhatsApp, and audio bridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from openjarvis.channels.telegram import TelegramChannel
from openjarvis.channels.whatsapp import WhatsAppChannel
from openjarvis.speech.voice_channel_bridge import VoiceChannelBridge

# ---------------------------------------------------------------------------
# VoiceChannelBridge Tests
# ---------------------------------------------------------------------------


class TestVoiceChannelBridge:
    def test_transcribe_empty_bytes_returns_empty_string(self):
        bridge = VoiceChannelBridge()
        assert bridge.transcribe_audio(b"") == ""

    def test_transcribe_with_mock_backend(self):
        bridge = VoiceChannelBridge()
        mock_backend = MagicMock()
        mock_backend.transcribe.return_value = SimpleNamespace(
            text="Hello Jarvis, what is the weather?"
        )

        with patch(
            "openjarvis.speech.voice_channel_bridge.get_speech_backend",
            return_value=mock_backend,
        ):
            with patch("openjarvis.core.config.load_config", return_value=MagicMock()):
                result = bridge.transcribe_audio(b"fake-ogg-audio-data", suffix=".ogg")
                assert result == "Hello Jarvis, what is the weather?"
                mock_backend.transcribe.assert_called_once()

    def test_transcribe_no_backend_available(self):
        bridge = VoiceChannelBridge()
        with patch(
            "openjarvis.speech.voice_channel_bridge.get_speech_backend",
            return_value=None,
        ):
            with patch.dict("os.environ", {}, clear=True):
                result = bridge.transcribe_audio(b"fake-audio")
                assert "STT backend not configured" in result

    def test_transcribe_exception_returns_empty_string(self):
        bridge = VoiceChannelBridge()
        mock_backend = MagicMock()
        mock_backend.transcribe.side_effect = RuntimeError("decoder error")

        with patch(
            "openjarvis.speech.voice_channel_bridge.get_speech_backend",
            return_value=mock_backend,
        ):
            with patch("openjarvis.core.config.load_config", return_value=MagicMock()):
                result = bridge.transcribe_audio(b"fake-audio")
                assert result == ""

    def test_synthesize_empty_text_returns_none(self):
        bridge = VoiceChannelBridge()
        assert bridge.synthesize_voice("") is None
        assert bridge.synthesize_voice("   ") is None

    def test_synthesize_with_mock_tts(self):
        bridge = VoiceChannelBridge()
        mock_tts = MagicMock()
        mock_tts.backend_id = "mock_tts"
        mock_tts.synthesize.return_value = SimpleNamespace(audio=b"mp3-bytes")

        with patch(
            "openjarvis.speech.voice_channel_bridge.get_tts_backend",
            return_value=mock_tts,
        ):
            audio = bridge.synthesize_voice("Testing Jarvis audio output")
            assert audio == b"mp3-bytes"
            mock_tts.synthesize.assert_called_once()

    def test_synthesize_no_tts_backend_returns_none(self):
        bridge = VoiceChannelBridge()
        with patch(
            "openjarvis.speech.voice_channel_bridge.get_tts_backend",
            return_value=None,
        ):
            assert bridge.synthesize_voice("Testing speech") is None


# ---------------------------------------------------------------------------
# Telegram Voice Tests
# ---------------------------------------------------------------------------


class TestTelegramVoice:
    def test_send_voice_success(self):
        ch = TelegramChannel(bot_token="123:ABC")
        mock_resp = MagicMock(status_code=200)

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = ch.send_voice("9999", b"audio-bytes-ogg", caption="Test memo")
            assert result is True
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert "voice" in call_kwargs["files"]
            assert call_kwargs["data"]["caption"] == "Test memo"
            assert call_kwargs["data"]["chat_id"] == "9999"

    def test_send_voice_empty_bytes_fails(self):
        ch = TelegramChannel(bot_token="123:ABC")
        assert ch.send_voice("9999", b"") is False

    def test_send_voice_no_token_fails(self):
        ch = TelegramChannel()
        assert ch.send_voice("9999", b"audio-bytes") is False

    def test_send_with_voice_reply_metadata(self):
        ch = TelegramChannel(bot_token="123:ABC")
        mock_bridge = MagicMock()
        mock_bridge.synthesize_voice.return_value = b"synthesized-audio"

        with patch(
            "openjarvis.speech.voice_channel_bridge.VoiceChannelBridge",
            return_value=mock_bridge,
        ):
            with patch.object(ch, "send_voice", return_value=True) as mock_send_voice:
                success = ch.send(
                    "9999",
                    "Voice response text",
                    metadata={"voice_reply": True},
                )
                assert success is True
                mock_send_voice.assert_called_once_with(
                    "9999",
                    b"synthesized-audio",
                    conversation_id="",
                    caption="Voice response text",
                )

    def test_send_with_voice_reply_fallback_to_text(self):
        ch = TelegramChannel(bot_token="123:ABC")
        mock_bridge = MagicMock()
        mock_bridge.synthesize_voice.return_value = None  # synthesis fails

        mock_resp = MagicMock(status_code=200)
        with patch(
            "openjarvis.speech.voice_channel_bridge.VoiceChannelBridge",
            return_value=mock_bridge,
        ):
            with patch("httpx.post", return_value=mock_resp) as mock_post:
                success = ch.send(
                    "9999",
                    "Fallback text message",
                    metadata={"voice_reply": True},
                )
                assert success is True
                # Called sendMessage endpoint
                assert "sendMessage" in mock_post.call_args[0][0]


# ---------------------------------------------------------------------------
# WhatsApp Voice Tests
# ---------------------------------------------------------------------------


class TestWhatsAppVoice:
    def test_send_voice_success(self):
        ch = WhatsAppChannel(access_token="wa-token", phone_number_id="wa-phone")

        upload_resp = MagicMock(status_code=200)
        upload_resp.json.return_value = {"id": "uploaded-media-123"}

        send_resp = MagicMock(status_code=200)

        with patch("httpx.post", side_effect=[upload_resp, send_resp]) as mock_post:
            result = ch.send_voice("+15550001", b"audio-bytes-mp3")
            assert result is True
            assert mock_post.call_count == 2

            # Check upload call
            upload_call = mock_post.call_args_list[0]
            assert "media" in upload_call[0][0]
            assert "file" in upload_call[1]["files"]

            # Check message call
            send_call = mock_post.call_args_list[1]
            assert "messages" in send_call[0][0]
            assert send_call[1]["json"]["type"] == "audio"
            assert send_call[1]["json"]["audio"]["id"] == "uploaded-media-123"

    def test_send_voice_empty_bytes_or_missing_tokens(self):
        ch = WhatsAppChannel()
        assert ch.send_voice("+15550001", b"audio") is False

        ch_with_token = WhatsAppChannel(access_token="wa-token", phone_number_id="")
        assert ch_with_token.send_voice("+15550001", b"audio") is False

        ch_full = WhatsAppChannel(access_token="wa-token", phone_number_id="1234")
        assert ch_full.send_voice("+15550001", b"") is False

    def test_send_with_voice_reply_metadata(self):
        ch = WhatsAppChannel(access_token="wa-token", phone_number_id="wa-phone")
        mock_bridge = MagicMock()
        mock_bridge.synthesize_voice.return_value = b"synthesized-audio"

        with patch(
            "openjarvis.speech.voice_channel_bridge.VoiceChannelBridge",
            return_value=mock_bridge,
        ):
            with patch.object(ch, "send_voice", return_value=True) as mock_send_voice:
                success = ch.send(
                    "+15550001",
                    "WhatsApp Voice Reply",
                    metadata={"voice_reply": True},
                )
                assert success is True
                mock_send_voice.assert_called_once_with(
                    "+15550001",
                    b"synthesized-audio",
                    conversation_id="",
                )

    def test_process_webhook_payload_text_message(self):
        ch = WhatsAppChannel(access_token="wa-token", phone_number_id="wa-phone")
        received = []
        ch.on_message(lambda msg: received.append(msg))

        webhook_data = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "+15550002",
                                        "id": "wamid.123",
                                        "type": "text",
                                        "text": {"body": "Hello Jarvis"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        msgs = ch.process_webhook_payload(webhook_data)
        assert len(msgs) == 1
        assert msgs[0].content == "Hello Jarvis"
        assert msgs[0].sender == "+15550002"
        assert len(received) == 1

    def test_process_webhook_payload_voice_message(self):
        ch = WhatsAppChannel(access_token="wa-token", phone_number_id="wa-phone")
        received = []
        ch.on_message(lambda msg: received.append(msg))

        media_meta_resp = MagicMock(status_code=200)
        media_meta_resp.json.return_value = {"url": "https://media.fb.com/download/1"}

        media_dl_resp = MagicMock(status_code=200, content=b"audio-bytes-ogg")

        webhook_data = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "+15550002",
                                        "id": "wamid.voice456",
                                        "type": "voice",
                                        "voice": {"id": "media-id-999"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        mock_bridge = MagicMock()
        mock_bridge.transcribe_audio.return_value = "Turn on the living room lights"

        with patch("httpx.get", side_effect=[media_meta_resp, media_dl_resp]):
            with patch(
                "openjarvis.speech.voice_channel_bridge.VoiceChannelBridge",
                return_value=mock_bridge,
            ):
                msgs = ch.process_webhook_payload(webhook_data)
                assert len(msgs) == 1
                assert msgs[0].content == "Turn on the living room lights"
                assert msgs[0].metadata.get("is_voice") is True
                assert msgs[0].metadata.get("voice_reply") is True
                assert len(received) == 1
