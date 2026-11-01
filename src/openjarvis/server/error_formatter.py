"""Intelligent error parser and formatter for OpenJarvis/Ultron.

Transforms raw provider errors, HTTP status codes, and Google RPC dumps
into structured, human-friendly alerts with actionable remediation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def parse_retry_delay(delay_str: str) -> str:
    """Convert seconds or raw delay strings into friendly duration (e.g. '7h 17m')."""
    if not delay_str:
        return ""
    # Check for formats like "26225s" or raw numbers
    sec_match = re.search(r"(\d+(?:\.\d+)?)s?", delay_str)
    if sec_match:
        try:
            total_seconds = float(sec_match.group(1))
            if total_seconds < 60:
                return f"{int(total_seconds)}s"
            minutes = int((total_seconds % 3600) // 60)
            hours = int(total_seconds // 3600)
            days = int(hours // 24)
            if days > 0:
                return f"{days}d {hours % 24}h {minutes}m"
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m {int(total_seconds % 60)}s"
        except Exception:
            pass
    # Check for strings like "7h17m5.8s"
    h_m_match = re.search(r"(\d+h\d+m|\d+m\d+s)", delay_str)
    if h_m_match:
        return h_m_match.group(1)
    return delay_str


def format_friendly_error(exc_or_text: Any, default_model: str = "") -> str:
    """Parse an exception or raw error string and return a polished error presentation."""
    raw_text = str(exc_or_text).strip()

    # Default fallback data
    err_type = "unknown_error"
    status_code = 500
    title = "Generation Error"
    model = default_model
    message = "An unexpected error occurred during generation."
    retry_delay = ""
    help_url = ""
    suggestion = "Please check your network connection or try switching to another model."

    # 1. Check for Gemini / Google RPC 429 Quota Exhaustion
    if "429" in raw_text or "RESOURCE_EXHAUSTED" in raw_text or "Quota exceeded" in raw_text:
        err_type = "quota_exceeded"
        status_code = 429
        title = "API Rate Limit & Quota Reached"
        suggestion = "Switch to an alternative model in the top-left dropdown (such as OpenRouter free models or local Ollama), or provide a custom API key in Settings."

        # Extract model
        model_match = re.search(r"model:\s*([\w\.\-]+)", raw_text, re.IGNORECASE)
        if model_match:
            model = model_match.group(1)

        # Extract limit
        limit_match = re.search(r"limit:\s*(\d+)", raw_text, re.IGNORECASE)
        limit_val = limit_match.group(1) if limit_match else ""

        # Extract retry delay
        retry_match = re.search(r"retryDelay[\"']?:\s*[\"']?([^\"'\}\]]+)[\"']?", raw_text)
        if retry_match:
            retry_delay = parse_retry_delay(retry_match.group(1))
        else:
            retry_text_match = re.search(r"retry in\s+([0-9a-zA-Z\.\-]+)", raw_text, re.IGNORECASE)
            if retry_text_match:
                retry_delay = parse_retry_delay(retry_text_match.group(1))

        if limit_val:
            message = f"You have reached the free tier quota limit of {limit_val} requests/day for this model."
        else:
            message = "You have exceeded your current request or token rate limit for this model."

        if "ai.google.dev" in raw_text:
            help_url = "https://ai.google.dev/gemini-api/docs/rate-limits"

    # 2. Check for 401 / 403 Authentication & Permission errors
    elif "401" in raw_text or "Unauthorized" in raw_text or "Invalid API Key" in raw_text or "API_KEY_INVALID" in raw_text:
        err_type = "auth_error"
        status_code = 401
        title = "Authentication Failed (Invalid API Key)"
        message = "The configured API key was rejected by the provider. It may be missing, expired, or invalid."
        suggestion = "Head to Settings to enter a valid API key or switch to local Ollama inference."

    elif "403" in raw_text or "Forbidden" in raw_text or "PERMISSION_DENIED" in raw_text:
        err_type = "permission_denied"
        status_code = 403
        title = "Access Restricted (HTTP 403)"
        message = "Your API key does not have permission to access this model or region."
        suggestion = "Verify your account permissions or select a model available in your region."

    # 3. Check for 503 / 504 / Overloaded server
    elif "503" in raw_text or "Overloaded" in raw_text or "Service Unavailable" in raw_text:
        err_type = "service_overloaded"
        status_code = 503
        title = "Model Service Overloaded (HTTP 503)"
        message = "The AI provider's servers are temporarily experiencing high traffic and cannot serve this request."
        retry_delay = "30s"
        suggestion = "Wait a few seconds and try again, or switch to an alternate provider."

    # 4. Check for Context Window Exceeded
    elif "context_length_exceeded" in raw_text or "maximum context length" in raw_text or "too many tokens" in raw_text:
        err_type = "context_limit"
        status_code = 400
        title = "Context Length Limit Exceeded"
        message = "The total conversation history exceeds the maximum context window of the selected model."
        suggestion = "Start a new chat using the '+' button in the sidebar or switch to a model with a larger context window."

    # 5. Check for NIM / no-model unreachable
    elif "NIM engine not reachable" in raw_text or ("not reachable" in raw_text and "engine" in raw_text.lower()):
        err_type = "no_model_configured"
        status_code = 503
        title = "No AI Model Available"
        message = "No local or cloud model is currently configured. The default engine could not be reached."
        suggestion = "Open the model picker (top-left) → 'Cloud Models' tab and add your Google, OpenAI, or Anthropic API key. Or install Ollama and pull a local model."

    # 6. Check for Connection / Timeout errors
    elif "ConnectError" in raw_text or "Timeout" in raw_text or "Connection refused" in raw_text:
        err_type = "connection_failed"
        status_code = 504
        title = "Connection Failed"
        message = "Could not connect to the inference server. It may be offline or unreachable."
        suggestion = "Verify that the backend or local Ollama engine is running. Alternatively, add a cloud API key in Settings → API Keys."

    else:
        # Fallback to sanitized message
        from openjarvis.security.credential_stripper import sanitize_error_message

        message = sanitize_error_message(raw_text[:200])

    card_data = {
        "type": err_type,
        "status_code": status_code,
        "title": title,
        "model": model or default_model,
        "message": message,
        "retry_delay": retry_delay,
        "help_url": help_url,
        "suggestion": suggestion,
    }

    # Format as structured card tag block with clean markdown alert
    card_json = json.dumps(card_data)
    model_str = f" `{model}`" if model else ""
    delay_str = f"\n> **Estimated Reset:** {retry_delay}" if retry_delay else ""

    formatted = (
        f":::ultron-error-card\n{card_json}\n:::\n\n"
        f"> [!WARNING]\n"
        f"> ### {title}\n"
        f"> **Model:**{model_str}\n"
        f"> **Details:** {message}{delay_str}\n"
        f"> \n"
        f"> 💡 **Recommended Action:** {suggestion}\n"
    )
    return formatted
