from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SENSITIVE_PARAM_NAMES = {
    "key",
    "api_key",
    "apikey",
    "api-key",
    "token",
    "access_token",
    "secret",
    "secret_key",
    "auth",
    "password",
    "pwd",
}

_CREDENTIAL_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("google_gemini_key", re.compile(r"(?:AIza[0-9A-Za-z\-_]{35}|AQ\.[0-9A-Za-z\-_]{30,})")),
    ("api_key", re.compile(r"sk-[a-zA-Z0-9_\-]{20,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"(?:ghp|gho|ghs|ghr|github_pat)_[a-zA-Z0-9_]{36,}")),
    ("slack_token", re.compile(r"xox[bpors]-[0-9A-Za-z\-]+")),
    ("bearer_token", re.compile(r"Bearer\s+[a-zA-Z0-9_\-.~+/=]{20,}")),
]


class CredentialStripper:
    """Redacts credentials from text using compiled regex patterns."""

    def __init__(self) -> None:
        self._patterns = _CREDENTIAL_PATTERNS

    def strip(self, text: str) -> str:
        return sanitize_error_message(text)


def sanitize_url(url: str) -> str:
    """Strip or redact sensitive query parameters from a URL."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if not parts.query:
            return url
        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        cleaned_pairs = []
        for k, v in query_pairs:
            if k.lower() in _SENSITIVE_PARAM_NAMES or any(
                pat[1].search(v) for pat in _CREDENTIAL_PATTERNS[:4]
            ):
                cleaned_pairs.append((k, "[REDACTED]"))
            else:
                cleaned_pairs.append((k, v))
        cleaned_query = urlencode(cleaned_pairs)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, cleaned_query, parts.fragment)
        )
    except Exception:
        return re.sub(
            r"(?i)([?&](?:key|api_key|token|auth)=)[^&\s'\"]+",
            r"\1[REDACTED]",
            url,
        )


def sanitize_error_message(text: str) -> str:
    """Scrub sensitive keys, query strings, and tokens from error messages."""
    if not text:
        return ""
    # Redact URL parameters
    result = re.sub(
        r"(?i)([?&](?:key|api_key|apikey|token|access_token|auth)=)[^&\s'\"\)]+",
        r"\1[REDACTED]",
        text,
    )
    # Redact Authorization header values
    result = re.sub(
        r"(?i)(Bearer\s+)[a-zA-Z0-9_\-.~+/=]{10,}",
        r"\1[REDACTED]",
        result,
    )
    # Redact known API key patterns
    for label, pattern in _CREDENTIAL_PATTERNS:
        result = pattern.sub(f"[REDACTED:{label}]", result)
    return result


def wrap_tool_output(tool_name: str, content: str, success: bool = True) -> str:
    status = "success" if success else "error"
    header = f'<tool_result name="{tool_name}" status="{status}">'
    return f"{header}\n{content}\n</tool_result>"
