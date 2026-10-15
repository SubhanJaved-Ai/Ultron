"""Unit tests for error_formatter."""

from openjarvis.server.error_formatter import format_friendly_error, parse_retry_delay


def test_parse_retry_delay():
    assert parse_retry_delay("26225s") == "7h 17m"
    assert parse_retry_delay("45s") == "45s"
    assert parse_retry_delay("120s") == "2m 0s"


def test_format_gemini_429_quota():
    raw_error = (
        'Error during generation: gemini engine at https://generativelanguage.googleapis.com/v1beta/openai '
        'returned HTTP 429: [{ "error": { "code": 429, "message": "You exceeded your current quota, '
        'please check your plan and billing details.\\n* Quota exceeded for metric: '
        'generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash\\n'
        'Please retry in 7h17m5.824868652s.", "status": "RESOURCE_EXHAUSTED", "details": '
        '[ { "@type": "type.googleapis.com/google.rpc.QuotaFailure" }, '
        '{ "@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "26225s" } ] } } ]'
    )
    res = format_friendly_error(raw_error, default_model="gemini-3.6-flash")
    assert ":::ultron-error-card" in res
    assert "quota_exceeded" in res
    assert "gemini-3.6-flash" in res
    assert "7h 17m" in res
    assert "API Rate Limit & Quota Reached" in res
    assert "20 requests/day" in res


def test_format_auth_error():
    raw_error = "Authentication error: 401 Unauthorized - Invalid API Key provided"
    res = format_friendly_error(raw_error)
    assert "auth_error" in res
    assert "Authentication Failed (Invalid API Key)" in res


def test_format_service_overloaded():
    raw_error = "503 Service Unavailable: The model is currently overloaded. Please try again later."
    res = format_friendly_error(raw_error)
    assert "service_overloaded" in res
    assert "Model Service Overloaded" in res
