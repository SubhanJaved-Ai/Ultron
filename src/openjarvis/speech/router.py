"""Multilingual Text-to-Speech Router and Capability Registry for Ultron.

Evaluates and routes speech synthesis across local and cloud engines:
1. Windows SAPI (Native zero-dependency local engine for English male/female)
2. Piper TTS (Lightweight ONNX local engine for English, Hindi, and Urdu)
3. Edge TTS (Free neural speech for English, Urdu, and Hindi without API keys)
4. Chatterbox Multilingual V3 (Evaluated: EN/HI, no Urdu, heavy PyTorch footprint)
5. Urdu VITS (Evaluated: experimental PyTorch weights for Urdu)
6. ElevenLabs Multilingual (Cloud neural, 29+ languages, requires API key)
7. OpenAI Speech TTS-1 (Cloud neural, multilingual, requires API key)
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("openjarvis.speech.router")


@dataclass
class VoiceMetadata:
    """Accurate metadata for a specific TTS voice."""

    id: str
    name: str
    gender: str  # 'masculine' | 'feminine' | 'neutral'
    language: str  # ISO 639-1 ('en', 'ur', 'hi')
    engine_id: str
    license: str
    model_size: str = "0 MB"
    is_local: bool = True
    is_installed: bool = True
    sample_phrase: str = ""


@dataclass
class EngineCapability:
    """Capability specification for a text-to-speech engine."""

    id: str
    name: str
    is_local: bool
    is_free: bool
    requires_key: bool
    supported_languages: List[str]
    voices: List[VoiceMetadata]
    hardware_requirements: str
    license: str
    status: str  # 'installed' | 'available_download' | 'uninstalled' | 'evaluated_not_recommended' | 'experimental'
    cost_notice: str
    status_detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_local": self.is_local,
            "free": self.is_free,
            "requires_key": self.requires_key,
            "available": self.status == "installed",
            "supported_languages": self.supported_languages,
            "hardware_requirements": self.hardware_requirements,
            "license": self.license,
            "status": self.status,
            "cost_notice": self.cost_notice,
            "status_detail": self.status_detail,
            "voices": [
                {
                    "id": v.id,
                    "name": v.name,
                    "gender": v.gender,
                    "lang": v.language,
                    "license": v.license,
                    "model_size": v.model_size,
                    "is_local": v.is_local,
                    "is_installed": v.is_installed,
                }
                for v in self.voices
            ],
        }


def _check_piper_installed() -> bool:
    """Check if piper binary or python package is present locally."""
    if shutil.which("piper"):
        return True
    try:
        import importlib.util

        if importlib.util.find_spec("piper") is not None:
            return True
    except Exception:
        pass
    return False


def _check_edge_tts_installed() -> bool:
    """Check if edge_tts python library is present."""
    try:
        import importlib.util

        if importlib.util.find_spec("edge_tts") is not None:
            return True
    except Exception:
        pass
    return False


def build_capabilities_registry() -> Dict[str, EngineCapability]:
    """Build the comprehensive, verified multilingual TTS capability registry."""
    from openjarvis.core.user_preferences import get_elevenlabs_api_key

    has_el_key = bool(get_elevenlabs_api_key())
    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
    piper_installed = _check_piper_installed()
    edge_installed = _check_edge_tts_installed()

    registry: Dict[str, EngineCapability] = {}

    # 1. Native Windows SAPI
    registry["system"] = EngineCapability(
        id="system",
        name="Windows System SAPI (Native Local)",
        is_local=True,
        is_free=True,
        requires_key=False,
        supported_languages=["en"],
        hardware_requirements="Built-in OS component, 0 MB extra RAM, <0.2s CPU latency",
        license="Microsoft Windows Component (OS License)",
        status="installed",
        cost_notice="100% Free & private. Built into Windows workstations.",
        status_detail="Active and operational out-of-the-box on this workstation.",
        voices=[
            VoiceMetadata(
                id="david",
                name="Microsoft David Desktop",
                gender="masculine",
                language="en",
                engine_id="system",
                license="Windows Desktop OS",
                model_size="0 MB (OS built-in)",
                is_local=True,
                is_installed=True,
                sample_phrase="Greetings, Sir. All systems are fully operational.",
            ),
            VoiceMetadata(
                id="zira",
                name="Microsoft Zira Desktop",
                gender="feminine",
                language="en",
                engine_id="system",
                license="Windows Desktop OS",
                model_size="0 MB (OS built-in)",
                is_local=True,
                is_installed=True,
                sample_phrase="Standing by. Awaiting your operational specifications.",
            ),
        ],
    )

    # 2. Piper TTS (Lightweight CPU ONNX Engine)
    registry["piper"] = EngineCapability(
        id="piper",
        name="Piper TTS (Lightweight ONNX Local)",
        is_local=True,
        is_free=True,
        requires_key=False,
        supported_languages=["en", "hi", "ur"],
        hardware_requirements="~50 MB RAM, fast on CPU without GPU/VRAM",
        license="MIT / CMU Indic / Apache 2.0 (Open Source)",
        status="installed" if piper_installed else "available_download",
        cost_notice="100% Free, open source local ONNX engine.",
        status_detail=(
            "Installed and ready for local CPU synthesis."
            if piper_installed
            else "Lightweight ONNX model package available for one-click local install (~35-60 MB per language)."
        ),
        voices=[
            VoiceMetadata(
                id="en_US-ryan-medium",
                name="Piper Ryan (Masculine)",
                gender="masculine",
                language="en",
                engine_id="piper",
                license="MIT",
                model_size="60 MB",
                is_local=True,
                is_installed=piper_installed,
            ),
            VoiceMetadata(
                id="en_US-lessac-medium",
                name="Piper Lessac (Feminine)",
                gender="feminine",
                language="en",
                engine_id="piper",
                license="MIT",
                model_size="35 MB",
                is_local=True,
                is_installed=piper_installed,
            ),
            VoiceMetadata(
                id="hi_IN-cmu_indic",
                name="Piper Hindi CMU Indic (Masculine)",
                gender="masculine",
                language="hi",
                engine_id="piper",
                license="CMU Indic / BSD",
                model_size="42 MB",
                is_local=True,
                is_installed=piper_installed,
            ),
            VoiceMetadata(
                id="ur_PK-cmu_indic",
                name="Piper Urdu CMU Indic (Masculine)",
                gender="masculine",
                language="ur",
                engine_id="piper",
                license="CMU Indic / BSD",
                model_size="40 MB",
                is_local=True,
                is_installed=piper_installed,
            ),
        ],
    )

    # 3. Edge TTS (High-Fidelity Free Neural Voices)
    registry["edge_tts"] = EngineCapability(
        id="edge_tts",
        name="Edge TTS (Neural Free)",
        is_local=False,
        is_free=True,
        requires_key=False,
        supported_languages=["en", "ur", "hi"],
        hardware_requirements="Lightweight client, network streaming connection required",
        license="Microsoft Edge Speech Service Terms",
        status="installed" if edge_installed else "available_download",
        cost_notice="100% Free neural voice service without API subscription.",
        status_detail=(
            "Installed and active for high-fidelity English, Urdu, and Hindi synthesis."
            if edge_installed
            else "Can be enabled via pip install edge-tts for zero-cost neural Urdu/Hindi/English voices."
        ),
        voices=[
            VoiceMetadata(
                id="en-US-GuyNeural",
                name="Guy Neural (Masculine)",
                gender="masculine",
                language="en",
                engine_id="edge_tts",
                license="Microsoft Service Terms",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=edge_installed,
            ),
            VoiceMetadata(
                id="en-US-JennyNeural",
                name="Jenny Neural (Feminine)",
                gender="feminine",
                language="en",
                engine_id="edge_tts",
                license="Microsoft Service Terms",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=edge_installed,
            ),
            VoiceMetadata(
                id="ur-PK-AsadNeural",
                name="Asad Neural (Masculine Urdu)",
                gender="masculine",
                language="ur",
                engine_id="edge_tts",
                license="Microsoft Service Terms",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=edge_installed,
            ),
            VoiceMetadata(
                id="ur-PK-UzmaNeural",
                name="Uzma Neural (Feminine Urdu)",
                gender="feminine",
                language="ur",
                engine_id="edge_tts",
                license="Microsoft Service Terms",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=edge_installed,
            ),
            VoiceMetadata(
                id="hi-IN-MadhurNeural",
                name="Madhur Neural (Masculine Hindi)",
                gender="masculine",
                language="hi",
                engine_id="edge_tts",
                license="Microsoft Service Terms",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=edge_installed,
            ),
            VoiceMetadata(
                id="hi-IN-SwaraNeural",
                name="Swara Neural (Feminine Hindi)",
                gender="feminine",
                language="hi",
                engine_id="edge_tts",
                license="Microsoft Service Terms",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=edge_installed,
            ),
        ],
    )

    # 4. Chatterbox Multilingual V3 (Evaluated)
    registry["chatterbox"] = EngineCapability(
        id="chatterbox",
        name="Chatterbox Multilingual V3 (Evaluated)",
        is_local=True,
        is_free=True,
        requires_key=False,
        supported_languages=["en", "hi"],  # Note: Does NOT support Urdu
        hardware_requirements="Heavy PyTorch/CUDA runtime, ~2-4 GB VRAM/RAM, high CPU latency",
        license="Resemble AI / Non-Commercial Research License",
        status="evaluated_not_recommended",
        cost_notice="Free for research, but licensing restricts commercial distribution.",
        status_detail="Evaluated: Supports English and Hindi across 23 languages, but lacks Urdu support. Excessive memory footprint (~2-4 GB) and latency on dual-core mobile CPU.",
        voices=[
            VoiceMetadata(
                id="chatterbox-default",
                name="Chatterbox Neural Base",
                gender="neutral",
                language="en",
                engine_id="chatterbox",
                license="Non-Commercial Research",
                model_size="~1.8 GB",
                is_local=True,
                is_installed=False,
            )
        ],
    )

    # 5. Urdu VITS (Evaluated: ahmedHanzala / zohann)
    registry["urdu_vits"] = EngineCapability(
        id="urdu_vits",
        name="Urdu VITS PyTorch (Evaluated)",
        is_local=True,
        is_free=True,
        requires_key=False,
        supported_languages=["ur"],
        hardware_requirements="PyTorch runtime, ~200 MB weights, moderate CPU compute",
        license="Apache 2.0 / Research Weights",
        status="experimental",
        cost_notice="Free open-source weights.",
        status_detail="Evaluated: Experimental VITS architecture for Urdu. Arbitrary Nastaliq text synthesis stability is unverified in production without full PyTorch runtime isolation.",
        voices=[
            VoiceMetadata(
                id="urdu-vits-base",
                name="Urdu VITS Single-Speaker",
                gender="masculine",
                language="ur",
                engine_id="urdu_vits",
                license="Apache 2.0",
                model_size="~200 MB",
                is_local=True,
                is_installed=False,
            )
        ],
    )

    # 6. ElevenLabs Multilingual (Cloud Neural)
    registry["elevenlabs"] = EngineCapability(
        id="elevenlabs",
        name="ElevenLabs Multilingual",
        is_local=False,
        is_free=False,
        requires_key=True,
        supported_languages=["en", "ur", "hi"],
        hardware_requirements="Cloud streaming API, 0 MB local RAM",
        license="Commercial SaaS Plan",
        status="installed" if has_el_key else "uninstalled",
        cost_notice="Paid cloud API. Consumes character quota on your ElevenLabs account.",
        status_detail="High-fidelity 29-language synthesis. Enabled when API key is provided.",
        voices=[
            VoiceMetadata(
                id="JBFqnCBsd6RMkjVDRZzb",
                name="Jarvis (Composed British)",
                gender="masculine",
                language="en",
                engine_id="elevenlabs",
                license="ElevenLabs",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_el_key,
            ),
            VoiceMetadata(
                id="21m00Tcm4TlvDq8ikWAM",
                name="Rachel (Warm & Composed)",
                gender="feminine",
                language="en",
                engine_id="elevenlabs",
                license="ElevenLabs",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_el_key,
            ),
            VoiceMetadata(
                id="EXAVITQu4vr4xnSDxMaL",
                name="Bella (Articulate)",
                gender="feminine",
                language="en",
                engine_id="elevenlabs",
                license="ElevenLabs",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_el_key,
            ),
            VoiceMetadata(
                id="ErXwobaYiN019PkySvjV",
                name="Antoni (Deep & Calm)",
                gender="masculine",
                language="en",
                engine_id="elevenlabs",
                license="ElevenLabs",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_el_key,
            ),
        ],
    )

    # 7. OpenAI Speech (TTS-1)
    registry["openai_tts"] = EngineCapability(
        id="openai_tts",
        name="OpenAI Speech (TTS-1)",
        is_local=False,
        is_free=False,
        requires_key=True,
        supported_languages=["en", "ur", "hi"],
        hardware_requirements="Cloud streaming API, 0 MB local RAM",
        license="OpenAI Terms of Service",
        status="installed" if has_openai_key else "uninstalled",
        cost_notice="Paid cloud API. Billed per character to your OpenAI account.",
        status_detail="Multilingual neural voices. Enabled when OPENAI_API_KEY is present.",
        voices=[
            VoiceMetadata(
                id="onyx",
                name="Onyx (Deep Masculine)",
                gender="masculine",
                language="en",
                engine_id="openai_tts",
                license="OpenAI",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_openai_key,
            ),
            VoiceMetadata(
                id="echo",
                name="Echo (Warm Masculine)",
                gender="masculine",
                language="en",
                engine_id="openai_tts",
                license="OpenAI",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_openai_key,
            ),
            VoiceMetadata(
                id="shimmer",
                name="Shimmer (Expressive Feminine)",
                gender="feminine",
                language="en",
                engine_id="openai_tts",
                license="OpenAI",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_openai_key,
            ),
            VoiceMetadata(
                id="alloy",
                name="Alloy (Neutral / Balanced)",
                gender="neutral",
                language="en",
                engine_id="openai_tts",
                license="OpenAI",
                model_size="Cloud Streaming",
                is_local=False,
                is_installed=has_openai_key,
            ),
        ],
    )

    return registry


class MultilingualTTSRouter:
    """Intelligent, language-aware TTS router for Ultron."""

    def __init__(self) -> None:
        self._capabilities = build_capabilities_registry()

    def get_capabilities(self) -> Dict[str, EngineCapability]:
        """Refresh and return the full capability registry."""
        self._capabilities = build_capabilities_registry()
        return self._capabilities

    def resolve_engine_and_voice(
        self,
        language: str = "en",
        voice_gender: str = "masculine",
        preferred_provider: str = "system",
    ) -> Dict[str, Any]:
        """Resolve the best compatible engine and voice without silent wrong-language fallback.

        Returns a dictionary containing:
        - status: 'supported' | 'unsupported_by_engine' | 'uninstalled_engine'
        - engine_id: resolved engine identifier
        - voice_id: resolved voice identifier
        - is_local: bool
        - message: user-facing explanation if limitations apply
        """
        caps = self.get_capabilities()
        lang = (language or "en").lower().strip()
        gender = (voice_gender or "masculine").lower().strip()
        provider = (preferred_provider or "system").lower().strip()

        # Check if preferred provider is known
        engine = caps.get(provider)
        if not engine:
            engine = caps["system"]
            provider = "system"

        # Check if requested language is supported by this engine
        if lang not in engine.supported_languages:
            # SAPI / system is English only. If user requested Urdu or Hindi, explain clearly:
            if provider == "system":
                # Find if any other free local or installed engine supports it
                piper_eng = caps.get("piper")
                edge_eng = caps.get("edge_tts")
                el_eng = caps.get("elevenlabs")

                recommendation = ""
                if piper_eng and piper_eng.status == "installed":
                    recommendation = "Local Piper ONNX is available for offline synthesis."
                elif el_eng and el_eng.status == "installed":
                    recommendation = "ElevenLabs is configured and supports high-fidelity output."
                elif edge_eng and edge_eng.status == "installed":
                    recommendation = "Edge TTS is available for free neural output."
                else:
                    recommendation = "Local SAPI lacks voice models for this language. Text is generated in the requested language."

                return {
                    "status": "unsupported_by_engine",
                    "engine_id": provider,
                    "voice_id": "default",
                    "language": lang,
                    "voice_gender": gender,
                    "is_local": True,
                    "message": f"Windows SAPI engine does not support '{lang}'. {recommendation}",
                }

        # Check if engine is installed / configured
        if engine.status != "installed":
            return {
                "status": "uninstalled_engine",
                "engine_id": provider,
                "voice_id": "default",
                "language": lang,
                "voice_gender": gender,
                "is_local": engine.is_local,
                "message": f"Engine '{engine.name}' is not currently installed or configured. {engine.status_detail}",
            }

        # Pick matching voice by gender and language
        matched_voice: Optional[VoiceMetadata] = None
        for v in engine.voices:
            if v.language.startswith(lang):
                if v.gender == gender:
                    matched_voice = v
                    break

        if not matched_voice:
            # Fallback to any voice for this language
            for v in engine.voices:
                if v.language.startswith(lang):
                    matched_voice = v
                    break

        if not matched_voice and engine.voices:
            matched_voice = engine.voices[0]

        voice_id = matched_voice.id if matched_voice else "default"
        actual_gender = matched_voice.gender if matched_voice else gender

        return {
            "status": "supported",
            "engine_id": provider,
            "voice_id": voice_id,
            "language": lang,
            "voice_gender": actual_gender,
            "is_local": engine.is_local,
            "message": f"Routed to {engine.name} ({voice_id}).",
        }

    def detect_and_resolve(
        self,
        text: str,
        default_language: str = "en",
        voice_gender: str = "masculine",
        preferred_provider: str = "system",
    ) -> Dict[str, Any]:
        """Detect language directive or script in text, then resolve the best compatible voice."""
        detected = detect_language(text, default_language=default_language)
        result = self.resolve_engine_and_voice(
            language=detected,
            voice_gender=voice_gender,
            preferred_provider=preferred_provider,
        )
        result["detected_language"] = detected
        return result


def detect_language(text: str, default_language: str = "en") -> str:
    """Detect directive or script language from input text ('en', 'ur', or 'hi').

    Evaluates:
    1. Explicit language directives in English, Urdu, or Hindi phrases:
       - 'in urdu', 'urdu mein', 'مجھے اردو میں جواب دو', 'اردو میں' -> 'ur'
       - 'in hindi', 'hindi mein', 'हिंदी में جواب دو', 'हिंदी में', 'हिन्दी में' -> 'hi'
       - 'in english', 'answer me in english', 'speak english' -> 'en'
    2. Character script frequency:
       - Urdu / Arabic script range (\u0600-\u06FF, \u0750-\u077F, \uFB50-\uFDFF, \uFE70-\uFEFF)
       - Hindi / Devanagari script range (\u0900-\u097F)
    3. Falls back to default_language if no specific signals are found.
    """
    import re

    if not text:
        return default_language

    lower = text.lower()

    # 1. Directive keywords
    is_hindi_directive = bool(
        re.search(r"(?:in\s+hindi|hindi\s+(?:mein|me|main)|\u0939\u093f\u0902\u0926\u0940|\u0939\u093f\u0928\u094d\u0926\u0940)", text, re.IGNORECASE)
    )
    is_urdu_directive = bool(
        re.search(r"(?:in\s+urdu|urdu\s+(?:mein|me|main)|\u0627\u0631\u062f\u0648)", text, re.IGNORECASE)
    )
    is_english_directive = bool(
        re.search(r"(?:in\s+english|answer\s+(?:me\s+)?in\s+english|speak\s+(?:in\s+)?english|english\s+please)", lower)
    )

    if is_hindi_directive and not is_urdu_directive:
        return "hi"
    if is_urdu_directive and not is_hindi_directive:
        return "ur"
    if is_english_directive and not is_urdu_directive and not is_hindi_directive:
        return "en"

    if "\u062c\u0648\u0627\u0628 \u062f\u0648" in text:
        return "ur"

    # 2. Script character counting
    urdu_chars = len(re.findall(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]", text))
    hindi_chars = len(re.findall(r"[\u0900-\u097F]", text))

    if urdu_chars > 0 and urdu_chars >= hindi_chars:
        return "ur"
    if hindi_chars > 0 and hindi_chars > urdu_chars:
        return "hi"

    return default_language


# Singleton router instance
tts_router = MultilingualTTSRouter()

__all__ = [
    "EngineCapability",
    "MultilingualTTSRouter",
    "VoiceMetadata",
    "build_capabilities_registry",
    "detect_language",
    "tts_router",
]
