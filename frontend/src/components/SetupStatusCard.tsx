import { useState, type FormEvent } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  Cpu,
  Eye,
  EyeOff,
  Globe,
  Key,
  Loader2,
  RefreshCw,
  Server,
  Sparkles,
} from 'lucide-react';
import type { SetupStatus } from '../lib/api';
import { sanitizeDiagnosticText } from '../lib/sanitize';

export type SetupErrorCategory =
  | 'credential'
  | 'network'
  | 'rate_limit'
  | 'endpoint'
  | 'backend';

export interface ClassifiedSetupError {
  category: SetupErrorCategory;
  title: string;
  explanation: string;
  recommendation: string;
  canRetry: boolean;
  canUpdateKey: boolean;
  canChangeProvider: boolean;
}

export function classifySetupError(status: SetupStatus | null): ClassifiedSetupError {
  const err = (typeof status?.error === 'string' ? status.error : '').toLowerCase();
  const phase = status?.phase || '';

  if (
    status?.requires_credential ||
    phase === 'credential_required' ||
    phase === 'credential_invalid' ||
    err.includes('401') ||
    err.includes('rejected') ||
    err.includes('revoked') ||
    err.includes('api key') ||
    err.includes('unauthorized') ||
    err.includes('forbidden')
  ) {
    return {
      category: 'credential',
      title: 'API Key Rejected or Missing',
      explanation:
        'The configured API key was rejected or revoked by the provider, or authentication credentials are required.',
      recommendation:
        'Generate a valid API key from your provider console (e.g. Google AI Studio) and update it below.',
      canRetry: false,
      canUpdateKey: true,
      canChangeProvider: true,
    };
  }

  if (
    phase === 'network_error' ||
    err.includes('network') ||
    err.includes('timeout') ||
    err.includes('timed out') ||
    err.includes('connection refused') ||
    err.includes('econnrefused') ||
    err.includes('enotfound') ||
    err.includes('dns')
  ) {
    return {
      category: 'network',
      title: 'Connection Timed Out',
      explanation:
        'Could not reach the AI service provider endpoint. The network connection timed out or is unavailable.',
      recommendation:
        'Check your internet connection and proxy settings, then retry connecting.',
      canRetry: true,
      canUpdateKey: false,
      canChangeProvider: true,
    };
  }

  if (
    phase === 'provider_busy' ||
    err.includes('429') ||
    err.includes('rate limit') ||
    err.includes('quota') ||
    err.includes('busy') ||
    err.includes('overloaded') ||
    err.includes('temporarily unavailable')
  ) {
    return {
      category: 'rate_limit',
      title: 'Provider Temporarily Busy',
      explanation:
        'The AI service provider is currently experiencing high load or rate limits. Your saved configuration is preserved.',
      recommendation:
        'Wait a moment for provider capacity to recover, then retry connecting.',
      canRetry: true,
      canUpdateKey: false,
      canChangeProvider: true,
    };
  }

  if (
    err.includes('404') ||
    err.includes('not found') ||
    err.includes('unsupported model') ||
    err.includes('invalid endpoint') ||
    err.includes('model does not exist')
  ) {
    return {
      category: 'endpoint',
      title: 'Model or Endpoint Not Supported',
      explanation:
        'The configured model or API endpoint was not recognized by the provider.',
      recommendation:
        'Switch to a supported model or select a different inference provider.',
      canRetry: true,
      canUpdateKey: false,
      canChangeProvider: true,
    };
  }

  return {
    category: 'backend',
    title: 'Backend Service Startup Error',
    explanation:
      'The local Ultron background service encountered an unexpected error during initialization.',
    recommendation:
      'Retry starting the background service. If the problem continues, switch providers or check logs.',
    canRetry: true,
    canUpdateKey: false,
    canChangeProvider: true,
  };
}

