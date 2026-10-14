/**
 * Client-side secret sanitization and log redaction.
 *
 * Ensures API keys, authorization bearer tokens, and sensitive query
 * parameters are never exposed in UI status messages, error logs, or diagnostics.
 */

export function sanitizeDiagnosticText(text: string | null | undefined): string {
  if (!text) return '';
  return text
    // Google Gemini API keys (AIza... or AQ...)
    .replace(/(?:AIza[0-9A-Za-z\-_]{35}|AQ\.[0-9A-Za-z\-_]{25,})/g, '[REDACTED]')
    // Standard OpenAI/Anthropic/Groq/etc keys (sk-...)
    .replace(/sk-[a-zA-Z0-9_\-]{20,}/g, '[REDACTED]')
    // AWS keys
    .replace(/AKIA[0-9A-Z]{16}/g, '[REDACTED]')
    // GitHub tokens
    .replace(/(?:ghp|gho|ghs|ghr|github_pat)_[a-zA-Z0-9_]{36,}/g, '[REDACTED]')
    // Slack tokens
    .replace(/xox[bpors]-[0-9A-Za-z\-]+/g, '[REDACTED]')
    // Bearer tokens in headers or logs
    .replace(/Bearer\s+[a-zA-Z0-9_\-.~+/=]{15,}/gi, 'Bearer [REDACTED]')
    // Authorization headers in strings
    .replace(/(Authorization:\s*)[^\r\n]+/gi, '$1Bearer [REDACTED]')
    // URL query parameter keys (e.g. ?key=... or &api_key=...)
    .replace(/([?&](?:key|api[_-]?key|token|access_token|secret)=)[^& \r\n]+/gi, '$1[REDACTED]');
}
