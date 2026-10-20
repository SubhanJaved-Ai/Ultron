import React from 'react';
import {
  AlertTriangle,
  Clock,
  Key,
  RefreshCw,
  ExternalLink,
  Cpu,
  Settings,
  ArrowRight,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { useNavigate } from 'react-router';

export interface UltronErrorInfo {
  type: string;
  status_code?: number;
  title: string;
  model?: string;
  message: string;
  retry_delay?: string;
  help_url?: string;
  suggestion?: string;
}

interface Props {
  error: UltronErrorInfo;
}

export function ErrorAlertCard({ error }: Props) {
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const navigate = useNavigate();

  const isQuota = error.type === 'quota_exceeded' || error.status_code === 429;
  const isAuth = error.type === 'auth_error' || error.status_code === 401;

  const badgeColor = isQuota ? '#f59e0b' : isAuth ? '#ef4444' : '#8b5cf6';
  const badgeBg = isQuota
    ? 'rgba(245, 158, 11, 0.12)'
    : isAuth
    ? 'rgba(239, 68, 68, 0.12)'
    : 'rgba(139, 92, 246, 0.12)';

  return (
    <div
      className="my-3 rounded-xl border p-4 shadow-sm transition-all"
      style={{
        background: 'var(--color-bg-secondary)',
        borderColor: isQuota
          ? 'rgba(245, 158, 11, 0.35)'
          : isAuth
          ? 'rgba(239, 68, 68, 0.35)'
          : 'var(--color-border)',
      }}
    >
      {/* Top Header Badge */}
      <div className="flex items-center justify-between gap-2 mb-2.5">
        <div className="flex items-center gap-2">
          <span
            className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold tracking-wide uppercase"
            style={{ background: badgeBg, color: badgeColor }}
          >
            {isQuota ? (
              <Clock size={12} />
            ) : isAuth ? (
              <Key size={12} />
            ) : (
              <AlertTriangle size={12} />
            )}
            {error.title || 'Inference Notice'}
          </span>
          {error.status_code && (
            <span
              className="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded"
              style={{
                background: 'var(--color-bg-tertiary)',
                color: 'var(--color-text-tertiary)',
              }}
            >
              HTTP {error.status_code}
            </span>
          )}
        </div>

        {error.model && (
          <span
            className="flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md"
            style={{
              background: 'var(--color-bg-tertiary)',
              color: 'var(--color-text-secondary)',
            }}
          >
            <Cpu size={11} />
            {error.model}
          </span>
        )}
      </div>

      {/* Main Friendly Message */}
      <p
        className="text-sm font-medium mb-1.5 leading-snug"
        style={{ color: 'var(--color-text)' }}
      >
        {error.message}
      </p>

      {/* Retry window if available */}
      {error.retry_delay && (
        <div
          className="flex items-center gap-1.5 text-xs font-mono my-2 px-2.5 py-1.5 rounded-lg"
          style={{
            background: 'var(--color-bg-tertiary)',
            color: 'var(--color-warning)',
          }}
        >
          <Clock size={13} />
          <span>
            Quota recovery delay: <strong>{error.retry_delay}</strong>
          </span>
        </div>
      )}

      {/* Suggestion / Tip */}
      {error.suggestion && (
        <p
          className="text-xs mb-3.5 leading-relaxed"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          💡 {error.suggestion}
        </p>
      )}

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-2 border-t" style={{ borderColor: 'var(--color-border)' }}>
        <button
          onClick={() => setCommandPaletteOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
          style={{
            background: 'var(--color-accent)',
            color: 'var(--color-on-accent)',
          }}
        >
          <RefreshCw size={12} />
          Switch Model (⌘K)
        </button>

        <button
          onClick={() => navigate('/settings')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
          style={{
            background: 'var(--color-bg-tertiary)',
            color: 'var(--color-text)',
            border: '1px solid var(--color-border)',
          }}
        >
          <Settings size={12} />
          Configure Keys in Settings
        </button>

        {error.help_url && (
          <a
            href={error.help_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors ml-auto"
            style={{ color: 'var(--color-text-tertiary)' }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-text-secondary)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--color-text-tertiary)')}
          >
            Quota Docs
            <ExternalLink size={11} />
          </a>
        )}
      </div>
    </div>
  );
}

/**
 * Extracts UltronErrorInfo from message text if present.
 */
export function extractUltronError(content: string): UltronErrorInfo | null {
  if (!content) return null;
  // Check for :::ultron-error-card ... :::
  const match = /:::ultron-error-card\s*([\s\S]*?)\s*:::/i.exec(content);
  if (match) {
    try {
      return JSON.parse(match[1]);
    } catch {}
  }

  // Fallback pattern detection for raw 429/401 messages that slipped through
  if (content.includes('429') && (content.includes('quota') || content.includes('RESOURCE_EXHAUSTED') || content.includes('rate_limits'))) {
    return {
      type: 'quota_exceeded',
      status_code: 429,
      title: 'API Rate Limit & Quota Reached',
      message: 'You have reached the request limit for this model on your current plan.',
      suggestion: 'Switch to an alternative free model via ⌘K or configure your own key in Settings.',
      retry_delay: content.match(/retry in\s+([^\.]+)/i)?.[1],
      help_url: 'https://ai.google.dev/gemini-api/docs/rate-limits',
    };
  }

  if (content.includes('401') && (content.includes('Unauthorized') || content.includes('Invalid API Key'))) {
    return {
      type: 'auth_error',
      status_code: 401,
      title: 'Authentication Failed',
      message: 'The model API key was rejected by the provider.',
      suggestion: 'Please verify your API key in the Settings page.',
    };
  }

  return null;
}
