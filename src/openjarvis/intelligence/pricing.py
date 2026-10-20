"""Official versioned pricing registry and cost calculation for AI models and speech APIs.

Prices are defined in USD per 1,000,000 tokens for text models, or USD per character/unit
for multimodal and speech services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

PRICING_REGISTRY_VERSION = "2026-10-v1"
PRICING_VERIFICATION_DATE = "2026-10-18"


@dataclass(frozen=True)
class ModelPriceEntry:
    """Pricing rates and metadata for a specific model or model family."""

    provider: str
    model_id: str
    label: str
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float = 0.0
    reasoning_per_1m: float = 0.0
    char_rate_per_1k: float = 0.0  # For speech synthesis
    currency: str = "USD"
    is_local: bool = False
    source_url: str = ""
    effective_date: str = "2026-10-01"


# Official model pricing rates as of October 2026
MODEL_PRICING: Dict[str, ModelPriceEntry] = {
    # --- OpenAI ---
    "gpt-4o": ModelPriceEntry(
        provider="openai",
        model_id="gpt-4o",
        label="GPT-4o",
        input_per_1m=2.50,
        output_per_1m=10.00,
        cached_input_per_1m=1.25,
        source_url="https://developers.openai.com/api/pricing",
    ),
    "gpt-4o-mini": ModelPriceEntry(
        provider="openai",
        model_id="gpt-4o-mini",
        label="GPT-4o mini",
        input_per_1m=0.15,
        output_per_1m=0.60,
        cached_input_per_1m=0.075,
        source_url="https://developers.openai.com/api/pricing",
    ),
    "gpt-5": ModelPriceEntry(
        provider="openai",
        model_id="gpt-5",
        label="GPT-5",
        input_per_1m=10.00,
        output_per_1m=30.00,
        cached_input_per_1m=5.00,
        reasoning_per_1m=30.00,
        source_url="https://developers.openai.com/api/pricing",
    ),
    "o3-mini": ModelPriceEntry(
        provider="openai",
        model_id="o3-mini",
        label="o3-mini",
        input_per_1m=1.10,
        output_per_1m=4.40,
        cached_input_per_1m=0.55,
        reasoning_per_1m=4.40,
        source_url="https://developers.openai.com/api/pricing",
    ),
    "o1": ModelPriceEntry(
        provider="openai",
        model_id="o1",
        label="o1",
        input_per_1m=15.00,
        output_per_1m=60.00,
        cached_input_per_1m=7.50,
        reasoning_per_1m=60.00,
        source_url="https://developers.openai.com/api/pricing",
    ),
    "tts-1": ModelPriceEntry(
        provider="openai",
        model_id="tts-1",
        label="OpenAI TTS 1",
        input_per_1m=0.0,
        output_per_1m=0.0,
        char_rate_per_1k=0.015,
        source_url="https://openai.com/api/pricing",
    ),
    "tts-1-hd": ModelPriceEntry(
        provider="openai",
        model_id="tts-1-hd",
        label="OpenAI TTS 1 HD",
        input_per_1m=0.0,
        output_per_1m=0.0,
        char_rate_per_1k=0.030,
        source_url="https://openai.com/api/pricing",
    ),

    # --- Anthropic ---
    "claude-3-5-sonnet-20241022": ModelPriceEntry(
        provider="anthropic",
        model_id="claude-3-5-sonnet-20241022",
        label="Claude 3.5 Sonnet",
        input_per_1m=3.00,
        output_per_1m=15.00,
        cached_input_per_1m=0.30,
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-sonnet-4-20250514": ModelPriceEntry(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        label="Claude Sonnet 4",
        input_per_1m=3.00,
        output_per_1m=15.00,
        cached_input_per_1m=0.30,
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-3-5-haiku-20241022": ModelPriceEntry(
        provider="anthropic",
        model_id="claude-3-5-haiku-20241022",
        label="Claude 3.5 Haiku",
        input_per_1m=0.80,
        output_per_1m=4.00,
        cached_input_per_1m=0.08,
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),
    "claude-3-opus-20240229": ModelPriceEntry(
        provider="anthropic",
        model_id="claude-3-opus-20240229",
        label="Claude 3 Opus",
        input_per_1m=15.00,
        output_per_1m=75.00,
        cached_input_per_1m=1.50,
        source_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
    ),

    # --- Google Gemini ---
    "gemini-1.5-pro": ModelPriceEntry(
        provider="google",
        model_id="gemini-1.5-pro",
        label="Gemini 1.5 Pro",
        input_per_1m=1.25,
        output_per_1m=5.00,
        cached_input_per_1m=0.3125,
        source_url="https://ai.google.dev/gemini-api/docs/pricing",
    ),
    "gemini-1.5-flash": ModelPriceEntry(
        provider="google",
        model_id="gemini-1.5-flash",
        label="Gemini 1.5 Flash",
        input_per_1m=0.075,
        output_per_1m=0.30,
        cached_input_per_1m=0.01875,
        source_url="https://ai.google.dev/gemini-api/docs/pricing",
    ),
    "gemini-2.5-flash": ModelPriceEntry(
        provider="google",
        model_id="gemini-2.5-flash",
        label="Gemini 2.5 Flash",
        input_per_1m=0.30,
        output_per_1m=2.50,
        cached_input_per_1m=0.075,
        source_url="https://ai.google.dev/gemini-api/docs/pricing",
    ),
    "gemini-2.5-pro": ModelPriceEntry(
        provider="google",
        model_id="gemini-2.5-pro",
        label="Gemini 2.5 Pro",
        input_per_1m=1.25,
        output_per_1m=10.00,
        cached_input_per_1m=0.3125,
        source_url="https://ai.google.dev/gemini-api/docs/pricing",
    ),
    "gemini-3.8-flash": ModelPriceEntry(
        provider="google",
        model_id="gemini-3.8-flash",
        label="Gemini 3.8 Flash",
        input_per_1m=0.30,
        output_per_1m=2.50,
        cached_input_per_1m=0.075,
        source_url="https://ai.google.dev/gemini-api/docs/pricing",
    ),

    # --- ElevenLabs Voice / Speech ---
    "eleven_multilingual_v2": ModelPriceEntry(
        provider="elevenlabs",
        model_id="eleven_multilingual_v2",
        label="Eleven Multilingual v2",
        input_per_1m=0.0,
        output_per_1m=0.0,
        char_rate_per_1k=0.30,  # ~$0.30 per 1,000 characters
        source_url="https://elevenlabs.io/pricing",
    ),
    "eleven_flash_v2_5": ModelPriceEntry(
        provider="elevenlabs",
        model_id="eleven_flash_v2_5",
        label="Eleven Flash v2.5",
        input_per_1m=0.0,
        output_per_1m=0.0,
        char_rate_per_1k=0.15,
        source_url="https://elevenlabs.io/pricing",
    ),
    "eleven_turbo_v2_5": ModelPriceEntry(
        provider="elevenlabs",
        model_id="eleven_turbo_v2_5",
        label="Eleven Turbo v2.5",
        input_per_1m=0.0,
        output_per_1m=0.0,
        char_rate_per_1k=0.20,
        source_url="https://elevenlabs.io/pricing",
    ),

    # --- DeepSeek ---
    "deepseek-chat": ModelPriceEntry(
        provider="deepseek",
        model_id="deepseek-chat",
        label="DeepSeek V3",
        input_per_1m=0.14,
        output_per_1m=0.28,
        cached_input_per_1m=0.014,
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
    ),
    "deepseek-reasoner": ModelPriceEntry(
        provider="deepseek",
        model_id="deepseek-reasoner",
        label="DeepSeek R1",
        input_per_1m=0.55,
        output_per_1m=2.19,
        cached_input_per_1m=0.14,
        reasoning_per_1m=2.19,
        source_url="https://api-docs.deepseek.com/quick_start/pricing",
    ),

    # --- MiniMax ---
    "MiniMax-M3": ModelPriceEntry(
        provider="minimax",
        model_id="MiniMax-M3",
        label="MiniMax M3",
        input_per_1m=0.30,
        output_per_1m=1.20,
        source_url="https://api.minimax.io",
    ),

    # --- Local Models (Explicitly $0.00 API inference cost) ---
    "ollama": ModelPriceEntry(
        provider="ollama",
        model_id="ollama",
        label="Local Ollama (Hardware)",
        input_per_1m=0.0,
        output_per_1m=0.0,
        is_local=True,
    ),
}


@dataclass
class CostBreakdown:
    """Calculated cost for an inference or speech generation request."""

    estimated_cost_usd: float
    cost_type: str  # 'estimated', 'provider_billed', 'local_zero', 'unknown'
    input_cost: float = 0.0
    output_cost: float = 0.0
    cached_input_cost: float = 0.0
    reasoning_cost: float = 0.0
    speech_cost: float = 0.0
    pricing_version: str = PRICING_REGISTRY_VERSION
    is_local: bool = False
    rate_matched: bool = True


def resolve_price_entry(provider: str, model: str) -> Optional[ModelPriceEntry]:
    """Find the best matching pricing entry for a provider and model."""
    provider_norm = (provider or "").lower().strip()
    model_norm = (model or "").lower().strip()

    # Exact match on model ID
    if model_norm in MODEL_PRICING:
        return MODEL_PRICING[model_norm]

    # Check local providers
    if provider_norm == "ollama" or model_norm.startswith(("ollama/", "local/")):
        return MODEL_PRICING["ollama"]

    # Specific prefix match (e.g. gpt-4o-2024-08-06 matches gpt-4o)
    for key, entry in MODEL_PRICING.items():
        if model_norm.startswith(key):
            return entry

    # Unknown or unverified models must NOT silently inherit another model's rates
    return None


def calculate_cost(
    provider: str,
    model: str,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_prompt_tokens: int = 0,
    reasoning_tokens: int = 0,
    characters: int = 0,
) -> CostBreakdown:
    """Calculate exact structured cost for a request.

    Separates uncached input, cached input, reasoning output, standard output, and speech characters.
    """
    entry = resolve_price_entry(provider, model)

    if entry is None:
        # Unknown provider/model: do NOT fabricate 0.0 without marking unknown!
        return CostBreakdown(
            estimated_cost_usd=0.0,
            cost_type="unknown",
            rate_matched=False,
        )

    if entry.is_local:
        return CostBreakdown(
            estimated_cost_usd=0.0,
            cost_type="local_zero",
            is_local=True,
            rate_matched=True,
        )

    # Calculate speech cost if characters present
    speech_cost = 0.0
    if characters > 0 and entry.char_rate_per_1k > 0:
        speech_cost = (characters / 1_000.0) * entry.char_rate_per_1k

    # Calculate token costs
    # Net uncached prompt tokens
    uncached_prompt = max(0, prompt_tokens - cached_prompt_tokens)
    input_cost = (uncached_prompt / 1_000_000.0) * entry.input_per_1m

    # Cached prompt tokens (at discounted rate if configured, else standard)
    cached_rate = entry.cached_input_per_1m if entry.cached_input_per_1m > 0 else entry.input_per_1m
    cached_input_cost = (cached_prompt_tokens / 1_000_000.0) * cached_rate

    # Reasoning tokens (at reasoning rate if configured, else standard output)
    net_completion = max(0, completion_tokens - reasoning_tokens)
    output_cost = (net_completion / 1_000_000.0) * entry.output_per_1m

    reasoning_rate = entry.reasoning_per_1m if entry.reasoning_per_1m > 0 else entry.output_per_1m
    reasoning_cost = (reasoning_tokens / 1_000_000.0) * reasoning_rate

    total_est = input_cost + cached_input_cost + output_cost + reasoning_cost + speech_cost

    return CostBreakdown(
        estimated_cost_usd=round(total_est, 6),
        cost_type="estimated",
        input_cost=round(input_cost, 6),
        output_cost=round(output_cost, 6),
        cached_input_cost=round(cached_input_cost, 6),
        reasoning_cost=round(reasoning_cost, 6),
        speech_cost=round(speech_cost, 6),
        pricing_version=PRICING_REGISTRY_VERSION,
        is_local=False,
        rate_matched=True,
    )