export function SetupStatusCard({
  status,
  onRetry,
  onUpdateCredential,
  onChangeProvider,
  recovering = false,
}: {
  status: SetupStatus;
  onRetry?: () => Promise<void>;
  onUpdateCredential?: (keyName: string, keyValue: string) => Promise<void>;
  onChangeProvider: () => Promise<void> | void;
  recovering?: boolean;
}) {
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [showKeyPassword, setShowKeyPassword] = useState(false);
  const [submittingKey, setSubmittingKey] = useState(false);
  const [keyError, setKeyError] = useState('');
  const [retrying, setRetrying] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const classified = classifySetupError(status);
  const sanitizedDetails = sanitizeDiagnosticText(status.error);

  const provider = status.credential_provider;
  const displayProvider =
    provider === 'gemini'
      ? 'Google Gemini'
      : provider
        ? provider.charAt(0).toUpperCase() + provider.slice(1)
        : 'Inference Provider';

  const resolvedKeyName =
    status.credential_key_name ||
    (provider === 'gemini'
      ? 'GEMINI_API_KEY'
      : `${(provider || 'CUSTOM').toUpperCase()}_API_KEY`);

  const handleRetry = async () => {
    if (!onRetry) return;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  };

  const handleKeySubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim() || !onUpdateCredential) return;
    setSubmittingKey(true);
    setKeyError('');
    try {
      await onUpdateCredential(resolvedKeyName, apiKey.trim());
      setShowKeyForm(false);
      setApiKey('');
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmittingKey(false);
    }
  };

  const renderCategoryIcon = () => {
    switch (classified.category) {
      case 'credential':
        return <Key size={20} />;
      case 'network':
        return <Globe size={20} />;
      case 'rate_limit':
        return <AlertTriangle size={20} />;
      case 'endpoint':
        return <Server size={20} />;
      case 'backend':
      default:
        return <Cpu size={20} />;
    }
  };

  return (
    <div
      role="region"
      aria-label="Setup Status"
      className="p-5 rounded-2xl w-full text-left transition-all"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* Header */}
      <div className="flex items-start gap-3.5 mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 mt-0.5"
          style={{
            background:
              classified.category === 'credential'
                ? 'var(--color-accent-subtle)'
                : 'color-mix(in srgb, var(--color-warning, #f59e0b) 15%, transparent)',
            color:
              classified.category === 'credential'
                ? 'var(--color-accent)'
                : 'var(--color-warning, #f59e0b)',
          }}
        >
          {renderCategoryIcon()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2
              className="text-sm font-semibold truncate"
              style={{ color: 'var(--color-text)' }}
            >
              {classified.title}
            </h2>
            {provider && (
              <span
                className="text-[10px] font-medium px-2 py-0.5 rounded-full"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {displayProvider}
              </span>
            )}
          </div>
          <p
            className="text-xs mt-1 leading-relaxed"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {classified.explanation}
          </p>
        </div>
      </div>

      {/* Recommended Action */}
      <div
        className="px-3.5 py-2.5 rounded-xl text-xs mb-4 leading-relaxed"
        style={{
          background: 'var(--color-accent-subtle)',
          border: '1px solid color-mix(in srgb, var(--color-accent) 25%, transparent)',
          color: 'var(--color-text)',
        }}
      >
        <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
          Recommended action:{' '}
        </span>
        {classified.recommendation}
      </div>

      {/* Inline Credential Form if expanded */}
      {showKeyForm && (
        <form
          onSubmit={handleKeySubmit}
          className="p-3.5 rounded-xl mb-4 flex flex-col gap-3"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
        >
          <label className="text-xs font-medium" style={{ color: 'var(--color-text)' }}>
            Enter new {displayProvider} API key:
            <div className="relative mt-1.5">
              <input
                aria-label={`New ${displayProvider} API key`}
                type={showKeyPassword ? 'text' : 'password'}
                required
                autoComplete="off"
                placeholder={provider === 'gemini' ? 'AIzaSy...' : 'sk-...'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                disabled={submittingKey}
                className="block w-full px-3 py-2 pr-9 rounded-lg text-xs outline-none font-mono"
                style={{
                  background: 'var(--color-bg)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
              <button
                type="button"
                onClick={() => setShowKeyPassword(!showKeyPassword)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded hover:opacity-80"
                style={{ color: 'var(--color-text-tertiary)' }}
                aria-label={showKeyPassword ? 'Hide key' : 'Show key'}
              >
                {showKeyPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </label>

          {keyError && (
            <div
              role="alert"
              className="text-[11px] px-2.5 py-1.5 rounded-lg"
              style={{
                background: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
                color: 'var(--color-error)',
              }}
            >
              {keyError}
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={submittingKey || !apiKey.trim()}
              className="flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              {submittingKey ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Connecting...</span>
                </>
              ) : (
                <>
                  <Sparkles size={13} />
                  <span>Save & Reconnect</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowKeyForm(false);
                setApiKey('');
              }}
              disabled={submittingKey}
              className="py-2 px-3 rounded-lg text-xs font-medium cursor-pointer"
              style={{
                background: 'transparent',
                color: 'var(--color-text-secondary)',
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center gap-2 mb-3">
        {classified.canUpdateKey && !showKeyForm && (
          <button
            type="button"
            onClick={() => setShowKeyForm(true)}
            disabled={recovering || retrying}
            className="w-full sm:flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 cursor-pointer transition-opacity disabled:opacity-50"
            style={{ background: 'var(--color-accent)', color: 'white' }}
          >
            <Key size={14} />
            <span>Update API Key</span>
          </button>
        )}

        {classified.canRetry && onRetry && (
          <button
            type="button"
            onClick={handleRetry}
            disabled={retrying || recovering}
            className="w-full sm:flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 cursor-pointer transition-opacity disabled:opacity-50"
            style={{ background: 'var(--color-accent)', color: 'white' }}
          >
            {retrying ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            <span>{retrying ? 'Retrying...' : 'Retry Connection'}</span>
          </button>
        )}

        {classified.canChangeProvider && (
          <button
            type="button"
            onClick={onChangeProvider}
            disabled={recovering || retrying || submittingKey}
            className="w-full sm:w-auto py-2.5 px-4 rounded-xl text-xs font-medium cursor-pointer transition-opacity disabled:opacity-50 hover:bg-(--color-surface)"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
            }}
          >
            {recovering ? 'Switching...' : 'Change Provider'}
          </button>
        )}
      </div>

      {/* Sanitized Diagnostics Accordion */}
      {sanitizedDetails && (
        <div className="pt-2 border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <button
            type="button"
            onClick={() => setShowDiagnostics(!showDiagnostics)}
            className="text-[11px] flex items-center gap-1 cursor-pointer font-medium hover:underline select-none"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            <span>{showDiagnostics ? 'Hide diagnostic details' : 'Show diagnostic details'}</span>
            <ChevronDown
              size={12}
              className={`transition-transform duration-200 ${showDiagnostics ? 'rotate-180' : ''}`}
            />
          </button>
          {showDiagnostics && (
            <pre
              className="mt-2 p-2.5 rounded-lg font-mono text-[10px] leading-relaxed overflow-x-auto whitespace-pre-wrap select-all max-h-36"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {sanitizedDetails}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
